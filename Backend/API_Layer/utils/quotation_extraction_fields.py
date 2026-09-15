"""Textract-backed field extraction for the /quotations/extract endpoint.

Uses the shared invoice Textract infrastructure:
    - textract_client
    - call_textract_with_retry
    - run_document_analysis_queries

Quotation extraction is query-driven with deterministic full-text fallbacks
for fields that are commonly confused by generic Textract queries.

Important:
    PR/reference numbers must NEVER be accepted as quotation numbers.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import BotoCoreError, ClientError

from Backend.API_Layer.utils.invoice_extraction_fields import (
    clean_text,
    normalize_date,
    normalize_number,
    run_document_analysis_queries,
)
from Backend.Business_Layer.utils.exceptions import TextractServiceError


# ============================================================
# Textract queries
# ============================================================

QUOTATION_QUERIES = [
    (
        "What is the vendor, supplier, seller, or company name issuing this quotation?",
        "VENDOR_NAME",
    ),
    (
        "What is the quotation number or quote number shown on the quotation?",
        "QUOTATION_NUMBER",
    ),
    (
        "What is the grand total, total amount, final amount, or amount payable on the quotation?",
        "TOTAL_AMOUNT",
    ),
    (
        "What is the quotation date, quote date, or date of quotation?",
        "QUOTATION_DATE",
    ),
    (
        "What is the valid until date, validity date, valid through date, or offer validity date?",
        "VALID_UNTIL",
    ),
    (
        "What is the delivery time, delivery period, delivery days, or lead time?",
        "DELIVERY_DAYS",
    ),
    (
        "What are the payment terms or terms of payment?",
        "PAYMENT_TERMS",
    ),
]

TEXTRACT_SYNC_QUERY_LIMIT = 15

assert len(QUOTATION_QUERIES) <= TEXTRACT_SYNC_QUERY_LIMIT, (
    "QUOTATION_QUERIES exceeds the Textract per-page query limit."
)


# ============================================================
# Full-text fallback patterns
# ============================================================

# IMPORTANT:
# Do not use generic "Reference Number" here.
# A quotation document can contain:
#   PR Reference: PR-2026-0001
#   Quote Number: AWS-QT-2026-0908
#
# The PR reference must never become quotation_number.

QUOTATION_NUMBER_PATTERNS = [
    re.compile(
        r"\b(?:quotation\s*(?:no\.?|number|#)|quote\s*(?:no\.?|number|#))"
        r"\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\/._-]*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:quotation\s*id|quote\s*id)\s*[:\-]?\s*"
        r"([A-Za-z0-9][A-Za-z0-9\/._-]*)",
        re.IGNORECASE,
    ),
]

# Explicitly identify PR/reference fields so they cannot be mistaken
# for quotation numbers.
PR_REFERENCE_PATTERN = re.compile(
    r"\b(?:pr\s*(?:reference|ref|number|no\.?|#)|"
    r"purchase\s+requisition(?:\s+(?:reference|ref|number|no\.?|#))?)"
    r"\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\/._-]*)",
    re.IGNORECASE,
)


TOTAL_AMOUNT_PATTERNS = [
    re.compile(
        r"\bgrand\s*total\b\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btotal\s+amount\b\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfinal\s+amount\b\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bamount\s+payable\b\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnet\s+total\b\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
]


VALID_UNTIL_PATTERNS = [
    re.compile(
        r"\bvalid\s*(?:until|till|through)\b\s*[:\-]?\s*"
        r"([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bvalid\s*(?:until|till|through)\b\s*[:\-]?\s*"
        r"([0-9]{1,2}[-\s][A-Za-z]{3,9}[-\s][0-9]{4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bvalidity\b\s*[:\-]?\s*"
        r"([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})",
        re.IGNORECASE,
    ),
]


DELIVERY_DAYS_LABEL_PATTERN = re.compile(
    r"\b(?:delivery|lead\s*time)\s*"
    r"(?:days?|time|period)?\s*[:\-]?\s*"
    r"(\d+)\s*(?:working\s*)?days?\b",
    re.IGNORECASE,
)

DELIVERY_DAYS_NUMBER_PATTERN = re.compile(r"\d+")


# ============================================================
# Normalization
# ============================================================

def normalize_quotation_number(value: Optional[Any]) -> Optional[str]:
    """Trim whitespace without modifying meaningful quotation characters."""
    value = clean_text(value)

    if not value:
        return None

    if is_pr_reference(value):
        return None

    return value


def normalize_payment_terms(value: Optional[Any]) -> Optional[str]:
    return clean_text(value)


def normalize_delivery_days(value: Optional[Any]) -> Optional[int]:
    """
    "15 Days" / "Within 15 days" / "15" -> 15.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    match = DELIVERY_DAYS_NUMBER_PATTERN.search(str(value))

    return int(match.group(0)) if match else None


