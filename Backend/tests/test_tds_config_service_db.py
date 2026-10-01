# Backend/tests/test_tds_config_service_db.py
"""TDS Configuration service + import against the REAL configured database
(same precedent as test_tds_determination_integration.py), but fully
isolated: every test runs inside an outer transaction that is rolled back at
the end, with the Session in join_transaction_mode="create_savepoint" - the
services' own commit()/rollback() only release/roll back SAVEPOINTs, so
nothing a test does is ever persisted, even on failure.

Requires migration_tds_configuration.sql to have been applied.
"""
from __future__ import annotations

import datetime
import io
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from Backend.Business_Layer.services import tds_determination_service
from Backend.Business_Layer.services.tds_config_import_service import (
    IMPORT_COLUMNS,
    TdsConfigImportService,
    TdsImportFileError,
)
from Backend.Business_Layer.services.tds_config_service import (
    TdsConfigConflictError,
    TdsConfigNotFoundError,
    TdsConfigService,
)
from Backend.Business_Layer.services.tds_determination_service import TDSDeterminationService
from Backend.Business_Layer.utils.vendor_auto_onboarding import GSTVerificationResult
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import TaxRateRule
from Backend.Data_Access_Layer.models.tds import InvoiceTds
from Backend.Data_Access_Layer.utils.database import engine

USER = "test-suite"
AWS_VENDOR_ID = 15  # existing vendor, COMPANY PAN, profile on file
# Test rules use a section no live rule has, so the variant-conflict check
# never trips over real configuration unless a test targets it on purpose.
TEST_SECTION = "999ZZ"


@pytest.fixture
def db():
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def tag():
    return "ZZT" + uuid.uuid4().hex[:8].upper()


def _master(code, name=None, description=None, is_active=None):
    return SimpleNamespace(code=code, name=name or code.title(), description=description, is_active=is_active)


def _rule_raw(code, nature, **overrides):
    raw = {
        "code": code, "old_section": TEST_SECTION, "new_section": None, "payment_nature": nature, "deductor": None,
        "rate": "1", "threshold_amount": "100000", "threshold_period": "Financial Year (Aggregate)",
        "rate_condition": None, "effective_from": "2026-04-01", "effective_to": None,
    }
    raw.update(overrides)
    return raw


def _audits(db, table_name, record_id):
    return db.query(AuditLog).filter(AuditLog.table_name == table_name, AuditLog.record_id == record_id).order_by(AuditLog.audit_log_id).all()


# =========================================================
# Payment nature
# =========================================================

def test_payment_nature_crud_and_audit(db, tag):
    svc = TdsConfigService(db)
    nature = svc.create_payment_nature(_master(f"{tag}_nat", "Test Nature"), USER)
    assert nature.code == f"{tag}_NAT" and nature.is_active is True

    assert svc.get_payment_nature(nature.id).name == "Test Nature"
    assert [n.id for n in svc.list_payment_natures(search=tag)] == [nature.id]

    updated = svc.update_payment_nature(nature.id, _master(None, "Renamed", "desc"), USER)
    assert updated.name == "Renamed" and updated.description == "desc"

    assert svc.set_payment_nature_status(nature.id, False, USER).is_active is False
    assert svc.set_payment_nature_status(nature.id, True, USER).is_active is True

    svc.delete_payment_nature(nature.id, USER)
    with pytest.raises(TdsConfigNotFoundError):
        svc.get_payment_nature(nature.id)

    actions = [a.action for a in _audits(db, "tds_payment_nature", nature.id)]
    assert actions == ["CREATE", "UPDATE", "DEACTIVATE", "ACTIVATE", "DELETE"]


def test_payment_nature_duplicate_code_conflicts(db):
    with pytest.raises(TdsConfigConflictError, match="already exists"):
        TdsConfigService(db).create_payment_nature(_master("contractor"), USER)


def test_payment_nature_invalid_code_rejected(db):
    with pytest.raises(ValueError, match="may contain only"):
        TdsConfigService(db).create_payment_nature(_master("bad code!"), USER)


