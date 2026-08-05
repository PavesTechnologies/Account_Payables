# Backend/Business_Layer/utils/vendor_matcher.py
"""Vendor matching — placeholder implementation.

No vendor database integration exists yet. This module mocks the
lookup against a small fixed directory so the rest of the pipeline
(and the /match-vendor endpoint) can be built and tested end to end.
Once vendor persistence is wired up, replace ``_MOCK_VENDORS_BY_GSTIN``
/ ``_MOCK_VENDORS_BY_NAME`` with a query through
Backend.Business_Layer.services.vendor_service, keeping this module's
``match_vendor()`` signature unchanged.
"""
from __future__ import annotations

from typing import Dict

from Backend.API_Layer.interface.intake_process_interface import ExtractedInvoice, VendorMatch

GSTIN_MATCH_CONFIDENCE = 98.0
NAME_MATCH_CONFIDENCE = 85.0

# Placeholder vendor directory — stands in for the real vendor master lookup.
_MOCK_VENDORS_BY_GSTIN: Dict[str, int] = {
    "27ABCDE1234F1Z5": 1,
}
_MOCK_VENDORS_BY_NAME: Dict[str, int] = {
    "abc enterprises": 1,
}


def match_vendor(extracted: ExtractedInvoice) -> VendorMatch:
    """Match an ExtractedInvoice against the (currently mocked) vendor master.

    Tries GSTIN first (unique and authoritative when present), then
    falls back to a normalized vendor-name lookup.
    """
    if extracted.gstin:
        vendor_id = _MOCK_VENDORS_BY_GSTIN.get(extracted.gstin.strip().upper())
        if vendor_id is not None:
            return VendorMatch(matched=True, vendor_id=vendor_id, confidence=GSTIN_MATCH_CONFIDENCE)

    if extracted.vendor_name:
        vendor_id = _MOCK_VENDORS_BY_NAME.get(extracted.vendor_name.strip().lower())
        if vendor_id is not None:
            return VendorMatch(matched=True, vendor_id=vendor_id, confidence=NAME_MATCH_CONFIDENCE)

    return VendorMatch(matched=False, vendor_id=None, confidence=0.0)
