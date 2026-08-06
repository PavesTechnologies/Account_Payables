# Backend/Business_Layer/utils/extraction/vendor.py
"""Vendor (seller) name extraction — the field the legacy extractor got wrong most often.

Two independent candidate sources are merged and ranked together:

1. An explicit label ("Vendor:", "Seller:", "From:", "Billed By") —
   scored like every other anchor+geometry field.
2. Every other line on page 1, scored purely on how "company-like" it
   looks (a company suffix, title case, low digit density, top of the
   page, near the vendor's own GSTIN) versus how strongly it looks
   like something else instead — a boilerplate label ("Tax Invoice",
   "GSTIN", "Buyer", "IRN", ...), an address, a table row, bank
   details, or a website/email/phone line.

Whichever candidate scores highest wins; a strong company-suffix line
beats a weak/garbled label match, matching the design brief's example
of preferring "Manan Agency" over "GSTIN..." or "Tax Invoice".
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry
from Backend.Business_Layer.utils.extraction.base import BELOW, Candidate, FALLBACK, SAME_LINE, BaseFieldExtractor

_MIN_LINE_LENGTH = 3
_MAX_LINE_LENGTH = 80
_MAX_DIGIT_RATIO = 0.3
_GSTIN_PROXIMITY_LINES = 3
_TOP_SECTION_HEIGHT_RATIO = 0.2
_BOTTOM_SECTION_HEIGHT_RATIO = 0.6

_COMPANY_SUFFIX_BONUS = 25.0
_TOP_SECTION_BONUS = 20.0
_NEAR_VENDOR_GSTIN_BONUS = 15.0
_TITLE_OR_UPPER_CASE_BONUS = 8.0
_BOTTOM_SECTION_PENALTY = -15.0


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(ch.isdigit() for ch in text) / len(text)


def _is_blocklisted(text: str) -> bool:
    return anchors.matches_any(text, anchors.VENDOR_LINE_BLOCKLIST)


def _is_rejected_line(line: geometry.Line, text: str) -> bool:
    """Lines that can never be a vendor name, regardless of how company-like they look."""
    if not (_MIN_LINE_LENGTH <= len(text) <= _MAX_LINE_LENGTH):
        return True
    if _is_blocklisted(text):
        return True
    if _digit_ratio(text) > _MAX_DIGIT_RATIO:
        return True
    if anchors.matches_any(text, anchors.ADDRESS_MARKERS):
        return True
    if anchors.matches_any(text, anchors.BANK_MARKERS):
        return True
    if anchors.matches_any(text, anchors.CONTACT_MARKERS):
        return True
    if geometry.looks_like_table_row(line):
        return True
    return False


class VendorNameExtractor(BaseFieldExtractor):
    field_name = "vendor_name"

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)
        page_heights: Dict[int, float] = {page.page_number: page.height for page in document.pages}
        page_one_lines = lines_by_page.get(1, [])
        vendor_gstin_line_indexes = self._vendor_gstin_line_indexes(page_one_lines)

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, anchors.VENDOR_SECTION_ANCHORS):
            page_lines = lines_by_page[hit.line.page_number]
            candidates.extend(self._label_candidates(hit, page_lines))

        page_height = page_heights.get(1, 0.0)
        for line in page_one_lines:
            candidate = self._line_candidate(line, page_height, vendor_gstin_line_indexes)
            if candidate is not None:
                candidates.append(candidate)

        return candidates

    @staticmethod
    def _vendor_gstin_line_indexes(page_one_lines: List[geometry.Line]) -> Set[int]:
        return {
            line.line_index for line in page_one_lines
            if anchors.matches_any(line.text, anchors.VENDOR_GSTIN_ANCHORS)
        }

    def _label_candidates(self, hit: geometry.AnchorHit, page_lines: List[geometry.Line]) -> List[Candidate]:
        found: List[Candidate] = []

        same_line_text = geometry.extract_right_of_anchor(hit).strip(" :-\t")
        if same_line_text and not _is_blocklisted(same_line_text) and _digit_ratio(same_line_text) < _MAX_DIGIT_RATIO:
            found.append(Candidate(
                value=same_line_text, raw_text=same_line_text, page_number=hit.line.page_number,
                line=hit.line, anchor_text=hit.matched_text, relation=SAME_LINE,
            ))

        for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
            text = below.text.strip()
            if text and not _is_blocklisted(text) and _digit_ratio(text) < _MAX_DIGIT_RATIO:
                found.append(Candidate(
                    value=text, raw_text=text, page_number=below.page_number,
                    line=below, anchor_text=hit.matched_text, relation=BELOW,
                ))

        return found

    def _line_candidate(
        self, line: geometry.Line, page_height: float, vendor_gstin_line_indexes: Set[int]
    ) -> Optional[Candidate]:
        text = line.text.strip()
        if _is_rejected_line(line, text):
            return None

        bonus = 0.0
        if anchors.matches_any(text, anchors.COMPANY_SUFFIXES):
            bonus += _COMPANY_SUFFIX_BONUS
        if page_height and line.y0 <= page_height * _TOP_SECTION_HEIGHT_RATIO:
            bonus += _TOP_SECTION_BONUS
        if any(abs(line.line_index - idx) <= _GSTIN_PROXIMITY_LINES for idx in vendor_gstin_line_indexes):
            bonus += _NEAR_VENDOR_GSTIN_BONUS
        if text == text.title() or text == text.upper():
            bonus += _TITLE_OR_UPPER_CASE_BONUS
        if page_height and line.y0 >= page_height * _BOTTOM_SECTION_HEIGHT_RATIO:
            bonus += _BOTTOM_SECTION_PENALTY

        candidate = Candidate(
            value=text, raw_text=text, page_number=line.page_number, line=line,
            anchor_text=None, has_anchor=False, relation=FALLBACK,
        )
        candidate.score_bonus = bonus
        return candidate