def test_referenced_payment_nature_cannot_be_deleted_or_recoded(db):
    svc = TdsConfigService(db)
    professional = svc.dao.get_payment_nature_by_code("PROFESSIONAL_SERVICE")  # invoice_tds + rule + mapping refs
    with pytest.raises(TdsConfigConflictError, match="cannot be deleted.*deactivate"):
        svc.delete_payment_nature(professional.id, USER)
    with pytest.raises(TdsConfigConflictError, match="code cannot be changed"):
        svc.update_payment_nature(professional.id, _master("PROF_NEW"), USER)


# =========================================================
# Deductor
# =========================================================

def test_deductor_crud_duplicate_and_referenced_delete(db, tag):
    svc = TdsConfigService(db)
    deductor = svc.create_deductor(_master(f"{tag}_ANY", "Any Person"), USER)
    with pytest.raises(TdsConfigConflictError):
        svc.create_deductor(_master(f"{tag}_any"), USER)

    assert svc.update_deductor(deductor.id, _master(None, "Any person (updated)"), USER).name == "Any person (updated)"
    assert svc.set_deductor_status(deductor.id, False, USER).is_active is False
    svc.set_deductor_status(deductor.id, True, USER)

    svc.create_rule(_rule_raw(f"{tag}_R1", "CONTRACTOR", deductor=deductor.code, effective_from="2030-04-01"), USER)
    with pytest.raises(TdsConfigConflictError, match="in use"):
        svc.delete_deductor(deductor.id, USER)

    other = svc.create_deductor(_master(f"{tag}_GOV"), USER)
    svc.delete_deductor(other.id, USER)
    assert svc.dao.get_deductor(other.id) is None


# =========================================================
# Rules
# =========================================================

def test_rule_create_read_update_status_and_audit(db, tag):
    svc = TdsConfigService(db)
    deductor = svc.create_deductor(_master(f"{tag}_DED"), USER)
    created = svc.create_rule(_rule_raw(
        f"{tag}_194c_ind", "Contractor Payments", old_section="194C", deductor=deductor.id, new_section="393",
        rate_condition="ENTITY_TYPE IN individual,huf", effective_from="2030-04-01", effective_to="2031-03-31",
    ), USER)

    assert created["code"] == f"{tag}_194C_IND"
    assert created["payment_nature"]["code"] == "CONTRACTOR"
    assert created["deductor"]["id"] == deductor.id
    assert created["rate_percent"] == Decimal("1.0000")
    assert created["threshold_period"] == "AGGREGATE_PERIOD"
    assert created["threshold_period_label"] == "Financial Year (Aggregate)"
    assert created["rate_condition"] == "ENTITY_TYPE IN HUF,INDIVIDUAL"
    assert [c["condition_type"] for c in created["conditions"]] == ["PAYMENT_NATURE", "ENTITY_TYPE"]
    assert len(created["rates"]) == 1 and created["status"] == "ACTIVE"
    assert created["rule_name"].startswith("TDS 194C - Contractor Payments")

    assert svc.get_rule(created["id"])["new_section"] == "393"
    listed = svc.list_rules(search=tag, status="ACTIVE", payment_nature="CONTRACTOR", effective_date=datetime.date(2030, 6, 1))
    assert [r["id"] for r in listed] == [created["id"]]
    assert svc.list_rules(search=tag, effective_date=datetime.date(2029, 6, 1)) == []

    rate_row_id = created["current_rate_rule_id"]
    updated = svc.update_rule(created["id"], _rule_raw(
        f"{tag}_194C_IND", "CONTRACTOR", old_section="194C", rate="0.75", threshold_amount=None, threshold_period=None,
        rate_condition="ENTITY_TYPE EQUALS INDIVIDUAL", effective_from="2030-04-01",
    ), USER)
    assert updated["rate_percent"] == Decimal("0.7500")
    assert updated["current_rate_rule_id"] == rate_row_id  # unreferenced -> edited in place
    assert updated["threshold_amount"] is None and updated["threshold_period"] is None
    assert updated["rate_condition"] == "ENTITY_TYPE EQUALS INDIVIDUAL"
    assert updated["effective_to"] is None
    assert updated["rule_name"] == created["rule_name"]  # names are never auto-rewritten

    assert svc.set_rule_status(created["id"], False, USER)["status"] == "INACTIVE"
    assert svc.set_rule_status(created["id"], True, USER)["status"] == "ACTIVE"

    actions = [a.action for a in _audits(db, "tax_rule", created["id"])]
    assert actions == ["CREATE", "UPDATE", "DEACTIVATE", "ACTIVATE"]
    update_audit = _audits(db, "tax_rule", created["id"])[1]
    assert update_audit.old_values["rate_percent"] == "1.0000"
    assert update_audit.new_values["rate_percent"] == "0.7500"


