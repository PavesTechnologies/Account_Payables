# Backend/Business_Layer/utils/field_extractors.py
"""Rule-based invoice field extraction — no AI/ML, only anchors, regex, and geometry.

Each field has its own extractor class implementing ``extract()`` and
``confidence()``, per the pipeline design. Extractors that search for
a labelled value (e.g. "Invoice No: INV-123") share the anchor+regex
strategy via ``AnchorRegexExtractor``; ``VendorNameExtractor`` is the
one exception, since vendor names aren't preceded by a reliable label
and instead rely on page geometry (the topmost line on page 1).

Anchor strings are plain regex fragments (not literal text) so callers
can express word boundaries and negative lookarounds directly (see
``TotalExtractor``, which must not match inside "Subtotal").
"""
from __future__ import annotations

import datetime
import decimal
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Pattern, Tuple

from Backend.Business_Layer.utils.exceptions import FieldExtractionError
from Backend.API_Layer.interface.invoice_process_interface import DocumentResult, ExtractedInvoice

ANCHOR_MATCH_CONFIDENCE = 90.0
FALLBACK_MATCH_CONFIDENCE = 55.0
ANCHOR_SEARCH_WINDOW = 60

_DATE_PATTERN = re.compile(
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})"
)
_CODE_PATTERN = re.compile(r"[:\-#\s]{0,5}([A-Z0-9][A-Z0-9\-/]{2,19})", re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(r"[:\-#₹Rs.\s]{0,6}([\d][\d,]*\.\d{2}|[\d][\d,]*)")
_GSTIN_PATTERN = re.compile(r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9]Z[A-Z0-9])", re.IGNORECASE)

_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y",
    "%d %B %Y", "%d %b %Y",
    "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
    "%Y-%m-%d", "%Y/%m/%d",
)


def _document_text(document: DocumentResult) -> str:
    return "\n".join(page.text for page in document.pages)


def _find_anchor_value(
    text: str,
    anchor_patterns: List[str],
    value_pattern: Pattern[str],
    window: int = ANCHOR_SEARCH_WINDOW,
    allow_fallback: bool = True,
) -> Tuple[Optional[str], float]:
    """Search for a value near one of the given anchors, optionally falling back to a bare regex scan.

    Anchor hits are trusted more (higher confidence) than a match found
    anywhere in the text with no supporting label. The blind, no-anchor
    fallback is only safe for highly distinctive patterns (e.g. GSTIN);
    for generic numeric/code patterns it is disabled by callers because
    it will happily latch onto an unrelated number elsewhere in the
    document (e.g. digits inside a GSTIN) when the real anchor is
    missing or was mangled by OCR.
    """
    for anchor_pattern in anchor_patterns:
        anchor_match = re.search(anchor_pattern, text, re.IGNORECASE)
        if not anchor_match:
            continue

        segment = text[anchor_match.end(): anchor_match.end() + window]
        value_match = value_pattern.search(segment)
        if value_match:
            return value_match.group(1).strip(), ANCHOR_MATCH_CONFIDENCE

    if allow_fallback:
        value_match = value_pattern.search(text)
        if value_match:
            return value_match.group(1).strip(), FALLBACK_MATCH_CONFIDENCE

    return None, 0.0


def _parse_date(raw: str) -> datetime.date:
    normalized = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


def _topmost_line(document: DocumentResult) -> Optional[str]:
    """Geometry-based fallback: the topmost line of words on page 1."""
    if not document.pages:
        return None

    first_page = document.pages[0]
    if not first_page.words:
        return first_page.text.strip().splitlines()[0].strip() if first_page.text.strip() else None

    min_y0 = min(w.y0 for w in first_page.words)
    band = [w for w in first_page.words if w.y0 <= min_y0 + 5]
    band.sort(key=lambda w: w.x0)
    line = " ".join(w.text for w in band).strip()
    return line or None


def _line_after_anchor(text: str, anchor_pattern: str) -> Optional[str]:
    match = re.search(anchor_pattern, text, re.IGNORECASE)
    if not match:
        return None

    remainder = text[match.end():]
    newline_index = remainder.find("\n")
    line = remainder[:newline_index] if newline_index != -1 else remainder
    return line.lstrip(":-# \t").strip() or None


class BaseFieldExtractor(ABC):
    """Base for all rule-based field extractors."""

    field_name: str = ""

    def __init__(self) -> None:
        self._last_confidence = 0.0

    @abstractmethod
    def extract(self, document: DocumentResult):
        """Extract this field's value from a DocumentResult, or None if not found."""

    def confidence(self) -> float:
        """Confidence (0-100) of the value returned by the most recent extract() call."""
        return self._last_confidence


class AnchorRegexExtractor(BaseFieldExtractor):
    """Extractor that searches for ``anchors`` and pulls a value with ``pattern``."""

    anchors: List[str] = []
    pattern: Pattern[str] = _CODE_PATTERN
    # Blind whole-document fallback is unsafe for generic numeric/code
    # patterns (see _find_anchor_value); amount and PO extractors turn
    # it off so a missing anchor yields None instead of a wrong guess.
    allow_fallback: bool = True

    def _postprocess(self, raw: str):
        return raw

    def extract(self, document: DocumentResult):
        text = _document_text(document)
        raw, conf = _find_anchor_value(
            text, self.anchors, self.pattern, allow_fallback=self.allow_fallback
        )

        if raw is None:
            self._last_confidence = 0.0
            return None

        try:
            value = self._postprocess(raw)
        except (ValueError, decimal.InvalidOperation):
            self._last_confidence = 0.0
            return None

        self._last_confidence = conf
        return value


