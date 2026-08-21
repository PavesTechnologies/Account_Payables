# Backend/API_Layer/routes/invoice_extraction_route.py

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    UploadFile,
)

from Backend.API_Layer.interface.invoice_extraction_interface import (
    ExtractedInvoiceResponse,
    ExtractedInvoiceResult,
    ValidationJobQueued,
    ValidationJobStatus,
)

from Backend.API_Layer.utils.invoice_extraction_fields import (
    extract_invoice_from_s3,
)

from Backend.API_Layer.utils.s3_utils import (
    delete_from_s3,
    upload_to_s3,
)

from Backend.API_Layer.utils.validation_progress import (
    get_validation_status,
    init_validation_job,
    new_job_id,
)

from Backend.Business_Layer.services.invoice_extraction_service import (
    run_validation_job,
)


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

@router.post(
    "/validate-fields",
    response_model=ValidationJobQueued,
)
async def validate_fields(
    extracted_data: ExtractedInvoiceResult,
    background_tasks: BackgroundTasks,
):

    # ========================================================
    # Create the job and initialize its Redis progress record
    # up front, so a GET .../status immediately after this
    # response always finds something (QUEUED, every stage
    # WAITING) rather than a 404 race.
    # ========================================================

    job_id = new_job_id()

    init_validation_job(job_id)

    # ========================================================
    # The actual extraction/vendor/buyer/GST pipeline runs in
    # the background, after this response is sent - it opens
    # its own DB session (see run_validation_job) since the
    # request-scoped session is gone by then. This endpoint
    # never blocks on the pipeline.
    # ========================================================

    background_tasks.add_task(
        run_validation_job,
        job_id,
        extracted_data.extracted_invoice,
        extracted_data.file_path,
    )

    return ValidationJobQueued(
        job_id=job_id,
        status="QUEUED",
    )


@router.get(
    "/validate-fields/{job_id}/status",
    response_model=ValidationJobStatus,
)
async def get_validate_fields_status(job_id: str):

    job = get_validation_status(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Validation job not found - it may have expired "
                "or never existed."
            ),
        )

    return job