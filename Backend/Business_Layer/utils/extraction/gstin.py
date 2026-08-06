# Backend/Business_Layer/utils/extraction/gstin.py
"""Seller (vendor) and buyer GSTIN extraction.

Invoices frequently print two or more GSTINs — the seller's own
registration plus the buyer's/consignee's — under the exact same
label ("GSTIN"), so wording alone can't disambiguate them. Both
extractors collect every GSTIN-shaped token in the document and let
proximity to "Buyer"/"Bill To"/"Ship To" vs "Vendor"/"Seller"/"From"
context decide which one wins:

- ``VendorGSTINExtractor`` (``gstin``) avoids buyer/ship-to context.
- ``BuyerGSTINExtractor`` (``buyer_gstin``, optional) only considers
  tokens that *are* near buyer/ship-to context, so a single-GSTIN
  invoice correctly yields ``None`` for it instead of duplicating the
  vendor's own GSTIN.

GSTIN's format is distinctive enough that a bare, unlabelled token
elsewhere in the document is still a safe candidate — unlike a
generic code or amount, it can't be confused with unrelated digits.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import List, Set, Tuple

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers
from Backend.Business_Layer.utils.extraction.base import (
    AVOID_BUYER,
    BELOW,
    Candidate,
    NEAREST,
    PREFER_BUYER,
    SAME_LINE,
    BaseFieldExtractor,
)

_CHECKSUM_BONUS = 5.0

# Checked in this order against the nearest heading above a GSTIN
# token; whichever section it falls under decides whether it's the
# vendor's own registration or someone else's.
_SECTION_MARKERS = OrderedDict([
    ("BUYER", anchors.BUYER_MARKERS),
    ("SHIP_TO", anchors.SHIP_TO_MARKERS),
    ("SELLER", anchors.VENDOR_SECTION_ANCHORS),
])


class _GSTINExtractorBase(BaseFieldExtractor):
    """Shared candidate collection for both GSTIN fields."""

    context_polarity = AVOID_BUYER

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)
        claimed: Set[Tuple[int, int, str]] = set()

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, anchors.VENDOR_GSTIN_ANCHORS):
            page_lines = lines_by_page[hit.line.page_number]

            candidates.extend(
                self._scan_line(hit.line, page_lines, hit.matched_text, SAME_LINE, claimed, offset=hit.end_char)
            )
            for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
                candidates.extend(self._scan_line(below, page_lines, hit.matched_text, BELOW, claimed))

        for line in lines:
            candidates.extend(self._scan_line(line, lines_by_page[line.page_number], None, NEAREST, claimed))

        return candidates

    def _scan_line(self, line, page_lines, anchor_text, relation, claimed, offset: int = 0) -> List[Candidate]:
        matches = list(normalizers.GSTIN_PATTERN.finditer(line.text[offset:]))
        if not matches:
            return []

        section = geometry.nearest_section(page_lines, line, _SECTION_MARKERS)
        near_buyer = section == "BUYER"
        near_ship_to = section == "SHIP_TO"
        near_seller = section == "SELLER"

        # Symmetric hard filter, not just a score penalty: a GSTIN
        # confirmed to sit in buyer/ship-to context is never a
        # candidate for VendorGSTINExtractor, no matter how starved of
        # alternatives it is — reporting the buyer's own GSTIN as the
        # vendor's is worse than returning None. BuyerGSTINExtractor
        # is the mirror image: without this, a single-GSTIN invoice
        # would return the vendor's own GSTIN as the buyer's too.
        if self.context_polarity == PREFER_BUYER and not (near_buyer or near_ship_to):
            return []
        if self.context_polarity == AVOID_BUYER and (near_buyer or near_ship_to):
            return []

        inside_table = geometry.looks_like_table_row(line)

        found: List[Candidate] = []
        for match in matches:
            raw = match.group(1)
            key = (line.page_number, line.line_index, raw.upper())
            if key in claimed:
                continue
            claimed.add(key)
            found.append(
                self._build_candidate(raw, line, anchor_text, relation, near_buyer, near_ship_to, near_seller, inside_table)
            )
        return found

    def _build_candidate(
        self, raw_token, line, anchor_text, relation, near_buyer, near_ship_to, near_seller, inside_table
    ) -> Candidate:
        try:
            value = normalizers.normalize_gstin(raw_token)
            valid = True
        except ValueError:
            value = None
            valid = False

        candidate = Candidate(
            value=value,
            raw_text=raw_token,
            page_number=line.page_number,
            line=line,
            anchor_text=anchor_text,
            has_anchor=relation != NEAREST,
            relation=relation,
            valid_format=valid,
            near_buyer=near_buyer,
            near_ship_to=near_ship_to,
            near_seller=near_seller,
            inside_table=inside_table,
            context_polarity=self.context_polarity,
        )
        if valid and normalizers.gstin_checksum_valid(value):
            candidate.score_bonus += _CHECKSUM_BONUS
        return candidate


class VendorGSTINExtractor(_GSTINExtractorBase):
    """The seller's own GSTIN — the field historically named ``gstin``."""

    field_name = "gstin"
    context_polarity = AVOID_BUYER


class BuyerGSTINExtractor(_GSTINExtractorBase):
    """Buyer's GSTIN, when present. Optional — ``None`` if only one GSTIN exists."""

    field_name = "buyer_gstin"
    context_polarity = PREFER_BUYER
