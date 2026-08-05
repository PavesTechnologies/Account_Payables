# Backend/Business_Layer/utils/ocr_provider.py
"""OCR engine abstraction.

Every caller in the pipeline should only ever use the module-level
:func:`extract_words`. It hides which engine is actually doing the
work behind the ``OCRProvider`` interface, so the engine can later be
swapped for PaddleOCR, EasyOCR, or AWS Textract (see
:func:`aws_textract_extract`) without touching field extraction,
quality assessment, or the service layer.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Protocol

import numpy as np

from Backend.Business_Layer.utils.exceptions import OCRFailure
from Backend.API_Layer.interface.invoice_process_interface import DocumentResult, Word


class OCRProvider(Protocol):
    """Interface every OCR engine implementation must satisfy."""

    def extract_words(self, image: np.ndarray) -> List[Word]:
        ...


class RapidOCRProvider:
    """Default OCR engine: RapidOCR running on ONNX Runtime."""

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OCRFailure(
                "rapidocr_onnxruntime is not installed; add it to requirements.txt"
            ) from exc

        self._engine = RapidOCR()

    def extract_words(self, image: np.ndarray) -> List[Word]:
        try:
            result, _ = self._engine(image)
        except Exception as exc:
            raise OCRFailure(f"RapidOCR failed to process image: {exc}") from exc

        if not result:
            return []

        words: List[Word] = []
        for box, text, score in result:
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            words.append(
                Word(
                    text=text,
                    x0=float(min(xs)),
                    y0=float(min(ys)),
                    x1=float(max(xs)),
                    y1=float(max(ys)),
                    confidence=float(score) * 100.0,
                )
            )
        return words


@lru_cache(maxsize=1)
def get_ocr_provider() -> OCRProvider:
    """Return the process-wide OCR engine instance, initializing it lazily.

    Cached (rather than a plain module global) so the expensive ONNX
    model load happens at most once per process, while still allowing
    tests to bypass it by calling a provider directly.
    """
    return RapidOCRProvider()


def extract_words(image: np.ndarray) -> List[Word]:
    """Extract words with bounding boxes and confidence from an image.

    This is the single entry point the rest of the pipeline should
    call — it is completely engine-agnostic.
    """
    return get_ocr_provider().extract_words(image)


def words_to_text(words: List[Word]) -> str:
    """Reconstruct newline-separated text from OCR words using their bounding boxes.

    OCR engines return words as independent boxes with no inherent line
    structure. Downstream field extraction (e.g. VendorNameExtractor)
    relies on "rest of the line" logic, so words are clustered into
    lines by vertical proximity and ordered left-to-right within each
    line — matching how PyMuPDF's native "text" mode reads.
    """
    if not words:
        return ""

    sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))
    heights = [w.y1 - w.y0 for w in sorted_words if w.y1 > w.y0]
    line_threshold = (sum(heights) / len(heights) * 0.6) if heights else 10.0

    lines: List[List[Word]] = [[sorted_words[0]]]
    current_y = sorted_words[0].y0
    for word in sorted_words[1:]:
        if abs(word.y0 - current_y) <= line_threshold:
            lines[-1].append(word)
        else:
            lines.append([word])
            current_y = word.y0

    line_strings = []
    for line in lines:
        line.sort(key=lambda w: w.x0)
        line_strings.append(" ".join(w.text for w in line))

    return "\n".join(line_strings)


def aws_textract_extract(document: DocumentResult) -> DocumentResult:
    """Placeholder for future AWS Textract integration.

    Intended to re-run OCR on pages flagged as poor quality using AWS
    Textract for higher-accuracy extraction on difficult scans, and
    return an updated DocumentResult. Not implemented yet — requires
    AWS credentials and boto3 wiring, which is out of scope until the
    Textract integration is scheduled.
    """
    raise NotImplementedError("AWS Textract integration is not yet implemented")
