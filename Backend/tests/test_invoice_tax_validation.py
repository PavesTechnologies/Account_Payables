# Backend/tests/test_invoice_tax_validation.py
"""Unit tests for InvoiceExtractionService's DB-driven tax validation.

The DAO is faked with data shaped exactly like the real seeded rows in
ap.tax_rule / ap.tax_rule_condition / ap.tax_rate_rule (SAC 997331/998315
-> 18% GST_RATE rule; SAME_STATE -> CGST 9% + SGST 9%; DIFFERENT_STATE ->
IGST 18%) — see Database/migrations/2026-08-13_gst_split_tax_types_seed.sql
and the live ap.tax_rule/ap.tax_rule_condition/ap.tax_rate_rule rows this
was verified against. No real DB connection is used in these tests.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

from Backend.Business_Layer.services.invoice_extraction_service import (
    InvoiceExtractionService,
)
from Backend.API_Layer.interface.invoice_extraction_interface import (
    ExtractedInvoiceResponse,
    ExtractionMetadata,
    InvoiceAmounts,
    InvoiceBuyer,
    InvoiceCompliance,
    InvoiceDocument,
    InvoiceLine,
    InvoicePayment,
    InvoiceReference,
    InvoiceTax,
    InvoiceValidation,
    InvoiceVendor,
)


# ---------------------------------------------------------------------------
# Fake DAO - mirrors the real seeded tax_rule/tax_rule_condition/
# tax_rate_rule shape without touching a database.
# ---------------------------------------------------------------------------


class FakeTaxDAO:

    def __init__(
        self,
        sac_rates: Optional[Dict[str, Decimal]] = None,
    ):
        # SAC -> combined GST rate, mirrors ap.tax_rule rows with
        # rule_category="GST_RATE".
        self.sac_rates = sac_rates or {
            "997331": Decimal("18.0000"),
            "998315": Decimal("18.0000"),
        }

    def get_country_id_by_code(self, country_code: str) -> Optional[int]:
        return 1

    def get_gst_rate_rule_for_sac(
        self,
        sac: str,
        country_id: int,
        as_of_date,
    ) -> Optional[Dict[str, Any]]:

        rate = self.sac_rates.get(sac)

        if rate is None:
            return None

        return {
            "tax_rule_id": 1,
            "rule_code": f"GST_SAC_{sac}",
            "rate_percent": rate,
        }

    def get_tax_component_rules(
        self,
        country_id: int,
        same_state: bool,
        as_of_date,
    ) -> List[Dict[str, Any]]:

        if same_state:
            return [
                {
                    "tax_rule_id": 3,
                    "rule_code": "CGST_9_SAME_STATE",
                    "tax_code": "CGST",
                    "rate_percent": Decimal("9.0000"),
                },
                {
                    "tax_rule_id": 4,
                    "rule_code": "SGST_9_SAME_STATE",
                    "tax_code": "SGST",
                    "rate_percent": Decimal("9.0000"),
                },
            ]

        return [
            {
                "tax_rule_id": 5,
                "rule_code": "IGST_18_DIFFERENT_STATE",
                "tax_code": "IGST",
                "rate_percent": Decimal("18.0000"),
            },
        ]

    # Only needed by the end-to-end validate_invoice() test below.
    def get_vendor_details_by_gstin(self, gstin, name):
        return {"vendor_id": 1, "vendor_name": name, "status_name": "ACTIVE"}

    def create_inbound_document(self, request):
        return None


def make_service(fake_dao: Optional[FakeTaxDAO] = None) -> InvoiceExtractionService:
    service = InvoiceExtractionService(db=None)
    service.invoice_extraction_dao = fake_dao or FakeTaxDAO()
    return service


# ---------------------------------------------------------------------------
# Extracted-invoice builders
# ---------------------------------------------------------------------------


def make_line(**overrides) -> InvoiceLine:
    base = dict(
        line_number=1,
        hsn_sac="997331",
        taxable_amount=10000.0,
    )
    base.update(overrides)
    return InvoiceLine(**base)


def make_extracted(
    lines: List[InvoiceLine],
    vendor_state_code: Optional[str] = "27",
    buyer_state_code: Optional[str] = "27",
    tax_type: Optional[str] = "INTRA_STATE_CGST_SGST",
    amounts: Optional[Dict[str, Any]] = None,
) -> ExtractedInvoiceResponse:

    amounts = amounts or {}

    return ExtractedInvoiceResponse(
        document=InvoiceDocument(
            invoice_number="INV-1",
            invoice_date="2026-08-01",
        ),
        vendor=InvoiceVendor(
            name="Acme Traders",
            gstin=f"{vendor_state_code}AABCU9603R1ZM" if vendor_state_code else None,
            state_code=vendor_state_code,
        ),
        buyer=InvoiceBuyer(
            name="Beta Buyers",
            gstin=f"{buyer_state_code}AAAAA0000A1Z5" if buyer_state_code else None,
            state_code=buyer_state_code,
        ),
        reference=InvoiceReference(),
        amounts=InvoiceAmounts(**amounts),
        payment=InvoicePayment(),
        tax=InvoiceTax(tax_type=tax_type),
        compliance=InvoiceCompliance(),
        invoice_lines=lines,
        extraction=ExtractionMetadata(status="SUCCESS"),
        validation=InvoiceValidation(status="READY_FOR_VALIDATION", is_valid=True),
    )


# ---------------------------------------------------------------------------
# TEST 1: same-state invoice - PASS
# ---------------------------------------------------------------------------


def test_same_state_invoice_passes():
    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=900.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            "total_tax": 1800.0,
            "grand_total": 11800.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is True
    assert result["issues"] == []


# ---------------------------------------------------------------------------
# TEST 2: inter-state invoice - PASS
# ---------------------------------------------------------------------------


def test_inter_state_invoice_passes():
    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        igst_rate=18.0,
        igst_amount=1800.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="36",
        tax_type="INTER_STATE_IGST",
        amounts={
            "taxable_amount": 10000.0,
            "igst_amount": 1800.0,
            "total_tax": 1800.0,
            "grand_total": 11800.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is True
    assert result["issues"] == []


# ---------------------------------------------------------------------------
# TEST 3: wrong tax type (same-state invoice but IGST used) - FAIL
# ---------------------------------------------------------------------------


def test_wrong_tax_type_fails():
    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        igst_rate=18.0,
        igst_amount=1800.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTER_STATE_IGST",
        amounts={
            "taxable_amount": 10000.0,
            "igst_amount": 1800.0,
            "total_tax": 1800.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is False
    assert any("Tax type mismatch" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# TEST 4: wrong rate - FAIL
# ---------------------------------------------------------------------------


def test_wrong_rate_fails():
    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=5.0,
        cgst_amount=500.0,
        sgst_rate=5.0,
        sgst_amount=500.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 500.0,
            "sgst_amount": 500.0,
            "total_tax": 1000.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is False
    assert any(
        "CGST rate mismatch" in issue and "Expected 9" in issue
        for issue in result["issues"]
    )
    assert any(
        "SGST rate mismatch" in issue and "Expected 9" in issue
        for issue in result["issues"]
    )


# ---------------------------------------------------------------------------
# TEST 5: wrong tax amount - FAIL
# ---------------------------------------------------------------------------


def test_wrong_amount_fails():
    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=500.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 500.0,
            "sgst_amount": 900.0,
            "total_tax": 1400.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is False
    assert any(
        "CGST amount mismatch" in issue and "Expected 900.00" in issue
        for issue in result["issues"]
    )


# ---------------------------------------------------------------------------
# TEST 6: wrong total tax - FAIL
# ---------------------------------------------------------------------------


def test_wrong_total_tax_fails():
    service = make_service()

    line1 = make_line(
        line_number=1,
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=900.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line1],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            # Header total_tax deliberately wrong: line taxes sum to
            # 1800 but the header claims 2000.
            "total_tax": 2000.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is False
    assert any("Total tax amount mismatch" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# TEST 7 (revised): an unresolvable SAC/HSN no longer blocks validation
# by itself - CGST/SGST/IGST component rates are supply-location-based,
# not SAC-based, in this schema. An unknown SAC whose line rates already
# match the location-derived expected rates must PASS; a mismatch must
# still be caught regardless of the SAC.
# ---------------------------------------------------------------------------


def test_unknown_sac_with_correct_rates_still_passes():
    service = make_service()

    line = make_line(
        hsn_sac="000000",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=900.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            "total_tax": 1800.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is True
    assert result["issues"] == []


def test_unknown_sac_with_wrong_rate_still_fails():
    service = make_service()

    line = make_line(
        hsn_sac="000000",
        taxable_amount=10000.0,
        cgst_rate=5.0,
        cgst_amount=500.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 500.0,
            "sgst_amount": 900.0,
            "total_tax": 1400.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is False
    assert any("CGST rate mismatch" in issue for issue in result["issues"])


def test_no_supply_location_anywhere_still_requires_manual_review(monkeypatch):
    """The one case that genuinely still blocks: no vendor/buyer state
    code from GSTIN AND no BUYER_CODE env fallback configured either -
    there's truly no supply location to derive anything from."""

    import Backend.Business_Layer.services.invoice_extraction_service as svc_module

    monkeypatch.setattr(svc_module, "BUYER_STATE_CODE", "")
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")

    service = make_service()

    line = make_line(hsn_sac=None, taxable_amount=10000.0)

    extracted = make_extracted(
        lines=[line],
        vendor_state_code=None,
        buyer_state_code=None,
        tax_type=None,
    )
    extracted.vendor.gstin = None
    extracted.buyer.gstin = None

    validation_result = service.validate_invoice(extracted, file_path="s3/key.pdf")

    assert validation_result.is_valid is False
    assert validation_result.requires_manual_review is True
    assert any(
        "Cannot determine supply location" in issue
        for issue in validation_result.issues
    )


