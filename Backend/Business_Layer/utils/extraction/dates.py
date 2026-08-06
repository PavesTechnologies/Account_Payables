# Backend/Business_Layer/utils/extraction/dates.py
"""Invoice date and due date extraction.

Both use the same anchor+geometry code search as identifiers.py, but
with date-shaped values and an important asymmetry: a due date that
can't be found must stay ``None`` — it must never fall back to the
invoice date or to an unrelated date elsewhere in the document.
Dispatch date, order date, and PO date all use different anchor
wording and are deliberately excluded from both lists below, so
neither extractor can accidentally latch onto them.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import List

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers
from Backend.Business_Layer.utils.extraction.base import BELOW, Candidate, SAME_LINE, BaseFieldExtractor

_SECTION_MARKERS = OrderedDict([
    ("BUYER", anchors.BUYER_MARKERS),
    ("SHIP_TO", anchors.SHIP_TO_MARKERS),
])


class _DateExtractorBase(BaseFieldExtractor):
    anchor_patterns: List[str] = []

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, self.anchor_patterns):
            page_lines = lines_by_page[hit.line.page_number]

            for match in normalizers.DATE_PATTERN.finditer(geometry.extract_right_of_anchor(hit)):
                candidates.append(self._build_candidate(match.group(0), hit.line, page_lines, hit, SAME_LINE))

            for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
                for match in normalizers.DATE_PATTERN.finditer(below.text):
                    candidates.append(self._build_candidate(match.group(0), below, page_lines, hit, BELOW))

        return candidates

    def _build_candidate(self, raw_token, line, page_lines, hit, relation) -> Candidate:
        try:
            value = normalizers.normalize_date(raw_token)
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


class InvoiceDateExtractor(_DateExtractorBase):
    field_name = "invoice_date"
    anchor_patterns = anchors.INVOICE_DATE_ANCHORS


class DueDateExtractor(_DateExtractorBase):
    """Only matches its own anchors — structurally incapable of copying the invoice date."""

    field_name = "due_date"
    anchor_patterns = anchors.DUE_DATE_ANCHORS