def normalize_total_amount(value: Optional[Any]) -> Optional[float]:
    """
    Normalize currency symbols and thousands separators.
    """
    return normalize_number(value)


def normalize_quotation_date(value: Optional[Any]):
    """
    Normalize quotation dates to the standard ISO date representation.
    """
    return normalize_date(value)


# ============================================================
# Helpers
# ============================================================

def is_pr_reference(value: Optional[Any]) -> bool:
    """
    Returns True when a value looks like a purchase-requisition reference.

    Examples:
        PR-2026-0001
        PR/2026/0001
        PR 2026 0001
    """
    if value is None:
        return False

    normalized = str(value).strip().upper()

    return bool(
        re.match(
            r"^PR(?:[-_/ ]|$)",
            normalized,
        )
    )


def _query_value(
    query_results: Dict[str, Dict[str, Any]],
    alias: str,
) -> Tuple[Optional[str], float]:
    query = query_results.get(alias)

    if not query:
        return None, 0.0

    value = clean_text(query.get("value"))
    confidence = query.get("confidence", 0.0)

    return value, confidence


def _extract_first_match(
    patterns,
    text: str,
) -> Optional[str]:
    for pattern in patterns:
        match = pattern.search(text)

        if match:
            value = clean_text(match.group(1))

            if value:
                return value

    return None


def _extract_quotation_number_from_text(
    full_text: str,
) -> Optional[str]:
    """
    Extract quotation number from an explicit quotation/quote label.

    Generic reference numbers are deliberately NOT supported because
    documents commonly contain PR Reference / PO Reference fields.
    """

    if not full_text:
        return None

    value = _extract_first_match(
        QUOTATION_NUMBER_PATTERNS,
        full_text,
    )

    if not value:
        return None

    if is_pr_reference(value):
        return None

    return value


def _extract_total_amount_from_text(
    full_text: str,
) -> Optional[float]:
    """
    Prefer Grand Total over every other total.
    """

    if not full_text:
        return None

    value = _extract_first_match(
        TOTAL_AMOUNT_PATTERNS,
        full_text,
    )

    if value is None:
        return None

    return normalize_total_amount(value)


def _extract_valid_until_from_text(
    full_text: str,
):
    """
    Extract the date attached to:
        Valid Until
        Valid Till
        Valid Through
        Validity
    """

    if not full_text:
        return None

    raw_value = _extract_first_match(
        VALID_UNTIL_PATTERNS,
        full_text,
    )

    if not raw_value:
        return None

    return normalize_quotation_date(raw_value)


def _extract_delivery_days_from_text(
    full_text: str,
) -> Optional[int]:
    if not full_text:
        return None

    match = DELIVERY_DAYS_LABEL_PATTERN.search(full_text)

    if not match:
        return None

    return normalize_delivery_days(match.group(1))


# ============================================================
# Field extraction
# ============================================================

