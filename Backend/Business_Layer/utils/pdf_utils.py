# Backend/Business_Layer/utils/pdf_utils.py
"""PDF handling backed by PyMuPDF (fitz).

Responsible for opening PDFs, pulling their native text layer (words +
bounding boxes), and rasterizing individual pages to images so scanned
pages can be handed off to the OCR provider. Contains no business
logic — page-level scanned/text classification is delegated to
:mod:`Backend.Business_Layer.utils.document_classifier`.
"""
from __future__ import annotations

import fitz  # PyMuPDF

from Backend.Business_Layer.utils.document_classifier import is_text_usable
from Backend.Business_Layer.utils.exceptions import OCRFailure
from Backend.API_Layer.interface.intake_process_interface import Page, Word


def open_pdf(content: bytes) -> fitz.Document:
    """Open a PDF from raw bytes.

    Raises:
        OCRFailure: if the bytes cannot be parsed as a PDF.
    """
    try:
        return fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise OCRFailure(f"Unable to open PDF: {exc}") from exc


def extract_text_layer(doc: fitz.Document) -> List[Page]:
    """
    Extract native text and word coordinates from every PDF page.

    Each page is classified as either:
        - Text PDF (usable text layer)
        - Scanned PDF (requires OCR)

    The classification is heuristic-based and determines whether
    downstream OCR should run.
    """

    pages: List[Page] = []

    for page_index in range(doc.page_count):

        fitz_page = doc.load_page(page_index)

        # Extract native text
        text = (fitz_page.get_text("text") or "").strip()

        # Extract word-level coordinates
        raw_words = fitz_page.get_text("words") or []

        words = [
            Word(
                text=word[4],
                x0=float(word[0]),
                y0=float(word[1]),
                x1=float(word[2]),
                y1=float(word[3]),
            )
            for word in raw_words
        ]

        pages.append(
            Page(
                page_number=page_index + 1,
                width=float(fitz_page.rect.width),
                height=float(fitz_page.rect.height),
                text=text,
                words=words,
                is_scanned=not is_text_usable(
                    fitz_page=fitz_page,
                    text=text,
                ),
            )
        )

    return pages


def render_page(doc: fitz.Document, page_number: int, dpi: int = 300) -> bytes:
    """Rasterize a page (1-indexed) to PNG bytes at the given DPI.

    Used to hand scanned pages to the OCR provider, which expects an
    image rather than a PDF page object.
    """
    try:
        fitz_page = doc.load_page(page_number - 1)
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = fitz_page.get_pixmap(matrix=matrix)
        return pixmap.tobytes("png")
    except Exception as exc:
        raise OCRFailure(f"Unable to render page {page_number}: {exc}") from exc
