# Backend/API_Layer/routes/nda_route.py
"""NDA lifecycle endpoints.

Permissions use the established "new string OR existing grant" convention:
``permission_based_access`` is any-of by default, so a PR Officer who already
holds INVITE_VENDOR/SEND_RFQ keeps working today, and the new NDA_* strings
take effect once UMS provisions them. No new RFQ_* permission is invented -
see tests/test_rfq_authorization.py for the 403 incident that convention
exists to prevent.

Literal paths are declared before dynamic /{nda_id} paths.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from Backend.API_Layer.interface.nda_interface import (
    ExistingNdaResponse,
    NdaDocumentUrlResponse,
    NdaGenerateRequest,
    NdaGenerateResponse,
    NdaSendResponse,
    NdaSignedUploadResponse,
    NdaStatusUpdateRequest,
    NdaStatusUpdateResponse,
    VendorNdaDTO,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.utils.file_validation import validate_pdf_upload
from Backend.Business_Layer.services.nda_service import NdaService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType
from Backend.Data_Access_Layer.models.nda import VendorNda

router = APIRouter()

NDA_VIEW = ["NDA_VIEW", "INVITE_VENDOR", "SEND_RFQ"]
NDA_GENERATE = ["NDA_GENERATE", "INVITE_VENDOR", "SEND_RFQ"]
NDA_SEND = ["NDA_SEND", "INVITE_VENDOR", "SEND_RFQ"]
# Uploading a signed NDA is an internal reviewer action, gated like the other
# NDA write operations: new string first, existing officer grants as fallback.
NDA_UPLOAD_SIGNED = ["NDA_UPLOAD", "NDA_SEND", "INVITE_VENDOR", "SEND_RFQ"]


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _to_dto(nda: VendorNda) -> VendorNdaDTO:
    return VendorNdaDTO(
        nda_id=nda.nda_id,
        vendor_id=nda.vendor_id,
        pr_id=nda.pr_id,
        department_id=nda.department_id,
        purchase_category_id=nda.purchase_category_id,
        nda_required=nda.nda_required,
        nda_status_id=nda.nda_status_id,
        status_code=nda.status.status_code if nda.status is not None else None,
        template_id=nda.template_id,
        template_version=nda.template_version,
        document_key=nda.document_key,
        signed_document_key=nda.signed_document_key,
        recipient_email=nda.recipient_email,
        valid_from=nda.valid_from,
        valid_until=nda.valid_until,
        sent_at=nda.sent_at,
        signed_at=nda.signed_at,
        completed_at=nda.completed_at,
        created_at=nda.created_at,
        updated_at=nda.updated_at,
    )


def _status_code(nda: VendorNda) -> Optional[str]:
    return nda.status.status_code if nda.status is not None else None


def _raise_for_value_error(exc: ValueError):
    message = str(exc)
    status_code = 404 if "not found" in message.lower() else 422
    raise HTTPException(status_code=status_code, detail=message)


# ---------------------------------------------------------
# Literal paths (declared before /{nda_id})
# ---------------------------------------------------------
@router.post(
    "/generate",
    response_model=NdaGenerateResponse,
    dependencies=[Depends(permission_based_access(NDA_GENERATE))],
)
def generate_nda(payload: NdaGenerateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        result = NdaService(db).generate_nda(
            vendor_id=payload.vendor_id,
            user_id=user_id,
            pr_id=payload.pr_id,
            department_id=payload.department_id,
            purchase_category_id=payload.purchase_category_id,
            template_code=payload.template_code,
            recipient_email=payload.recipient_email,
        )

        if not result.required:
            message = "NDA is not required for this vendor engagement"
        elif result.reused:
            message = "An existing valid NDA was reused"
        else:
            message = "NDA generated successfully"

        return NdaGenerateResponse(
            nda_id=result.nda.nda_id,
            status_code=_status_code(result.nda),
            nda_required=result.required,
            reused=result.reused,
            document_key=result.nda.document_key,
            message=message,
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/vendor/{vendor_id}",
    response_model=ExistingNdaResponse,
    dependencies=[Depends(permission_based_access(NDA_VIEW))],
)
def get_vendor_nda(
    vendor_id: int,
    http_request: Request,
    department_id: Optional[int] = None,
    purchase_category_id: Optional[int] = None,
):
    db = http_request.state.db

    try:
        service = NdaService(db)
        lookup = service.check_existing_nda(vendor_id, department_id, purchase_category_id)

        return ExistingNdaResponse(
            vendor_id=vendor_id,
            outcome=lookup.outcome,
            reason=lookup.reason,
            nda=_to_dto(lookup.nda) if lookup.nda is not None else None,
            ndas=[_to_dto(nda) for nda in service.list_for_vendor(vendor_id)],
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Dynamic paths
# ---------------------------------------------------------
@router.get(
    "/{nda_id}",
    response_model=VendorNdaDTO,
    dependencies=[Depends(permission_based_access(NDA_VIEW))],
)
def get_nda(nda_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return _to_dto(NdaService(db).get_nda(nda_id))

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{nda_id}/document",
    response_model=NdaDocumentUrlResponse,
    dependencies=[Depends(permission_based_access(NDA_VIEW))],
)
def get_nda_document_url(
    nda_id: int,
    http_request: Request,
    signed: bool = False,
    expires_in: Optional[int] = None,
):
    """Returns a short-lived presigned URL. The bucket stays private and no
    public URL is ever exposed; the permission dependency above authorizes
    the caller before any URL is minted."""

    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        url, ttl = NdaService(db).get_document_url(
            nda_id, user_id, signed=signed, expires_in=expires_in
        )

        return NdaDocumentUrlResponse(nda_id=nda_id, url=url, expires_in_seconds=ttl)

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{nda_id}/send",
    response_model=NdaSendResponse,
    dependencies=[Depends(permission_based_access(NDA_SEND))],
)
def send_nda(nda_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        nda, result = NdaService(db).send_nda(nda_id, user_id)

        return NdaSendResponse(
            nda_id=nda.nda_id,
            status_code=_status_code(nda),
            sent=result.success,
            recipient_email=nda.recipient_email,
            error=result.error,
            message=(
                "NDA sent to the vendor"
                if result.success
                else "NDA could not be sent; status is unchanged"
            ),
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{nda_id}/signed-document",
    response_model=NdaSignedUploadResponse,
    dependencies=[Depends(permission_based_access(NDA_UPLOAD_SIGNED))],
)
async def upload_signed_nda_document(
    nda_id: int,
    http_request: Request,
    file: UploadFile = File(...),
):
    """Upload the vendor-signed NDA (PDF only) and move the NDA to SIGNED.

    SIGNED means "signed document received, pending internal review" - RFQ
    eligibility stays blocked until the NDA is explicitly moved to COMPLETED
    via PATCH /{nda_id}/status. Only the S3 object key is persisted; the
    document is fetched through a short-lived presigned URL.
    """

    db = http_request.state.db

    content = await file.read()

    try:
        validate_pdf_upload(file, content)
    except UnsupportedFileType as e:
        raise HTTPException(
            status_code=415, detail="Signed NDA must be a PDF document"
        ) from e
    except InvalidUploadFile as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        user_id = _get_user_id(http_request)

        nda = NdaService(db).upload_signed_document(
            nda_id=nda_id,
            filename=file.filename,
            content=content,
            content_type=file.content_type,
            user_id=user_id,
        )

        return NdaSignedUploadResponse(
            nda_id=nda.nda_id,
            status_code=_status_code(nda),
            signed_document_key=nda.signed_document_key,
            signed_at=nda.signed_at,
            message="Signed NDA uploaded successfully; pending internal review",
            nda=_to_dto(nda),
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except HTTPException:
        # S3 upload failures surface as HTTPException from s3_utils - roll back
        # so the NDA is never left marked SIGNED without a stored document.
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/{nda_id}/status",
    response_model=NdaStatusUpdateResponse,
    dependencies=[Depends(permission_based_access(NDA_SEND))],
)
def update_nda_status(
    nda_id: int,
    payload: NdaStatusUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        nda = NdaService(db).update_status(
            nda_id,
            payload.status_code,
            user_id,
            signed_document_key=payload.signed_document_key,
            reason=payload.reason,
        )

        return NdaStatusUpdateResponse(
            nda_id=nda.nda_id,
            status_code=_status_code(nda),
            message="NDA status updated successfully",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
