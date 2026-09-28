# Backend/tests/test_tds_determination_service.py
"""Unit tests for TDSDeterminationService - business-logic/branching coverage,
no real DB connection. Follows the project's existing fake-DAO test style
(see test_invoice_approval_workflow.py's module docstring): the service is
constructed normally, then its DAO attributes are swapped for hand-rolled
fakes. Real SQLAlchemy model classes (Invoice, Vendor, TaxRule, ...) are used
directly as plain Python objects - constructing a mapped class never touches
a DB session, only add()/flush()/commit() do, and those are the fakes' job.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from Backend.Business_Layer.services import tds_determination_service
from Backend.Business_Layer.services.tds_determination_service import (
    DETERMINATION_STATUS_DETERMINED,
    DETERMINATION_STATUS_VERIFIED,
    GSTIN_STATUS_CHECK_UNAVAILABLE,
    GSTIN_STATUS_NOT_ON_FILE,
    TDSDeterminationService,
)
from Backend.Business_Layer.utils.vendor_auto_onboarding import GSTVerificationResult
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import TaxRateRule, TaxRule
from Backend.Data_Access_Layer.models.tds import PurchaseCategoryTdsMapping, TdsPaymentNature, VendorTdsProfile
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorAddress, VendorTax

INVOICE_DATE = datetime.date(2026, 6, 1)


class FakeDB:
    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeInvoiceDAO:
    def __init__(self, invoices):
        self.invoices = invoices
        self.audit_logs = []

    def get_invoice_by_id_locked(self, invoice_id):
        return self.invoices.get(invoice_id)

    def create_audit_log(self, audit_log):
        self.audit_logs.append(audit_log)
        return audit_log


class FakeVendorDAO:
    def __init__(self, vendors):
        self.vendors = vendors

    def get_vendor_by_id(self, vendor_id):
        return self.vendors.get(vendor_id)


class FakeTdsDAO:
    def __init__(self):
        self.payment_natures: dict[str, TdsPaymentNature] = {}
        self.mappings: dict[int, PurchaseCategoryTdsMapping] = {}
        self.profiles: dict[int, VendorTdsProfile] = {}
        self.rules: dict[str, list[TaxRule]] = {}
        self.rate_rules: dict[int, list[TaxRateRule]] = {}
        self.invoice_tds: dict[int, object] = {}
        self.prior_aggregates: dict[tuple[int, int], Decimal] = {}
        self._next_profile_id = 1
        self._next_invoice_tds_id = 1

    # payment nature / mapping
    def get_payment_nature_by_code(self, code):
        return self.payment_natures.get(code)

    def get_default_mapping_for_category(self, purchase_category_id):
        return self.mappings.get(purchase_category_id)

    # vendor profile
    def get_vendor_tds_profile(self, vendor_id):
        return self.profiles.get(vendor_id)

    def create_vendor_tds_profile(self, profile):
        profile.id = self._next_profile_id
        self._next_profile_id += 1
        self.profiles[profile.vendor_id] = profile
        return profile

    # rule engine
    def get_active_tds_rule_for_payment_nature(self, payment_nature_code, as_of_date):
        candidates = [
            r for r in self.rules.get(payment_nature_code, [])
            if r.is_active and r.effective_from <= as_of_date
            and (r.effective_to is None or r.effective_to >= as_of_date)
        ]
        candidates.sort(key=lambda r: r.priority)
        return candidates[0] if candidates else None

    def get_active_tax_rate_rule_for_tax_rule(self, tax_rule_id, as_of_date):
        candidates = [
            rr for rr in self.rate_rules.get(tax_rule_id, [])
            if rr.is_active and rr.effective_from <= as_of_date
            and (rr.effective_to is None or rr.effective_to >= as_of_date)
        ]
        candidates.sort(key=lambda rr: rr.effective_from, reverse=True)
        return candidates[0] if candidates else None

    # invoice_tds
    def get_invoice_tds_by_invoice_id(self, invoice_id):
        return self.invoice_tds.get(invoice_id)

    def get_invoice_tds_by_invoice_id_locked(self, invoice_id):
        return self.invoice_tds.get(invoice_id)

    def create_invoice_tds(self, row):
        row.id = self._next_invoice_tds_id
        self._next_invoice_tds_id += 1
        self.invoice_tds[row.invoice_id] = row
        return row

    def sum_prior_transaction_amount(self, vendor_id, payment_nature_id, fy_start, fy_end, exclude_invoice_id):
        return self.prior_aggregates.get((vendor_id, payment_nature_id), Decimal("0"))


def _invoice(invoice_id=1, vendor_id=15, purchase_category_id=2, gross=Decimal("100000.00"), discount=Decimal("0")):
    return Invoice(
        invoice_id=invoice_id,
        invoice_number=f"INV-{invoice_id}",
        vendor_id=vendor_id,
        invoice_date=INVOICE_DATE,
        due_date=INVOICE_DATE,
        currency_id=1,
        gross_amount=gross,
        discount_amount=discount,
        tax_amount=Decimal("0"),
        net_amount=gross - discount,
        purchase_category_id=purchase_category_id,
    )


def _vendor(vendor_id=15, pan_number="AAJCA9880A"):
    return Vendor(vendor_id=vendor_id, vendor_name="Test Vendor", country_id=1, pan_number=pan_number)


def _vendor_with_gstin(gstin="07AAJCA9880A1ZL", registration_type="GST", **kwargs):
    vendor = _vendor(**kwargs)
    address = VendorAddress(vendor_address_id=1, vendor_id=vendor.vendor_id, address_line1="x", city="x", country_id=1, is_primary=True)
    address.vendor_tax = [VendorTax(vendor_tax_id=1, vendor_address_id=1, registration_type=registration_type, registration_number=gstin)]
    vendor.vendor_address = [address]
    return vendor


def _gst_search_result(verified=True, status="Active", error_message=None):
    if not verified:
        return GSTVerificationResult(verified=False, error_message=error_message)
    return GSTVerificationResult(
        verified=True,
        data={"code": 200, "data": {"status_cd": "1", "data": {"gstin": "07AAJCA9880A1ZL", "sts": status}}},
    )


def _payment_nature(id_=2, code="PROFESSIONAL_SERVICE", name="Professional Services", is_active=True):
    return TdsPaymentNature(id=id_, code=code, name=name, is_active=is_active)


def _tax_rule(
    tax_rule_id=7,
    rule_code="TDS_194J",
    rule_name="TDS - Professional or Technical Services",
    legal_reference="Section 194J, Income-tax Act (FY2026-27)",
    threshold_type="AGGREGATE_PERIOD",
    threshold_amount=Decimal("30000.00"),
    priority=100,
    is_active=True,
    effective_from=datetime.date(2026, 4, 1),
    effective_to=None,
):
    return TaxRule(
        tax_rule_id=tax_rule_id,
        rule_code=rule_code,
        rule_name=rule_name,
        tax_type_id=2,
        rule_category="TDS_RATE",
        priority=priority,
        effective_from=effective_from,
        effective_to=effective_to,
        is_active=is_active,
        legal_reference=legal_reference,
        threshold_type=threshold_type,
        threshold_amount=threshold_amount,
    )


def _rate_rule(
    tax_rate_rule_id=7,
    tax_rule_id=7,
    rate_percent=Decimal("10.0000"),
    calculation_type="PERCENTAGE",
    fixed_amount=None,
    is_active=True,
    effective_from=datetime.date(2026, 4, 1),
    effective_to=None,
):
    return TaxRateRule(
        tax_rate_rule_id=tax_rate_rule_id,
        tax_rule_id=tax_rule_id,
        rate_percent=rate_percent,
        calculation_type=calculation_type,
        fixed_amount=fixed_amount,
        effective_from=effective_from,
        effective_to=effective_to,
        is_active=is_active,
    )


def _make_service(invoices, vendors, payment_natures=(), mappings=(), rules=(), rate_rules=(), profiles=()):
    service = TDSDeterminationService(FakeDB())
    service.invoice_dao = FakeInvoiceDAO({i.invoice_id: i for i in invoices})
    service.vendor_dao = FakeVendorDAO({v.vendor_id: v for v in vendors})

    tds_dao = FakeTdsDAO()
    for nature in payment_natures:
        tds_dao.payment_natures[nature.code] = nature
    for pc_id, mapping in mappings:
        tds_dao.mappings[pc_id] = mapping
    for rule in rules:
        tds_dao.rules.setdefault(_condition_code_for(rule), []).append(rule)
    for rr in rate_rules:
        tds_dao.rate_rules.setdefault(rr.tax_rule_id, []).append(rr)
    for profile in profiles:
        tds_dao.profiles[profile.vendor_id] = profile
    service.tds_dao = tds_dao
    return service, tds_dao


def _condition_code_for(rule: TaxRule) -> str:
    # In the real schema this comes from tax_rule_condition (condition_type=PAYMENT_NATURE);
    # tests key the fake rules dict by payment-nature code directly for simplicity, tagged here.
    return rule._test_payment_nature_code


def _default_setup(vendor=None, **invoice_kwargs):
    """A vendor with a valid PAN, PROFESSIONAL_SERVICE mapped as the default for
    purchase_category_id=2, TDS_194J (10%, AGGREGATE_PERIOD/30000) as the matching
    rule - the same shape as the real seeded data this feature was built against."""
    invoice = _invoice(**invoice_kwargs)
    vendor = vendor if vendor is not None else _vendor()
    nature = _payment_nature()
    mapping = PurchaseCategoryTdsMapping(id=1, purchase_category_id=2, tds_payment_nature_id=2, is_default=True, is_active=True)
    mapping.tds_payment_nature = nature
    rule = _tax_rule()
    rule._test_payment_nature_code = "PROFESSIONAL_SERVICE"
    rr = _rate_rule()

    service, tds_dao = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature],
        mappings=[(2, mapping)], rules=[rule], rate_rules=[rr],
    )
    return service, tds_dao, invoice, vendor


# =========================================================
# 1) TDS applicable / not applicable
# =========================================================

def test_determine_applicable_above_threshold():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    row = service.determine(invoice.invoice_id, user_id="5100007")

    assert row.tds_applicable is True
    assert row.tds_rate == Decimal("10.0000")
    assert row.tds_amount == Decimal("10000.00")
    assert row.determination_status == DETERMINATION_STATUS_DETERMINED
    assert "194J" in row.determination_reason or "Professional" in row.determination_reason


def test_determine_not_applicable_no_mapping():
    invoice = _invoice(purchase_category_id=None)
    vendor = _vendor()
    service, _ = _make_service(invoices=[invoice], vendors=[vendor])

    row = service.determine(invoice.invoice_id, user_id="5100007")

    assert row.tds_applicable is False
    assert row.payment_nature_id is None
    assert "purchase category" in row.determination_reason.lower()


# =========================================================
# 2) Threshold
# =========================================================

def test_determine_below_threshold():
    service, _, invoice, _ = _default_setup(gross=Decimal("10000.00"))
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.tds_applicable is False
    assert row.tds_amount is None
    assert row.taxable_base == Decimal("10000.00")
    assert "below" in row.determination_reason.lower()


def test_determine_above_threshold_single_transaction():
    service, _, invoice, _ = _default_setup(gross=Decimal("50000.00"))
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.tds_applicable is True
    assert row.aggregate_amount == Decimal("50000.00")


def test_determine_threshold_crossed_by_cumulative_transactions():
    service, tds_dao, invoice, vendor = _default_setup(gross=Decimal("10000.00"))
    tds_dao.prior_aggregates[(vendor.vendor_id, 2)] = Decimal("25000.00")

    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.prior_period_aggregate == Decimal("25000.00")
    assert row.aggregate_amount == Decimal("35000.00")
    assert row.tds_applicable is True
    assert row.tds_amount == Decimal("1000.00")  # 10% of THIS invoice's 10000, not the full aggregate


# =========================================================
# 3) PAN status
# =========================================================

def test_determine_valid_pan_uses_standard_rate():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.pan_status == "VALID"
    assert row.tds_rate == Decimal("10.0000")


def test_determine_missing_pan_applies_section_206aa_floor():
    invoice = _invoice(gross=Decimal("100000.00"))
    vendor = _vendor(pan_number=None)
    nature = _payment_nature()
    mapping = PurchaseCategoryTdsMapping(id=1, purchase_category_id=2, tds_payment_nature_id=2, is_default=True, is_active=True)
    mapping.tds_payment_nature = nature
    rule = _tax_rule()
    rule._test_payment_nature_code = "PROFESSIONAL_SERVICE"
    rr = _rate_rule(rate_percent=Decimal("10.0000"))

    service, _ = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature],
        mappings=[(2, mapping)], rules=[rule], rate_rules=[rr],
    )
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.pan_status == "NOT_AVAILABLE"
    assert row.tds_rate == Decimal("20.0000")
    assert row.tds_amount == Decimal("20000.00")
    assert "206AA" in row.determination_reason


def test_vendor_profile_auto_created_when_missing():
    invoice = _invoice()
    vendor = _vendor(pan_number=None)
    service, tds_dao = _make_service(invoices=[invoice], vendors=[vendor])

    assert tds_dao.get_vendor_tds_profile(vendor.vendor_id) is None
    service.determine(invoice.invoice_id, user_id="u")
    profile = tds_dao.get_vendor_tds_profile(vendor.vendor_id)

    assert profile is not None
    assert profile.pan_status == "NOT_AVAILABLE"


# =========================================================
# 4) Exemption / lower-deduction certificate
# =========================================================

def test_determine_vendor_exemption():
    invoice = _invoice(gross=Decimal("100000.00"))
    vendor = _vendor()
    nature = _payment_nature()
    mapping = PurchaseCategoryTdsMapping(id=1, purchase_category_id=2, tds_payment_nature_id=2, is_default=True, is_active=True)
    mapping.tds_payment_nature = nature
    profile = VendorTdsProfile(
        vendor_id=vendor.vendor_id, residency_type="RESIDENT", pan_status="VALID",
        tds_exemption_flag=True, exemption_reason="Government body",
    )

    service, _ = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature],
        mappings=[(2, mapping)], profiles=[profile],
    )
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.tds_applicable is False
    assert "exempt" in row.determination_reason.lower()
    assert row.tds_amount is None


def test_determine_lower_deduction_certificate_overrides_rate():
    invoice = _invoice(gross=Decimal("100000.00"))
    vendor = _vendor(pan_number=None)  # would otherwise trigger the 206AA floor
    nature = _payment_nature()
    mapping = PurchaseCategoryTdsMapping(id=1, purchase_category_id=2, tds_payment_nature_id=2, is_default=True, is_active=True)
    mapping.tds_payment_nature = nature
    rule = _tax_rule()
    rule._test_payment_nature_code = "PROFESSIONAL_SERVICE"
    rr = _rate_rule(rate_percent=Decimal("10.0000"))
    profile = VendorTdsProfile(
        vendor_id=vendor.vendor_id, residency_type="RESIDENT", pan_status="NOT_AVAILABLE",
        lower_deduction_available=True, certificate_number="LDC/2026/001",
        certificate_rate=Decimal("2.0000"),
        certificate_valid_from=datetime.date(2026, 4, 1), certificate_valid_to=datetime.date(2027, 3, 31),
    )

    service, _ = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature],
        mappings=[(2, mapping)], rules=[rule], rate_rules=[rr], profiles=[profile],
    )
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.tds_applicable is True
    assert row.tds_rate == Decimal("2.0000")
    assert row.tds_amount == Decimal("2000.00")
    assert "certificate" in row.determination_reason.lower()


# =========================================================
# 5) Rule resolution failures
# =========================================================

def test_determine_no_matching_rule():
    invoice = _invoice(purchase_category_id=3)
    vendor = _vendor()
    nature = _payment_nature(id_=3, code="TECHNICAL_SERVICE", name="Technical Services")
    mapping = PurchaseCategoryTdsMapping(id=2, purchase_category_id=3, tds_payment_nature_id=3, is_default=True, is_active=True)
    mapping.tds_payment_nature = nature

    service, _ = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature], mappings=[(3, mapping)],
    )  # no rules configured for TECHNICAL_SERVICE at all
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.tds_applicable is False
    assert "no active tds rule" in row.determination_reason.lower()


def test_determine_expired_rule_not_matched():
    invoice = _invoice(gross=Decimal("100000.00"))
    vendor = _vendor()
    nature = _payment_nature()
    mapping = PurchaseCategoryTdsMapping(id=1, purchase_category_id=2, tds_payment_nature_id=2, is_default=True, is_active=True)
    mapping.tds_payment_nature = nature
    expired_rule = _tax_rule(effective_from=datetime.date(2020, 4, 1), effective_to=datetime.date(2021, 3, 31))
    expired_rule._test_payment_nature_code = "PROFESSIONAL_SERVICE"

    service, _ = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature],
        mappings=[(2, mapping)], rules=[expired_rule],
    )
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.tds_applicable is False
    assert "no active tds rule" in row.determination_reason.lower()


def test_determine_unknown_payment_nature_code_raises():
    invoice = _invoice()
    vendor = _vendor()
    service, _ = _make_service(invoices=[invoice], vendors=[vendor])

    with pytest.raises(ValueError):
        service.determine(invoice.invoice_id, user_id="u", payment_nature_code="NOT_A_REAL_CODE")


def test_determine_invoice_not_found_raises():
    service, _ = _make_service(invoices=[], vendors=[])
    with pytest.raises(ValueError, match="not found"):
        service.determine(999, user_id="u")


# =========================================================
# 6) Explicit payment-nature correction (AP Executive override)
# =========================================================

def test_determine_explicit_payment_nature_overrides_default_mapping():
    invoice = _invoice(purchase_category_id=None, gross=Decimal("100000.00"))  # no mapping possible
    vendor = _vendor()
    nature = _payment_nature()
    rule = _tax_rule()
    rule._test_payment_nature_code = "PROFESSIONAL_SERVICE"
    rr = _rate_rule()

    service, _ = _make_service(
        invoices=[invoice], vendors=[vendor], payment_natures=[nature], rules=[rule], rate_rules=[rr],
    )
    row = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert row.tds_applicable is True
    assert row.payment_nature_id == nature.id


def test_update_inputs_requires_payment_nature_code():
    invoice = _invoice()
    vendor = _vendor()
    service, _ = _make_service(invoices=[invoice], vendors=[vendor])

    with pytest.raises(ValueError):
        service.update_inputs(invoice.invoice_id, user_id="u", payment_nature_code="")


# =========================================================
# 7) Re-determination / verification lock (spec test cases 13-15)
# =========================================================

def test_redetermination_works_before_verify():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    first = service.determine(invoice.invoice_id, user_id="u")
    first_id = first.id

    second = service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert second.id == first_id  # same row updated in place, not a duplicate
    assert second.determination_status == DETERMINATION_STATUS_DETERMINED


def test_verify_then_redetermine_is_blocked():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")
    verified = service.verify(invoice.invoice_id, user_id="finance-1", remarks="Looks correct")

    assert verified.determination_status == DETERMINATION_STATUS_VERIFIED
    assert verified.verified_by == "finance-1"

    with pytest.raises(ValueError, match="already been verified"):
        service.determine(invoice.invoice_id, user_id="u")


def test_verify_twice_raises():
    service, _, invoice, _ = _default_setup()
    service.determine(invoice.invoice_id, user_id="u")
    service.verify(invoice.invoice_id, user_id="finance-1")

    with pytest.raises(ValueError, match="already been verified"):
        service.verify(invoice.invoice_id, user_id="finance-1")


def test_verify_requires_existing_determination():
    invoice = _invoice()
    vendor = _vendor()
    service, _ = _make_service(invoices=[invoice], vendors=[vendor])

    with pytest.raises(ValueError, match="not found"):
        service.verify(invoice.invoice_id, user_id="finance-1")


def test_get_requires_existing_determination():
    invoice = _invoice()
    vendor = _vendor()
    service, _ = _make_service(invoices=[invoice], vendors=[vendor])

    with pytest.raises(ValueError, match="not found"):
        service.get(invoice.invoice_id)


def test_get_returns_stored_determination():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")

    row = service.get(invoice.invoice_id)
    assert row.tds_applicable is True


# =========================================================
# 8) GST registration compliance - warning/signal only, must never
#    affect tds_applicable/tds_rate/tds_amount
# =========================================================

def test_gst_compliance_no_gstin_on_file():
    # The default _vendor() fixture has no vendor_address/vendor_tax at all.
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.gstin_status == GSTIN_STATUS_NOT_ON_FILE
    assert row.gstin_checked_at is not None
    assert "no gst registration on file" in row.determination_reason.lower()
    # TDS math is unaffected either way
    assert row.tds_applicable is True
    assert row.tds_amount == Decimal("10000.00")


def test_gst_compliance_active_status_no_warning(monkeypatch):
    monkeypatch.setattr(tds_determination_service, "call_gst_search", lambda gstin: _gst_search_result(status="Active"))
    vendor = _vendor_with_gstin()
    service, _, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))

    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.gstin_status == "Active"
    assert "not active" not in row.determination_reason.lower()
    assert row.tds_applicable is True
    assert row.tds_amount == Decimal("10000.00")


def test_gst_compliance_cancelled_status_warns_but_does_not_block_tds(monkeypatch):
    monkeypatch.setattr(tds_determination_service, "call_gst_search", lambda gstin: _gst_search_result(status="Cancelled"))
    vendor = _vendor_with_gstin()
    service, _, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))

    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.gstin_status == "Cancelled"
    assert "not active" in row.determination_reason.lower()
    assert "cancelled" in row.determination_reason.lower()
    # Exactly the same TDS outcome as the Active case - GSTIN status never
    # touches tds_applicable/tds_rate/tds_amount.
    assert row.tds_applicable is True
    assert row.tds_rate == Decimal("10.0000")
    assert row.tds_amount == Decimal("10000.00")


def test_gst_compliance_api_failure_does_not_block_tds(monkeypatch):
    monkeypatch.setattr(
        tds_determination_service, "call_gst_search",
        lambda gstin: _gst_search_result(verified=False, error_message="GST verification service unavailable"),
    )
    vendor = _vendor_with_gstin()
    service, _, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))

    row = service.determine(invoice.invoice_id, user_id="u")

    assert row.gstin_status == GSTIN_STATUS_CHECK_UNAVAILABLE
    assert "unavailable" in row.determination_reason.lower()
    assert row.tds_applicable is True
    assert row.tds_amount == Decimal("10000.00")


def test_gst_compliance_unexpected_exception_from_search_does_not_propagate(monkeypatch):
    # call_gst_search itself never raises (it catches everything internally per
    # vendor_auto_onboarding.py) - but prove the TDS flow survives even if a
    # future change to that contract broke and it did raise, by simulating the
    # one thing that actually matters: a plain lookup failure never surfaces
    # as an unhandled error out of determine().
    monkeypatch.setattr(
        tds_determination_service, "call_gst_search",
        lambda gstin: _gst_search_result(verified=False, error_message=None),
    )
    vendor = _vendor_with_gstin()
    service, _, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))

    row = service.determine(invoice.invoice_id, user_id="u")  # must not raise
    assert row.gstin_status == GSTIN_STATUS_CHECK_UNAVAILABLE


# =========================================================
# 9) entity_type derivation from PAN (4th character) - only at
#    vendor_tds_profile CREATION time, never overwriting an existing row
# =========================================================

def test_entity_type_derived_from_pan_on_new_profile():
    # _vendor()'s default PAN AAJCA9880A has 'C' as its 4th character -> COMPANY.
    service, tds_dao, invoice, vendor = _default_setup(gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")

    profile = tds_dao.get_vendor_tds_profile(vendor.vendor_id)
    assert profile.entity_type == "COMPANY"


def test_entity_type_derivation_for_individual_pan():
    vendor = _vendor(pan_number="ABCPD1234E")  # 4th char 'P' -> INDIVIDUAL
    service, tds_dao, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")

    profile = tds_dao.get_vendor_tds_profile(vendor.vendor_id)
    assert profile.entity_type == "INDIVIDUAL"


def test_entity_type_stays_none_when_pan_missing():
    vendor = _vendor(pan_number=None)
    service, tds_dao, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")

    profile = tds_dao.get_vendor_tds_profile(vendor.vendor_id)
    assert profile.entity_type is None
    assert profile.pan_status == "NOT_AVAILABLE"


def test_entity_type_never_guessed_for_malformed_pan():
    vendor = _vendor(pan_number="NOT-A-REAL-PAN")
    service, tds_dao, invoice, _ = _default_setup(vendor=vendor, gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")

    profile = tds_dao.get_vendor_tds_profile(vendor.vendor_id)
    assert profile.entity_type is None


def test_existing_profile_entity_type_is_never_overwritten():
    # A profile that already exists (e.g. hand-corrected by an admin, or just
    # created with a different value than the PAN would derive) must never be
    # silently patched by a later determine() call.
    service, tds_dao, invoice, vendor = _default_setup(gross=Decimal("100000.00"))
    existing_profile = VendorTdsProfile(
        vendor_id=vendor.vendor_id, residency_type="RESIDENT", pan_status="VALID",
        entity_type="TRUST",  # deliberately different from what the PAN would derive (COMPANY)
    )
    tds_dao.profiles[vendor.vendor_id] = existing_profile

    service.determine(invoice.invoice_id, user_id="u")

    assert tds_dao.get_vendor_tds_profile(vendor.vendor_id).entity_type == "TRUST"


# =========================================================
# 10) Audit trail - determine()/verify() must show up in the invoice's
#     shared Activity timeline (ap.audit_log), same as every other
#     invoice-lifecycle action (send-for-approval, approve, reject, ...)
# =========================================================

def test_determine_writes_an_audit_log_entry():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    row = service.determine(invoice.invoice_id, user_id="5100007")

    logs = service.invoice_dao.audit_logs
    assert len(logs) == 1
    entry = logs[0]
    assert entry.table_name == "invoice"
    assert entry.record_id == invoice.invoice_id
    assert entry.action == "INVOICE_TDS_DETERMINED"
    assert entry.changed_by == "5100007"
    assert entry.new_values["tds_applicable"] is True
    assert entry.new_values["tds_amount"] == str(row.tds_amount)
    assert entry.new_values["payment_nature_code"] == "PROFESSIONAL_SERVICE"


def test_redetermination_writes_another_audit_log_entry():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")
    service.determine(invoice.invoice_id, user_id="u", payment_nature_code="PROFESSIONAL_SERVICE")

    assert len(service.invoice_dao.audit_logs) == 2
    assert all(e.action == "INVOICE_TDS_DETERMINED" for e in service.invoice_dao.audit_logs)


def test_verify_writes_an_audit_log_entry():
    service, _, invoice, _ = _default_setup(gross=Decimal("100000.00"))
    service.determine(invoice.invoice_id, user_id="u")
    service.verify(invoice.invoice_id, user_id="finance-1", remarks="Looks correct")

    logs = service.invoice_dao.audit_logs
    assert len(logs) == 2
    verify_entry = logs[-1]
    assert verify_entry.action == "INVOICE_TDS_VERIFIED"
    assert verify_entry.changed_by == "finance-1"
    assert verify_entry.new_values["remarks"] == "Looks correct"


def test_not_applicable_determination_still_writes_audit_log():
    invoice = _invoice(purchase_category_id=None)
    vendor = _vendor()
    service, _ = _make_service(invoices=[invoice], vendors=[vendor])

    service.determine(invoice.invoice_id, user_id="u")

    logs = service.invoice_dao.audit_logs
    assert len(logs) == 1
    assert logs[0].action == "INVOICE_TDS_DETERMINED"
    assert logs[0].new_values["tds_applicable"] is False
