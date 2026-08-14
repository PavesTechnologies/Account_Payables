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
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from Backend.Business_Layer.utils import (
    confidence as confidence_util,
    document_quality,
    field_extractors,
    image_utils,
    invoice_status,
    line_persistence,
    notifications,
    ocr_provider,
    pdf_utils,
    validators,
    vendor_auto_onboarding,
    vendor_matcher,
)
from Backend.Business_Layer.utils.document_classifier import (
    container_to_document_type,
    detect_file_type,
)
from Backend.Business_Layer.utils.document_quality import calculate_quality_score
from Backend.Business_Layer.utils.exceptions import (
    DuplicateInvoiceError,
    FieldExtractionError,
    UnsupportedFileType,
)
from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoice,
    FinalResponse,
    InvoiceLineReviewRequest,
    InvoiceOCRReviewRequest,
    InvoiceType,
    UploadInvoiceRequest,
    Page,
    TechnicalDocumentType,
    ValidationResult,
    VendorMatch,
    Word,
    UploadDocumentResponse,
    UploadPageSummary,
)
from Backend.Business_Layer.utils.vendor_auto_onboarding import get_numeric_system_config
from Backend.Business_Layer.utils.vendor_matcher import match_vendor
from Backend.Data_Access_Layer.dao.inbound_document_dao import InboundDocumentDAO
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceAttachment, InvoiceLine

logger = logging.getLogger(__name__)

_IMAGE_CONTAINERS = {"PNG", "JPEG", "TIFF"}

PO_MANDATORY_CONFIG_KEY = "PO_MANDATORY"
AUTO_APPROVAL_LIMIT_CONFIG_KEY = "AUTO_APPROVAL_LIMIT"
ISSUE_TYPE_PO_REQUIRED = "PO_REQUIRED"


def _config_bool(db, key: str) -> bool:
    config = MasterDAO(db).get_system_config_by_key(key)
    if config is None:
        return False
    return config.config_value.strip().lower() == "true"


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
@dataclass
class PersistenceOutcome:
    inbound_document_id: int
    invoice_id: Optional[int]
    invoice_status: str


def create_pending_inbound_document(filename: str, s3_key: str, db) -> InboundDocument:
    """Create the InboundDocument row before invoice processing starts.

    Committed immediately (its own transaction) so the record survives
    even if OCR/extraction/persistence fails afterward.
    """
    inbound_document = InboundDocument(
        source_type="UPLOAD",
        file_name=filename,
        file_path=s3_key,
        extraction_status="PENDING",
    )
    InboundDocumentDAO(db).create_inbound_document(inbound_document)
    db.commit()
    db.refresh(inbound_document)
    return inbound_document


def mark_inbound_document_failed(inbound_document: InboundDocument, db, final_response: Optional[FinalResponse] = None) -> None:
    inbound_document.extraction_status = "FAILED"
    if final_response is not None:
        inbound_document.extraction_confidence = _to_confidence_decimal(
            final_response.confidence.overall_confidence
        )
        inbound_document.raw_extracted_data = final_response.extracted_invoice.model_dump(mode="json")
    db.commit()


def _to_confidence_decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _resolve_currency_id(currency_code: Optional[str], db) -> tuple[int, Optional[str]]:
    """Map an extracted currency code to currency_id, falling back to a default.

    Returns (currency_id, issue_description). issue_description is None
    when the extracted currency mapped cleanly.
    """
    master_dao = MasterDAO(db)

    if currency_code:
        currency = master_dao.get_currency_by_code(currency_code)
        if currency is not None:
            return currency.currency_id, None

    fallback = master_dao.get_currency_by_code(invoice_status.DEFAULT_CURRENCY_CODE)
    if fallback is None:
        raise FieldExtractionError(
            f"Default currency '{invoice_status.DEFAULT_CURRENCY_CODE}' is not configured "
            "in the currency master"
        )

    reason = (
        f"Currency '{currency_code}' could not be mapped to a known currency; "
        f"defaulted to {invoice_status.DEFAULT_CURRENCY_CODE}"
        if currency_code
        else f"No currency was extracted; defaulted to {invoice_status.DEFAULT_CURRENCY_CODE}"
    )
    return fallback.currency_id, reason


