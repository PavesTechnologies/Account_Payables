# Backend/API_Layer/routes/invoice_extraction_route.py

from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Request,
    UploadFile,
)

from Backend.API_Layer.interface.invoice_extraction_interface import (
    AmountsCorrectionRequest,
    BuyerCorrectionRequest,
    ConfirmSectionRequest,
    CorrectionResponse,
    ExtractedInvoiceResponse,
    ExtractedInvoiceResult,
    ExtractionCacheResponse,
    InvoiceCreationResult,
    TaxCorrectionRequest,
    ValidationJobQueued,
    ValidationJobStatus,
    VendorCorrectionRequest,
)

from Backend.API_Layer.utils.invoice_extraction_fields import (
    extract_invoice_from_s3,
)

from Backend.API_Layer.utils.extraction_cache import (
    apply_correction,
    get_extraction_cache,
    init_extraction_cache,
    is_section_confirmed,
    new_extraction_id,
    record_confirmation,
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
    InvoiceExtractionService,
    run_validation_job,
)
from Backend.Business_Layer.utils.exceptions import (
    DuplicateInvoiceError,
    FieldExtractionError,
)


router = APIRouter()


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}

MAX_FILE_SIZE = 10 * 1024 * 1024

def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id

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

        # ====================================================
        # Cache - the extracted invoice (vendor/buyer fields
        # included) is cached server-side under a new
        # extraction_id, editable via the correction endpoints
        # below. Nothing is written to the Invoice DB here or
        # at any later validation stage - only /create-invoice
        # persists.
        # ====================================================

        extraction_id = new_extraction_id()

        init_extraction_cache(
            extraction_id,
            result.model_dump(mode="json"),
            s3_key,
        )

        return ExtractedInvoiceResult(
            extracted_invoice = result,
            file_path = s3_key,
            extraction_id = extraction_id,
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
    http_request: Request,
    background_tasks: BackgroundTasks,
):

    # ========================================================
    # Resolve the invoice to validate. The request body is read
    # as raw JSON (rather than binding directly to a Pydantic
    # model) because two shapes must both keep working here:
    #
    #   1. Preferred (new): {"extraction_id": "ext_..."} - loads
    #      the latest cached data from /extract-fields, including
    #      any vendor/buyer corrections applied since via
    #      PATCH .../vendor|buyer, so validation always sees the
    #      user's current edits.
    #   2. Back-compat (original): the full extracted body,
    #      either bare {"extracted_invoice":..., "file_path":...}
    #      (unchanged from before this endpoint knew about
    #      extraction_id) or wrapped as {"extracted_data": {...}}.
    # ========================================================

    try:
        body = await http_request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Request body must be valid JSON.",
        ) from exc

    extraction_id = body.get("extraction_id") if isinstance(body, dict) else None

    if extraction_id:

        cached = get_extraction_cache(extraction_id)

        if cached is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Extraction not found - it may have expired "
                    "or never existed."
                ),
            )

        extracted_invoice = ExtractedInvoiceResponse(
            **cached["extracted_invoice"]
        )
        file_path = cached["file_path"]

    else:

        raw = body.get("extracted_data") or body if isinstance(body, dict) else None

        if not raw:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Either extraction_id or the extracted invoice "
                    "data must be provided."
                ),
            )

        try:
            extracted_data = ExtractedInvoiceResult(**raw)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid extracted invoice data: {exc}",
            ) from exc

        extracted_invoice = extracted_data.extracted_invoice
        file_path = extracted_data.file_path

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
        extracted_invoice,
        file_path,
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


# ============================================================
# Stage 1 - Vendor/Buyer/GST correction endpoints
#
# The cached extraction (see extraction_cache.py) is the only place
# a user's field corrections live before all validations are done -
# nothing here ever touches the Invoice DB. GET returns the current
# state; the PATCH endpoints apply a sparse field-level correction
# (only fields present in the body are changed) recorded as
# BEFORE -> AFTER events; POST .../confirm records an explicit
# "reviewed and accepted as-is" checkpoint for a section. GST tax
# fields are split across two sections (tax, amounts) mirroring
# InvoiceTax/InvoiceAmounts - a correction to either is picked up by
# the next /validate-fields run against the same extraction_id,
# which re-runs GST calculation/rule checks against the corrected
# cache (no separate recalculation step needed).
# ============================================================

def _extraction_cache_response(cached: dict) -> ExtractionCacheResponse:
    corrections = cached.get("corrections", [])

    return ExtractionCacheResponse(
        extraction_id=cached["extraction_id"],
        extracted_invoice=ExtractedInvoiceResponse(
            **cached["extracted_invoice"]
        ),
        file_path=cached["file_path"],
        corrections=corrections,
        vendor_confirmed=is_section_confirmed(corrections, "vendor"),
        buyer_confirmed=is_section_confirmed(corrections, "buyer"),
        tax_confirmed=is_section_confirmed(corrections, "tax"),
        amounts_confirmed=is_section_confirmed(corrections, "amounts"),
    )