# ---------------------------------------------------------------------------
# Buyer state falls back to the BUYER_CODE env var when the buyer's own
# GSTIN wasn't extracted (buyer is always our own company - unlike the
# vendor, its state doesn't vary per invoice).
# ---------------------------------------------------------------------------


def test_buyer_state_code_env_fallback(monkeypatch):

    import Backend.Business_Layer.services.invoice_extraction_service as svc_module

    monkeypatch.setattr(svc_module, "BUYER_STATE_CODE", "36")

    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        igst_rate=18.0,
        igst_amount=1800.0,
    )

    # Vendor in Delhi (07), buyer GSTIN not extracted at all - only the
    # BUYER_CODE env fallback (Telangana, 36) makes supply location
    # resolvable.
    extracted = make_extracted(
        lines=[line],
        vendor_state_code="07",
        buyer_state_code=None,
        tax_type="INTER_STATE_IGST",
        amounts={
            "taxable_amount": 10000.0,
            "igst_amount": 1800.0,
            "total_tax": 1800.0,
        },
    )
    extracted.buyer.gstin = None

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is True
    assert result["issues"] == []


# ---------------------------------------------------------------------------
# Header-only tax data (no invoice line carries any rate/amount at all -
# e.g. AWS-style cloud billing invoices that state tax once at the
# header). Must fall back to a single invoice-level check instead of
# emitting "HSN/SAC is missing" per line or skipping validation entirely.
# ---------------------------------------------------------------------------


