# Backend/API_Layer/routes/vendor_bank_verification_route.py
"""Vendor bank verification and approval (mounted at /apm/vendor-bank-verification).

View: vendor readers + Finance. Verify / approve / reject: VENDOR_BANK_VERIFY, AP_AUTOMATION_MANAGE
or PAYMENT_PROCESS (approval must be by someone other than whoever added / changed the account).
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import view_from_s3
from Backend.Business_Layer.services.vendor_bank_verification_service import (
    VERIFY_PERMISSIONS,
    VIEW_PERMISSIONS,
    VendorBankVerificationService,
)
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()


class RemarksBody(BaseModel):
    remarks: Optional[str] = Field(None, max_length=500)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


def _call(fn, *args):
    try:
        return JSONResponse(jsonable_encoder(fn(*args)))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/vendor/{vendor_id}", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def vendor_banks(vendor_id: int, request: Request):
    """bank_id -> verification / approval state for each of the vendor's accounts."""
    return _call(VendorBankVerificationService(request.state.db).for_vendor, vendor_id)


@router.get("/vendor/{vendor_id}/bank/{bank_id}", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def bank_status(vendor_id: int, bank_id: int, request: Request):
    return _call(VendorBankVerificationService(request.state.db).status, vendor_id, bank_id)


@router.post("/vendor/{vendor_id}/bank/{bank_id}/penny-drop", dependencies=[Depends(permission_based_access(VERIFY_PERMISSIONS))])
def penny_drop(vendor_id: int, bank_id: int, request: Request):
    """Live bank check: the name registered at the bank vs the vendor's legal name."""
    return _call(VendorBankVerificationService(request.state.db).verify_penny_drop, vendor_id, bank_id, _user_id(request))


@router.post("/vendor/{vendor_id}/bank/{bank_id}/document", dependencies=[Depends(permission_based_access(VERIFY_PERMISSIONS))])
async def document(vendor_id: int, bank_id: int, request: Request, remarks: str = Form(...), file: UploadFile = File(...)):
    """Cancelled cheque / bank letter, checked by Finance."""
    content = await file.read()
    try:
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as exc:
        raise HTTPException(status_code=415 if isinstance(exc, UnsupportedFileType) else 400, detail=str(exc)) from exc
    return _call(VendorBankVerificationService(request.state.db).verify_document, vendor_id, bank_id,
                 (file.filename, content, file.content_type), remarks, _user_id(request))


@router.post("/vendor/{vendor_id}/bank/{bank_id}/approve", dependencies=[Depends(permission_based_access(VERIFY_PERMISSIONS))])
def approve(vendor_id: int, bank_id: int, body: RemarksBody, request: Request):
    return _call(VendorBankVerificationService(request.state.db).approve, vendor_id, bank_id, body.remarks, _user_id(request))


@router.post("/vendor/{vendor_id}/bank/{bank_id}/reject", dependencies=[Depends(permission_based_access(VERIFY_PERMISSIONS))])
def reject(vendor_id: int, bank_id: int, body: RemarksBody, request: Request):
    return _call(VendorBankVerificationService(request.state.db).reject, vendor_id, bank_id, body.remarks or "", _user_id(request))


@router.get("/vendor/{vendor_id}/bank/{bank_id}/document", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def view_document(vendor_id: int, bank_id: int, request: Request):
    try:
        row = VendorBankVerificationService(request.state.db).document(vendor_id, bank_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return view_from_s3(row.file_path)