def test_rule_duplicate_code_conflicts(db, tag):
    svc = TdsConfigService(db)
    svc.create_rule(_rule_raw(f"{tag}_DUP", "CONTRACTOR", effective_from="2030-04-01"), USER)
    with pytest.raises(TdsConfigConflictError, match="already exists"):
        svc.create_rule(_rule_raw(f"{tag.lower()}_dup", "CONTRACTOR", rate="2", effective_from="2031-04-01"), USER)


def test_rule_code_used_by_gst_rule_conflicts(db):
    with pytest.raises(TdsConfigConflictError, match="non-TDS"):
        TdsConfigService(db).create_rule(_rule_raw("GST_SAC_997331", "CONTRACTOR", effective_from="2030-04-01"), USER)


@pytest.mark.parametrize("overrides, message", [
    ({"effective_from": "2030-04-01", "effective_to": "2030-03-31"}, "Effective To must be on or after"),
    ({"rate": "abc"}, "Rate must be numeric"),
    ({"rate": "150"}, "between 0 and 100"),
    ({"rate": "-1"}, "between 0 and 100"),
    ({"threshold_amount": "-5"}, "cannot be negative"),
    ({"threshold_amount": "1000", "threshold_period": None}, "Threshold Period is required"),
    ({"threshold_period": "Monthly"}, "Threshold Period must be one of"),
    ({"payment_nature": "NOPE"}, "does not exist"),
    ({"deductor": "NOPE"}, "Deductor 'NOPE' does not exist"),
    ({"rate_condition": "ASSET EQUALS X"}, "not supported"),
    ({"effective_from": "31/31/2030"}, "not a valid date"),
    ({"old_section": None}, "Old Section is required"),
])
def test_rule_validation_errors(db, tag, overrides, message):
    with pytest.raises(ValueError, match=message):
        TdsConfigService(db).create_rule(_rule_raw(f"{tag}_V", "CONTRACTOR", **overrides), USER)


def test_conflicting_variant_rejected_but_distinct_variant_allowed(db, tag):
    svc = TdsConfigService(db)
    base = dict(rate_condition="ENTITY_TYPE IN INDIVIDUAL,HUF", effective_from="2030-04-01")
    svc.create_rule(_rule_raw(f"{tag}_A", "CONTRACTOR", **base), USER)

    with pytest.raises(TdsConfigConflictError, match="overlapping effective dates"):
        svc.create_rule(_rule_raw(f"{tag}_B", "CONTRACTOR", **base), USER)

    # different rate condition = a legitimate second variant of the same section
    svc.create_rule(_rule_raw(f"{tag}_C", "CONTRACTOR", rate="2", rate_condition="ENTITY_TYPE NOT_IN INDIVIDUAL,HUF",
                              effective_from="2030-04-01"), USER)
    # same signature, non-overlapping dates = fine
    svc.create_rule(_rule_raw(f"{tag}_D", "CONTRACTOR", rate_condition="ENTITY_TYPE IN INDIVIDUAL,HUF",
                              effective_from="2029-04-01", effective_to="2030-03-31"), USER)
    assert len(svc.list_rules(search=tag)) == 3


def test_reactivating_a_conflicting_variant_is_blocked(db, tag):
    svc = TdsConfigService(db)
    first = svc.create_rule(_rule_raw(f"{tag}_A", "CONTRACTOR", effective_from="2030-04-01"), USER)
    svc.set_rule_status(first["id"], False, USER)
    svc.create_rule(_rule_raw(f"{tag}_B", "CONTRACTOR", effective_from="2030-04-01"), USER)
    with pytest.raises(TdsConfigConflictError):
        svc.set_rule_status(first["id"], True, USER)


