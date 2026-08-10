# Backend/Business_Layer/services/invoice_process_service.py
"""Invoice processing orchestration.

This service only sequences calls into Backend.Business_Layer.utils.* —
it does not implement OCR, parsing, validation, or matching itself.
/process-invoice (production) and the developer endpoints
(/upload-document, /extract-fields, /validate-fields, /match-vendor)
all call into the same functions defined here, so behavior never
diverges between debug and production paths.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from Backend.Business_Layer.utils import (
    confidence as confidence_util,
    document_quality,
    field_extractors,
    image_utils,
    ocr_provider,
    pdf_utils,
    validators,
    vendor_matcher,
)
from Backend.Business_Layer.utils.document_classifier import (
    container_to_document_type,
    detect_file_type,
)
from Backend.Business_Layer.utils.document_quality import calculate_quality_score
from Backend.Business_Layer.utils.exceptions import UnsupportedFileType
from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoice,
    FinalResponse,
    Page,
    TechnicalDocumentType,
    ValidationResult,
    VendorMatch,
    Word,
    UploadDocumentResponse,
    UploadPageSummary,
)
from Backend.Business_Layer.utils.vendor_matcher import match_vendor
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
logger = logging.getLogger(__name__)

_IMAGE_CONTAINERS = {"PNG", "JPEG", "TIFF"}


def _average_word_confidence(words):
    scored = [w.confidence for w in words if w.confidence is not None]

    if not scored:
        return None

    avg = sum(scored) / len(scored)

    if avg > 1:
        avg /= 100

    return round(avg, 4)


def _ocr_page(page: Page, page_image_bytes: bytes) -> None:
    """Run OCR over one page's rasterized image and fill in its words/text in place."""
    image = image_utils.load_image(page_image_bytes)
    cv_image = image_utils.convert_to_cv(image)
    words = ocr_provider.extract_words(cv_image)

    page.words = words
    page.text = ocr_provider.words_to_text(words)
    page.ocr_confidence = _average_word_confidence(words)


def _extract_pdf(filename: str, content: bytes) -> DocumentResult:
    doc = pdf_utils.open_pdf(content)
    try:
        pages = pdf_utils.extract_text_layer(doc)

        for page in pages:
            if page.is_scanned:
                _ocr_page(page, pdf_utils.render_page(doc, page.page_number))

        technical_type = (
            TechnicalDocumentType.SCANNED_PDF
            if any(p.is_scanned for p in pages)
            else TechnicalDocumentType.TEXT_PDF
        )

        return DocumentResult(
            source_filename=filename,
            technical_document_type=technical_type,
            page_count=len(pages),
            pages=pages,
        )
    finally:
        doc.close()


def _extract_image(filename: str, content: bytes, container: str) -> DocumentResult:
    image = image_utils.load_image(content)

    page = Page(
        page_number=1,
        width=float(image.width),
        height=float(image.height),
        is_scanned=True,
    )
    _ocr_page(page, content)

    return DocumentResult(
        source_filename=filename,
        technical_document_type=container_to_document_type(container),
        page_count=1,
        pages=[page],
    )

def to_upload_response(result: DocumentResult) -> UploadDocumentResponse:
    return UploadDocumentResponse(
        status="SUCCESS",
        message="Document uploaded and text extracted successfully.",
        source_filename=result.source_filename,
        technical_document_type=result.technical_document_type.value,
        page_count=result.page_count,
        quality_score=calculate_quality_score(result.pages),
        pages=[
            UploadPageSummary(
                page_number=page.page_number,
                is_scanned=page.is_scanned,
                word_count=len(page.words),
                ocr_confidence=page.ocr_confidence,
            )
            for page in result.pages
        ],
    )


def extract_document(filename: str, content: bytes) -> DocumentResult:
    """Stages: upload -> technical classification -> text extraction (OCR where needed)."""
    container = detect_file_type(filename, content)

    if container == "PDF":
        return _extract_pdf(filename, content)

    if container in _IMAGE_CONTAINERS:
        return _extract_image(filename, content, container)

    raise UnsupportedFileType(f"Unsupported file type for '{filename}'")


def extract_invoice_fields(document: DocumentResult) -> ExtractedInvoice:
    """Stage: rule-based field extraction (anchors/regex/geometry, no AI)."""
    return field_extractors.extract_invoice_fields(document)


def validate_invoice(extracted: ExtractedInvoice) -> ValidationResult:
    """Stage: business validation, independent of extraction and vendor matching."""
    return validators.validate_invoice(extracted)



def _apply_textract_fallback(document: DocumentResult, filename: str) -> DocumentResult:
    """Escalate to AWS Textract when quality assessment flags the document as poor.

    AWS Textract integration is not implemented yet (see
    Backend.Business_Layer.utils.ocr_provider.aws_textract_extract) —
    until it lands, the existing OCR/native-text result is kept as-is.
    """
    try:
        return ocr_provider.aws_textract_extract(document)
    except NotImplementedError:
        logger.warning(
            "Document '%s' flagged as poor quality but AWS Textract is not yet "
            "integrated; continuing with existing extraction results",
            filename,
        )
        return document


def process_invoice(filename: str, content: bytes, db) -> FinalResponse:
    """Production pipeline: reuses every stage above plus quality-gated OCR fallback."""
    document = extract_document(filename, content)

    quality = document_quality.calculate_quality(document)
    if quality.poor:
        logger.warning(
            "Document '%s' flagged as poor quality (score=%.1f): %s",
            filename, quality.score, "; ".join(quality.reasons),
        )
        document = _apply_textract_fallback(document, filename)
        quality = document_quality.calculate_quality(document)

    extracted = extract_invoice_fields(document)
    validation = validate_invoice(extracted)
    vendor_match = match_vendor(extracted, db=db)
    final_confidence = confidence_util.calculate_confidence(
        document, quality, extracted, validation, vendor_match
    )

    return FinalResponse(
        document=document,
        extracted_invoice=extracted,
        validation=validation,
        vendor_match=vendor_match,
        confidence=final_confidence,
    )
def upload_to_db(invoice, db):
    invoice_dao = InvoiceDAO(db)
    invoice_dao.create_invoice(invoice)