def _resolve_payment_term_id(payment_terms_text: Optional[str], db) -> Optional[int]:
    if not payment_terms_text:
        return None
    term = MasterDAO(db).get_payment_term_by_name(payment_terms_text.strip())
    return term.payment_term_id if term else None


def _apply_line_tax_types(
    line_models: List[InvoiceLine],
    extracted_lines,
    vendor_id: int,
    invoice_date,
    db,
) -> None:
    """Best-effort tax_type_id mapping for lines that extracted a tax_type label.

    Requires an exact (country_id, tax_code, effective_from) match in the
    tax_type master, so this will often resolve to None — that's allowed
    by the schema and never blocks persistence.
    """
    try:
        vendor = VendorDAO(db).get_vendor_by_id(vendor_id)
        if vendor is None:
            return
        master_dao = MasterDAO(db)
        extracted_by_number = {line.line_number: line for line in extracted_lines}
        for model in line_models:
            source = extracted_by_number.get(model.line_number)
            if source is None or not source.tax_type:
                continue
            tax_type = master_dao.get_tax_type_by_code(
                country_id=vendor.country_id,
                tax_code=source.tax_type.strip().upper(),
                effective_from=invoice_date,
            )
            if tax_type is not None:
                model.tax_type_id = tax_type.tax_type_id
    except Exception:
        logger.exception("Best-effort line tax_type_id mapping failed; leaving tax_type_id unset")


def _sum_header_tax(extracted: ExtractedInvoice) -> Decimal:
    return sum(
        (value for value in (extracted.cgst, extracted.sgst, extracted.igst, extracted.cess, extracted.tax_amount) if value is not None),
        Decimal("0"),
    )


def _handle_vendor_not_found(
    extracted: ExtractedInvoice,
    inbound_document: InboundDocument,
    final_response: FinalResponse,
    db,
) -> PersistenceOutcome:
    """Path B: no vendor matched and automatic onboarding wasn't possible either.

    Only the InboundDocument is updated (full extraction kept in
    raw_extracted_data); Invoice creation is deferred to the manual
    OCR-review endpoint, once a vendor is supplied. See the vendor_id
    NOT NULL constraint discussion in the implementation plan.
    """
    inbound_document.vendor_id = None
    inbound_document.extraction_status = "EXTRACTED"
    inbound_document.extraction_confidence = _to_confidence_decimal(
        final_response.confidence.overall_confidence
    )
    inbound_document.raw_extracted_data = extracted.model_dump(mode="json")
    db.commit()

    notifications.notify_vendor_not_found(
        db, extracted, inbound_document, reason="No vendor matched the extracted GSTIN"
    )

    return PersistenceOutcome(
        inbound_document_id=inbound_document.inbound_document_id,
        invoice_id=None,
        invoice_status=invoice_status.RESPONSE_STATUS_PENDING_VENDOR_ONBOARDING,
    )


