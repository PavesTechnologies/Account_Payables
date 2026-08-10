# Backend/Business_Layer/utils/extraction/geometry.py
"""Word/line geometry helpers shared by every extractor.

OCR engines and PyMuPDF's native text layer both populate
``Page.words`` as a flat, unordered list of bounding boxes with no
line structure. Every geometry-aware extractor ("same line as
anchor", "right of anchor", "below anchor", "nearest neighbor") needs
that structure reconstructed first — this module does it once so no
extractor re-implements line clustering.

Clustering mirrors ``ocr_provider.words_to_text`` (vertical-proximity
banding, then left-to-right within a band) so geometry-based
extraction agrees with the page's reconstructed text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from Backend.API_Layer.interface.invoice_process_interface import Page, Word

TABLE_HEADER_KEYWORDS = (
    # Deliberately excludes generic words like "amount" or "total" —
    # those appear in plenty of legitimate single-value summary lines
    # ("Taxable Amount: 5000.00", "Amount Due: 5500.00") that must NOT
    # be mistaken for an item-table header/row.
    "description", "qty", "quantity", "rate", "hsn", "sac", "item",
    "unit price", "particulars",
)
_TABLE_AMOUNT_PATTERN = re.compile(r"\d[\d,]*\.\d{2}")
_MIN_TABLE_AMOUNT_HITS = 3

# Two or more tax labels crammed onto one line (e.g. "CGST: SGST:
# Total GST: 14,000.00") is a per-item tax breakdown cell, never a
# real "CGST: <value>" summary line — a genuine summary always gives
# each tax its own line. Catches this even when the line has too few
# decimal amounts to trip the generic table-row heuristic above.
_TAX_LABEL_PATTERNS = (r"\bcgst\b", r"\bsgst\b", r"\bigst\b", r"total\s*gst")
_MIN_TAX_LABEL_HITS = 2


@dataclass
class Line:
    """One reconstructed line of words on a page."""

    page_number: int
    line_index: int
    words: List[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def y0(self) -> float:
        return min(w.y0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def y1(self) -> float:
        return max(w.y1 for w in self.words)


@dataclass
class AnchorHit:
    """One anchor label found on one line."""

    line: Line
    pattern: str
    matched_text: str
    end_char: int


def cluster_words_into_lines(words: Sequence[Word], page_number: int) -> List[Line]:
    """Group words into left-to-right, top-to-bottom lines by vertical proximity."""
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))
    heights = [w.y1 - w.y0 for w in sorted_words if w.y1 > w.y0]
    line_threshold = (sum(heights) / len(heights) * 0.6) if heights else 10.0

    groups: List[List[Word]] = [[sorted_words[0]]]
    current_y = sorted_words[0].y0
    for word in sorted_words[1:]:
        if abs(word.y0 - current_y) <= line_threshold:
            groups[-1].append(word)
        else:
            groups.append([word])
            current_y = word.y0

    lines: List[Line] = []
    for index, group in enumerate(groups):
        group.sort(key=lambda w: w.x0)
        lines.append(Line(page_number=page_number, line_index=index, words=group))
    return lines


def all_lines(pages: Sequence[Page]) -> List[Line]:
    """Cluster every page's words into lines, in document order."""
    lines: List[Line] = []
    for page in pages:
        lines.extend(cluster_words_into_lines(page.words, page.page_number))
    return lines


def group_lines_by_page(lines: Sequence[Line]) -> Dict[int, List[Line]]:
    """Bucket already-clustered lines back by page number for below/context lookups."""
    grouped: Dict[int, List[Line]] = {}
    for line in lines:
        grouped.setdefault(line.page_number, []).append(line)
    return grouped


def find_anchors(lines: Sequence[Line], anchor_patterns: Sequence[str]) -> List[AnchorHit]:
    """Find every line that contains one of ``anchor_patterns`` — never just the first.

    Skips lines that look like an item-table column *header* (e.g.
    "Description Qty Rate HSN CGST SGST IGST Total"): a field name
    showing up as a table heading is not a labelled value and must
    not be treated as one — the real summary line elsewhere in the
    document is what should win.

    Deliberately narrower than ``looks_like_table_row``: a line can
    look table-ish (several decimal amounts, two tax labels) purely
    because OCR line-clustering merged it with an adjacent tabular
    row, while still containing a perfectly genuine "Add: CGST 852.88"
    label+value. Excluding *those* from anchor search entirely would
    throw away real data; ``inside_table`` scoring already penalizes
    them appropriately without discarding them outright.
    """
    hits: List[AnchorHit] = []
    for line in lines:
        if looks_like_table_header(line):
            continue
        text = line.text
        for pattern in anchor_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hits.append(AnchorHit(line=line, pattern=pattern, matched_text=match.group(0).strip(), end_char=match.end()))
    return hits


def find_same_line(hit: AnchorHit) -> Line:
    """The line an anchor was found on (named per the extraction-strategy spec)."""
    return hit.line


def extract_right_of_anchor(hit: AnchorHit) -> str:
    """Text on the anchor's own line, after the anchor label."""
    return hit.line.text[hit.end_char:]

