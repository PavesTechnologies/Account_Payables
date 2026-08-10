# Backend/Business_Layer/utils/confidence.py
"""Composite confidence scoring.

Combines the confidence signal from every pipeline stage into a
single FinalConfidence, weighted so extraction and validation
(the stages most likely to catch a bad read) dominate the score.
"""
from __future__ import annotations

from Backend.API_Layer.interface.invoice_process_interface import (
    ConfidenceResult,
    DocumentQuality,
    DocumentResult,
    ExtractedInvoice,
    ValidationResult,
    VendorMatch,
)

VALIDATION_ERROR_PENALTY = 20.0

# When pages went through OCR, blend the engine's own word-level
# confidence with the document quality score (word density,
# completeness, keyword presence) rather than trusting either alone.
OCR_ENGINE_WEIGHT = 0.7
OCR_QUALITY_WEIGHT = 0.3

WEIGHTS = {
    "ocr": 0.20,
    "extraction": 0.35,
    "validation": 0.25,
    "vendor": 0.20,
}

# Fields that are frequently and legitimately absent from a valid
# invoice (single-GSTIN invoices have no buyer_gstin, cash invoices
# have no due_date/payment_terms, non-PO invoices have no po_number,
# many invoices carry no cess). Counting their "not found" 0.0
# confidence in the average would penalize a correct extraction the
# same as a genuine miss on a required field, so they're excluded from
# the average whenever the extractor came back empty for them.
OPTIONAL_FIELDS = frozenset({
    "due_date", "buyer_gstin", "po_number", "cess", "payment_terms", "currency",
    "tax_type", "tax_rate", "tax_amount",
})


def _ocr_confidence(document: DocumentResult, quality: DocumentQuality) -> float:
    scanned_confidences = [
        p.ocr_confidence for p in document.pages if p.is_scanned and p.ocr_confidence is not None
    ]
    if scanned_confidences:
        avg_engine_confidence = sum(scanned_confidences) / len(scanned_confidences)
        return avg_engine_confidence * OCR_ENGINE_WEIGHT + quality.score * OCR_QUALITY_WEIGHT

    # No OCR ran (native PDF text) — the quality score itself is the
    # best available signal for extraction reliability.
    return quality.score if document.pages else 0.0


def _extraction_confidence(extracted: ExtractedInvoice) -> float:
    scores = [
        conf for name, conf in extracted.field_confidences.items()
        if not (name in OPTIONAL_FIELDS and getattr(extracted, name, None) is None)
    ]
    return sum(scores) / len(scores) if scores else 0.0


def _validation_confidence(validation: ValidationResult) -> float:
    if validation.valid:
        return 100.0
    return max(0.0, 100.0 - VALIDATION_ERROR_PENALTY * len(validation.errors))


def calculate_confidence(
    document: DocumentResult,
    quality: DocumentQuality,
    extracted: ExtractedInvoice,
    validation: ValidationResult,
    vendor_match: VendorMatch,
) -> ConfidenceResult:
    """Calculate OCR, extraction, validation, vendor, and overall confidence."""
    ocr_confidence = _ocr_confidence(document, quality)
    extraction_confidence = _extraction_confidence(extracted)
    validation_confidence = _validation_confidence(validation)
    vendor_confidence = vendor_match.confidence

    overall_confidence = (
        ocr_confidence * WEIGHTS["ocr"]
        + extraction_confidence * WEIGHTS["extraction"]
        + validation_confidence * WEIGHTS["validation"]
        + vendor_confidence * WEIGHTS["vendor"]
    )

    return ConfidenceResult(
        ocr_confidence=round(ocr_confidence, 2),
        extraction_confidence=round(extraction_confidence, 2),
        validation_confidence=round(validation_confidence, 2),
        vendor_confidence=round(vendor_confidence, 2),
        overall_confidence=round(overall_confidence, 2),
    )