def persist_processed_invoice(
    final_response: FinalResponse,
    inbound_document: InboundDocument,
    db,
    user_id: str,
) -> PersistenceOutcome:
    """Persist the result of ``process_invoice`` per the Path A / Path B split.

    Path A (vendor matched, or auto-onboarded from a GST-verified GSTIN):
    Invoice + InvoiceLine(s) + InvoiceAttachment + InvoiceIssue(s) in one
    transaction, status OCR_REVIEW_PENDING. When a new vendor is
    auto-created, it is part of that same transaction (see
    vendor_auto_onboarding.auto_create_vendor_from_extraction) — nothing
    commits until the invoice itself is ready to commit.
    Path B (vendor not matched and not eligible for automatic onboarding):
    see _handle_vendor_not_found.
    """
    extracted = final_response.extracted_invoice
    print("Confidence Matrix:", final_response.confidence.overall_confidence)
    print("ocr_confidence:", final_response.confidence.ocr_confidence)
    print("extraction_confidence:", final_response.confidence.extraction_confidence)
    print("validation_confidence:", final_response.confidence.validation_confidence)
    unusable_reason = invoice_status.is_extraction_unusable(extracted)
    if unusable_reason is not None:
        mark_inbound_document_failed(inbound_document, db, final_response)
        raise FieldExtractionError(
            f"Extraction did not produce a usable invoice: {unusable_reason}"
        )

    vendor_match = final_response.vendor_match
    invoice_dao = InvoiceDAO(db)

    if vendor_match.matched and vendor_match.vendor_id:
        vendor_id = vendor_match.vendor_id
    else:
        try:
            vendor_id = vendor_auto_onboarding.auto_create_vendor_from_extraction(
                extracted, final_response.confidence.ocr_confidence, db, user_id,
            )
        except Exception:
            db.rollback()
            raise

        if vendor_id is None:
            return _handle_vendor_not_found(extracted, inbound_document, final_response, db)

    existing = invoice_dao.get_invoice_by_vendor_and_number(vendor_id, extracted.invoice_number)
    if existing is not None:
        inbound_document.invoice_id = existing.invoice_id
        inbound_document.vendor_id = vendor_id
        inbound_document.extraction_status = "EXTRACTED"
        db.commit()
        raise DuplicateInvoiceError(
            f"Invoice '{extracted.invoice_number}' already exists for vendor {vendor_id} "
            f"(invoice_id={existing.invoice_id})"
        )

    try:
        review_status = invoice_dao.get_status_by_code(invoice_status.STATUS_CODE_OCR_REVIEW_PENDING)
        if review_status is None:
            raise FieldExtractionError(
                f"Status '{invoice_status.STATUS_CODE_OCR_REVIEW_PENDING}' is not configured "
                "in status_master"
            )

        currency_id, currency_issue_reason = _resolve_currency_id(extracted.currency, db)
        payment_term_id = _resolve_payment_term_id(extracted.payment_terms, db)
        invoice_type = InvoiceType.PO if extracted.po_number else InvoiceType.NON_PO
        due_date = extracted.due_date if extracted.due_date is not None else extracted.invoice_date
        gross_amount = extracted.subtotal if extracted.subtotal is not None else extracted.total
        net_amount = extracted.total if extracted.total is not None else extracted.subtotal
        tax_amount = _sum_header_tax(extracted)

        invoice = Invoice(
            invoice_number=extracted.invoice_number,
            vendor_id=vendor_id,
            invoice_type=invoice_type.value,
            invoice_date=extracted.invoice_date,
            due_date=due_date,
            currency_id=currency_id,
            gross_amount=gross_amount,
            discount_amount=Decimal("0"),
            tax_amount=tax_amount,
            net_amount=net_amount,
            inbound_document_id=inbound_document.inbound_document_id,
            payment_term_id=payment_term_id,
            status_id=review_status.status_id,
            created_by=user_id,
            updated_by=user_id,
        )
        invoice_dao.create_invoice(invoice)

        line_models, skipped_line_count = line_persistence.build_invoice_line_models(extracted.lines)
        for line_model in line_models:
            line_model.invoice_id = invoice.invoice_id
        if line_models:
            _apply_line_tax_types(line_models, extracted.lines, vendor_id, extracted.invoice_date, db)
            invoice_dao.create_invoice_lines(line_models)

        invoice_dao.create_invoice_attachment(
            InvoiceAttachment(
                invoice_id=invoice.invoice_id,
                file_name=inbound_document.file_name,
                file_path=inbound_document.file_path,
            )
        )

        issues = []
        if final_response.confidence.overall_confidence < invoice_status.LOW_CONFIDENCE_THRESHOLD:
            issues.append(
                invoice_status.build_issue(
                    invoice_status.ISSUE_SOURCE_EXTRACTION,
                    invoice_status.ISSUE_TYPE_LOW_CONFIDENCE,
                    invoice_status.SEVERITY_WARNING,
                    f"Overall extraction confidence {final_response.confidence.overall_confidence:.1f} "
                    f"is below the {invoice_status.LOW_CONFIDENCE_THRESHOLD} review threshold",
                )
            )
        if not final_response.validation.valid:
            issues.append(
                invoice_status.build_issue(
                    invoice_status.ISSUE_SOURCE_VALIDATION,
                    invoice_status.ISSUE_TYPE_VALIDATION_FAILED,
                    invoice_status.SEVERITY_WARNING,
                    "; ".join(final_response.validation.errors) or "Validation reported errors",
                )
            )
        mismatch_reason = line_persistence.check_line_total_mismatch(extracted.lines, extracted)
        if mismatch_reason:
            issues.append(
                invoice_status.build_issue(
                    invoice_status.ISSUE_SOURCE_VALIDATION,
                    invoice_status.ISSUE_TYPE_LINE_TOTAL_MISMATCH,
                    invoice_status.SEVERITY_WARNING,
                    mismatch_reason,
                )
            )
        if currency_issue_reason:
            issues.append(
                invoice_status.build_issue(
                    invoice_status.ISSUE_SOURCE_VALIDATION,
                    invoice_status.ISSUE_TYPE_CURRENCY_UNMAPPED,
                    invoice_status.SEVERITY_WARNING,
                    currency_issue_reason,
                )
            )
        if skipped_line_count:
            issues.append(
                invoice_status.build_issue(
                    invoice_status.ISSUE_SOURCE_EXTRACTION,
                    invoice_status.ISSUE_TYPE_LINE_ITEMS_INCOMPLETE,
                    invoice_status.SEVERITY_INFO,
                    f"{skipped_line_count} extracted line item(s) lacked enough data to be saved",
                )
            )

        for issue in issues:
            issue.invoice_id = invoice.invoice_id
            invoice_dao.create_invoice_issue(issue)

        inbound_document.invoice_id = invoice.invoice_id
        inbound_document.vendor_id = vendor_id
        inbound_document.extraction_status = "EXTRACTED"
        inbound_document.extraction_confidence = _to_confidence_decimal(
            final_response.confidence.overall_confidence
        )
        inbound_document.raw_extracted_data = extracted.model_dump(mode="json")

        db.commit()
        db.refresh(invoice)

        return PersistenceOutcome(
            inbound_document_id=inbound_document.inbound_document_id,
            invoice_id=invoice.invoice_id,
            invoice_status=invoice_status.STATUS_CODE_OCR_REVIEW_PENDING,
        )
    except Exception:
        db.rollback()
        raise


