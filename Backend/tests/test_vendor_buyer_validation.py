# Backend/tests/test_vendor_buyer_validation.py
"""Unit tests for InvoiceExtractionService.validate_vendor and
.validate_buyer (Stage 1 - Vendor & Buyer Validation).

Vendor master lookups are faked (no real DB connection). Buyer has no
master DB table - its "expected profile" comes from module-level
BUYER_* constants in invoice_extraction_service, monkeypatched per
test the same way BUYER_STATE_NAME/BUYER_STATE_CODE already are
elsewhere (they're read once at import time, not per call, unlike
BUYER_NAME which is re-read via get_env_var on every validate_buyer
call).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

import Backend.Business_Layer.services.invoice_extraction_service as svc_module
from Backend.API_Layer.interface.invoice_extraction_interface import (
    FieldComparisonStatus,
    InvoiceBuyer,
    InvoiceVendor,
)
from Backend.Business_Layer.services.invoice_extraction_service import (
    InvoiceExtractionService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeVendorDAO:

    def __init__(self, vendor_details: Optional[Dict[str, Any]]):
        self._vendor_details = vendor_details

    def get_vendor_details_by_gstin(self, gstin, name):
        return self._vendor_details


def make_service(vendor_details: Optional[Dict[str, Any]]) -> InvoiceExtractionService:
    service = InvoiceExtractionService(db=None)
    service.invoice_extraction_dao = FakeVendorDAO(vendor_details)
    return service


def make_extracted(vendor=None, buyer=None):
    return SimpleNamespace(
        vendor=vendor or InvoiceVendor(),
        buyer=buyer or InvoiceBuyer(),
    )


def comparisons_by_field(result):
    return {c.field: c for c in result["field_comparisons"]}


MASTER_VENDOR = {
    "vendor_id": 1,
    "vendor_name": "Acme Traders Pvt Ltd",
    "pan_number": "AABCU9603R",
    "status_name": "ACTIVE",
    "state": "Maharashtra",
    "address_line1": "12 MG Road",
    "address_line2": "Andheri East",
    "city": "Mumbai",
    "postal_code": "400069",
    "vendor_address_id": 10,
    "vendor_tax_id": 20,
    "registration_number": "27AABCU9603R1ZM",
}


# ---------------------------------------------------------------------------
# Vendor validation
# ---------------------------------------------------------------------------


def test_vendor_exact_match_is_valid():
    vendor = InvoiceVendor(
        name="Acme Traders Pvt Ltd",
        gstin="27AABCU9603R1ZM",
        pan="AABCU9603R",
        address="12 MG Road Andheri East Mumbai 400069",
        state="Maharashtra",
    )
    service = make_service(MASTER_VENDOR)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert result["is_valid"] is True
    assert result["issues"] == []

    comparisons = comparisons_by_field(result)
    assert comparisons["gstin"].status == FieldComparisonStatus.MATCH
    assert comparisons["pan"].status == FieldComparisonStatus.MATCH
    assert comparisons["address"].status == FieldComparisonStatus.MATCH
    assert comparisons["state"].status == FieldComparisonStatus.MATCH


def test_vendor_gstin_mismatch_is_blocking():
    vendor = InvoiceVendor(name="Acme Traders Pvt Ltd", gstin="27AABCU9603R1ZM")
    master = {**MASTER_VENDOR, "registration_number": "27ZZZZZ0000Z1Z9"}
    service = make_service(master)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert result["is_valid"] is False
    assert any("gstin" in issue for issue in result["issues"])
    assert comparisons_by_field(result)["gstin"].status == FieldComparisonStatus.MISMATCH


def test_vendor_pan_mismatch_is_blocking():
    vendor = InvoiceVendor(name="Acme Traders Pvt Ltd", pan="ZZZZZ0000Z")
    service = make_service(MASTER_VENDOR)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert result["is_valid"] is False
    assert comparisons_by_field(result)["pan"].status == FieldComparisonStatus.MISMATCH


def test_vendor_blocked_status_is_blocking_even_with_matching_fields():
    vendor = InvoiceVendor(name="Acme Traders Pvt Ltd", gstin="27AABCU9603R1ZM")
    master = {**MASTER_VENDOR, "status_name": "BLOCKED"}
    service = make_service(master)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert result["is_valid"] is False
    assert any("BLOCKED" in issue for issue in result["issues"])


def test_vendor_name_only_mismatch_is_non_blocking():
    vendor = InvoiceVendor(
        name="Acme Trading Co",  # differs from master's vendor_name
        gstin="27AABCU9603R1ZM",
        pan="AABCU9603R",
    )
    service = make_service(MASTER_VENDOR)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert result["is_valid"] is True
    assert comparisons_by_field(result)["name"].status == FieldComparisonStatus.MISMATCH
    assert any("name" in issue for issue in result["issues"])


def test_vendor_address_fuzzy_match_within_threshold():
    vendor = InvoiceVendor(
        name="Acme Traders Pvt Ltd",
        gstin="27AABCU9603R1ZM",
        # OCR noise/reordering, but most significant tokens overlap.
        address="12, MG Road, Andheri East, Mumbai - 400069",
    )
    service = make_service(MASTER_VENDOR)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert comparisons_by_field(result)["address"].status == FieldComparisonStatus.MATCH


def test_vendor_address_fuzzy_mismatch_below_threshold():
    vendor = InvoiceVendor(
        name="Acme Traders Pvt Ltd",
        gstin="27AABCU9603R1ZM",
        address="99 Totally Different Street, Bengaluru 560001",
    )
    service = make_service(MASTER_VENDOR)

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert comparisons_by_field(result)["address"].status == FieldComparisonStatus.MISMATCH
    assert result["is_valid"] is True  # address is non-blocking


def test_vendor_missing_gstin_and_name_is_invalid():
    service = make_service(None)

    result = service.validate_vendor(make_extracted(vendor=InvoiceVendor()))

    assert result["is_valid"] is False
    assert result["field_comparisons"] == []


def test_vendor_not_found_in_master_is_invalid():
    service = make_service(None)
    vendor = InvoiceVendor(name="Totally Unknown Vendor", gstin="99ZZZZZ0000Z1Z9")

    result = service.validate_vendor(make_extracted(vendor=vendor))

    assert result["is_valid"] is False
    assert result["issues"] == ["Vendor details not found"]


# ---------------------------------------------------------------------------
# Buyer validation
# ---------------------------------------------------------------------------


def test_buyer_name_match_is_valid(monkeypatch):
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")

    service = InvoiceExtractionService(db=None)
    result = service.validate_buyer(
        make_extracted(buyer=InvoiceBuyer(name="Beta Buyers"))
    )

    assert result["is_valid"] is True
    assert result["issues"] == []


def test_buyer_name_mismatch_is_blocking(monkeypatch):
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")

    service = InvoiceExtractionService(db=None)
    result = service.validate_buyer(
        make_extracted(buyer=InvoiceBuyer(name="Someone Else"))
    )

    assert result["is_valid"] is False
    assert comparisons_by_field(result)["name"].status == FieldComparisonStatus.MISMATCH


def test_buyer_unconfigured_gstin_and_pan_are_never_mismatch(monkeypatch):
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")
    monkeypatch.setattr(svc_module, "BUYER_GSTIN", "")
    monkeypatch.setattr(svc_module, "BUYER_PAN", "")

    service = InvoiceExtractionService(db=None)
    result = service.validate_buyer(
        make_extracted(
            buyer=InvoiceBuyer(
                name="Beta Buyers", gstin="27AAAAA0000A1Z5", pan="AAAAA0000A"
            )
        )
    )

    comparisons = comparisons_by_field(result)
    assert comparisons["gstin"].status != FieldComparisonStatus.MISMATCH
    assert comparisons["pan"].status != FieldComparisonStatus.MISMATCH
    assert result["is_valid"] is True


def test_buyer_configured_gstin_mismatch_is_non_blocking(monkeypatch):
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")
    monkeypatch.setattr(svc_module, "BUYER_GSTIN", "27ZZZZZ0000Z1Z9")

    service = InvoiceExtractionService(db=None)
    result = service.validate_buyer(
        make_extracted(
            buyer=InvoiceBuyer(name="Beta Buyers", gstin="27AAAAA0000A1Z5")
        )
    )

    assert comparisons_by_field(result)["gstin"].status == FieldComparisonStatus.MISMATCH
    assert result["is_valid"] is True  # only name is blocking for buyer


def test_buyer_missing_name_is_invalid(monkeypatch):
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")

    service = InvoiceExtractionService(db=None)
    result = service.validate_buyer(make_extracted(buyer=InvoiceBuyer()))

    assert result["is_valid"] is False
    assert result["issues"] == ["Buyer name not found in invoice"]