class InvoiceNumberExtractor(AnchorRegexExtractor):
    field_name = "invoice_number"
    anchors = [r"invoice\s*(?:no\.?|number|#)", r"\binv\s*no\.?", r"bill\s*no\.?"]
    pattern = _CODE_PATTERN

    def _postprocess(self, raw: str) -> str:
        return raw.strip().upper()


class GSTINExtractor(AnchorRegexExtractor):
    field_name = "gstin"
    anchors = [r"gstin", r"gst\s*no\.?", r"gst\s*number"]
    pattern = _GSTIN_PATTERN

    def _postprocess(self, raw: str) -> str:
        return raw.strip().upper()


class InvoiceDateExtractor(AnchorRegexExtractor):
    field_name = "invoice_date"
    anchors = [r"invoice\s*date", r"date\s*of\s*invoice", r"bill\s*date"]
    pattern = _DATE_PATTERN

    def _postprocess(self, raw: str) -> datetime.date:
        return _parse_date(raw)


class DueDateExtractor(AnchorRegexExtractor):
    field_name = "due_date"
    anchors = [r"due\s*date", r"payment\s*due\s*date", r"payment\s*due"]
    pattern = _DATE_PATTERN

    def _postprocess(self, raw: str) -> datetime.date:
        return _parse_date(raw)


class PONumberExtractor(AnchorRegexExtractor):
    field_name = "po_number"
    anchors = [
        r"po\s*number", r"po\s*no\.?",
        r"purchase\s*order\s*no\.?", r"purchase\s*order",
        r"p\.o\.\s*no\.?",
    ]
    pattern = _CODE_PATTERN
    allow_fallback = False  # a PO number is optional; never guess one from unrelated text

    def _postprocess(self, raw: str) -> str:
        return raw.strip().upper()


class AmountExtractor(AnchorRegexExtractor):
    pattern = _AMOUNT_PATTERN
    allow_fallback = False  # amounts are numeric and easily confused with unrelated digits (e.g. GSTIN)

    def _postprocess(self, raw: str) -> decimal.Decimal:
        return decimal.Decimal(raw.replace(",", ""))


class SubtotalExtractor(AmountExtractor):
    field_name = "subtotal"
    anchors = [r"sub\s*-?\s*total", r"taxable\s*value", r"taxable\s*amount"]


class CGSTExtractor(AmountExtractor):
    field_name = "cgst"
    anchors = [r"\bcgst\b"]


class SGSTExtractor(AmountExtractor):
    field_name = "sgst"
    anchors = [r"\bsgst\b"]


class IGSTExtractor(AmountExtractor):
    field_name = "igst"
    anchors = [r"\bigst\b"]


class TotalExtractor(AmountExtractor):
    field_name = "total"
    # Bare "total" must not match inside "Subtotal"/"Sub Total" — the
    # negative lookbehinds rule that out while still matching a
    # standalone "Total" line.
    anchors = [
        r"grand\s*total",
        r"invoice\s*total",
        r"total\s*amount",
        r"amount\s*due",
        r"net\s*payable",
        r"(?<!sub)(?<!sub-)(?<!sub\s)\btotal\b",
    ]


class VendorNameExtractor(BaseFieldExtractor):
    field_name = "vendor_name"
    anchors = [r"vendor\s*name", r"\bvendor\b", r"\bfrom\b", r"\bseller\b", r"billed\s*by", r"sold\s*by"]

    def extract(self, document: DocumentResult) -> Optional[str]:
        text = _document_text(document)

        for anchor in self.anchors:
            line = _line_after_anchor(text, anchor)
            if line:
                self._last_confidence = 80.0
                return line

        topmost = _topmost_line(document)
        if topmost:
            self._last_confidence = 45.0
            return topmost

        self._last_confidence = 0.0
        return None


EXTRACTOR_CLASSES = (
    InvoiceNumberExtractor,
    InvoiceDateExtractor,
    DueDateExtractor,
    GSTINExtractor,
    VendorNameExtractor,
    PONumberExtractor,
    SubtotalExtractor,
    CGSTExtractor,
    SGSTExtractor,
    IGSTExtractor,
    TotalExtractor,
)


def extract_invoice_fields(document: DocumentResult) -> ExtractedInvoice:
    """Run every extractor over a DocumentResult and assemble an ExtractedInvoice."""
    if not document.pages:
        raise FieldExtractionError("Document has no pages to extract fields from")

    values: dict = {}
    confidences: dict = {}

    for extractor_cls in EXTRACTOR_CLASSES:
        extractor = extractor_cls()
        values[extractor.field_name] = extractor.extract(document)
        confidences[extractor.field_name] = extractor.confidence()

    return ExtractedInvoice(field_confidences=confidences, **values)