@router.get(
    "/extract-fields/{extraction_id}",
    response_model=ExtractionCacheResponse,
)
async def get_extraction(extraction_id: str):

    cached = get_extraction_cache(extraction_id)

    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Extraction not found - it may have expired or "
                "never existed."
            ),
        )

    return _extraction_cache_response(cached)


def _correct_section(
    extraction_id: str,
    section: str,
    field_updates: dict,
    http_request: Request,
) -> CorrectionResponse:

    if field_updates:
        user_id = _get_user_id(http_request)
        cached = apply_correction(
            extraction_id, section, field_updates, str(user_id)
        )
    else:
        cached = get_extraction_cache(extraction_id)

    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Extraction not found - it may have expired or "
                "never existed."
            ),
        )

    return CorrectionResponse(
        extraction_id=extraction_id,
        section=section,
        updated=cached["extracted_invoice"].get(section, {}),
        corrections=cached.get("corrections", []),
    )


@router.patch(
    "/extract-fields/{extraction_id}/vendor",
    response_model=CorrectionResponse,
)
async def correct_vendor(
    extraction_id: str,
    patch: VendorCorrectionRequest,
    http_request: Request,
):
    return _correct_section(
        extraction_id,
        "vendor",
        patch.model_dump(exclude_unset=True),
        http_request,
    )


@router.patch(
    "/extract-fields/{extraction_id}/buyer",
    response_model=CorrectionResponse,
)
async def correct_buyer(
    extraction_id: str,
    patch: BuyerCorrectionRequest,
    http_request: Request,
):
    return _correct_section(
        extraction_id,
        "buyer",
        patch.model_dump(exclude_unset=True),
        http_request,
    )


@router.patch(
    "/extract-fields/{extraction_id}/tax",
    response_model=CorrectionResponse,
)
async def correct_tax(
    extraction_id: str,
    patch: TaxCorrectionRequest,
    http_request: Request,
):
    return _correct_section(
        extraction_id,
        "tax",
        patch.model_dump(exclude_unset=True),
        http_request,
    )


@router.patch(
    "/extract-fields/{extraction_id}/amounts",
    response_model=CorrectionResponse,
)
async def correct_amounts(
    extraction_id: str,
    patch: AmountsCorrectionRequest,
    http_request: Request,
):
    return _correct_section(
        extraction_id,
        "amounts",
        patch.model_dump(exclude_unset=True),
        http_request,
    )


@router.post(
    "/extract-fields/{extraction_id}/confirm",
    response_model=ExtractionCacheResponse,
)
async def confirm_section(
    extraction_id: str,
    body: ConfirmSectionRequest,
    http_request: Request,
):

    if body.section not in ("vendor", "buyer", "tax", "amounts"):
        raise HTTPException(
            status_code=400,
            detail="section must be one of 'vendor', 'buyer', 'tax', 'amounts'.",
        )

    user_id = _get_user_id(http_request)
    cached = record_confirmation(
        extraction_id, body.section, str(user_id)
    )

    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Extraction not found - it may have expired or "
                "never existed."
            ),
        )

    return _extraction_cache_response(cached)


@router.post(
    "/create-invoice",
    response_model=InvoiceCreationResult,
)
async def create_invoice(
    extracted_data: ExtractedInvoiceResult,
    http_request: Request,
    job_id: Optional[str] = None,
):

    # ========================================================
    # Persists Invoice + InvoiceLine(s) + InvoiceAttachment +
    # InboundDocument from the same extracted-invoice shape
    # /validate-fields accepts. This is a synchronous DB write
    # (a handful of inserts), not a multi-stage pipeline, so it
    # runs directly on the request - no job/Redis involved.
    #
    # Called once the frontend has a validation result (pass or
    # fail) it's ready to act on - regardless of outcome, this
    # is what actually creates the invoice, always landing at
    # OCR_REVIEW_PENDING for a human to review in Invoice
    # Management afterward.
    #
    # job_id is optional and purely an extra guard: if given, the
    # referenced validation job must exist and have completed
    # successfully, or this call is rejected. Omitting it keeps
    # today's unconditional behavior unchanged (create-invoice is
    # deliberately independent of validation outcome by design).
    # ========================================================

    if job_id:

        job = get_validation_status(job_id)

        if job is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Validation job not found - it may have expired "
                    "or never existed."
                ),
            )

        if job.get("status") != "COMPLETED" or not job.get("is_valid"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Invoice cannot be created - validation job "
                    f"'{job_id}' has not completed successfully. "
                    "Call create-invoice without job_id to force-"
                    "create despite validation issues."
                ),
            )

    db = http_request.state.db
    user_id=_get_user_id(http_request)
    service = InvoiceExtractionService(db)

    try:
        result = service.create_invoice(
            extracted_data.extracted_invoice,
            extracted_data.file_path,
            created_by=str(user_id),
        )

        return InvoiceCreationResult(**result)

    except DuplicateInvoiceError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except FieldExtractionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while creating the invoice.",
        ) from exc