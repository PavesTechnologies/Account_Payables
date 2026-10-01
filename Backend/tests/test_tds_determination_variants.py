# Backend/tests/test_tds_determination_variants.py
"""TDS determination across every configured section, rule VARIANTS (one
section, several rates chosen by rate condition), no-matching-rule natures,
effective dating, the payment-nature lock and verification rules.

Same fake-DAO style as test_tds_determination_service.py (whose helpers are
reused). Rates/thresholds mirror the live seed data after
migration_tds_configuration.sql; the 2% variants are illustrative test data.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from Backend.Business_Layer.services.tds_determination_service import (
    DETERMINATION_STATUS_VERIFIED,
    tds_determination_problem,
)
from Backend.Data_Access_Layer.models.master import StatusMaster, TaxRuleCondition
from Backend.Data_Access_Layer.models.tds import VendorTdsProfile
from Backend.tests.test_tds_determination_service import (
    _invoice,
    _make_service,
    _payment_nature,
    _rate_rule,
    _tax_rule,
    _vendor,
)

NATURES = {
    "CONTRACTOR": 1,
    "PROFESSIONAL_SERVICE": 2,
    "TECHNICAL_SERVICE": 3,
    "RENT": 4,
    "COMMISSION": 5,
    "PURCHASE_OF_GOODS": 6,
    "INTEREST": 7,
    "OTHER": 8,
}


def _variant(rule_id, code, nature, rate, threshold, section, rate_condition=None, priority=100,
             threshold_type="AGGREGATE_PERIOD", effective_from=datetime.date(2026, 4, 1), effective_to=None):
    rule = _tax_rule(
        tax_rule_id=rule_id, rule_code=code, rule_name=f"TDS {section}", legal_reference=None,
        threshold_type=threshold_type, threshold_amount=Decimal(threshold) if threshold is not None else None,
        priority=priority, effective_from=effective_from, effective_to=effective_to,
    )
    rule.old_section = section
    rule._test_payment_nature_code = nature
    rule.conditions = [
        TaxRuleCondition(condition_type="PAYMENT_NATURE", operator="EQUALS", condition_value=nature, logical_group=1, sequence_no=1)
    ]
    if rate_condition:
        condition_type, operator, value = rate_condition
        rule.conditions.append(
            TaxRuleCondition(condition_type=condition_type, operator=operator, condition_value=value, logical_group=1, sequence_no=2)
        )
    rate = _rate_rule(tax_rate_rule_id=rule_id, tax_rule_id=rule_id, rate_percent=Decimal(rate),
                      effective_from=effective_from, effective_to=effective_to)
    return rule, rate


def _seeded_rules():
    """Live configuration after migration_tds_configuration.sql, plus the
    illustrative multi-variant examples from the TDS Configuration spec."""
    return [
        _variant(6, "TDS_194C_IND", "CONTRACTOR", "1", "100000", "194C", ("ENTITY_TYPE", "IN", "HUF,INDIVIDUAL")),
        _variant(12, "TDS_194C_OTH", "CONTRACTOR", "2", "100000", "194C", ("ENTITY_TYPE", "NOT_IN", "HUF,INDIVIDUAL")),
        _variant(9, "TDS_194H", "COMMISSION", "2", "15000", "194H"),
        _variant(8, "TDS_194I", "RENT", "10", "240000", "194I"),
        _variant(7, "TDS_194J", "PROFESSIONAL_SERVICE", "10", "30000", "194J"),
        _variant(11, "TDS_194J_TECH", "TECHNICAL_SERVICE", "2", "30000", "194J"),
        _variant(10, "TDS_194Q", "PURCHASE_OF_GOODS", "0.1", "5000000", "194Q"),
    ]


def _service(entity_type="COMPANY", gross="6000000.00", status_code=None, rules=None, profile_kwargs=None):
    invoice = _invoice(gross=Decimal(gross))
    if status_code:
        invoice.status = StatusMaster(status_id=1, module_name="INVOICE", status_code=status_code, status_name=status_code)
    vendor = _vendor()
    profile = VendorTdsProfile(
        id=1, vendor_id=vendor.vendor_id, entity_type=entity_type, residency_type="RESIDENT", pan_status="VALID",
        lower_deduction_available=False, tds_exemption_flag=False, **(profile_kwargs or {}),
    )
    natures = [_payment_nature(id_=i, code=c, name=c.title()) for c, i in NATURES.items()]
    pairs = rules if rules is not None else _seeded_rules()
    service, tds_dao = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=natures,
        rules=[r for r, _ in pairs], rate_rules=[rr for _, rr in pairs], profiles=[profile],
    )
    return service, tds_dao, invoice


# =========================================================
# Every section
# =========================================================

@pytest.mark.parametrize("nature, expected_code, expected_rate, expected_amount", [
    ("CONTRACTOR", "TDS_194C_OTH", "2.0000", "120000.00"),
    ("COMMISSION", "TDS_194H", "2.0000", "120000.00"),
    ("RENT", "TDS_194I", "10.0000", "600000.00"),
    ("PROFESSIONAL_SERVICE", "TDS_194J", "10.0000", "600000.00"),
    ("TECHNICAL_SERVICE", "TDS_194J_TECH", "2.0000", "120000.00"),
    ("PURCHASE_OF_GOODS", "TDS_194Q", "0.1000", "6000.00"),
])
def test_each_section_determines_its_own_rule_and_rate(nature, expected_code, expected_rate, expected_amount):
    service, _, invoice = _service()
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code=nature)

    assert row.tds_applicable is True
    assert row.rule_snapshot["rule_code"] == expected_code
    assert row.tds_rate == Decimal(expected_rate)
    assert row.tds_amount == Decimal(expected_amount)
    assert row.tds_rate_rule_id == row.tds_rule_id  # fixture pairs rate row id with rule id


@pytest.mark.parametrize("nature", ["INTEREST", "OTHER"])
def test_natures_without_a_rule_are_a_valid_not_applicable_outcome(nature):
    service, _, invoice = _service()
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code=nature)

    assert row.tds_applicable is False
    assert row.payment_nature_id == NATURES[nature]
    assert row.tds_rule_id is None and row.tds_rate is None and row.tds_amount is None
    assert f"No active TDS rule is configured for payment nature '{nature}'" in row.determination_reason
    # complete - such an invoice may go for approval and be verified
    assert tds_determination_problem(row) is None
    assert service.verify(invoice.invoice_id, user_id="fin").determination_status == DETERMINATION_STATUS_VERIFIED


# =========================================================
# Multiple variants of one section
# =========================================================

@pytest.mark.parametrize("entity_type, expected_code, expected_rate", [
    ("INDIVIDUAL", "TDS_194C_IND", "1.0000"),
    ("HUF", "TDS_194C_IND", "1.0000"),
    ("COMPANY", "TDS_194C_OTH", "2.0000"),
    ("FIRM", "TDS_194C_OTH", "2.0000"),
])
def test_194c_variant_chosen_by_vendor_entity_type(entity_type, expected_code, expected_rate):
    service, _, invoice = _service(entity_type=entity_type, gross="200000.00")
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="CONTRACTOR")

    assert row.rule_snapshot["rule_code"] == expected_code
    assert row.tds_rate == Decimal(expected_rate)
    assert row.entity_type == entity_type
    assert set(row.rule_snapshot["variants_considered"]) == {"TDS_194C_IND", "TDS_194C_OTH"}


def test_unknown_entity_type_matches_no_conditional_variant_and_explains_why():
    service, _, invoice = _service(entity_type=None, gross="200000.00")
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="CONTRACTOR")

    assert row.tds_applicable is False
    assert row.tds_rule_id is None
    assert "No TDS rule variant" in row.determination_reason
    assert "TDS_194C_IND" in row.determination_reason and "TDS_194C_OTH" in row.determination_reason


def test_catch_all_variant_used_when_specific_one_does_not_match():
    rules = [
        _variant(1, "TDS_194I_PM", "RENT", "2", "240000", "194I", ("ENTITY_TYPE", "EQUALS", "INDIVIDUAL")),
        _variant(2, "TDS_194I_LB", "RENT", "10", "240000", "194I"),
    ]
    service, _, invoice = _service(entity_type="COMPANY", rules=rules, gross="300000.00")
    assert service.determine(invoice.invoice_id, user_id="u", payment_nature_code="RENT").rule_snapshot["rule_code"] == "TDS_194I_LB"

    service, _, invoice = _service(entity_type="INDIVIDUAL", rules=rules, gross="300000.00")
    assert service.determine(invoice.invoice_id, user_id="u", payment_nature_code="RENT").rule_snapshot["rule_code"] == "TDS_194I_PM"


# =========================================================
# Threshold / effective dates
# =========================================================

def test_threshold_not_crossed_is_not_applicable_but_snapshots_the_rule():
    service, _, invoice = _service(gross="20000.00")
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert row.tds_applicable is False
    assert row.threshold_amount == Decimal("30000")
    assert row.threshold_type == "AGGREGATE_PERIOD"
    assert row.rule_snapshot["rule_code"] == "TDS_194J"
    assert "below" in row.determination_reason


def test_per_transaction_threshold_ignores_prior_aggregate():
    rules = [_variant(9, "TDS_194H", "COMMISSION", "2", "15000", "194H", threshold_type="PER_TRANSACTION")]
    service, tds_dao, invoice = _service(rules=rules, gross="10000.00")
    tds_dao.prior_aggregates[(invoice.vendor_id, NATURES["COMMISSION"])] = Decimal("90000.00")
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="COMMISSION")

    assert row.tds_applicable is False
    assert row.threshold_type == "PER_TRANSACTION"


def test_rule_outside_effective_dates_is_not_used():
    rules = [
        _variant(1, "TDS_194J_OLD", "PROFESSIONAL_SERVICE", "5", "30000", "194J",
                 effective_from=datetime.date(2025, 4, 1), effective_to=datetime.date(2026, 3, 31)),
        _variant(2, "TDS_194J_NEW", "PROFESSIONAL_SERVICE", "10", "30000", "194J",
                 effective_from=datetime.date(2026, 4, 1)),
    ]
    service, _, invoice = _service(rules=rules, gross="100000.00")  # invoice dated 2026-06-01
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")
    assert row.rule_snapshot["rule_code"] == "TDS_194J_NEW"
    assert row.tds_rate == Decimal("10.0000")


# =========================================================
# Vendor tax facts
# =========================================================

def test_pan_not_available_raises_rate_to_206aa_floor_and_records_basis():
    service, _, invoice = _service(gross="100000.00")
    service.tds_dao.profiles[invoice.vendor_id].pan_status = "NOT_AVAILABLE"
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert row.tds_rate == Decimal("20.0000")
    assert row.rule_snapshot["rate_basis"] == "PAN_NOT_AVAILABLE_206AA"


def test_exempt_vendor_is_not_applicable():
    service, _, invoice = _service(profile_kwargs={"exemption_reason": "Govt body"})
    service.tds_dao.profiles[invoice.vendor_id].tds_exemption_flag = True
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert row.tds_applicable is False
    assert "exempt" in row.determination_reason


def test_lower_deduction_certificate_rate_is_snapshotted():
    service, _, invoice = _service(gross="100000.00", profile_kwargs={
        "certificate_number": "LDC-1", "certificate_rate": Decimal("1.5000"),
        "certificate_valid_from": datetime.date(2026, 4, 1), "certificate_valid_to": datetime.date(2027, 3, 31),
    })
    service.tds_dao.profiles[invoice.vendor_id].lower_deduction_available = True
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert row.tds_rate == Decimal("1.5000")
    assert row.tds_amount == Decimal("1500.00")
    assert row.rule_snapshot["rate_basis"] == "LOWER_DEDUCTION_CERTIFICATE"
    assert row.rule_snapshot["lower_deduction_certificate"]["certificate_number"] == "LDC-1"
    assert row.rule_snapshot["configured_rate_percent"] == "10"


# =========================================================
# Snapshot stability / lock / verification
# =========================================================

def test_snapshot_survives_later_configuration_edit():
    service, tds_dao, invoice = _service(gross="100000.00")
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")
    service.verify(invoice.invoice_id, user_id="fin")

    # Finance later edits the live rule/rate
    rule = next(r for r in tds_dao.rules["PROFESSIONAL_SERVICE"] if r.rule_code == "TDS_194J")
    rule.old_section = "393"
    tds_dao.rate_rules[rule.tax_rule_id][0].rate_percent = Decimal("12.0000")

    with pytest.raises(ValueError, match="already been verified"):
        service.determine(invoice.invoice_id, user_id="u")
    stored = service.get(invoice.invoice_id)
    assert stored.tds_rate == Decimal("10.0000")
    assert stored.tds_amount == Decimal("10000.00")
    assert stored.rule_snapshot["old_section"] == "194J"
    assert stored.rule_snapshot["configured_rate_percent"] == "10"


@pytest.mark.parametrize("status_code", ["PENDING_APPROVAL", "APPROVED", "READY_FOR_PAYMENT", "PAID", "REJECTED"])
def test_payment_nature_locked_after_sent_for_approval(status_code):
    service, _, invoice = _service(status_code=status_code)
    with pytest.raises(ValueError, match="locked"):
        service.update_inputs(invoice.invoice_id, user_id="u", payment_nature_code="RENT")


@pytest.mark.parametrize("status_code", ["OCR_REVIEWED", "RETURNED_FOR_REVIEW", "DRAFT"])
def test_payment_nature_editable_before_sending(status_code):
    service, _, invoice = _service(status_code=status_code)
    row = service.update_inputs(invoice.invoice_id, user_id="u", payment_nature_code="RENT")
    assert row.rule_snapshot["rule_code"] == "TDS_194I"


def test_verify_rejects_determination_without_payment_nature():
    invoice = _invoice(purchase_category_id=None)
    service, _ = _make_service(invoices=[invoice], vendors=[_vendor()])
    service.determine(invoice.invoice_id, user_id="u")

    with pytest.raises(ValueError, match="cannot be verified.*no payment nature"):
        service.verify(invoice.invoice_id, user_id="fin")


def test_verify_rejects_rule_without_active_rate():
    rule, _ = _variant(7, "TDS_194J", "PROFESSIONAL_SERVICE", "10", "30000", "194J")
    service, _, invoice = _service(rules=[(rule, _rate_rule(tax_rate_rule_id=7, tax_rule_id=7, is_active=False))])
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")
    assert row.tds_rule_id == 7 and row.tds_rate_rule_id is None

    with pytest.raises(ValueError, match="no active rate"):
        service.verify(invoice.invoice_id, user_id="fin")


def test_verify_records_verifier_and_keeps_snapshot():
    service, _, invoice = _service(gross="100000.00")
    determined = service.determine(invoice.invoice_id, user_id="ap-1", payment_nature_code="PROFESSIONAL_SERVICE")
    snapshot = dict(determined.rule_snapshot)
    amount = determined.tds_amount

    verified = service.verify(invoice.invoice_id, user_id="fin-1", remarks="ok")
    assert verified.determination_status == DETERMINATION_STATUS_VERIFIED
    assert verified.verified_by == "fin-1" and verified.verified_at is not None
    assert verified.determined_by == "ap-1"
    assert verified.tds_amount == amount and verified.rule_snapshot == snapshot
    audit = service.invoice_dao.audit_logs[-1]
    assert audit.action == "INVOICE_TDS_VERIFIED"
    assert audit.new_values["tds_rate_rule_id"] == verified.tds_rate_rule_id
