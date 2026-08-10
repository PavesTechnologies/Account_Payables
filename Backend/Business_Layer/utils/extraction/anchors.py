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
    r"net\s*value", r"net\s*charges", r"net\s*worth", r"amount\s*before\s*tax",
]
CGST_ANCHORS = [r"\bcgst\b"]
SGST_ANCHORS = [r"\bsgst\b"]
IGST_ANCHORS = [r"\bigst\b"]
CESS_ANCHORS = [r"\bcess\b"]

# Explicit grand-total semantics — outrank the generic "total" anchor
# below (see amounts.py's anchor-strength scoring bonus), since a
# generic label is a much weaker signal that a given line is really
# the document's grand total.
GRAND_TOTAL_STRONG_ANCHORS = [
    r"grand\s*total", r"invoice\s*total", r"total\s*amount",
    r"net\s*payable", r"amount\s*payable", r"amount\s*due",
    r"total\s*payable", r"gross\s*total", r"gross\s*worth",
]
# Bare "total" is the weakest possible anchor: it must not match inside
# "Subtotal"/"Sub Total", nor match "Total GST"/"Total Tax"/"Total
# Discount" (a tax or discount subtotal, not the grand total) or "Tax
# Total"/"Line Total"/"Item Total" (someone else's total, not this
# document's).
GRAND_TOTAL_WEAK_ANCHOR = (
    r"(?<!sub)(?<!sub-)(?<!sub\s)(?<!tax\s)(?<!line\s)(?<!item\s)"
    r"\btotal\b(?!\s*gst)(?!\s*tax)(?!\s*discount)"
)
GRAND_TOTAL_ANCHORS = GRAND_TOTAL_STRONG_ANCHORS + [GRAND_TOTAL_WEAK_ANCHOR]

# ---------------------------------------------------------------------------
# Payment terms / currency
# ---------------------------------------------------------------------------

PAYMENT_TERMS_ANCHORS = [
    r"payment\s*terms", r"\bterms\b", r"credit\s*days",
    # Free-text payment sentences ("Payment is due within 7 days from
    # the date of invoice.") carry no "terms" word at all — anchoring
    # on the sentence's own due-date phrasing is the only way to find
    # them without touching the generic bare "terms" anchor above.
    r"payment\s*is\s*due", r"due\s*within",
]
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
    # "(?!\s*care)" excludes "Customer Care" (a support contact line,
    # not a buyer-section heading).
    r"\bcustomer\b(?!\s*care)", r"\bclient\b", r"issued\s*to", r"sold\s*to", r"\brecipient\b",
]
SHIP_TO_MARKERS = [r"ship(?:ped)?\s*to"]
ENTITY_BOUNDARY_MARKERS = BUYER_MARKERS + SHIP_TO_MARKERS

# ---------------------------------------------------------------------------
# Vendor-name line classification
# ---------------------------------------------------------------------------

VENDOR_LINE_BLOCKLIST = [
    r"tax\s*invoice", r"\binvoice\b", r"\boriginal\b", r"\bduplicate\b", r"\bcopy\b",
    r"\bgstin\b", r"\bgst\b", r"\bbuyer\b", r"bill\s*to", r"ship\s*to", r"\bconsignee\b",
    r"\bcustomer\b(?!\s*care)", r"\bclient\b", r"sold\s*to", r"\brecipient\b",
    r"\btransport\b", r"e-?way\s*bill", r"acknowledge?ment", r"\birn\b", r"qr\s*code",
    r"\bhsn\b", r"\bsac\b", r"\bpan\b", r"\bcin\b", r"reverse\s*charge",
    r"issued\s*to", r"billing\s*(?:&|and)\s*shipping",
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

# ---------------------------------------------------------------------------
# Line-item table columns
# ---------------------------------------------------------------------------
# Regex fragments used by extraction.line_items to detect a table header
# line and label each of its columns. A header line is one that matches
# at least a handful of these across distinct columns (see
# line_items.detect_header). Order doesn't matter — column position is
# inferred from where each pattern matches on the header line, not from
# this list's order.

LINE_ITEM_SNO_ANCHORS = [r"^s\.?\s*no\.?$", r"^sr\.?\s*no\.?$", r"item\s*no\.?", r"^#$"]
LINE_ITEM_DESCRIPTION_ANCHORS = [
    r"description", r"particulars", r"item\s*(?:name|description)?", r"product",
    r"service", r"goods",
]
LINE_ITEM_HSN_ANCHORS = [r"\bhsn\b"]
LINE_ITEM_SAC_ANCHORS = [r"\bsac\b"]
LINE_ITEM_QTY_ANCHORS = [r"\bqty\b", r"\bquantity\b"]
LINE_ITEM_UOM_ANCHORS = [r"\buom\b"]
LINE_ITEM_UNIT_PRICE_ANCHORS = [r"unit\s*price", r"\brate\b", r"price\s*/\s*unit", r"price\s*per\s*unit"]
LINE_ITEM_AMOUNT_ANCHORS = [r"\bamount\b", r"\btotal\b", r"line\s*total", r"taxable\s*value"]
LINE_ITEM_TAX_ANCHORS = [r"\bgst\b", r"\btax\b", r"\bcgst\b", r"\bsgst\b", r"\bigst\b"]
LINE_ITEM_DISCOUNT_ANCHORS = [r"\bdiscount\b"]

# Table-row-shaped column groups, keyed by the ExtractedInvoiceLine field
# they populate. First matching pattern within a header cell wins.
LINE_ITEM_COLUMN_ANCHORS = {
    "sno": LINE_ITEM_SNO_ANCHORS,
    "description": LINE_ITEM_DESCRIPTION_ANCHORS,
    "hsn_sac": LINE_ITEM_HSN_ANCHORS + LINE_ITEM_SAC_ANCHORS,
    "quantity": LINE_ITEM_QTY_ANCHORS,
    "uom": LINE_ITEM_UOM_ANCHORS,
    "unit_price": LINE_ITEM_UNIT_PRICE_ANCHORS,
    "discount": LINE_ITEM_DISCOUNT_ANCHORS,
    "tax": LINE_ITEM_TAX_ANCHORS,
    "amount": LINE_ITEM_AMOUNT_ANCHORS,
}

# Lines that end the item table even though they may contain numbers —
# summary/footer rows that must never be mistaken for a line item.
LINE_ITEM_STOP_ANCHORS = (
    SUBTOTAL_ANCHORS
    + GRAND_TOTAL_ANCHORS
    + CGST_ANCHORS
    + SGST_ANCHORS
    + IGST_ANCHORS
    + CESS_ANCHORS
    + [
        r"amount\s*in\s*words", r"rupees\s*only", r"\bonly\b\s*$",
        r"\bbank\b", r"\bifsc\b", r"account\s*no", r"\bswift\b",
        r"round\s*-?\s*off", r"\bdiscount\s*total\b",
        r"terms\s*(?:&|and)\s*conditions", r"payment\s*terms",
        r"page\s*\d+\s*(?:of|/)\s*\d+", r"declaration",
        r"authorised?\s*signatory", r"for\s+[\w\s]+(?:pvt|ltd|llp)",
    ]
)
