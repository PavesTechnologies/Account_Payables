# Backend/Business_Layer/utils/extraction/payment_terms.py
"""Payment terms extraction (e.g. "Net 30", "Immediate", "15 Days Credit")."""
from __future__ import annotations

import re
from typing import List

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult
from Backend.Business_Layer.utils.extraction import anchors, geometry
from Backend.Business_Layer.utils.extraction.base import BELOW, Candidate, SAME_LINE, BaseFieldExtractor

_TERM_PATTERN = re.compile(
    r"net\s*\d{1,3}(?:\s*days?)?|\d{1,3}\s*days?(?:\s*credit)?|immediate|"
    r"cash\s*on\s*delivery|\bcod\b|advance|due\s*on\s*receipt",
    re.IGNORECASE,
)


class PaymentTermsExtractor(BaseFieldExtractor):
    field_name = "payment_terms"

    def collect_candidates(self, document: DocumentResult) -> List[Candidate]:
        lines = geometry.all_lines(document.pages)
        lines_by_page = geometry.group_lines_by_page(lines)

        candidates: List[Candidate] = []
        for hit in geometry.find_anchors(lines, anchors.PAYMENT_TERMS_ANCHORS):
            page_lines = lines_by_page[hit.line.page_number]
            remainder = geometry.extract_right_of_anchor(hit)

            match = _TERM_PATTERN.search(remainder)
            if match:
                candidates.append(self._build(match.group(0), hit.line, hit, SAME_LINE))
            else:
                cleaned = remainder.strip(" :-\t")
                if cleaned:
                    candidates.append(self._build(cleaned, hit.line, hit, SAME_LINE))

            for below in geometry.extract_below_anchor(page_lines, hit, max_lines=1):
                match = _TERM_PATTERN.search(below.text)
                if match:
                    candidates.append(self._build(match.group(0), below, hit, BELOW))

        return candidates

    def _build(self, raw_text, line, hit, relation) -> Candidate:
        value = raw_text.strip().title() or None
        return Candidate(
            value=value,
            raw_text=raw_text,
            page_number=line.page_number,
            line=line,
            anchor_text=hit.matched_text,
            relation=relation,
            valid_format=value is not None,
            inside_table=geometry.looks_like_table_row(line),
        )
