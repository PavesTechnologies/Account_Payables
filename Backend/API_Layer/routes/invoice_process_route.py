# Backend/API_Layer/routes/invoice_process_route.py
"""Invoice processing API.

Routes only validate the request and delegate to
Backend.Business_Layer.services.invoice_process_service — no OCR,
extraction, validation, or matching logic lives here.

Endpoints:
    POST /upload-document  - developer API: upload + technical classification + text extraction
    POST /extract-fields   - developer API: rule-based field extraction
    POST /validate-fields  - developer API: business validation
    POST /match-vendor     - developer API: vendor master matching (placeholder)
    POST /process-invoice  - production API: full pipeline, reusing every stage above

NOT CALLED BY THE FRONTEND (confirmed by tracing every AP invoice service call in
src/pages/accounts-payable/invoice/services/*.js, 2026-09): the frontend's real upload/intake
pipeline is invoice_extraction_route.py's separate extract-fields -> validate-fields ->
per-section corrections -> create-invoice flow, not this file's upload-document/extract-fields/
validate-fields/match-vendor/process-invoice. Each of those five is annotated individually below.
Kept live and tested (see test_process_invoice_route.py) rather than removed — this predates the
other pipeline and may still serve a non-UI integration — but do not assume it's what Invoice
Management actually runs today. inbound-documents/{id}/ocr-review and /review-queue below ARE
live (the OCR Review Queue page), and {invoice_id}/matching is real, callable capability simply
not yet wired into any frontend screen (see InvoicePaymentPanel's own gap note) — neither of
those three is "unused" in the sense the five above are.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services import invoice_process_service as service
from Backend.Business_Layer.utils.exceptions import (
    DuplicateInvoiceError,
    FieldExtractionError,
    InvalidUploadFile,
    OCRFailure,
    UnsupportedFileType,
    ValidationFailure,
    VendorNotFound,
)
from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoice,
    FinalResponse,
    InvoiceOCRReviewRequest,
    ValidationResult,
    VendorMatch,
    UploadDocumentResponse,
)
from Backend.API_Layer.interface.matching_interface import MatchResult
from Backend.API_Layer.interface.review_queue_interface import ReviewQueueResponse
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.response_utils import success_response
from Backend.Business_Layer.services.matching_service import MatchingService
from Backend.Business_Layer.utils.vendor_matcher import match_vendor as vendor_matcher
from Backend.API_Layer.utils.s3_utils import upload_to_s3
logger = logging.getLogger(__name__)

router = APIRouter()

# Same intake capability as invoice_extraction_route.py's pipeline — one permission for the
# whole extract/validate/match/persist chain, since only /process-invoice and /ocr-review
# actually write to the Invoice DB.
_INTAKE_PERMISSIONS = ["INVOICE_CREATE"]
_OCR_REVIEW_PERMISSIONS = ["INVOICE_OCR_REVIEW"]
_VIEW_PERMISSIONS = ["INVOICE_VIEW"]


def _get_user_id(http_request: Request) -> str:
    """Extract the authenticated user id from the JWT payload set by JWTMiddleware.

    Duplicated from master_route.py/vendor_route.py's identical helper
    rather than factored into a shared module, to avoid touching routes
    unrelated to this feature.
    """
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


# ---------------------------------------------------------
# 1. Upload Document (developer API) — NOT CALLED BY THE FRONTEND, see module docstring.
# ---------------------------------------------------------
@router.post(
    "/upload-document",
    response_model=DocumentResult,
    dependencies=[Depends(permission_based_access(_INTAKE_PERMISSIONS))],
)
async def upload_document(file: UploadFile = File(...)):
    """Upload a document and run technical classification + text extraction only.

    No field extraction happens here — use /extract-fields for that.
    """
    content = await file.read()

    try:
        result = service.extract_document(file.filename, content)

        # return service.to_upload_response(result)
        return result

    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))

    except OCRFailure as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("upload-document failed for '%s'", file.filename)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# 2. Extract Fields (developer API) — NOT CALLED BY THE FRONTEND, see module docstring.
# ---------------------------------------------------------
@router.post(
    "/extract-fields",
    response_model=ExtractedInvoice,
    dependencies=[Depends(permission_based_access(_INTAKE_PERMISSIONS))],
)
def extract_fields(document: DocumentResult):
    """Extract invoice fields from a DocumentResult using anchors/regex/geometry only."""
    try:
        return service.extract_invoice_fields(document)

    except FieldExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("extract-fields failed")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# 3. Validate Fields (developer API) — NOT CALLED BY THE FRONTEND, see module docstring.
# ---------------------------------------------------------
@router.post(
    "/validate-fields",
    response_model=ValidationResult,
    dependencies=[Depends(permission_based_access(_INTAKE_PERMISSIONS))],
)
def validate_fields(extracted_invoice: ExtractedInvoice):
    """Validate GSTIN, invoice date, due date, totals, and invoice number."""
    try:
        return service.validate_invoice(extracted_invoice)

    except ValidationFailure as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("validate-fields failed")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# 4. Match Vendor (developer API) — NOT CALLED BY THE FRONTEND, see module docstring.
# ---------------------------------------------------------
@router.post(
    "/match-vendor",
    response_model=VendorMatch,
    dependencies=[Depends(permission_based_access(_INTAKE_PERMISSIONS))],
)
def match_vendor(
    extracted_invoice: ExtractedInvoice,
    http_request: Request,
):
    """Match an ExtractedInvoice against the vendor master."""

    try:
        db = http_request.state.db

        return vendor_matcher(
            extracted=extracted_invoice,
            db=db,
        )

    except VendorNotFound as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        logger.exception("match-vendor failed")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# 5. Process Invoice (production API) — NOT CALLED BY THE FRONTEND, see module docstring. Despite
# the "production API" label this carries from its original design, Invoice Management today
# runs entirely on invoice_extraction_route.py's extract-fields/validate-fields/create-invoice
# instead — this full auto-pipeline (OCR -> vendor match -> persist) is not what's live in the UI.
# ---------------------------------------------------------
@router.post(
    "/process-invoice",
    response_model=FinalResponse,
    dependencies=[Depends(permission_based_access(_INTAKE_PERMISSIONS))],
)
async def process_invoice(http_request: Request, file: UploadFile = File(...)):
    """Full production pipeline: validate -> S3 upload -> InboundDocument ->
    OCR/extraction/validation/vendor-matching/confidence (service.process_invoice,
    unchanged) -> persist (Invoice/InvoiceLine/InvoiceAttachment/InvoiceIssue, or
    just InboundDocument + notification if the vendor couldn't be matched).
    """
    content = await file.read()

    try:
        logger.debug("Validating upload file '%s'", file.filename)
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as e:
        status_code = 415 if isinstance(e, UnsupportedFileType) else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    try:
        user_id = _get_user_id(http_request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = http_request.state.db

    upload_result = upload_to_s3(file.filename, content, file.content_type)
    s3_key = upload_result["filepath"]

    inbound_document = service.create_pending_inbound_document(file.filename, s3_key, db)

    try:
        final_response = service.process_invoice(file.filename, content, db)
    except (OCRFailure, FieldExtractionError) as e:
        service.mark_inbound_document_failed(inbound_document, db)
        raise HTTPException(status_code=422, detail=str(e))
    except UnsupportedFileType as e:
        service.mark_inbound_document_failed(inbound_document, db)
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        service.mark_inbound_document_failed(inbound_document, db)
        logger.exception("process-invoice extraction failed for '%s'", file.filename)
        raise HTTPException(status_code=500, detail="Invoice processing failed unexpectedly")

    try:
        outcome = service.persist_processed_invoice(final_response, inbound_document, db, user_id)
    except FieldExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DuplicateInvoiceError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="This invoice conflicts with an existing record")
    except Exception as e:
        logger.exception("process-invoice persistence failed for '%s'", file.filename)
        raise HTTPException(status_code=500, detail="Invoice processing failed unexpectedly")

    final_response.inbound_document_id = outcome.inbound_document_id
    final_response.invoice_id = outcome.invoice_id
    final_response.invoice_status = outcome.invoice_status
    return final_response


# ---------------------------------------------------------
# 6. Manual OCR Review (AP Executive correction/confirmation)
# ---------------------------------------------------------
@router.patch(
    "/inbound-documents/{inbound_document_id}/ocr-review",
    dependencies=[Depends(permission_based_access(_OCR_REVIEW_PERMISSIONS))],
)
def ocr_review(
    inbound_document_id: int,
    review: InvoiceOCRReviewRequest,
    http_request: Request,
):
    """AP Executive confirms/corrects an OCR-extracted invoice.

    Creates the Invoice for the first time when this document's vendor
    could not be auto-matched at /process-invoice time (``vendor_id`` is
    then required in the body), or updates the existing invoice
    otherwise. Either way, ends at OCR_REVIEWED — Send for Approval is
    the separate, deliberate action that moves it on to PENDING_APPROVAL.
    """
    try:
        user_id = _get_user_id(http_request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = http_request.state.db

    try:
        invoice = service.apply_ocr_review(inbound_document_id, review, db, user_id)
    except DuplicateInvoiceError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This invoice conflicts with an existing record")
    except Exception:
        logger.exception("ocr-review failed for inbound_document_id=%s", inbound_document_id)
        raise HTTPException(status_code=500, detail="OCR review failed unexpectedly")

    return success_response(
        data={"invoice_id": invoice.invoice_id, "status_id": invoice.status_id},
        message="Invoice review completed; moved to OCR_REVIEWED.",
    )


# ---------------------------------------------------------
# 7. OCR Review Queue (derived from invoice/inbound_document — no queue table)
# ---------------------------------------------------------
@router.get(
    "/review-queue",
    response_model=ReviewQueueResponse,
    dependencies=[Depends(permission_based_access(_OCR_REVIEW_PERMISSIONS))],
)
def get_review_queue(http_request: Request, skip: int = 0, limit: int = 50):
    db = http_request.state.db

    try:
        items, total_path_a, total_path_b = service.get_review_queue(db, skip, limit)
        return ReviewQueueResponse(
            total_path_a=total_path_a,
            total_path_b=total_path_b,
            skip=skip,
            limit=limit,
            items=items,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# 8. PO / GRN / Invoice Matching (2-way / 3-way, read-only) — real, working capability that is
# simply not yet called by any frontend screen (InvoicePaymentPanel's payment-readiness view
# doesn't surface PO/GRN matching today — a documented, deferred gap, not dead code like 1-5
# above). Leave this wired and permission-gated as-is; it's a candidate for a future call site.
# ---------------------------------------------------------
@router.get(
    "/{invoice_id}/matching",
    response_model=MatchResult,
    dependencies=[Depends(permission_based_access(_VIEW_PERMISSIONS))],
)
def get_invoice_matching(invoice_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return MatchingService(db).match_invoice(invoice_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.exception("matching failed for invoice_id=%s", invoice_id)
        raise HTTPException(status_code=500, detail=str(e))