def horizontal_gap(a: Line, b: Line) -> float:
    if a.x1 < b.x0:
        return b.x0 - a.x1
    if b.x1 < a.x0:
        return a.x0 - b.x1
    return 0.0


def horizontal_overlap(a: Line, b: Line) -> float:
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    return max(0.0, overlap)


def is_same_spatial_region(
    anchor: Line,
    candidate: Line,
    max_horizontal_gap: float = 150.0,
) -> bool:
    gap = horizontal_gap(anchor, candidate)
    overlap = horizontal_overlap(anchor, candidate)

    return overlap > 0 or gap <= max_horizontal_gap


def extract_below_anchor(page_lines: Sequence[Line], hit: AnchorHit, max_lines: int = 2) -> List[Line]:
    """Up to ``max_lines`` lines directly below the anchor's line on the same page."""
    below = [line for line in page_lines if line.line_index > hit.line.line_index]
    below.sort(key=lambda line: line.line_index)
    return below[:max_lines]


def nearby_text(page_lines: Sequence[Line], line: Line, span: int = 2) -> str:
    """Text of every line within ``span`` lines of ``line`` (inclusive), for context checks."""
    lo, hi = line.line_index - span, line.line_index + span
    picked = [l for l in page_lines if lo <= l.line_index <= hi]
    return "\n".join(l.text for l in picked)


def nearest_section(
    page_lines: Sequence[Line],
    line: Line,
    pattern_groups: "Dict[str, Sequence[str]]",
    max_lookback: int = 12,
) -> Optional[str]:
    """Which section (Buyer/Ship To/Seller/...) a line belongs to, by its nearest heading.

    Scans upward from ``line`` (inclusive) for the nearest preceding
    line matching one of ``pattern_groups`` and returns that group's
    key, or ``None`` if none is found within ``max_lookback`` lines.

    A fixed-size *symmetric* window (±N lines) is the wrong tool for
    this: a value 3 lines above a "Bill To" heading is not "near the
    buyer section" just because it's within N lines of it — it likely
    belongs to whatever heading precedes *it*. Scanning upward for the
    nearest actual heading classifies by real document structure
    instead of raw line distance.

    The scan also stops the moment it crosses an item-table row —
    the header/buyer/consignee block above an invoice's item table and
    the tax-summary block below it are different sections even though
    nothing but the table sits between them, so a stale "Bill To"
    heading from three inches up the page must never leak into a
    Subtotal/Total line found below the table.
    """
    by_index = {candidate.line_index: candidate for candidate in page_lines}
    floor = line.line_index - max_lookback

    for index in range(line.line_index, floor - 1, -1):
        candidate = by_index.get(index)
        if candidate is None:
            continue
        matches = []
        for key, patterns in pattern_groups.items():
            for pattern in patterns:
                match = re.search(pattern, candidate.text, re.IGNORECASE)
                if match:
                    matches.append((match.start(), key))
        if matches:
            return min(matches, key=lambda item: item[0])[1]
        if looks_like_table_row(candidate):
            return None

    return None


def nearest_words(anchor_line: Line, words: Sequence[Word], k: int = 5) -> List[Word]:
    """The ``k`` words nearest an anchor line's centroid, by Euclidean distance."""
    acx = (anchor_line.x0 + anchor_line.x1) / 2
    acy = (anchor_line.y0 + anchor_line.y1) / 2

    def distance(word: Word) -> float:
        wcx = (word.x0 + word.x1) / 2
        wcy = (word.y0 + word.y1) / 2
        return ((wcx - acx) ** 2 + (wcy - acy) ** 2) ** 0.5

    return sorted(words, key=distance)[:k]


def looks_like_table_header(line: Line) -> bool:
    """Heuristic: is this line an item-table column *heading* (not a value line)?

    Narrower than :func:`looks_like_table_row` on purpose — used to
    exclude a line from anchor search entirely, so it must only catch
    lines that could never be a genuine "Label: Value" pair, such as
    "Description Qty Rate HSN CGST SGST IGST Total".
    """
    text_lower = line.text.lower()
    return any(keyword in text_lower for keyword in TABLE_HEADER_KEYWORDS)


def looks_like_table_row(line: Line) -> bool:
    """Heuristic: does this line look like an item-table header or row?

    Broader than :func:`looks_like_table_header` — also flags rows
    dense with decimal amounts or multiple tax labels, even if a
    genuine label+value happens to share the line (OCR line-clustering
    sometimes merges a real summary line with an adjacent tabular
    row). Used only to *penalize* candidates via ``inside_table``,
    never to discard an anchor outright — see :func:`find_anchors`.
    """
    if looks_like_table_header(line):
        return True
    if len(_TABLE_AMOUNT_PATTERN.findall(line.text)) >= _MIN_TABLE_AMOUNT_HITS:
        return True
    tax_label_hits = sum(1 for pattern in _TAX_LABEL_PATTERNS if re.search(pattern, line.text, re.IGNORECASE))
    return tax_label_hits >= _MIN_TAX_LABEL_HITS