def test_unreferenced_rule_can_be_deleted_with_children(db, tag):
    svc = TdsConfigService(db)
    rule = svc.create_rule(_rule_raw(f"{tag}_DEL", "CONTRACTOR", effective_from="2030-04-01"), USER)
    svc.delete_rule(rule["id"], USER)
    with pytest.raises(TdsConfigNotFoundError):
        svc.get_rule(rule["id"])
    assert db.execute(text("SELECT count(*) FROM ap.tax_rate_rule WHERE tax_rule_id = :id"), {"id": rule["id"]}).scalar() == 0
    assert _audits(db, "tax_rule", rule["id"])[-1].action == "DELETE"


def test_referenced_rule_cannot_be_deleted_and_rate_change_is_versioned(db, tag):
    """A rule an invoice_tds snapshot references: delete refused, rate edit versioned."""
    svc = TdsConfigService(db)
    created = svc.create_rule(_rule_raw(f"{tag}_REF", "PROFESSIONAL_SERVICE", rate="10", effective_from="2026-04-01"), USER)
    old_rate_id = created["current_rate_rule_id"]

    invoice = Invoice(
        invoice_number=f"TDS-REF-{tag}", vendor_id=AWS_VENDOR_ID, invoice_type="NON_PO",
        invoice_date=datetime.date(2026, 6, 15), due_date=datetime.date(2026, 7, 15), currency_id=1,
        gross_amount=Decimal("100000.00"), discount_amount=Decimal("0"), tax_amount=Decimal("0"),
        net_amount=Decimal("100000.00"), created_by=USER,
    )
    db.add(invoice)
    db.flush()
    db.add(InvoiceTds(
        invoice_id=invoice.invoice_id, tds_applicable=True, tds_rule_id=created["id"], tds_rate_rule_id=old_rate_id,
        tds_rate=Decimal("10.0000"), tds_amount=Decimal("10000.00"), determination_status="VERIFIED",
    ))
    db.commit()  # releases a SAVEPOINT only - so the refused delete's rollback below can't undo the fixture

    with pytest.raises(TdsConfigConflictError, match="deactivate it instead"):
        svc.delete_rule(created["id"], USER)

    updated = svc.update_rule(created["id"], _rule_raw(f"{tag}_REF", "PROFESSIONAL_SERVICE", rate="12", effective_from="2026-04-01"), USER)

    assert updated["current_rate_rule_id"] != old_rate_id
    assert updated["rate_percent"] == Decimal("12.0000")
    old_row = db.get(TaxRateRule, old_rate_id)
    assert old_row.is_active is False and old_row.rate_percent == Decimal("10.0000")  # history untouched
    snapshot = db.query(InvoiceTds).filter(InvoiceTds.invoice_id == invoice.invoice_id).one()
    assert snapshot.tds_rate_rule_id == old_rate_id and snapshot.tds_rate == Decimal("10.0000")


# =========================================================
# Excel / CSV import
# =========================================================

def _xlsx(rows, headers=IMPORT_COLUMNS):
    import openpyxl
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _row(code, nature="CONTRACTOR", rate=1, threshold=100000, period="Financial Year (Aggregate)",
         condition=None, effective_from=datetime.date(2030, 4, 1), effective_to=None, section=TEST_SECTION, deductor=None):
    return [code, section, None, nature, deductor, rate, threshold, period, condition, effective_from, effective_to]


def test_import_valid_file_then_reupload_is_unchanged_then_update(db, tag):
    importer = TdsConfigImportService(db)
    content = _xlsx([
        _row(f"{tag}_IND", condition="ENTITY_TYPE IN INDIVIDUAL,HUF"),
        _row(f"{tag}_OTH", rate=2, condition="ENTITY_TYPE NOT_IN INDIVIDUAL,HUF"),
    ])

    preview = importer.validate("rules.xlsx", content)
    assert preview["valid"] and preview["new_rows"] == 2 and preview["imported"] is False
    assert TdsConfigService(db).list_rules(search=tag) == []  # validate never writes

    result = importer.import_rules("rules.xlsx", content, USER)
    assert result["valid"] and result["imported"] and result["new_rows"] == 2
    rules = {r["code"]: r for r in TdsConfigService(db).list_rules(search=tag)}
    assert rules[f"{tag}_OTH"]["rate_percent"] == Decimal("2.0000")
    audit = _audits(db, "tax_rule", rules[f"{tag}_IND"]["id"])[-1]
    assert audit.action == "IMPORT" and audit.new_values["import_batch_id"] == result["import_batch_id"]

    again = importer.import_rules("rules.xlsx", content, USER)
    assert again["unchanged_rows"] == 2 and again["new_rows"] == 0 and again["updated_rows"] == 0
    assert len(TdsConfigService(db).list_rules(search=tag)) == 2  # no duplicates

    changed = _xlsx([
        _row(f"{tag}_IND", rate="0.5", condition="ENTITY_TYPE IN INDIVIDUAL,HUF"),
        _row(f"{tag}_OTH", rate=2, condition="ENTITY_TYPE NOT_IN INDIVIDUAL,HUF"),
    ])
    report = importer.import_rules("rules.xlsx", changed, USER)
    statuses = {r["code"]: (r["status"], r["changed_fields"]) for r in report["rows"]}
    assert statuses[f"{tag}_IND"] == ("UPDATED", ["Rate"])
    assert statuses[f"{tag}_OTH"][0] == "UNCHANGED"