def test_header_only_tax_data_validates_at_invoice_level():
    service = make_service()

    # 9 lines, none carrying any tax rate/amount - mirrors a real
    # AWS cloud-services invoice.
    lines = [
        make_line(
            line_number=i,
            hsn_sac=None,
            taxable_amount=None,
            cgst_rate=None,
            cgst_amount=None,
            sgst_rate=None,
            sgst_amount=None,
            igst_rate=None,
            igst_amount=None,
        )
        for i in range(1, 10)
    ]

    extracted = make_extracted(
        lines=lines,
        vendor_state_code="07",
        buyer_state_code="36",
        tax_type="INTER_STATE_IGST",
        amounts={
            "taxable_amount": 3055.72,
            "igst_amount": 550.03,
            "total_tax": 550.03,
        },
    )
    extracted.tax.igst_rate = 18.0

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is True
    assert not any("HSN/SAC is missing" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# TEST 8: multiple invoice lines validated independently, then aggregated
# ---------------------------------------------------------------------------


def test_multiple_lines_validated_independently_and_aggregated():
    service = make_service()

    line1 = make_line(
        line_number=1,
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=900.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    # Line 2 has a wrong rate - line 1 must still be judged correct.
    line2 = make_line(
        line_number=2,
        hsn_sac="998315",
        taxable_amount=20000.0,
        cgst_rate=5.0,
        cgst_amount=1000.0,
        sgst_rate=5.0,
        sgst_amount=1000.0,
    )

    extracted = make_extracted(
        lines=[line1, line2],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 30000.0,
            "cgst_amount": 1900.0,
            "sgst_amount": 1900.0,
            "total_tax": 3800.0,
        },
    )

    result = service.validate_tax(extracted, vendor_details=None)

    assert result["is_valid"] is False
    issues = result["issues"]

    # Line 1 (correct) must not be flagged.
    assert not any("Line 1:" in issue for issue in issues)

    # Line 2 (wrong rate) must be flagged, independently of line 1.
    assert any(
        "Line 2" in issue and "CGST rate mismatch" in issue
        for issue in issues
    )
    assert any(
        "Line 2" in issue and "SGST rate mismatch" in issue
        for issue in issues
    )


# ---------------------------------------------------------------------------
# End-to-end: ValidationResult.success carries one ValidationSummary per
# passing check, alongside the existing issues/is_valid contract.
# ---------------------------------------------------------------------------


def test_validate_invoice_returns_success_summaries(monkeypatch):

    import Backend.Business_Layer.services.invoice_extraction_service as svc_module

    monkeypatch.setattr(
        svc_module, "get_env_var", lambda *a, **k: "Beta Buyers"
    )

    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=900.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            "total_tax": 1800.0,
            "grand_total": 11800.0,
        },
    )

    result = service.validate_invoice(extracted, file_path="s3/key.pdf")

    assert result.is_valid is True
    assert result.requires_manual_review is False

    validation_types = {entry.validation_type for entry in result.success}
    assert validation_types == {"EXTRACTION", "VENDOR", "BUYER", "TAX"}

    tax_summary = next(
        entry.source for entry in result.success
        if entry.validation_type == "TAX"
    )
    assert "CGST 9%" in tax_summary
    assert "SGST 9%" in tax_summary
    assert "INTRA_STATE_CGST_SGST" in tax_summary
    assert "line-level" in tax_summary

    vendor_summary = next(
        entry.source for entry in result.success
        if entry.validation_type == "VENDOR"
    )
    assert "vendor_id=" in vendor_summary


