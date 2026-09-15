# Backend/Business_Layer/services/quotation_extraction_service.py
"""Orchestrates document -> structured quotation data for
/quotations/extract. Never creates or updates a Quotation/Vendor
record - persistence remains the job of the existing
ProcurementService.create_quotation, called later by the frontend once
the PR Officer has reviewed/corrected these values."""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from Backend.API_Layer.interface.quotation_extraction_interface import (
    QuotationExtractionData,
)
from Backend.API_Layer.utils.quotation_extraction_fields import (
    extract_quotation_from_s3,
)
from Backend.Business_Layer.utils.exceptions import QuotationExtractionFailure
from Backend.Business_Layer.utils.quotation_vendor_matcher import match_vendor

SUCCESS_MESSAGE = "Quotation details extracted successfully"
PARTIAL_MESSAGE = "Quotation partially extracted"

# Fields the PR Officer would expect the Add Quotation form to
# auto-populate. vendor_id is intentionally excluded from this
# completeness check - vendor matching is a separate concern (a vendor
# genuinely absent from Vendor Master doesn't mean the *document* was
# only partially read).
DOCUMENT_FIELDS = (
    "vendor_name",
    "quotation_number",
    "total_amount",
    "quotation_date",
    "valid_until",
    "delivery_days",
    "payment_terms",
)


class QuotationExtractionService:

    def __init__(self, db: Session):
        self.db = db

    async def extract(self, s3_key: str) -> Dict[str, Any]:

        extracted, field_confidence = await extract_quotation_from_s3(
            s3_key
        )

        if not extracted:
            raise QuotationExtractionFailure(
                "No quotation fields could be extracted from the "
                "document."
            )

        vendor_match = match_vendor(extracted.get("vendor_name"), self.db)

        data = QuotationExtractionData(
            vendor_id=vendor_match.vendor_id,
            vendor_name=vendor_match.vendor_name,
            quotation_number=extracted.get("quotation_number"),
            total_amount=extracted.get("total_amount"),
            quotation_date=extracted.get("quotation_date"),
            valid_until=extracted.get("valid_until"),
            delivery_days=extracted.get("delivery_days"),
            payment_terms=extracted.get("payment_terms"),
            field_confidence=field_confidence or None,
        )

        is_complete = all(
            extracted.get(field) is not None for field in DOCUMENT_FIELDS
        )

        return {
            "message": SUCCESS_MESSAGE if is_complete else PARTIAL_MESSAGE,
            "data": data,
        }
