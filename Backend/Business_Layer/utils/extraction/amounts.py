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

Two behaviors are specific to this module rather than shared via
``BaseFieldExtractor.extract``:

- A number immediately followed by "%" is a *rate*, never treated as
  an amount ("CGST 9% Rs.225.00" must never yield 9) —
  ``normalizers.iter_amount_matches`` filters these out at the source.
- CGST/SGST/IGST/CESS aggregate across every distinct qualifying
  summary occurrence instead of picking one winner, so an invoice that
  prints two tax slabs (e.g. 14% and 2.5% CGST as two separate
  summary lines) reports their sum, not whichever line scored higher.
"""
from __future__ import annotations

import decimal
import re
from collections import OrderedDict
from typing import Dict, List, Tuple

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult, FieldExtractionMeta
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers, scoring
from Backend.Business_Layer.utils.extraction.base import (
    BELOW,
    Candidate,
    SAME_LINE,
    BaseFieldExtractor,
    rank_candidates,
)

_SUMMARY_SECTION_BONUS = 8.0
_STRONG_ANCHOR_BONUS = 12.0
_VAT_ANCHORS = [r"\bvat\b"]
_VAT_RATE_PATTERN = re.compile(r"\bvat\b.*?(\d{1,2}(?:\.\d+)?)\s*%|(\d{1,2}(?:\.\d+)?)\s*%.*?\bvat\b", re.IGNORECASE)
_RATE_PATTERN = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")

_SECTION_MARKERS = OrderedDict([
    ("BUYER", anchors.BUYER_MARKERS),
    ("SHIP_TO", anchors.SHIP_TO_MARKERS),
])


class _AmountExtractorBase(BaseFieldExtractor):
    anchor_patterns: List[str] = []
    # Anchor patterns that unambiguously mean *this* field (e.g. "Grand
    # Total") as opposed to a weak generic pattern that merely happens
    # to match (e.g. bare "Total") — see GrandTotalExtractor.
    strong_anchor_patterns: List[str] = []
    # CGST/SGST/IGST/CESS only: sum every distinct qualifying summary
    # occurrence instead of returning a single winner.
    aggregate: bool = False
    below_table_amount_index: int | None = None

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)
        page_heights: Dict[int, float] = {page.page_number: page.height for page in document.pages}

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, self.anchor_patterns):
            page_lines = lines_by_page[hit.line.page_number]
            page_height = page_heights.get(hit.line.page_number, 0.0)

            for match in normalizers.iter_amount_matches(geometry.extract_right_of_anchor(hit)):
                candidates.append(self._build_candidate(match.group(0), hit.line, page_lines, hit, SAME_LINE, page_height))

            for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
                for match in self._below_amount_matches(hit, below.text):
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
            anchor_line_index=hit.line.line_index,
        )
        if page_height and line.y0 >= page_height * 0.5:
            candidate.score_bonus += _SUMMARY_SECTION_BONUS
        if hit.pattern in self.strong_anchor_patterns:
            candidate.score_bonus += _STRONG_ANCHOR_BONUS
        return candidate

    def _below_amount_matches(self, hit: geometry.AnchorHit, text: str):
        matches = list(normalizers.iter_amount_matches(text))
        if self.below_table_amount_index is None or not _looks_like_net_vat_gross_header(hit.line.text):
            return matches
        if not matches:
            return []
        index = self.below_table_amount_index
        if index < 0:
            index = len(matches) + index
        if 0 <= index < len(matches):
            return [matches[index]]
        return matches

    def extract(self, document: DocumentResult) -> FieldExtractionMeta:
        if not self.aggregate:
            return super().extract(document)
        return self._extract_aggregated(document)

    def _extract_aggregated(self, document: DocumentResult) -> FieldExtractionMeta:
        candidates = self.collect_candidates(document)
        if not candidates:
            return FieldExtractionMeta()

        accepted = [
            c for c in rank_candidates(candidates)
            if c.value is not None and c.score >= scoring.MIN_ACCEPT_SCORE
        ]
        if not accepted:
            return FieldExtractionMeta()

        # Multiple summary lines for the same tax type are multiple tax
        # slabs to sum, not competing guesses for one value — but a
        # per-item tax cell that slipped past the table-row penalty
        # must not be summed in as a phantom extra slab, so aggregation
        # is restricted to the bottom-of-page summary band (the same
        # band _SUMMARY_SECTION_BONUS rewards) and never to a candidate
        # already flagged as sitting inside a table row.
        best_per_hit: Dict[Tuple[int, int], Candidate] = {}
        for candidate in accepted:
            if candidate.inside_table:
                continue
            page_height = next(
                (p.height for p in document.pages if p.page_number == candidate.page_number), 0.0
            )
            if not (page_height and candidate.line and candidate.line.y0 >= page_height * 0.5):
                continue
            key = (candidate.page_number, candidate.anchor_line_index)
            best_per_hit.setdefault(key, candidate)  # `accepted` is rank-sorted: first wins per key

        if not best_per_hit:
            winner = accepted[0]
            return FieldExtractionMeta(
                value=winner.value,
                confidence=scoring.confidence_from_score(winner.score),
                matched_anchor=winner.anchor_text,
                page=winner.page_number,
                method="+".join(winner.method_tags) or "NONE",
            )

        representatives = list(best_per_hit.values())
        total_value = sum(r.value for r in representatives)
        weakest_score = min(r.score for r in representatives)
        method_tags = sorted(set(tag for r in representatives for tag in r.method_tags))
        if len(representatives) > 1:
            method_tags.append("AGGREGATED")
        anchors_joined = "+".join(sorted({r.anchor_text for r in representatives if r.anchor_text}))

        return FieldExtractionMeta(
            value=total_value,
            confidence=scoring.confidence_from_score(weakest_score),
            matched_anchor=anchors_joined or None,
            page=representatives[0].page_number,
            method="+".join(method_tags) or "NONE",
        )


class SubtotalExtractor(_AmountExtractorBase):
    field_name = "subtotal"
    anchor_patterns = anchors.SUBTOTAL_ANCHORS
    below_table_amount_index = 0


class CGSTExtractor(_AmountExtractorBase):
    field_name = "cgst"
    anchor_patterns = anchors.CGST_ANCHORS
    aggregate = True


class SGSTExtractor(_AmountExtractorBase):
    field_name = "sgst"
    anchor_patterns = anchors.SGST_ANCHORS
    aggregate = True


class IGSTExtractor(_AmountExtractorBase):
    field_name = "igst"
    anchor_patterns = anchors.IGST_ANCHORS
    aggregate = True


class CessExtractor(_AmountExtractorBase):
    field_name = "cess"
    anchor_patterns = anchors.CESS_ANCHORS
    aggregate = True


class TaxTypeExtractor(BaseFieldExtractor):
    field_name = "tax_type"

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, _VAT_ANCHORS):
            candidates.append(Candidate(
                value="VAT",
                raw_text=hit.matched_text,
                page_number=hit.line.page_number,
                line=hit.line,
                anchor_text=hit.matched_text,
                relation=SAME_LINE,
                inside_table=False,
            ))
        return candidates


class TaxRateExtractor(BaseFieldExtractor):
    field_name = "tax_rate"

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)
        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, _VAT_ANCHORS):
            candidates.extend(self._line_candidates(hit.line, hit.matched_text))
            for below in geometry.extract_below_anchor(lines_by_page[hit.line.page_number], hit, max_lines=1):
                if _looks_like_net_vat_gross_header(hit.line.text):
                    candidates.extend(self._rate_only_candidates(below, hit.matched_text))
                else:
                    candidates.extend(self._line_candidates(below, hit.matched_text))
        return candidates

    def _line_candidates(self, line: geometry.Line, anchor_text: str) -> List[Candidate]:
        found: List[Candidate] = []
        for match in _VAT_RATE_PATTERN.finditer(line.text):
            raw = next(group for group in match.groups() if group is not None)
            found.append(Candidate(
                value=decimal.Decimal(raw),
                raw_text=raw,
                page_number=line.page_number,
                line=line,
                anchor_text=anchor_text,
                relation=SAME_LINE,
                inside_table=geometry.looks_like_table_row(line),
                score_bonus=10.0,
            ))
        return found

    def _rate_only_candidates(self, line: geometry.Line, anchor_text: str) -> List[Candidate]:
        found: List[Candidate] = []
        for match in _RATE_PATTERN.finditer(line.text):
            raw = match.group(1)
            found.append(Candidate(
                value=decimal.Decimal(raw),
                raw_text=raw,
                page_number=line.page_number,
                line=line,
                anchor_text=anchor_text,
                relation=BELOW,
                inside_table=geometry.looks_like_table_row(line),
                score_bonus=10.0,
            ))
        return found


class TaxAmountExtractor(_AmountExtractorBase):
    field_name = "tax_amount"
    anchor_patterns = _VAT_ANCHORS
    below_table_amount_index = 1


class GrandTotalExtractor(_AmountExtractorBase):
    """Grand total / invoice total / amount payable — output field ``total``."""

    field_name = "total"
    anchor_patterns = anchors.GRAND_TOTAL_ANCHORS
    strong_anchor_patterns = anchors.GRAND_TOTAL_STRONG_ANCHORS
    below_table_amount_index = -1


def _looks_like_net_vat_gross_header(text: str) -> bool:
    return (
        anchors.matches_any(text, [r"net\s*worth", r"net\s*amount", r"taxable\s*(?:value|amount)"])
        and anchors.matches_any(text, [r"\bvat\b"])
        and anchors.matches_any(text, [r"gross\s*worth", r"gross\s*total"])
    )