def test_validate_invoice_partial_failure_still_reports_passing_checks(monkeypatch):
    """Vendor/buyer pass but tax fails - success must still list the
    checks that passed, while issues carries only the tax failure."""

    import Backend.Business_Layer.services.invoice_extraction_service as svc_module

    monkeypatch.setattr(
        svc_module, "get_env_var", lambda *a, **k: "Beta Buyers"
    )

    service = make_service()

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=5.0,
        cgst_amount=500.0,
        sgst_rate=5.0,
        sgst_amount=500.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 500.0,
            "sgst_amount": 500.0,
            "total_tax": 1000.0,
        },
    )

    result = service.validate_invoice(extracted, file_path="s3/key.pdf")

    assert result.is_valid is False
    assert result.requires_manual_review is True

    validation_types = {entry.validation_type for entry in result.success}
    assert validation_types == {"EXTRACTION", "VENDOR", "BUYER"}
    assert any("CGST rate mismatch" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# A failing check stops the pipeline entirely - a later check (tax) must
# not even run (no DB calls), not just be excluded from success.
# ---------------------------------------------------------------------------


def test_buyer_failure_stops_pipeline_before_tax_runs(monkeypatch):

    import Backend.Business_Layer.services.invoice_extraction_service as svc_module

    # Buyer name won't match this, so validate_buyer fails.
    monkeypatch.setattr(
        svc_module, "get_env_var", lambda *a, **k: "Some Other Company"
    )

    fake_dao = FakeTaxDAO()
    fake_dao.gst_rate_calls = 0
    fake_dao.component_calls = 0

    original_get_gst_rate_rule = fake_dao.get_gst_rate_rule_for_sac
    original_get_components = fake_dao.get_tax_component_rules

    def counting_get_gst_rate_rule(*args, **kwargs):
        fake_dao.gst_rate_calls += 1
        return original_get_gst_rate_rule(*args, **kwargs)

    def counting_get_components(*args, **kwargs):
        fake_dao.component_calls += 1
        return original_get_components(*args, **kwargs)

    fake_dao.get_gst_rate_rule_for_sac = counting_get_gst_rate_rule
    fake_dao.get_tax_component_rules = counting_get_components

    service = make_service(fake_dao)

    line = make_line(
        hsn_sac="997331",
        taxable_amount=10000.0,
        cgst_rate=9.0,
        cgst_amount=900.0,
        sgst_rate=9.0,
        sgst_amount=900.0,
    )

    extracted = make_extracted(
        lines=[line],
        vendor_state_code="27",
        buyer_state_code="27",
        tax_type="INTRA_STATE_CGST_SGST",
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            "total_tax": 1800.0,
        },
    )

    result = service.validate_invoice(extracted, file_path="s3/key.pdf")

    assert result.is_valid is False
    assert result.requires_manual_review is True
    assert result.issues == ["Buyer name does not match expected buyer"]

    validation_types = {entry.validation_type for entry in result.success}
    assert validation_types == {"EXTRACTION", "VENDOR"}

    # Tax validation must never have been reached - no DB calls at all.
    assert fake_dao.gst_rate_calls == 0
    assert fake_dao.component_calls == 0
