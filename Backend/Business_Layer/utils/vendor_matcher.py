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
from sqlalchemy.orm import Session

from Backend.API_Layer.interface.invoice_process_interface import ExtractedInvoice, VendorMatch
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO

GSTIN_MATCH_CONFIDENCE = 100.0

def match_vendor(
    extracted: ExtractedInvoice,
    db: Session,
) -> VendorMatch:
    vendor_dao = VendorDAO(db)

    if extracted.gstin:
        vendor_details = vendor_dao.get_vendor_by_gstin(
            extracted.gstin
        )

        if vendor_details:
            return VendorMatch(
                matched=True,
                vendor_id=vendor_details.vendor_id,
                confidence=GSTIN_MATCH_CONFIDENCE,
            )

    return VendorMatch(
        matched=False,
        vendor_id=None,
        confidence=0.0,
    )
