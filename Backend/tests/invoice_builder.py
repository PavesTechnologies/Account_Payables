# Backend/tests/invoice_builder.py
"""Synthetic ``DocumentResult`` construction for Document Intelligence tests.

Builds a plausible word/line geometry from a plain list of text
lines — one call site standing in for what PyMuPDF's text layer or
RapidOCR would normally hand the extraction engine. Lines are laid out
top-to-bottom in the order given, which is enough to exercise every
anchor/geometry/section-boundary rule in ``extraction/*`` without
depending on the (unchanged, out-of-scope) OCR/PDF layer itself.
"""
from __future__ import annotations

from typing import List

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult, Page, Word

_LINE_HEIGHT = 40
_TOP_MARGIN = 50
_BOTTOM_MARGIN = 100
_PAGE_WIDTH = 800.0


def build_document(lines: List[str], *, filename: str = "invoice.pdf") -> DocumentResult:
    """One-page synthetic document; ``lines`` in reading order top-to-bottom."""
    words: List[Word] = []
    y = float(_TOP_MARGIN)
    for line in lines:
        x = 40.0
        for token in line.split(" "):
            if not token:
                continue
            width = max(len(token) * 7.0, 6.0)
            words.append(Word(text=token, x0=x, y0=y, x1=x + width, y1=y + 12.0, confidence=98.0))
            x += width + 6.0
        y += _LINE_HEIGHT

    page_height = y + _BOTTOM_MARGIN
    page = Page(
        page_number=1,
        width=_PAGE_WIDTH,
        height=page_height,
        words=words,
        text="\n".join(lines),
    )
    return DocumentResult(source_filename=filename, page_count=1, pages=[page])