def test_import_csv_supported(db, tag):
    csv_text = ",".join(IMPORT_COLUMNS) + "\n" + f"{tag}_CSV,{TEST_SECTION},,COMMISSION,,2%,\"15,000\",Single Transaction,,01-04-2030,\n"
    report = TdsConfigImportService(db).validate("rules.csv", csv_text.encode())
    assert report["valid"], report["errors"]
    assert report["rows"][0]["status"] == "NEW"


def test_import_invalid_header_rejected(db):
    headers = list(IMPORT_COLUMNS)
    headers[5] = "Rate %"
    with pytest.raises(TdsImportFileError, match=r"missing column\(s\): Rate.*unexpected column\(s\): Rate %"):
        TdsConfigImportService(db).validate("rules.xlsx", _xlsx([], headers=headers))


def test_import_unsupported_file_type_rejected(db):
    with pytest.raises(TdsImportFileError, match="Unsupported file type"):
        TdsConfigImportService(db).validate("rules.xls", b"whatever")


def test_import_row_level_errors(db, tag):
    content = _xlsx([
        _row(f"{tag}_OK"),                                            # row 2
        _row(f"{tag}_RATE", rate="abc"),                              # row 3
        _row(f"{tag}_THR", threshold=-1),                             # row 4
        _row(f"{tag}_PER", period="Weekly"),                          # row 5
        _row(f"{tag}_DATE", effective_from="2030-13-45"),             # row 6
        _row(f"{tag}_RANGE", effective_to=datetime.date(2030, 1, 1)), # row 7
        _row(f"{tag}_NAT", nature=None),                              # row 8 (unknown values are now planned, blank is not)
        _row(f"{tag}_DED", deductor="***"),                           # row 9 (no letters/digits -> no code)
        _row(f"{tag}_CON", condition="COLOUR EQUALS RED"),            # row 10
        _row(None),                                                   # row 11
        _row(f"{tag}_DUP", section="194H", nature="COMMISSION"),      # row 12
        _row(f"{tag}_DUP", section="194H", nature="COMMISSION"),      # row 13
    ])
    report = TdsConfigImportService(db).validate("rules.xlsx", content)

    assert report["valid"] is False
    assert report["total_rows"] == 12 and report["error_rows"] == 11 and report["valid_rows"] == 1
    by_row = {}
    for e in report["errors"]:
        by_row.setdefault(e["row"], []).append((e["field"], e["message"]))
    assert ("Rate", "Rate must be numeric") in by_row[3]
    assert by_row[4][0][0] == "Threshold Amount"
    assert by_row[5][0][0] == "Threshold Period"
    assert by_row[6][0][0] == "Effective From"
    assert by_row[7][0] == ("Effective To", "Effective To must be on or after Effective From")
    assert by_row[8][0] == ("Nature of Payment", "Nature of Payment is required")
    assert by_row[9][0] == ("Deductor", "Deductor '***' must contain letters or digits")
    assert by_row[10][0][0] == "Rate Condition"
    assert by_row[11][0] == ("Code", "Code is required")
    assert any("Duplicate Code" in m for _, m in by_row[12]) and any("Duplicate Code" in m for _, m in by_row[13])