def parse_quotation_fields(
    query_results: Dict[str, Dict[str, Any]],
    full_text: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Maps Textract query answers to quotation fields.

    Query extraction is preferred.

    Deterministic full-text fallback is used when a query:
        - returns nothing
        - returns an invalid value
        - returns a PR reference instead of quotation number
    """

    extracted: Dict[str, Any] = {}
    confidence: Dict[str, float] = {}

    def _set(
        field: str,
        value: Any,
        field_confidence: float,
    ) -> None:
        if value is None or value == "":
            return

        extracted[field] = value
        confidence[field] = field_confidence

    # --------------------------------------------------------
    # Vendor
    # --------------------------------------------------------

    vendor_name, vendor_confidence = _query_value(
        query_results,
        "VENDOR_NAME",
    )

    _set(
        "vendor_name",
        vendor_name,
        vendor_confidence,
    )

    # --------------------------------------------------------
    # Quotation Number
    # --------------------------------------------------------

    raw_quotation_number, quotation_number_confidence = _query_value(
        query_results,
        "QUOTATION_NUMBER",
    )

    # Textract sometimes returns the PR reference because the old
    # query included "reference number".
    if is_pr_reference(raw_quotation_number):
        raw_quotation_number = None
        quotation_number_confidence = 0.0

    if not raw_quotation_number and full_text:
        raw_quotation_number = _extract_quotation_number_from_text(
            full_text
        )

        if raw_quotation_number:
            quotation_number_confidence = 90.0

    _set(
        "quotation_number",
        normalize_quotation_number(raw_quotation_number),
        quotation_number_confidence,
    )

    # --------------------------------------------------------
    # Total Amount
    # --------------------------------------------------------

    raw_total_amount, total_amount_confidence = _query_value(
        query_results,
        "TOTAL_AMOUNT",
    )

    normalized_total_amount = normalize_total_amount(
        raw_total_amount
    )

    if normalized_total_amount is None and full_text:
        normalized_total_amount = _extract_total_amount_from_text(
            full_text
        )

        if normalized_total_amount is not None:
            total_amount_confidence = 90.0

    _set(
        "total_amount",
        normalized_total_amount,
        total_amount_confidence,
    )

    # --------------------------------------------------------
    # Quotation Date
    # --------------------------------------------------------

    raw_quotation_date, quotation_date_confidence = _query_value(
        query_results,
        "QUOTATION_DATE",
    )

    _set(
        "quotation_date",
        normalize_quotation_date(raw_quotation_date),
        quotation_date_confidence,
    )

    # --------------------------------------------------------
    # Valid Until
    # --------------------------------------------------------

    raw_valid_until, valid_until_confidence = _query_value(
        query_results,
        "VALID_UNTIL",
    )

    normalized_valid_until = normalize_quotation_date(
        raw_valid_until
    )

    if normalized_valid_until is None and full_text:
        normalized_valid_until = _extract_valid_until_from_text(
            full_text
        )

        if normalized_valid_until is not None:
            valid_until_confidence = 90.0

    _set(
        "valid_until",
        normalized_valid_until,
        valid_until_confidence,
    )

    # --------------------------------------------------------
    # Delivery Days
    # --------------------------------------------------------

    raw_delivery_days, delivery_days_confidence = _query_value(
        query_results,
        "DELIVERY_DAYS",
    )

    normalized_delivery_days = normalize_delivery_days(
        raw_delivery_days
    )

    if normalized_delivery_days is None and full_text:
        normalized_delivery_days = _extract_delivery_days_from_text(
            full_text
        )

        if normalized_delivery_days is not None:
            delivery_days_confidence = 90.0

    _set(
        "delivery_days",
        normalized_delivery_days,
        delivery_days_confidence,
    )

    # --------------------------------------------------------
    # Payment Terms
    # --------------------------------------------------------

    raw_payment_terms, payment_terms_confidence = _query_value(
        query_results,
        "PAYMENT_TERMS",
    )

    _set(
        "payment_terms",
        normalize_payment_terms(raw_payment_terms),
        payment_terms_confidence,
    )

    return extracted, confidence


# ============================================================
# Textract execution
# ============================================================

def run_quotation_queries(
    s3_key: str,
) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """
    Blocking Textract call.
    """

    return run_document_analysis_queries(
        s3_key,
        QUOTATION_QUERIES,
    )


async def extract_quotation_from_s3(
    s3_key: str,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Runs quotation extraction asynchronously.
    """

    try:
        query_results, full_text = await asyncio.to_thread(
            run_quotation_queries,
            s3_key,
        )

    except (ClientError, BotoCoreError) as exc:
        raise TextractServiceError(
            f"AWS Textract error: {exc}"
        ) from exc

    except TimeoutError as exc:
        raise TextractServiceError(
            str(exc)
        ) from exc

    except RuntimeError as exc:
        raise TextractServiceError(
            str(exc)
        ) from exc

    return parse_quotation_fields(
        query_results,
        full_text,
    )