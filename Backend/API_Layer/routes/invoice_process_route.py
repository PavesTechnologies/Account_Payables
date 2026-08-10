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
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, Request

from Backend.Business_Layer.services import invoice_process_service as service
from Backend.Business_Layer.utils.exceptions import (
    FieldExtractionError,
    OCRFailure,
    UnsupportedFileType,
    ValidationFailure,
    VendorNotFound,
)
from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoice,
    FinalResponse,
    ValidationResult,
    VendorMatch,
    UploadDocumentResponse,
)
from Backend.Business_Layer.utils.vendor_matcher import match_vendor as vendor_matcher
from Backend.API_Layer.utils.s3_utils import upload_to_s3
logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------
# 1. Upload Document (developer API)
# ---------------------------------------------------------
@router.post("/upload-document", response_model=DocumentResult)
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
# 2. Extract Fields (developer API)
# ---------------------------------------------------------
@router.post("/extract-fields", response_model=ExtractedInvoice)
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
# 3. Validate Fields (developer API)
# ---------------------------------------------------------
@router.post("/validate-fields", response_model=ValidationResult)
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
# 4. Match Vendor (developer API)
# ---------------------------------------------------------
@router.post("/match-vendor", response_model=VendorMatch)
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
# 5. Process Invoice (production API)
# ---------------------------------------------------------
@router.post("/process-invoice", response_model=FinalResponse)
async def process_invoice(http_request: Request, file: UploadFile = File(...)):
    """Run the complete invoice processing pipeline end to end.

    extract_document -> quality_assessment -> (Textract fallback if poor)
    -> extract_invoice_fields -> validate_invoice -> match_vendor
    -> calculate_confidence -> FinalResponse.

    Reuses the exact same service functions as the developer APIs above.
    """
    content = await file.read()

    try:
        upload_result =upload_to_s3(file.filename, content)
        db = http_request.state.db
        process_result = service.process_invoice(file.filename, content, db)
        update_result = service.upload_to_db()


    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))

    except (OCRFailure, FieldExtractionError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("process-invoice failed for '%s'", file.filename)
        raise HTTPException(status_code=500, detail=str(e))
