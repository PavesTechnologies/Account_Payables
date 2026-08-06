# Backend/Business_Layer/utils/extraction/amounts.py
"""Tax and total amount extraction.

Handles Subtotal/Basic Amount, CGST, SGST, IGST, CESS, and the grand
total. Every one of these anchors can also appear as a table-row
label (e.g. a line item's own "CGST" column), so the shared
``looks_like_table_row`` penalty matters more here than anywhere else
in the engine — it is what keeps a per-item tax cell from outscoring
the real tax-summary line. A small bonus for sitting in the bottom
half of the page (where the tax-summary block almost always lives)
breaks the remaining ties in the summary's favor.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers
from Backend.Business_Layer.utils.extraction.base import BELOW, Candidate, SAME_LINE, BaseFieldExtractor

_SUMMARY_SECTION_BONUS = 8.0

_SECTION_MARKERS = OrderedDict([
    ("BUYER", anchors.BUYER_MARKERS),
    ("SHIP_TO", anchors.SHIP_TO_MARKERS),
])


class _AmountExtractorBase(BaseFieldExtractor):
    anchor_patterns: List[str] = []

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)
        page_heights: Dict[int, float] = {page.page_number: page.height for page in document.pages}

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, self.anchor_patterns):
            page_lines = lines_by_page[hit.line.page_number]
            page_height = page_heights.get(hit.line.page_number, 0.0)

            for match in normalizers.AMOUNT_PATTERN.finditer(geometry.extract_right_of_anchor(hit)):
                candidates.append(self._build_candidate(match.group(0), hit.line, page_lines, hit, SAME_LINE, page_height))

            for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
                for match in normalizers.AMOUNT_PATTERN.finditer(below.text):
                    candidates.append(self._build_candidate(match.group(0), below, page_lines, hit, BELOW, page_height))

        return candidates

    def _build_candidate(self, raw_token, line, page_lines, hit, relation, page_height) -> Candidate:
        try:
            value = normalizers.normalize_amount(raw_token)
            valid = True
        except ValueError:
            value = None
            valid = False

        section = geometry.nearest_section(page_lines, line, _SECTION_MARKERS)
        candidate = Candidate(
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
        if page_height and line.y0 >= page_height * 0.5:
            candidate.score_bonus += _SUMMARY_SECTION_BONUS
        return candidate


class SubtotalExtractor(_AmountExtractorBase):
    field_name = "subtotal"
    anchor_patterns = anchors.SUBTOTAL_ANCHORS


class CGSTExtractor(_AmountExtractorBase):
    field_name = "cgst"
    anchor_patterns = anchors.CGST_ANCHORS


class SGSTExtractor(_AmountExtractorBase):
    field_name = "sgst"
    anchor_patterns = anchors.SGST_ANCHORS


class IGSTExtractor(_AmountExtractorBase):
    field_name = "igst"
    anchor_patterns = anchors.IGST_ANCHORS


class CessExtractor(_AmountExtractorBase):
    field_name = "cess"
    anchor_patterns = anchors.CESS_ANCHORS


class GrandTotalExtractor(_AmountExtractorBase):
    """Grand total / invoice total / amount payable — output field ``total``."""

    field_name = "total"
    anchor_patterns = anchors.GRAND_TOTAL_ANCHORS
