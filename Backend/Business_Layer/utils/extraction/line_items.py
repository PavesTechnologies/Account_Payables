# Backend/Business_Layer/utils/extraction/line_items.py
"""Geometry-based invoice line-item (table row) extraction.

Reuses the same word/line geometry primitives as every other extractor
in this package (Backend.Business_Layer.utils.extraction.geometry) —
no new clustering logic, no LLM. The table's columns are inferred from
whichever header row the document actually has (S.No/Description/Qty/
Rate/Amount/HSN/GST in any order, any subset), never assumed fixed.

Pipeline, per page, in document order:
    1. Cluster words into lines (geometry.cluster_words_into_lines).
    2. Find a header line (>=3 recognized column labels, including a
       Description-like and an Amount-or-UnitPrice-like column) and
       infer each column's horizontal span from the header words'
       positions.
    3. Consume rows until a summary/footer/tax-total row is seen
       (anchors.LINE_ITEM_STOP_ANCHORS) or the page ends.
    4. Assign each row's words to a column by horizontal position.
       A row that yields a parseable Quantity/UnitPrice/Amount starts
       a new logical line item; a row that doesn't is a continuation
       of the previous item's description (multi-line descriptions).
    5. If a later page's table body opens with a line matching the
       same header shape, that repeated header is skipped and line
       numbering continues (never resets) across pages.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoiceLine,
)
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers

logger = logging.getLogger(__name__)

_MIN_HEADER_COLUMN_HITS = 3
_NUMERIC_COLUMNS = ("quantity", "unit_price", "amount")
_TAX_SUMMARY_ANCHOR_PATTERNS = (r"\bcgst\b", r"\bsgst\b", r"\bigst\b", r"total\s*gst")
_MIN_TAX_SUMMARY_HITS = 2


@dataclass
class _ColumnSpec:
    name: str
    x0: float
    x1: float


@dataclass
class _PendingLine:
    line_number: int
    description_parts: List[str] = field(default_factory=list)
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    tax_type: Optional[str] = None
    tax_rate: Optional[Decimal] = None

    def to_extracted(self) -> ExtractedInvoiceLine:
        description = " ".join(
            part.strip() for part in self.description_parts if part.strip()
        ).strip() or None
        present = sum(
            1
            for value in (description, self.quantity, self.unit_price, self.line_amount)
            if value is not None
        )
        return ExtractedInvoiceLine(
            line_number=self.line_number,
            description=description,
            quantity=self.quantity,
            unit_price=self.unit_price,
            line_amount=self.line_amount,
            tax_amount=self.tax_amount,
            tax_type=self.tax_type,
            tax_rate=self.tax_rate,
            confidence=round(present / 4, 4),
        )


def _match_column(text: str) -> Optional[str]:
    stripped = text.strip()
    if not stripped:
        return None
    for column, patterns in anchors.LINE_ITEM_COLUMN_ANCHORS.items():
        for pattern in patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                return column
    return None


def _match_multiword_column(bigram: str, first_word_len: int) -> Optional[str]:
    """Only for genuinely two-word headers (e.g. "Unit Price", "S No").

    Anchored at the start and required to extend past the first word, so
    a single-word pattern that happens to `re.search`-match inside a
    bigram (e.g. "description" matching "Description Qty") can never be
    mistaken for a two-word column and swallow the next header cell.
    """
    for column, patterns in anchors.LINE_ITEM_COLUMN_ANCHORS.items():
        for pattern in patterns:
            match = re.match(pattern, bigram, re.IGNORECASE)
            if match and match.end() > first_word_len:
                return column
    return None


def _detect_header(line: geometry.Line) -> Optional[List[_ColumnSpec]]:
    """If ``line`` looks like a line-item table header, infer its column layout."""
    words = line.words
    n = len(words)
    hits: Dict[str, Tuple[float, float]] = {}
    matched_indices: set = set()

    i = 0
    while i < n:
        if i in matched_indices:
            i += 1
            continue

        column = _match_column(words[i].text)
        span = 1
        if column is None and i + 1 < n:
            bigram = f"{words[i].text} {words[i + 1].text}"
            column = _match_multiword_column(bigram, len(words[i].text))
            if column:
                span = 2

        if column:
            span_words = words[i : i + span]
            new_x0 = min(w.x0 for w in span_words)
            new_x1 = max(w.x1 for w in span_words)
            if column in hits:
                prev_x0, prev_x1 = hits[column]
                hits[column] = (min(prev_x0, new_x0), max(prev_x1, new_x1))
            else:
                hits[column] = (new_x0, new_x1)
            matched_indices.update(range(i, i + span))
            i += span
            continue

        i += 1

    if len(hits) < _MIN_HEADER_COLUMN_HITS:
        return None
    if "description" not in hits or ("amount" not in hits and "unit_price" not in hits):
        return None

    ordered = sorted(hits.items(), key=lambda item: item[1][0])
    boundaries = [0.0]
    for idx in range(len(ordered) - 1):
        _, (_x0a, x1a) = ordered[idx]
        _, (x0b, _x1b) = ordered[idx + 1]
        boundaries.append((x1a + x0b) / 2)
    boundaries.append(float("inf"))

    return [
        _ColumnSpec(name=name, x0=boundaries[idx], x1=boundaries[idx + 1])
        for idx, (name, _bounds) in enumerate(ordered)
    ]


def _same_header_shape(header: List[_ColumnSpec], existing: Optional[List[_ColumnSpec]]) -> bool:
    if not existing:
        return False
    return {c.name for c in header} == {c.name for c in existing}


def _assign_row_to_columns(
    row: geometry.Line, columns: Sequence[_ColumnSpec]
) -> Dict[str, list]:
    buckets: Dict[str, list] = {col.name: [] for col in columns}
    for word in row.words:
        center = (word.x0 + word.x1) / 2
        target = columns[-1].name
        for col in columns:
            if col.x0 <= center < col.x1:
                target = col.name
                break
        buckets[target].append(word)
    return buckets


def _column_text(words: Sequence) -> str:
    return " ".join(w.text for w in sorted(words, key=lambda w: w.x0)).strip()


def _parse_amount(text: str) -> Optional[Decimal]:
    text = text.strip()
    if not text:
        return None
    match = normalizers.AMOUNT_PATTERN.search(text)
    if not match:
        return None
    try:
        return normalizers.normalize_amount(match.group(0))
    except ValueError:
        return None


def _is_stop_row(line: geometry.Line) -> bool:
    text = line.text
    if anchors.matches_any(text, anchors.LINE_ITEM_STOP_ANCHORS):
        return True
    tax_hits = sum(
        1 for pattern in _TAX_SUMMARY_ANCHOR_PATTERNS if re.search(pattern, text, re.IGNORECASE)
    )
    return tax_hits >= _MIN_TAX_SUMMARY_HITS


def _row_has_numeric_value(buckets: Dict[str, list]) -> bool:
    for column in _NUMERIC_COLUMNS:
        words = buckets.get(column)
        if words and _parse_amount(_column_text(words)) is not None:
            return True
    return False


def _is_meaningful(line: ExtractedInvoiceLine) -> bool:
    numeric_present = any(v is not None for v in (line.quantity, line.unit_price, line.line_amount))
    return bool(line.description) or numeric_present


def _extract_invoice_lines(document: DocumentResult) -> List[ExtractedInvoiceLine]:
    results: List[ExtractedInvoiceLine] = []
    pending: Optional[_PendingLine] = None
    next_line_number = 1
    columns: Optional[List[_ColumnSpec]] = None
    in_table = False

    for page in document.pages:
        lines = geometry.cluster_words_into_lines(page.words, page.page_number)
        if not lines:
            continue

        start_idx = 0
        if in_table and columns is not None:
            maybe_header = _detect_header(lines[0])
            if maybe_header is not None and _same_header_shape(maybe_header, columns):
                start_idx = 1

        for line in lines[start_idx:]:
            if not line.text.strip():
                continue

            if not in_table:
                header = _detect_header(line)
                if header is not None:
                    columns = header
                    in_table = True
                continue

            if _is_stop_row(line):
                in_table = False
                columns = None
                if pending is not None:
                    results.append(pending.to_extracted())
                    pending = None
                continue

            header_repeat = _detect_header(line)
            if header_repeat is not None and _same_header_shape(header_repeat, columns):
                continue

            assert columns is not None
            buckets = _assign_row_to_columns(line, columns)

            sno_text = _column_text(buckets.get("sno", []))
            description_text = _column_text(buckets.get("description", []))
            has_numeric = _row_has_numeric_value(buckets)

            if not sno_text and not description_text and not has_numeric:
                continue

            # A new logical item starts when: this is the very first row seen,
            # the row carries its own serial number (the strongest available
            # signal — present or not depending on the template), or the
            # in-progress item already has a line_amount (i.e. it's "done")
            # and this row brings new content. Otherwise the row is a
            # continuation of the in-progress item — covers both a
            # multi-line description ahead of its numbers and numbers that
            # complete a description given a few rows earlier.
            starts_new_item = (
                pending is None
                or bool(sno_text)
                or (pending.line_amount is not None and (description_text or has_numeric))
            )

            if starts_new_item:
                if pending is not None:
                    results.append(pending.to_extracted())
                pending = _PendingLine(line_number=next_line_number)
                next_line_number += 1

            if description_text:
                pending.description_parts.append(description_text)
            if pending.quantity is None and buckets.get("quantity"):
                parsed = _parse_amount(_column_text(buckets["quantity"]))
                if parsed is not None:
                    pending.quantity = parsed
            if pending.unit_price is None and buckets.get("unit_price"):
                parsed = _parse_amount(_column_text(buckets["unit_price"]))
                if parsed is not None:
                    pending.unit_price = parsed
            if pending.line_amount is None and buckets.get("amount"):
                parsed = _parse_amount(_column_text(buckets["amount"]))
                if parsed is not None:
                    pending.line_amount = parsed
            if pending.tax_amount is None and buckets.get("tax"):
                tax_text = _column_text(buckets["tax"])
                parsed_tax = _parse_amount(tax_text)
                if parsed_tax is not None:
                    pending.tax_amount = parsed_tax
                elif tax_text:
                    pending.tax_type = tax_text

    if pending is not None:
        results.append(pending.to_extracted())

    return [line for line in results if _is_meaningful(line)]


def extract_invoice_lines(document: DocumentResult) -> List[ExtractedInvoiceLine]:
    """Extract every line item from ``document``, never raising.

    A structural failure here (malformed geometry, unexpected table
    shape) must not fail the whole extraction pipeline — callers get
    an empty list and the failure is logged.
    """
    try:
        return _extract_invoice_lines(document)
    except Exception:
        logger.exception("Line-item extraction failed; returning no lines")
        return []
