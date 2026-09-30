# Backend/tests/test_tds_import_masters_db.py
"""Excel import creating missing Payment Natures / Deductors - against the REAL
configured database.

Three kinds of tests:
  * service tests on the savepoint-isolated `db` fixture from
    test_tds_config_service_db.py (outer transaction always rolled back);
  * route tests: the real tds_config_route + real services on that same
    isolated session, only auth faked - proves the server-side 403;
  * REAL-transaction rollback tests: a normal SessionLocal() that genuinely
    commits/rolls back, with the result checked through a SEPARATE
    connection, and a finally-block cleanup by tag as a safety net.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import tds_config_route
from Backend.Business_Layer.services.tds_config_import_service import (
    TdsConfigImportService,
    TdsImportPermissionError,
    generate_master_code,
)
from Backend.Business_Layer.services.tds_config_service import TdsConfigService
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.tds import TdsDeductor, TdsPaymentNature
from Backend.Data_Access_Layer.utils.database import SessionLocal, engine
from Backend.tests.test_tds_config_service_db import (  # noqa: F401 - fixtures
    TEST_SECTION,
    USER,
    _row,
    _xlsx,
    db,
    tag,
)

XLSX = "rules.xlsx"


def _nature_rows(db, code):
    return db.query(TdsPaymentNature).filter(TdsPaymentNature.code == code).all()


def _deductor_rows(db, code):
    return db.query(TdsDeductor).filter(TdsDeductor.code == code).all()


def _master(code, name):
    return SimpleNamespace(code=code, name=name, description=None, is_active=None)


# =========================================================
# Code generation
# =========================================================

@pytest.mark.parametrize("name, code", [
    ("Director Remuneration", "DIRECTOR_REMUNERATION"),
    ("Specified Person*", "SPECIFIED_PERSON"),
    ("  rent - plant & machinery ", "RENT_PLANT_MACHINERY"),
    ("Payment by firm to partners", "PAYMENT_BY_FIRM_TO_PARTNERS"),
    ("Ind/ HUF", "IND_HUF"),
])
def test_generated_code_is_deterministic_uppercase(name, code):
    assert generate_master_code(name) == code
    assert generate_master_code(name.upper()) == code  # same name, same code


# =========================================================
# Matching existing masters
# =========================================================

def test_existing_masters_matched_by_name_or_code_case_and_whitespace_insensitive(db, tag):
    svc = TdsConfigService(db)
    svc.create_deductor(_master(f"{tag}_ANY", f"{tag} Any Person"), USER)
    natures_before = len(svc.list_payment_natures())
    content = _xlsx([
        _row(f"{tag}_1", nature="  contractor   PAYMENTS ", deductor=f"  {tag.lower()}  any person"),  # names
        _row(f"{tag}_2", nature="contractor", deductor=f"{tag}_any", condition="ENTITY_TYPE IN HUF"),  # codes
    ])
    report = TdsConfigImportService(db).validate(XLSX, content)
    assert report["valid"], report["errors"]
    assert report["new_payment_natures"] == [] and report["new_deductors"] == []
    assert report["new_payment_nature_count"] == 0 and report["new_deductor_count"] == 0

    TdsConfigImportService(db).import_rules(XLSX, content, USER, can_create_masters=False)
    rules = svc.list_rules(search=tag)
    assert {r["payment_nature"]["code"] for r in rules} == {"CONTRACTOR"}
    assert {r["deductor"]["code"] for r in rules} == {f"{tag}_ANY"}
    assert len(svc.list_payment_natures()) == natures_before  # nothing duplicated


# =========================================================
# Planning / creating new masters
# =========================================================

def test_validate_reports_missing_masters_without_writing(db, tag):
    content = _xlsx([
        _row(f"{tag}_1", nature=f"{tag} Director Remuneration", deductor=f"{tag} Specified Person*"),
        _row(f"{tag}_2", nature=f"{tag}  director remuneration", deductor=f"{tag} Specified Person*",
             condition="ENTITY_TYPE IN HUF"),
        _row(f"{tag}_3", nature=f"{tag} Royalty"),
    ])
    report = TdsConfigImportService(db).validate(XLSX, content)

    assert report["valid"] and report["imported"] is False and report["new_rows"] == 3
    assert report["new_payment_natures"] == [
        {"name": f"{tag} Director Remuneration", "code": f"{tag}_DIRECTOR_REMUNERATION", "row_numbers": [2, 3]},
        {"name": f"{tag} Royalty", "code": f"{tag}_ROYALTY", "row_numbers": [4]},
    ]
    assert report["new_deductors"] == [
        {"name": f"{tag} Specified Person*", "code": f"{tag}_SPECIFIED_PERSON", "row_numbers": [2, 3]},
    ]
    assert report["new_payment_nature_count"] == 2 and report["new_deductor_count"] == 1
    # read-only
    assert _nature_rows(db, f"{tag}_DIRECTOR_REMUNERATION") == []
    assert _nature_rows(db, f"{tag}_ROYALTY") == []
    assert _deductor_rows(db, f"{tag}_SPECIFIED_PERSON") == []
    assert TdsConfigService(db).list_rules(search=tag) == []


def test_import_creates_masters_with_rules_and_reimport_does_not_duplicate(db, tag):
    content = _xlsx([
        _row(f"{tag}_1", nature=f"{tag} Director Remuneration", deductor=f"{tag} Company"),
        _row(f"{tag}_2", nature=f"{tag} Director Remuneration", deductor=f"{tag} Company", condition="ENTITY_TYPE IN HUF"),
    ])
    importer = TdsConfigImportService(db)
    report = importer.import_rules(XLSX, content, USER, can_create_masters=True)
    assert report["valid"] and report["imported"] and report["new_rows"] == 2
    assert report["new_payment_nature_count"] == 1 and report["new_deductor_count"] == 1

    [nature] = _nature_rows(db, f"{tag}_DIRECTOR_REMUNERATION")
    assert (nature.name, nature.description, nature.is_active) == (f"{tag} Director Remuneration", None, True)
    [deductor] = _deductor_rows(db, f"{tag}_COMPANY")
    assert (deductor.name, deductor.description, deductor.is_active) == (f"{tag} Company", None, True)

    rules = TdsConfigService(db).list_rules(search=tag)
    assert {r["payment_nature"]["code"] for r in rules} == {nature.code}
    assert {r["deductor"]["id"] for r in rules} == {deductor.id}

    audit = db.query(AuditLog).filter(AuditLog.table_name == "tds_payment_nature", AuditLog.record_id == nature.id).one()
    assert audit.action == "CREATE"
    assert audit.new_values["import_batch_id"] == report["import_batch_id"]
    assert audit.new_values["import_rows"] == [2, 3]

    again = importer.import_rules(XLSX, content, USER, can_create_masters=True)
    assert again["unchanged_rows"] == 2 and again["new_rows"] == 0
    assert again["new_payment_natures"] == [] and again["new_deductors"] == []
    assert len(_nature_rows(db, nature.code)) == 1 and len(_deductor_rows(db, deductor.code)) == 1


def test_inactive_master_is_rejected_and_not_reactivated(db, tag):
    svc = TdsConfigService(db)
    nature = svc.create_payment_nature(_master(f"{tag}_OLD", f"{tag} Old Nature"), USER)
    svc.set_payment_nature_status(nature.id, False, USER)
    content = _xlsx([_row(f"{tag}_1", nature=f"{tag} old nature")])

    report = TdsConfigImportService(db).validate(XLSX, content)
    assert report["valid"] is False
    assert report["errors"] == [{
        "row": 2, "field": "Nature of Payment",
        "message": f"Payment Nature '{tag} old nature' exists but is inactive. Activate it before importing.",
    }]
    assert report["new_payment_natures"] == []

    result = TdsConfigImportService(db).import_rules(XLSX, content, USER, can_create_masters=True)
    assert result["valid"] is False
    db.expire_all()
    assert svc.get_payment_nature(nature.id).is_active is False
    assert svc.list_rules(search=tag) == []


def test_ambiguous_near_duplicate_existing_masters_rejected(db, tag):
    svc = TdsConfigService(db)
    svc.create_payment_nature(_master(f"{tag}_A1", f"{tag} Prof Service"), USER)       # matches by name
    svc.create_payment_nature(_master(f"{tag}_PROF_SERVICE", f"{tag} Other"), USER)    # owns the generated code
    report = TdsConfigImportService(db).validate(XLSX, _xlsx([_row(f"{tag}_1", nature=f"{tag} Prof Service")]))
    assert report["valid"] is False
    assert "is ambiguous" in report["errors"][0]["message"]
    assert report["new_payment_natures"] == []


def test_generated_code_colliding_with_a_different_master_is_rejected(db, tag):
    svc = TdsConfigService(db)
    svc.create_deductor(_master(f"{tag}_ROYALTY", f"{tag} Royalty Payer"), USER)
    report = TdsConfigImportService(db).validate(XLSX, _xlsx([_row(f"{tag}_1", deductor=f"{tag} royalty")]))
    assert report["valid"] is False
    err = report["errors"][0]
    assert err["field"] == "Deductor"
    assert f"({tag}_ROYALTY) is already used by Deductor '{tag} Royalty Payer'" in err["message"]
    assert report["new_deductors"] == []


def test_two_spellings_generating_the_same_code_in_one_file_rejected(db, tag):
    content = _xlsx([
        _row(f"{tag}_1", nature=f"{tag} Rent-Plant"),
        _row(f"{tag}_2", nature=f"{tag} Rent Plant", condition="ENTITY_TYPE IN HUF"),
    ])
    report = TdsConfigImportService(db).validate(XLSX, content)
    assert report["valid"] is False
    assert [e["row"] for e in report["errors"]] == [3]
    assert "would both be created with code" in report["errors"][0]["message"]


# =========================================================
# Permissions - service level
# =========================================================

def test_service_refuses_to_create_masters_without_permission(db, tag):
    content = _xlsx([_row(f"{tag}_1", nature=f"{tag} Royalty")])
    with pytest.raises(TdsImportPermissionError, match="TDS_CONFIG_CREATE"):
        TdsConfigImportService(db).import_rules(XLSX, content, USER, can_create_masters=False)
    assert _nature_rows(db, f"{tag}_ROYALTY") == []
    assert TdsConfigService(db).list_rules(search=tag) == []


# =========================================================
# Permissions - real route (server-side enforcement)
# =========================================================

def _route_client(db, permissions):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": USER, "permissions": permissions}
            request.state.db = db
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(tds_config_route.router, prefix="/tds/config")
    return TestClient(app)


def _files(content):
    return {"file": (XLSX, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def test_route_import_only_permission_ok_when_no_new_masters(db, tag):
    client = _route_client(db, ["TDS_CONFIG_IMPORT"])
    response = client.post("/tds/config/import", files=_files(_xlsx([_row(f"{tag}_1", nature="CONTRACTOR")])))
    assert response.status_code == 200, response.text
    assert response.json()["imported"] is True and response.json()["new_payment_nature_count"] == 0


def test_route_import_only_permission_forbidden_when_file_creates_masters(db, tag):
    client = _route_client(db, ["TDS_CONFIG_IMPORT"])
    content = _xlsx([_row(f"{tag}_1", nature=f"{tag} Royalty", deductor=f"{tag} Firm")])

    preview = client.post("/tds/config/import/validate", files=_files(content))
    assert preview.status_code == 200
    assert preview.json()["new_payment_nature_count"] == 1 and preview.json()["new_deductor_count"] == 1

    response = client.post("/tds/config/import", files=_files(content))
    assert response.status_code == 403
    assert response.json() == {"detail": "This file would create 1 payment nature(s) and 1 deductor(s) - "
                                         "TDS_CONFIG_CREATE permission is required to import it"}
    assert _nature_rows(db, f"{tag}_ROYALTY") == [] and _deductor_rows(db, f"{tag}_FIRM") == []
    assert TdsConfigService(db).list_rules(search=tag) == []


def test_route_import_and_create_permissions_create_masters(db, tag):
    client = _route_client(db, ["TDS_CONFIG_IMPORT", "TDS_CONFIG_CREATE"])
    response = client.post("/tds/config/import", files=_files(_xlsx([_row(f"{tag}_1", nature=f"{tag} Royalty")])))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_payment_natures"] == [{"name": f"{tag} Royalty", "code": f"{tag}_ROYALTY", "row_numbers": [2]}]
    assert len(_nature_rows(db, f"{tag}_ROYALTY")) == 1


# =========================================================
# REAL transactions - nothing partial may survive
# =========================================================

def _real_counts(tag):
    """Read through a separate connection: sees only what was really committed."""
    with engine.connect() as conn:
        like = {"p": f"{tag}%"}
        return {
            "rules": conn.execute(text("SELECT count(*) FROM ap.tax_rule WHERE rule_code LIKE :p"), like).scalar(),
            "natures": conn.execute(text("SELECT count(*) FROM ap.tds_payment_nature WHERE code LIKE :p"), like).scalar(),
            "deductors": conn.execute(text("SELECT count(*) FROM ap.tds_deductor WHERE code LIKE :p"), like).scalar(),
        }


def _real_cleanup(tag):
    with engine.begin() as conn:
        like = {"p": f"{tag}%"}
        conn.execute(text("DELETE FROM ap.tax_rule WHERE rule_code LIKE :p"), like)  # cascades conditions/rates
        conn.execute(text("DELETE FROM ap.tds_payment_nature WHERE code LIKE :p"), like)
        conn.execute(text("DELETE FROM ap.tds_deductor WHERE code LIKE :p"), like)
        conn.execute(text("DELETE FROM ap.audit_log WHERE changed_by = :u"), {"u": f"real-{tag}"})


ZERO = {"rules": 0, "natures": 0, "deductors": 0}


def _multi_row_file(tag):
    return _xlsx([
        _row(f"{tag}_1", nature=f"{tag} Royalty", deductor=f"{tag} Buyer"),
        _row(f"{tag}_2", nature=f"{tag} Director Remuneration", deductor=f"{tag} Company"),
        _row(f"{tag}_3", nature=f"{tag} Royalty", deductor=f"{tag} Company", condition="ENTITY_TYPE IN HUF"),
    ])


def test_real_commit_control_successful_import_persists(tag):
    """Control for the rollback tests below: the same shape of file really
    commits, so a zero count there means a real rollback, not a no-op."""
    session = SessionLocal()
    try:
        report = TdsConfigImportService(session).import_rules(XLSX, _multi_row_file(tag), f"real-{tag}", can_create_masters=True)
        assert report["imported"]
        assert _real_counts(tag) == {"rules": 3, "natures": 2, "deductors": 2}
    finally:
        session.close()
        _real_cleanup(tag)
    assert _real_counts(tag) == ZERO


def test_real_failure_before_masters_row_error_writes_nothing(tag):
    content = _xlsx([
        _row(f"{tag}_1", nature=f"{tag} Royalty", deductor=f"{tag} Buyer"),
        _row(f"{tag}_2", nature=f"{tag} Director Remuneration", rate="abc"),
    ])
    session = SessionLocal()
    try:
        report = TdsConfigImportService(session).import_rules(XLSX, content, f"real-{tag}", can_create_masters=True)
        assert report["valid"] is False and report["imported"] is False
        assert report["new_payment_nature_count"] == 2  # planned, never created
        assert _real_counts(tag) == ZERO
    finally:
        session.close()
        _real_cleanup(tag)


def test_real_db_error_while_creating_masters_rolls_back_everything(tag, monkeypatch):
    session = SessionLocal()
    importer = TdsConfigImportService(session)
    original_add = importer.dao.add
    created = {"n": 0}

    def _add(obj):
        if isinstance(obj, (TdsPaymentNature, TdsDeductor)):
            created["n"] += 1
            if created["n"] == 3:  # 2 natures already INSERTed + flushed, fail on the first deductor
                session.execute(text("SELECT 1/0"))  # genuine DB error (division_by_zero)
        return original_add(obj)

    monkeypatch.setattr(importer.dao, "add", _add)
    try:
        with pytest.raises(Exception, match="division by zero"):
            importer.import_rules(XLSX, _multi_row_file(tag), f"real-{tag}", can_create_masters=True)
        assert created["n"] == 3
        assert _real_counts(tag) == ZERO
    finally:
        session.close()
        _real_cleanup(tag)


def test_real_db_error_after_masters_created_rolls_back_masters_and_rules(tag, monkeypatch):
    session = SessionLocal()
    importer = TdsConfigImportService(session)
    original_create = importer.config_service._create_rule_row
    calls = {"n": 0}

    def _create(rule_input, user_id):
        calls["n"] += 1
        if calls["n"] == 2:  # all 4 masters + rule 1 (with conditions/rate) already flushed
            session.execute(text("SELECT 1/0"))
        return original_create(rule_input, user_id)

    monkeypatch.setattr(importer.config_service, "_create_rule_row", _create)
    try:
        with pytest.raises(Exception, match="division by zero"):
            importer.import_rules(XLSX, _multi_row_file(tag), f"real-{tag}", can_create_masters=True)
        assert calls["n"] == 2
        assert _real_counts(tag) == ZERO
        with engine.connect() as conn:
            leftover_audit = conn.execute(
                text("SELECT count(*) FROM ap.audit_log WHERE changed_by = :u"), {"u": f"real-{tag}"}
            ).scalar()
        assert leftover_audit == 0
    finally:
        session.close()
        _real_cleanup(tag)
