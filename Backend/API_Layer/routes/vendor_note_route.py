# Backend/API_Layer/routes/vendor_note_route.py
"""Credit and debit notes (mounted at /apm/vendor-notes).

View: VENDOR_NOTE_MANAGE / PAYMENT_VIEW / PAYMENT_PROCESS / INVOICE_VIEW / AP_AUTOMATION_MANAGE.
Record / apply / cancel: VENDOR_NOTE_MANAGE, PAYMENT_PROCESS or AP_AUTOMATION_MANAGE.
"""
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import view_from_s3
from Backend.Business_Layer.services.vendor_note_service import MANAGE_PERMISSIONS, VIEW_PERMISSIONS, VendorNoteService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()


class ApplyBody(BaseModel):
    invoice_id: int


class CancelBody(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


def _write(fn, *args, db=None):
    try:
        note = fn(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        if db is not None:
            db.rollback()
        raise HTTPException(status_code=409, detail="This note number is already recorded for the vendor") from exc
    return {"note_id": note.note_id, "status": note.status, "applied_invoice_id": note.applied_invoice_id,
            "tds_adjusted": note.tds_adjusted, "tds_note": note.tds_note}


@router.get("", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def list_notes(request: Request, status: Optional[str] = Query(None), note_type: Optional[str] = Query(None),
               vendor_id: Optional[int] = Query(None)):
    return JSONResponse(jsonable_encoder(VendorNoteService(request.state.db).list(status, note_type, vendor_id)))


@router.get("/applicable-invoices", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def applicable_invoices(request: Request, vendor_id: int = Query(...)):
    """The vendor's approved, unpaid invoices a note can be applied to, with what is still owed."""
    return JSONResponse(jsonable_encoder(VendorNoteService(request.state.db).applicable_invoices(vendor_id)))


@router.post("", status_code=201, dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
async def record_note(request: Request, payload: str = Form(...), file: Optional[UploadFile] = File(None)):
    """payload: JSON {note_type, vendor_id, note_number, note_date, reason, taxable_value, cgst, sgst, igst,
    reference_invoice_id?, apply_to_invoice_id?}; file: the vendor's credit note / our debit note (PDF / image)."""
    try:
        data: Dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="payload must be JSON") from exc
    document = None
    if file is not None and file.filename:
        content = await file.read()
        try:
            validate_upload_file(file, content)
        except (UnsupportedFileType, InvalidUploadFile) as exc:
            raise HTTPException(status_code=415 if isinstance(exc, UnsupportedFileType) else 400, detail=str(exc)) from exc
        document = (file.filename, content, file.content_type)
    db = request.state.db
    return _write(VendorNoteService(db).record, data, _user_id(request), document, db=db)


@router.post("/{note_id}/apply", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def apply_note(note_id: int, body: ApplyBody, request: Request):
    return _write(VendorNoteService(request.state.db).apply, note_id, body.invoice_id, _user_id(request))


@router.post("/{note_id}/cancel", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def cancel_note(note_id: int, body: CancelBody, request: Request):
    return _write(VendorNoteService(request.state.db).cancel, note_id, body.reason, _user_id(request))


@router.get("/{note_id}/document", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def note_document(note_id: int, request: Request):
    try:
        note = VendorNoteService(request.state.db).document(note_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return view_from_s3(note.file_path)
