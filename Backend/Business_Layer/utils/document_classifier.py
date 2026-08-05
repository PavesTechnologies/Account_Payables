# Backend/Business_Layer/utils/document_classifier.py
"""Technical (non-business) document classification.

This module answers two narrow questions and nothing else:

1. What container format is this file? (``detect_file_type``)
2. Does this PDF page have a usable text layer, or is it effectively
   a scanned image? (``classify_pdf_page``)

It has no dependency on PyMuPDF, OpenCV, or any OCR engine — it only
inspects raw bytes and already-extracted text, so it stays trivially
unit-testable and reusable regardless of which library produced the
text.
"""

from pathlib import Path

from Backend.API_Layer.interface.invoice_process_interface import TechnicalDocumentType

# from __future__ import annotations

import fitz

DEFAULT_MIN_WORDS = 20

EXPECTED_INVOICE_KEYWORDS = (
    "invoice",
    "invoice no",
    "invoice number",
    "gst",
    "gstin",
    "tax",
    "total",
    "amount",
    "bill",
    "vendor",
)

_PDF_MAGIC = b"%PDF"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_TIFF_MAGIC_LE = b"II*\x00"
_TIFF_MAGIC_BE = b"MM\x00*"

_EXTENSION_FALLBACK = {
    ".pdf": "PDF",
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
}

# A page is considered to have a usable text layer once it has at
# least this many whitespace-separated tokens.
DEFAULT_MIN_WORD_COUNT = 5


def detect_file_type(filename: str, content: bytes) -> str:
    """Detect the container format of an uploaded file.

    Inspects magic bytes first (authoritative) and falls back to the
    filename extension only when the byte signature is inconclusive.

    Returns one of ``"PDF"``, ``"PNG"``, ``"JPEG"``, ``"TIFF"`` or
    ``"UNKNOWN"``. Note this identifies the *container*, not whether a
    PDF is text-based or scanned — see :func:`classify_pdf_page` for
    that distinction.
    """
    header = content[:16]

    if header.startswith(_PDF_MAGIC):
        return "PDF"
    if header.startswith(_PNG_MAGIC):
        return "PNG"
    if header.startswith(_JPEG_MAGIC):
        return "JPEG"
    if header.startswith(_TIFF_MAGIC_LE) or header.startswith(_TIFF_MAGIC_BE):
        return "TIFF"

    suffix = Path(filename).suffix.lower()
    return _EXTENSION_FALLBACK.get(suffix, "UNKNOWN")


def container_to_document_type(container: str) -> TechnicalDocumentType:
    """Map a non-PDF container format directly to a TechnicalDocumentType.

    PDFs are intentionally excluded — their final type (TEXT_PDF vs
    SCANNED_PDF) depends on per-page classification, which only the
    caller can aggregate once pages have been extracted.
    """
    return {
        "PNG": TechnicalDocumentType.PNG,
        "JPEG": TechnicalDocumentType.JPEG,
        "TIFF": TechnicalDocumentType.TIFF,
    }.get(container, TechnicalDocumentType.UNKNOWN)


def classify_pdf_page(text: str, min_word_count: int = DEFAULT_MIN_WORD_COUNT) -> bool:
    """Classify a single PDF page as scanned (True) or text-based (False).

    A page is treated as scanned when its native text layer yields
    fewer than ``min_word_count`` tokens.
    """
    word_count = len(text.split())
    return word_count < min_word_count
def is_text_usable(fitz_page, text):

    text = text.strip()

    words = fitz_page.get_text("words")

    if _is_probably_image_only_page(fitz_page):
        return False

    if len(text) < 30:
        return False

    if len(words) < 10:
        return False

    if len(text.split()) < 8:
        return False

    return True
def _printable_ratio(text: str) -> float:

    if not text:
        return 0.0

    printable = sum(ch.isprintable() for ch in text)

    return printable / len(text)
def _keyword_hits(text: str) -> int:

    text = text.lower()

    return sum(
        keyword in text
        for keyword in EXPECTED_INVOICE_KEYWORDS
    )
def _is_probably_image_only_page(
    page: fitz.Page,
) -> bool:
    """
    Detect pages that mostly consist of images.

    This helps identify scanned PDFs that contain little or
    no usable native text.
    """

    images = page.get_images(full=True)

    if not images:
        return False

    page_area = page.rect.width * page.rect.height

    for image in page.get_image_rects(images[0][0]):

        image_area = image.width * image.height

        coverage = image_area / page_area

        if coverage > 0.80:
            return True

    return False
