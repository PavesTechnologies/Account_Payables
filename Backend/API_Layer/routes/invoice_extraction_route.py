# Backend/API_Layer/routes/invoice_extraction_route.py

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
    Request,
)

from Backend.API_Layer.interface.invoice_extraction_interface import (
    ExtractedInvoiceResponse, ValidationResult, ExtractedInvoiceResult
)

from Backend.API_Layer.utils.invoice_extraction_fields import (
    extract_invoice_from_s3,
)

from Backend.API_Layer.utils.s3_utils import (
    delete_from_s3,
    upload_to_s3,
)

from Backend.Business_Layer.services.invoice_extraction_service import InvoiceExtractionService


router = APIRouter()


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}

MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post(
    "/extract-fields",
    response_model=ExtractedInvoiceResult,
)
async def extract_invoice_fields(
    file: UploadFile = File(...),
):

    # ========================================================
    # File validation
    # ========================================================

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="Invoice filename is required.",
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:

        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Supported formats: PDF, JPEG, PNG, TIFF."
            ),
        )

    content = await file.read()

    if not content:

        raise HTTPException(
            status_code=400,
            detail="Uploaded invoice is empty.",
        )

    if len(content) > MAX_FILE_SIZE:

        raise HTTPException(
            status_code=413,
            detail="Invoice exceeds 10 MB size limit.",
        )

    s3_key = None

    try:

        # ====================================================
        # Upload
        # ====================================================

        upload_result = upload_to_s3(
            filename=file.filename,
            content=content,
            content_type=file.content_type,
        )

        s3_key = upload_result["filepath"]

        # ====================================================
        # Extract
        # ====================================================

        result = await extract_invoice_from_s3(
            s3_key=s3_key,
            filename=file.filename,
        )

        return ExtractedInvoiceResult(
            extracted_invoice = result,
            file_path = s3_key,
        )

    except HTTPException:
        raise

    except RuntimeError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected invoice extraction error."
            ),
        ) from exc

    # finally:

    #     # ====================================================
    #     # Temporary S3 cleanup
    #     # ====================================================

    #     if s3_key:

    #         try:

    #             delete_from_s3(
    #                 s3_key
    #             )

    #         except Exception:

    #             # Do not hide extraction result because
    #             # temporary cleanup failed.
    #             pass

@router.post("/validate-fields", response_model=ValidationResult)
async def validate_fields(
    extracted_data: ExtractedInvoiceResult,
    http_request: Request
):
    db = http_request.state.db
    service = InvoiceExtractionService(db)

    try:
        extracted_invoice = extracted_data.extracted_invoice
        file_path = extracted_data.file_path

        return service.validate_invoice(
            extracted_invoice,
            file_path
        )

    except HTTPException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )