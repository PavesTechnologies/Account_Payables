# Backend/Business_Layer/utils/extraction/anchors.py
"""Anchor label synonyms and context markers for every extractable field.

Keeping every label variant a real invoice uses in one place means
adding OCR-observed phrasing to an existing field never touches
extractor logic — only this registry. Patterns are regex fragments
(not literal text) so callers get word boundaries and negative
lookarounds for free (see ``GRAND_TOTAL_ANCHORS``, which must not
match inside "Subtotal").
"""
from __future__ import annotations

import re
from typing import Sequence


def matches_any(text: str, patterns: Sequence[str]) -> bool:
    """True if any of ``patterns`` is found anywhere in ``text`` (case-insensitive)."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------

INVOICE_NUMBER_ANCHORS = [
    r"invoice\s*(?:no\.?|number|#)",
    r"\binv\s*no\.?",
    r"\binv\s*#",
    r"bill\s*no\.?",
    r"document\s*no\.?",
]

PO_NUMBER_ANCHORS = [
    r"po\s*number", r"po\s*no\.?",
    r"purchase\s*order\s*no\.?", r"purchase\s*order",
    r"p\.o\.\s*no\.?",
]

# ---------------------------------------------------------------------------
# GSTIN
# ---------------------------------------------------------------------------

VENDOR_GSTIN_ANCHORS = [
    r"gstin", r"gst\s*no\.?", r"gst\s*number", r"gst\s*registration\s*number",
]

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

INVOICE_DATE_ANCHORS = [
    r"invoice\s*date", r"date\s*of\s*invoice", r"bill\s*date",
    # Bare "Date:" is extremely common as the sole invoice-date label
    # on compact invoices (often sharing a line with "Invoice No").
    # Excluded whenever it's actually some other date field's label —
    # PO/dispatch/due/order/delivery/ship date all use "Date" as their
    # own suffix and must never be mistaken for the invoice date.
    r"(?<!po\s)(?<!dispatch\s)(?<!due\s)(?<!order\s)(?<!delivery\s)(?<!ship\s)\bdate\b",
]
DUE_DATE_ANCHORS = [r"due\s*date", r"payment\s*due\s*date", r"payment\s*due"]

# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------

SUBTOTAL_ANCHORS = [
    r"sub\s*-?\s*total", r"basic\s*amount", r"taxable\s*(?:value|amount)",
    r"net\s*amount", r"gross\s*before\s*tax", r"assessable\s*value",
]
CGST_ANCHORS = [r"\bcgst\b"]
SGST_ANCHORS = [r"\bsgst\b"]
IGST_ANCHORS = [r"\bigst\b"]
CESS_ANCHORS = [r"\bcess\b"]
GRAND_TOTAL_ANCHORS = [
    r"grand\s*total", r"invoice\s*total", r"total\s*amount",
    r"net\s*payable", r"amount\s*payable", r"amount\s*due",
    # bare "total" must not match inside "Subtotal"/"Sub Total"
    r"(?<!sub)(?<!sub-)(?<!sub\s)\btotal\b",
]

# ---------------------------------------------------------------------------
# Payment terms / currency
# ---------------------------------------------------------------------------

PAYMENT_TERMS_ANCHORS = [r"payment\s*terms", r"\bterms\b", r"credit\s*days"]
CURRENCY_ANCHORS = [r"\bcurrency\b", r"\bcurr\b"]

# ---------------------------------------------------------------------------
# Sections / context markers used for proximity scoring
# ---------------------------------------------------------------------------

VENDOR_SECTION_ANCHORS = [
    r"\bvendor\b", r"\bsupplier\b", r"\bseller\b", r"\bfrom\b", r"billed\s*by", r"sold\s*by",
]
BUYER_MARKERS = [
    # "(?<!for\s)" excludes the standard multi-copy legend Indian tax
    # invoices stamp on every page ("Original For Buyer", "Duplicate
    # for Transporter", "Triplicate for Supplier") — that's which
    # physical copy this is, not a "Buyer:" section heading, and must
    # never be mistaken for one.
    r"(?<!for\s)\bbuyer\b", r"bill(?:ed)?\s*to", r"\bconsignee\b", r"invoice\s*to",
]
SHIP_TO_MARKERS = [r"ship(?:ped)?\s*to"]

# ---------------------------------------------------------------------------
# Vendor-name line classification
# ---------------------------------------------------------------------------

VENDOR_LINE_BLOCKLIST = [
    r"tax\s*invoice", r"\binvoice\b", r"\boriginal\b", r"\bduplicate\b", r"\bcopy\b",
    r"\bgstin\b", r"\bgst\b", r"\bbuyer\b", r"bill\s*to", r"ship\s*to", r"\bconsignee\b",
    r"\btransport\b", r"e-?way\s*bill", r"acknowledge?ment", r"\birn\b", r"qr\s*code",
    r"\bhsn\b", r"\bsac\b", r"\bpan\b", r"\bcin\b", r"reverse\s*charge",
]

COMPANY_SUFFIXES = [
    r"pvt\.?\s*ltd\.?", r"private\s*limited", r"\bllp\b", r"\bltd\.?\b", r"\binc\.?\b",
    r"\bllc\b", r"\bcorp\.?\b", r"enterprises?", r"industries", r"traders", r"agency",
    r"agencies", r"&\s*co\b", r"\bcompany\b", r"solutions", r"technologies", r"associates",
]

ADDRESS_MARKERS = [
    r"\broad\b", r"\bstreet\b", r"\bnagar\b", r"\bfloor\b", r"\bbuilding\b", r"\bblock\b",
    r"\bsector\b", r"\bdist(?:rict)?\b", r"pin\s*code", r"\b\d{6}\b",
]

BANK_MARKERS = [r"\bbank\b", r"\bifsc\b", r"account\s*no", r"\bswift\b", r"\bbranch\b"]

CONTACT_MARKERS = [
    r"[\w.\-]+@[\w.\-]+\.\w+", r"www\.", r"https?://",
    r"\bphone\b", r"\bmobile\b", r"\btel\b", r"\+?\d[\d\-\s]{8,}\d",
]
