# Backend/Business_Layer/utils/extraction/normalizers.py
"""Low-level parsing/validation for raw OCR text fragments.

Pure functions with no anchor/geometry knowledge: given a candidate
string, decide whether it looks like a valid GSTIN / date / amount /
code / currency and parse it into the correct Python type. Extractors
call these to turn a raw regex match into a typed value, or discard it
(``ValueError``) when the format is invalid.
"""
from __future__ import annotations

import datetime
import decimal
import re

GSTIN_PATTERN = re.compile(r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9][A-Z][A-Z0-9])", re.IGNORECASE)
_GSTIN_CODE_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

CODE_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9\-/]{0,19}", re.IGNORECASE)

# Common label fragments that can end up immediately after an
# invoice/PO-number anchor on the same OCR line (e.g. "Invoice No 46
# Date: 24-03-2020" — "Date" is a neighbouring field's label, not a
# value) and must never be mistaken for the code itself.
NON_VALUE_WORDS = frozenset({
    "date", "no", "number", "the", "of", "to", "for", "on", "at", "and", "page",
})

AMOUNT_PATTERN = re.compile(r"(?<!\d)\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?(?!\d)|(?<!\d)\d+(?:\.\d{1,2})?(?!\d)")

# A number immediately followed by "%" is a tax *rate*, never a tax
# *amount* ("CGST 9% Rs.225.00" must yield 225.00, not 9) — checked
# right after every AMOUNT_PATTERN match via ``iter_amount_matches``.
_PERCENT_SUFFIX = re.compile(r"\s*%")

DATE_PATTERN = re.compile(
    r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
    r"|\d{1,2}[/.-][A-Za-z]{3,9}[/.-]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}",
    re.IGNORECASE,
)
_DATE_FORMATS = (
    # Numeric Indian formats
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d.%m.%y",

    # Day-MonthName-Year
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d/%b/%Y",
    "%d/%b/%y",
    "%d.%b.%Y",
    "%d.%b.%y",

    "%d %b %Y",
    "%d %b %y",
    "%d %B %Y",
    "%d %B %y",

    # MonthName-Day-Year
    "%b %d, %Y",
    "%b %d, %y",
    "%B %d, %Y",
    "%B %d, %y",

    "%b %d %Y",
    "%b %d %y",
    "%B %d %Y",
    "%B %d %y",

    # ISO
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
)

_CURRENCY_SYMBOLS = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
_CURRENCY_CODES = {"INR", "RS", "RS.", "USD", "EUR", "GBP", "AED", "SGD"}
_CURRENCY_CODE_MAP = {"RS": "INR", "RS.": "INR"}

# 1, not 3: plenty of small businesses number invoices with a bare
# 1-2 digit sequence ("Invoice No 46") — length alone can't rule out
# a short code, so disambiguation relies on anchor proximity instead.
MIN_CODE_LENGTH = 1
MAX_CODE_LENGTH = 30


def is_valid_gstin_format(raw: str) -> bool:
    return bool(GSTIN_PATTERN.fullmatch(raw.strip().upper()))


def gstin_checksum_valid(gstin: str) -> bool:
    """Verify the GSTIN's mod-36 check digit (15th character).

    Best-effort only: OCR mangles single characters often enough that
    a failed checksum should never hard-reject an otherwise
    well-formed, anchor-backed GSTIN — callers use this as a small
    positive signal, not a filter.
    """
    cleaned = gstin.strip().upper()
    if len(cleaned) != 15 or not is_valid_gstin_format(cleaned):
        return False

    factor = 2
    total = 0
    for char in cleaned[:14]:
        if char not in _GSTIN_CODE_CHARS:
            return False
        digit = _GSTIN_CODE_CHARS.index(char)
        addend = factor * digit
        factor = 1 if factor == 2 else 2
        addend = (addend // 36) + (addend % 36)
        total += addend

    checksum_index = (36 - (total % 36)) % 36
    return _GSTIN_CODE_CHARS[checksum_index] == cleaned[14]


def normalize_gstin(raw: str) -> str:
    match = GSTIN_PATTERN.search(raw.strip().upper())
    if not match:
        raise ValueError(f"Not a valid GSTIN: {raw!r}")
    return match.group(1)


def pan_from_gstin(gstin: str) -> str:
    """Extract the embedded PAN (GSTIN positions 3-12) from a valid-format GSTIN."""
    cleaned = gstin.strip().upper()
    if not is_valid_gstin_format(cleaned):
        raise ValueError(f"Cannot extract PAN from an invalid GSTIN: {gstin!r}")
    return cleaned[2:12]


def normalize_date(raw: str) -> datetime.date:
    cleaned = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


def iter_amount_matches(text: str):
    """Every ``AMOUNT_PATTERN`` match in ``text`` that is not a tax rate.

    A rate ("9%") and its amount ("Rs.225.00") often sit on the same
    label's line; both are digit runs, so a plain ``AMOUNT_PATTERN``
    scan would offer the rate as a candidate value too. Skipping any
    match immediately followed by "%" is what keeps CGST/SGST/IGST/
    CESS extraction from ever returning a percentage as the amount.
    """
    for match in AMOUNT_PATTERN.finditer(text):
        if _PERCENT_SUFFIX.match(text, match.end()):
            continue
        yield match


def normalize_amount(raw: str) -> decimal.Decimal:
    cleaned = raw.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    if not cleaned:
        raise ValueError(f"Not a valid amount: {raw!r}")
    try:
        return decimal.Decimal(cleaned)
    except decimal.InvalidOperation as exc:
        raise ValueError(f"Not a valid amount: {raw!r}") from exc


def normalize_code(raw: str, *, min_length: int = MIN_CODE_LENGTH, max_length: int = MAX_CODE_LENGTH) -> str:
    """Normalize a labelled alphanumeric code (invoice/PO number)."""
    cleaned = raw.strip().strip(":-#\t ").upper()
    if not (min_length <= len(cleaned) <= max_length):
        raise ValueError(f"Code length out of bounds: {raw!r}")
    if not re.search(r"[A-Z0-9]", cleaned):
        raise ValueError(f"Code has no alphanumeric content: {raw!r}")
    return cleaned


def normalize_currency(raw: str) -> str:
    cleaned = raw.strip().upper()
    if cleaned in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[cleaned]
    if cleaned in _CURRENCY_CODE_MAP:
        return _CURRENCY_CODE_MAP[cleaned]
    if cleaned in _CURRENCY_CODES:
        return cleaned
    raise ValueError(f"Not a recognized currency: {raw!r}")


def looks_like_date_or_gstin(token: str) -> bool:
    """True if ``token`` is itself shaped like a date or GSTIN.

    Used by code extractors (invoice/PO number) to reject a candidate
    that is actually a mis-anchored date or GSTIN.
    """
    cleaned = token.strip().upper()
    return bool(DATE_PATTERN.fullmatch(cleaned)) or bool(GSTIN_PATTERN.fullmatch(cleaned))