def apply_ocr_review(
    inbound_document_id: int, review: InvoiceOCRReviewRequest, db, user_id: str
) -> Invoice:
    """Manual OCR review: create-or-update the invoice, always ending at PENDING_APPROVAL.

    Create branch fires when the document's vendor could not be
    auto-matched at /process-invoice time (Path B) — this is the first
    time an Invoice row is created for it, and ``review.vendor_id`` is
    required. Update branch corrects/confirms an already-created invoice
    (Path A) and resolves any outstanding InvoiceIssue rows.
    """
    inbound_document = InboundDocumentDAO(db).get_by_id(inbound_document_id)
    if inbound_document is None:
        raise ValueError(f"InboundDocument {inbound_document_id} not found")

    invoice_dao = InvoiceDAO(db)
    approval_status = invoice_dao.get_status_by_code(invoice_status.STATUS_CODE_PENDING_APPROVAL)
    if approval_status is None:
        raise FieldExtractionError(
            f"Status '{invoice_status.STATUS_CODE_PENDING_APPROVAL}' is not configured in status_master"
        )

    try:
        if inbound_document.invoice_id is None:
            invoice = _create_invoice_from_review(inbound_document, review, invoice_dao, user_id)
            inbound_document.invoice_id = invoice.invoice_id
            inbound_document.vendor_id = invoice.vendor_id
        else:
            invoice = invoice_dao.get_invoice_by_id(inbound_document.invoice_id)
            if invoice is None:
                raise ValueError(
                    f"Invoice {inbound_document.invoice_id} referenced by this document no longer exists"
                )
            _apply_review_updates(invoice, review, invoice_dao, user_id)
            for issue in invoice_dao.get_open_invoice_issues(invoice.invoice_id):
                issue.resolved_by = user_id
                issue.resolved_at = datetime.utcnow()

        invoice.status_id = approval_status.status_id
        invoice.updated_by = user_id

        if _config_bool(db, PO_MANDATORY_CONFIG_KEY) and invoice.po_id is None:
            po_required_issue = invoice_status.build_issue(
                invoice_status.ISSUE_SOURCE_VALIDATION,
                ISSUE_TYPE_PO_REQUIRED,
                invoice_status.SEVERITY_ERROR,
                "PO_MANDATORY is enabled but this invoice has no linked purchase order",
            )
            po_required_issue.invoice_id = invoice.invoice_id
            invoice_dao.create_invoice_issue(po_required_issue)

        _maybe_auto_approve(invoice, invoice_dao, db)

        db.commit()
        db.refresh(invoice)
        return invoice
    except Exception:
        db.rollback()
        raise