def test_import_conflicting_variants_within_file_and_against_existing(db, tag):
    TdsConfigService(db).create_rule(_rule_raw(f"{tag}_EXISTING", "CONTRACTOR", effective_from="2026-04-01"), USER)
    content = _xlsx([
        _row(f"{tag}_A", condition="ENTITY_TYPE IN HUF"),
        _row(f"{tag}_B", condition="ENTITY_TYPE IN HUF"),
        # identical signature to the existing rule (no condition, CONTRACTOR, overlapping open-ended dates)
        _row(f"{tag}_C", effective_from=datetime.date(2027, 4, 1)),
    ])
    report = TdsConfigImportService(db).validate("rules.xlsx", content)
    messages = {e["row"]: e["message"] for e in report["errors"]}
    assert "Conflicts with row 3" in messages[2] and "Conflicts with row 2" in messages[3]
    assert f"existing active TDS rule '{tag}_EXISTING'" in messages[4]


def test_import_keeps_new_section_casing_and_long_references(db, tag):
    row = _row(f"{tag}_NS")
    row[2] = "393(1) Table 6(iii).D(a)"  # New Section: 24 chars, mixed case
    content = _xlsx([row])
    TdsConfigImportService(db).import_rules("rules.xlsx", content, USER)
    rule = TdsConfigService(db).list_rules(search=tag)[0]
    assert rule["new_section"] == "393(1) Table 6(iii).D(a)"


def test_import_is_all_or_nothing(db, tag):
    content = _xlsx([_row(f"{tag}_GOOD"), _row(f"{tag}_BAD", rate=500)])
    report = TdsConfigImportService(db).import_rules("rules.xlsx", content, USER)
    assert report["valid"] is False and report["imported"] is False
    assert TdsConfigService(db).list_rules(search=tag) == []


def test_import_failure_mid_write_rolls_everything_back(db, tag, monkeypatch):
    importer = TdsConfigImportService(db)
    original = importer.config_service._create_rule_row
    calls = {"n": 0}

    def _flaky(rule_input, user_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated DB failure")
        return original(rule_input, user_id)

    monkeypatch.setattr(importer.config_service, "_create_rule_row", _flaky)
    content = _xlsx([_row(f"{tag}_ONE", nature="COMMISSION"), _row(f"{tag}_TWO")])
    with pytest.raises(RuntimeError):
        importer.import_rules("rules.xlsx", content, USER)
    assert TdsConfigService(db).list_rules(search=tag) == []


# =========================================================
# Determination end-to-end on real data (variant chosen by entity type)
# =========================================================

def test_determination_picks_variant_for_real_company_vendor(db, tag, monkeypatch):
    monkeypatch.setattr(tds_determination_service, "call_gst_search", lambda gstin: GSTVerificationResult(
        verified=True, data={"code": 200, "data": {"status_cd": "1", "data": {"gstin": gstin, "sts": "Active"}}},
    ))
    svc = TdsConfigService(db)
    nature = svc.create_payment_nature(_master(f"{tag}_WORKS"), USER)
    svc.create_rule(_rule_raw(f"{tag}_IND", nature.code, rate="1", threshold_amount="1000",
                              rate_condition="ENTITY_TYPE IN INDIVIDUAL,HUF", effective_from="2026-04-01"), USER)
    svc.create_rule(_rule_raw(f"{tag}_OTH", nature.code, rate="2", threshold_amount="1000",
                              rate_condition="ENTITY_TYPE NOT_IN INDIVIDUAL,HUF", effective_from="2026-04-01"), USER)

    invoice = Invoice(
        invoice_number=f"TDS-CFG-{tag}", vendor_id=AWS_VENDOR_ID, invoice_type="NON_PO",
        invoice_date=datetime.date(2026, 6, 15), due_date=datetime.date(2026, 7, 15), currency_id=1,
        gross_amount=Decimal("50000.00"), discount_amount=Decimal("0"), tax_amount=Decimal("0"),
        net_amount=Decimal("50000.00"), created_by=USER,
    )
    db.add(invoice)
    db.flush()

    row = TDSDeterminationService(db).determine(invoice.invoice_id, USER, payment_nature_code=nature.code)
    assert row.entity_type == "COMPANY"
    assert row.rule_snapshot["rule_code"] == f"{tag}_OTH"
    assert row.tds_rate == Decimal("2.0000") and row.tds_amount == Decimal("1000.00")
    assert row.threshold_type == "AGGREGATE_PERIOD" and row.residency_type == "RESIDENT"
