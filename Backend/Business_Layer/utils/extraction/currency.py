# Backend/Business_Layer/utils/extraction/currency.py
"""Currency extraction.

Invoices rarely label currency explicitly with an anchor; the signal
is almost always a symbol/code sitting right next to an amount (₹,
Rs., INR, $, USD...). Candidates are gathered from anywhere in the
document, not just from a labelled anchor, then ranked the same way
as every other field — a currency token seen right next to the grand
total wins over one seen only once near a stray line-item figure.

A GST invoice (any document carrying a GSTIN) is necessarily an
Indian-domestic invoice, so when no explicit currency token exists
anywhere at all, INR is a safe last-resort default — scored low enough
that any real detected symbol/code still wins.
"""
from __future__ import annotations

import re
from typing import List

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry, normalizers
from Backend.Business_Layer.utils.extraction.base import NEAREST, Candidate, SAME_LINE, BaseFieldExtractor

_CURRENCY_TOKEN = re.compile(r"₹|Rs\.?|INR|USD|EUR|GBP|AED|SGD|\$|€|£", re.IGNORECASE)
_NEAR_TOTAL_BONUS = 15.0
_NEAR_TOTAL_LINE_SPAN = 1

# NEAREST alone scores 30 (see scoring.SCORE_NEAREST_FALLBACK) — this
# penalty pulls the GSTIN-implied default down to 16, just above
# scoring.MIN_ACCEPT_SCORE (15) so it's only ever picked when nothing
# else was found, and always loses to a real currency token (30+).
_GSTIN_IMPLIES_INR_PENALTY = -14.0


class CurrencyExtractor(BaseFieldExtractor):
    field_name = "currency"

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, anchors.CURRENCY_ANCHORS):
            match = _CURRENCY_TOKEN.search(geometry.extract_right_of_anchor(hit))
            if match:
                candidates.append(self._build(match.group(0), hit.line, hit.matched_text, SAME_LINE, has_anchor=True))

        total_line_indexes = {
            line.line_index for line in lines
            if anchors.matches_any(line.text, anchors.GRAND_TOTAL_ANCHORS)
        }

        for line in lines:
            near_total = any(abs(line.line_index - idx) <= _NEAR_TOTAL_LINE_SPAN for idx in total_line_indexes)
            for match in _CURRENCY_TOKEN.finditer(line.text):
                candidate = self._build(match.group(0), line, None, NEAREST, has_anchor=False)
                if near_total:
                    candidate.score_bonus += _NEAR_TOTAL_BONUS
                candidates.append(candidate)

        if document.pages and any(normalizers.GSTIN_PATTERN.search(page.text) for page in document.pages):
            fallback = Candidate(
                value="INR",
                raw_text="(inferred from GSTIN presence)",
                page_number=document.pages[0].page_number,
                anchor_text=None,
                has_anchor=False,
                relation=NEAREST,
                valid_format=True,
            )
            fallback.score_bonus = _GSTIN_IMPLIES_INR_PENALTY
            candidates.append(fallback)

        return candidates

    def _build(self, raw_token, line, anchor_text, relation, has_anchor) -> Candidate:
        try:
            value = normalizers.normalize_currency(raw_token)
            valid = True
        except ValueError:
            value = None
            valid = False

        return Candidate(
            value=value,
            raw_text=raw_token,
            page_number=line.page_number,
            line=line,
            anchor_text=anchor_text,
            has_anchor=has_anchor,
            relation=relation,
            valid_format=valid,
        )