def _maybe_auto_approve(invoice: Invoice, invoice_dao: InvoiceDAO, db) -> None:
    """AUTO_APPROVAL_LIMIT (system_configuration): invoices at or below this
    amount skip manual approval entirely IF no open InvoiceIssue remains —
    per Database/Database_README.md Module 6, the fully-automated path never
    creates an InvoiceApproval row, it just moves straight to APPROVED.
    Only applies while the invoice is currently PENDING_APPROVAL.
    """
    pending_status = invoice_dao.get_status_by_code(invoice_status.STATUS_CODE_PENDING_APPROVAL)
    if pending_status is None or invoice.status_id != pending_status.status_id:
        return

    limit = get_numeric_system_config(db, AUTO_APPROVAL_LIMIT_CONFIG_KEY)
    if limit is None or invoice.net_amount > limit:
        return

    if invoice_dao.get_open_invoice_issues(invoice.invoice_id):
        return

    approved_status = invoice_dao.get_status_by_code("APPROVED")
    if approved_status is None:
        return

    invoice.status_id = approved_status.status_id


def _create_invoice_from_review(
    inbound_document: InboundDocument,
    review: InvoiceOCRReviewRequest,
    invoice_dao: InvoiceDAO,
    user_id: str,
) -> Invoice:
    if review.vendor_id is None:
        raise ValueError("vendor_id is required: this document's vendor was not auto-matched")
    missing = [
        name
        for name, value in (
            ("invoice_number", review.invoice_number),
            ("invoice_date", review.invoice_date),
            ("due_date", review.due_date),
            ("currency_id", review.currency_id),
            ("gross_amount", review.gross_amount),
            ("net_amount", review.net_amount),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"Missing required field(s) to create the invoice: {', '.join(missing)}")

    if invoice_dao.get_invoice_by_vendor_and_number(review.vendor_id, review.invoice_number) is not None:
        raise DuplicateInvoiceError(
            f"Invoice '{review.invoice_number}' already exists for vendor {review.vendor_id}"
        )

    invoice = Invoice(
        invoice_number=review.invoice_number,
        vendor_id=review.vendor_id,
        invoice_type=(review.invoice_type.value if review.invoice_type else InvoiceType.NON_PO.value),
        invoice_date=review.invoice_date,
        due_date=review.due_date,
        currency_id=review.currency_id,
        gross_amount=review.gross_amount,
        discount_amount=review.discount_amount if review.discount_amount is not None else Decimal("0"),
        tax_amount=review.tax_amount if review.tax_amount is not None else Decimal("0"),
        net_amount=review.net_amount,
        inbound_document_id=inbound_document.inbound_document_id,
        po_id=review.po_id,
        payment_term_id=review.payment_term_id,
        created_by=user_id,
        updated_by=user_id,
    )
    invoice_dao.create_invoice(invoice)

    if review.lines:
        line_models = [_line_review_to_model(invoice.invoice_id, line) for line in review.lines]
        invoice_dao.create_invoice_lines(line_models)

    return invoice


def _apply_review_updates(
    invoice: Invoice, review: InvoiceOCRReviewRequest, invoice_dao: InvoiceDAO, user_id: str
) -> None:
    simple_fields = (
        "vendor_id", "invoice_number", "invoice_date", "due_date", "currency_id",
        "gross_amount", "discount_amount", "tax_amount", "net_amount", "po_id",
        "payment_term_id",
    )
    for field_name in simple_fields:
        value = getattr(review, field_name)
        if value is not None:
            setattr(invoice, field_name, value)
    if review.invoice_type is not None:
        invoice.invoice_type = review.invoice_type.value

    if review.lines is None:
        return

    existing_by_number = {line.line_number: line for line in invoice.invoice_line}
    for line_review in review.lines:
        existing_line = existing_by_number.get(line_review.line_number)
        if existing_line is not None:
            _apply_line_review_updates(existing_line, line_review)
        else:
            invoice_dao.create_invoice_line(_line_review_to_model(invoice.invoice_id, line_review))


def _line_review_to_model(invoice_id: int, line_review: InvoiceLineReviewRequest) -> InvoiceLine:
    return InvoiceLine(
        invoice_id=invoice_id,
        line_number=line_review.line_number,
        description=line_review.description or "",
        quantity=line_review.quantity if line_review.quantity is not None else Decimal("1"),
        unit_price=line_review.unit_price if line_review.unit_price is not None else Decimal("0"),
        line_amount=line_review.line_amount if line_review.line_amount is not None else Decimal("0"),
        tax_amount=line_review.tax_amount if line_review.tax_amount is not None else Decimal("0"),
        tax_type_id=line_review.tax_type_id,
    )


def _apply_line_review_updates(existing_line: InvoiceLine, line_review: InvoiceLineReviewRequest) -> None:
    for field_name in ("description", "quantity", "unit_price", "line_amount", "tax_amount", "tax_type_id"):
        value = getattr(line_review, field_name)
        if value is not None:
            setattr(existing_line, field_name, value)


def get_review_queue(db, skip: int = 0, limit: int = 50) -> tuple[list, int, int]:
    """OCR review queue, derived from existing rows (no dedicated queue table):

    Path A: Invoice.status_code == OCR_REVIEW_PENDING (invoice already
    created, awaiting the AP Executive's confirmation).
    Path B: InboundDocument.extraction_status == EXTRACTED and invoice_id
    IS NULL (vendor was never matched, so no Invoice exists yet).

    Both sets are fetched in full (queue volume is operational, not
    unbounded) and merged by created_at/received_at descending before
    skip/limit is applied as one combined pagination window.
    """
    invoice_dao = InvoiceDAO(db)
    inbound_document_dao = InboundDocumentDAO(db)

    path_a_invoices = invoice_dao.get_invoices_by_status_code(invoice_status.STATUS_CODE_OCR_REVIEW_PENDING)
    path_b_documents = inbound_document_dao.get_awaiting_vendor_assignment()

    combined = [("A", invoice.created_at, invoice) for invoice in path_a_invoices]
    combined += [("B", document.received_at, document) for document in path_b_documents]
    combined.sort(key=lambda entry: entry[1], reverse=True)

    window = combined[skip: skip + limit]

    items = []
    for path, _, record in window:
        if path == "A":
            items.append({
                "path": "PATH_A",
                "inbound_document_id": record.inbound_document_id,
                "invoice_id": record.invoice_id,
                "invoice_number": record.invoice_number,
                "vendor_id": record.vendor_id,
                "file_name": None,
                "status_code": invoice_status.STATUS_CODE_OCR_REVIEW_PENDING,
                "net_amount": record.net_amount,
                "extraction_confidence": None,
                "created_at": record.created_at,
            })
        else:
            items.append({
                "path": "PATH_B",
                "inbound_document_id": record.inbound_document_id,
                "invoice_id": None,
                "invoice_number": None,
                "vendor_id": record.vendor_id,
                "file_name": record.file_name,
                "status_code": record.extraction_status,
                "net_amount": None,
                "extraction_confidence": record.extraction_confidence,
                "created_at": record.received_at,
            })

    return items, len(path_a_invoices), len(path_b_documents)
