# Backend/Business_Layer/utils/extraction/identifiers.py
"""Invoice number and PO number extraction.

Both are short alphanumeric codes introduced by a label — the same
anchor+geometry strategy works for either, just with different anchor
synonyms. Neither falls back to a whole-document scan: a missing
anchor must yield None, never a guess pulled from an unrelated number
elsewhere in the document (a PO number is optional; an invoice number
that isn't labelled anywhere isn't safely guessable either).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import List, Optional

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers
from Backend.Business_Layer.utils.extraction.base import BELOW, Candidate, SAME_LINE, BaseFieldExtractor

_SECTION_MARKERS = OrderedDict([
    ("BUYER", anchors.BUYER_MARKERS),
    ("SHIP_TO", anchors.SHIP_TO_MARKERS),
])


def _first_code_token(text: str) -> Optional[str]:
    """The first alphanumeric-code-shaped token in ``text``, per field.

    Only the *nearest* token to the anchor is ever considered — never
    every token in the remainder of the line — so a neighbouring
    field's label sharing the same OCR line (e.g. "Invoice No 46
    Date: 24-03-2020") can't get picked up once the real value is
    skipped for looking too short. Date/GSTIN look-alikes and bare
    label fragments ("Date", "No", ...) are skipped in place so the
    scan can still reach a real value a token or two further along.
    """
    for match in normalizers.CODE_PATTERN.finditer(text):
        token = match.group(0)
        if normalizers.looks_like_date_or_gstin(token):
            continue
        if token.strip().lower() in normalizers.NON_VALUE_WORDS:
            continue
        return token
    return None


class _LabelledCodeExtractor(BaseFieldExtractor):
    """Shared anchor+geometry strategy for short labelled alphanumeric codes."""

    anchor_patterns: List[str] = []

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, self.anchor_patterns):
            page_lines = lines_by_page[hit.line.page_number]

            same_line_token = _first_code_token(geometry.extract_right_of_anchor(hit))
            if same_line_token:
                candidates.append(self._build_candidate(same_line_token, hit.line, page_lines, hit, SAME_LINE))

            for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
                below_token = _first_code_token(below.text)
                if below_token:
                    candidates.append(self._build_candidate(below_token, below, page_lines, hit, BELOW))

        return candidates

    def _build_candidate(self, raw_token, line, page_lines, hit, relation) -> Candidate:
        try:
            value = normalizers.normalize_code(raw_token)
            valid = True
        except ValueError:
            value = None
            valid = False

        section = geometry.nearest_section(page_lines, line, _SECTION_MARKERS)
        return Candidate(
            value=value,
            raw_text=raw_token,
            page_number=line.page_number,
            line=line,
            anchor_text=hit.matched_text,
            relation=relation,
            valid_format=valid,
            near_buyer=section == "BUYER",
            near_ship_to=section == "SHIP_TO",
            inside_table=geometry.looks_like_table_row(line),
        )


class InvoiceNumberExtractor(_LabelledCodeExtractor):
    field_name = "invoice_number"
    anchor_patterns = anchors.INVOICE_NUMBER_ANCHORS


class PONumberExtractor(_LabelledCodeExtractor):
    field_name = "po_number"
    anchor_patterns = anchors.PO_NUMBER_ANCHORS
