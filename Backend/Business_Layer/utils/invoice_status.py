# Backend/Business_Layer/utils/invoice_status.py
"""Invoice status/threshold constants and status-resolution helpers.

Nothing here talks to the database — status *codes* are resolved to
status_master rows by the DAO layer (see InvoiceDAO.get_status_by_code).
Keeping the codes, thresholds, and issue-type strings as named
constants here means invoice_process_service.py never hardcodes a
magic confidence number or a bare status string.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from Backend.API_Layer.interface.invoice_process_interface import ExtractedInvoice
from Backend.Data_Access_Layer.models.invoice import InvoiceIssue

INVOICE_STATUS_MODULE = "INVOICE"

STATUS_CODE_OCR_FAILED = "OCR_FAILED"
STATUS_CODE_OCR_REVIEW_PENDING = "OCR_REVIEW_PENDING"
STATUS_CODE_PENDING_APPROVAL = "PENDING_APPROVAL"

# Response-only marker for a document whose vendor could not be matched —
# no Invoice row exists yet, so this is never a status_master row/status_id,
# only a value surfaced in FinalResponse.invoice_status for the caller.
RESPONSE_STATUS_PENDING_VENDOR_ONBOARDING = "PENDING_VENDOR_ONBOARDING"

# ConfidenceResult is on a 0-100 scale (Backend.Business_Layer.utils.confidence).
LOW_CONFIDENCE_THRESHOLD = 80.0

# Tolerance for header-vs-line-item and subtotal-vs-total arithmetic checks.
LINE_TOTAL_MISMATCH_TOLERANCE = Decimal("1.00")

# Fallback currency when none could be extracted/mapped, so currency_id
# (NOT NULL on invoice) can still be resolved without blocking persistence.
DEFAULT_CURRENCY_CODE = "INR"

# InvoiceIssue.issue_source values (no DB check constraint; kept consistent).
ISSUE_SOURCE_VALIDATION = "VALIDATION"
ISSUE_SOURCE_VENDOR_MATCH = "VENDOR_MATCH"
ISSUE_SOURCE_EXTRACTION = "EXTRACTION"

# InvoiceIssue.issue_type values. VENDOR_NOT_FOUND/TAX_MISMATCH/GSTIN_MISMATCH/
# LOW_OCR_CONFIDENCE/FORMAT/DUPLICATE mirror the values already referenced in
# the invoice_issue table's column comment; the rest are new but the column
# has no CHECK constraint, so adding them is safe.
ISSUE_TYPE_LOW_CONFIDENCE = "LOW_OCR_CONFIDENCE"
ISSUE_TYPE_VALIDATION_FAILED = "VALIDATION_FAILED"
ISSUE_TYPE_TOTAL_MISMATCH = "TAX_MISMATCH"
ISSUE_TYPE_LINE_TOTAL_MISMATCH = "LINE_TOTAL_MISMATCH"
ISSUE_TYPE_VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
ISSUE_TYPE_CURRENCY_UNMAPPED = "CURRENCY_UNMAPPED"
ISSUE_TYPE_LINE_ITEMS_INCOMPLETE = "LINE_ITEMS_INCOMPLETE"

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"


def is_extraction_unusable(extracted: ExtractedInvoice) -> Optional[str]:
    """Return a human-readable reason the extraction cannot back an Invoice row, or None.

    Reserved for cases where the pipeline produced no exception but the
    result still can't populate the NOT NULL invoice header columns —
    this, not low confidence or a validation warning, is what OCR_FAILED
    means (see business rules in the /process-invoice spec).
    """
    if not extracted.invoice_number:
        return "invoice_number could not be extracted"
    if not extracted.invoice_date:
        return "invoice_date could not be extracted"
    if extracted.total is None and extracted.subtotal is None:
        return "no usable amount (subtotal/total) could be extracted"
    return None


def resolve_processing_status_code(extraction_failed: bool) -> str:
    """Section 23: processing failed -> OCR_FAILED, else OCR_REVIEW_PENDING.

    PENDING_APPROVAL is never returned here — it only happens from the
    manual OCR-review endpoint after an AP Executive confirms the invoice.
    """
    return STATUS_CODE_OCR_FAILED if extraction_failed else STATUS_CODE_OCR_REVIEW_PENDING


def build_issue(
    issue_source: str, issue_type: str, severity: str, description: str
) -> InvoiceIssue:
    """Construct an InvoiceIssue row (invoice_id is set by the caller before insert)."""
    return InvoiceIssue(
        issue_source=issue_source,
        issue_type=issue_type,
        severity=severity,
        description=description[:255],
    )
