# Backend/Business_Layer/utils/document_quality.py
"""Document quality assessment.

Determines whether the text extracted so far (native PDF text layer
or RapidOCR) is good enough to feed into field extraction, or whether
the caller should escalate to AWS Textract. This module never calls
AWS directly — it only produces a DocumentQuality verdict for the
service layer to act on.
"""
from __future__ import annotations

from typing import List

from Backend.API_Layer.interface.intake_process_interface import DocumentQuality, DocumentResult, Page

MIN_WORDS_PER_PAGE = 15
MIN_OCR_CONFIDENCE = 60.0
MIN_PAGE_COMPLETENESS_RATIO = 0.8
POOR_QUALITY_THRESHOLD = 60.0

INVOICE_KEYWORDS = (
    "invoice",
    "gstin",
    "gst no",
    "total",
    "tax",
    "bill to",
    "amount due",
    "due date",
    "po number",
    "purchase order",
)


def calculate_quality(document: DocumentResult) -> DocumentQuality:
    """Score a DocumentResult's extraction quality on a 0-100 scale.

    Checks empty pages, word density, OCR confidence (where OCR ran),
    invoice-keyword presence, and how many pages actually yielded
    usable text ("extraction completeness").
    """
    reasons: List[str] = []
    score = 100.0

    if not document.pages:
        return DocumentQuality(score=0.0, is_poor=True, reasons=["Document has no pages"])

    empty_pages = [p.page_number for p in document.pages if not p.text.strip()]
    if empty_pages:
        score -= 30.0
        reasons.append(f"Empty pages with no extracted text: {empty_pages}")

    word_counts = [len(p.text.split()) for p in document.pages]
    avg_words = sum(word_counts) / len(word_counts)
    if avg_words < MIN_WORDS_PER_PAGE:
        score -= 20.0
        reasons.append(
            f"Low average word density ({avg_words:.1f} words/page, expected >= {MIN_WORDS_PER_PAGE})"
        )

    ocr_confidences = [p.ocr_confidence for p in document.pages if p.ocr_confidence is not None]
    if ocr_confidences:
        avg_ocr_confidence = sum(ocr_confidences) / len(ocr_confidences)
        if avg_ocr_confidence < MIN_OCR_CONFIDENCE:
            score -= 25.0
            reasons.append(
                f"Low OCR confidence ({avg_ocr_confidence:.1f}, expected >= {MIN_OCR_CONFIDENCE})"
            )

    combined_text = " ".join(p.text for p in document.pages).lower()
    if not any(keyword in combined_text for keyword in INVOICE_KEYWORDS):
        score -= 15.0
        reasons.append("No recognizable invoice keywords found")

    complete_pages = sum(1 for p in document.pages if len(p.text.split()) >= MIN_WORDS_PER_PAGE)
    completeness_ratio = complete_pages / len(document.pages)
    if completeness_ratio < MIN_PAGE_COMPLETENESS_RATIO:
        score -= 10.0
        reasons.append(
            f"Only {complete_pages}/{len(document.pages)} pages extracted completely"
        )

    score = max(0.0, min(100.0, score))
    return DocumentQuality(score=score, is_poor=score < POOR_QUALITY_THRESHOLD, reasons=reasons)
def calculate_quality_score(
    pages: list[Page],
) -> float:

    score = 0.0

    # 1. OCR confidence
    confidences = [
        p.ocr_confidence
        for p in pages
        if p.ocr_confidence is not None
    ]

    if confidences:
        score += (sum(confidences) / len(confidences)) * 40
    else:
        # Native PDF
        score += 40

    # 2. Text coverage
    total_words = sum(len(p.words) for p in pages)

    if total_words >= 150:
        score += 20
    elif total_words >= 80:
        score += 16
    elif total_words >= 30:
        score += 10
    else:
        score += 5

    # 3. Keywords
    keywords = [
        "invoice",
        "gstin",
        "total",
        "amount",
        "tax",
    ]

    text = " ".join(page.text.lower() for page in pages)

    hits = sum(k in text for k in keywords)

    score += min(hits * 4, 20)

    # 4. Empty pages
    non_empty = sum(
        bool(page.text.strip())
        for page in pages
    )

    score += (non_empty / len(pages)) * 10

    # 5. Character quality
    printable = sum(
        c.isprintable()
        for c in text
    )

    ratio = printable / max(len(text), 1)

    score += ratio * 10

    return round(score, 2)