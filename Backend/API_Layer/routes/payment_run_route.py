# Backend/API_Layer/routes/payment_run_route.py
"""Payment runs (mounted at /apm/payment-runs).

View: PAYMENT_VIEW / PAYMENT_PROCESS / PAYMENT_RUN_APPROVE / AP_AUTOMATION_MANAGE.
Prepare, submit, bank file, mark sent, confirm: PAYMENT_PROCESS (Finance Executive).
Approve / reject: PAYMENT_RUN_APPROVE or AP_AUTOMATION_MANAGE (Finance Manager) - never the preparer.
"""
import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.payment_run_service import (
    APPROVE_PERMISSIONS,
    PREPARE_PERMISSIONS,
    VIEW_PERMISSIONS,
    PaymentRunService,
)

router = APIRouter()


class CreateRunBody(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    value_date: datetime.date
    invoice_ids: List[int] = Field(..., min_length=1, max_length=200)
    notes: Optional[str] = None


class RemarksBody(BaseModel):
    remarks: Optional[str] = Field(None, max_length=500)


class ConfirmRow(BaseModel):
    reference: Optional[str] = None
    vendor_id: Optional[int] = None
    status: str = Field(..., pattern="^(PAID|FAILED)$")
    utr: Optional[str] = Field(None, max_length=50)
    payment_date: Optional[datetime.date] = None
    reason: Optional[str] = Field(None, max_length=300)


class ConfirmBody(BaseModel):
    results: List[ConfirmRow] = Field(..., min_length=1)


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


@router.get("", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def list_runs(request: Request, status: Optional[str] = Query(None)):
    return _call(PaymentRunService(request.state.db).list, status)


@router.get("/candidates", dependencies=[Depends(permission_based_access(PREPARE_PERMISSIONS))])
def candidates(request: Request, due_by: Optional[datetime.date] = Query(None)):
    """Invoices ready to pay, with what (if anything) keeps each one out of a run."""
    return _call(PaymentRunService(request.state.db).candidates, due_by)


@router.post("", status_code=201, dependencies=[Depends(permission_based_access(PREPARE_PERMISSIONS))])
def create_run(body: CreateRunBody, request: Request):
    return _call(lambda: PaymentRunService(request.state.db).detail(PaymentRunService(request.state.db).create(
        body.name, body.value_date, body.invoice_ids, _user_id(request), body.notes).run_id))


@router.get("/{run_id}", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def run_detail(run_id: int, request: Request):
    return _call(PaymentRunService(request.state.db).detail, run_id)


@router.delete("/{run_id}/invoices/{invoice_id}", dependencies=[Depends(permission_based_access(PREPARE_PERMISSIONS))])
def remove_invoice(run_id: int, invoice_id: int, request: Request):
    return _call(lambda: PaymentRunService(request.state.db).remove_item(run_id, invoice_id, _user_id(request)) or {"removed": invoice_id})


def _step(method: str, permissions):
    def endpoint(run_id: int, request: Request, body: RemarksBody = RemarksBody()):
        service = PaymentRunService(request.state.db)
        args = {"submit": (run_id, _user_id(request)), "cancel": (run_id, _user_id(request)),
                "mark_sent": (run_id, _user_id(request)), "approve": (run_id, _user_id(request), body.remarks),
                "reject": (run_id, body.remarks or "", _user_id(request))}[method]
        return _call(lambda: service.detail(getattr(service, method)(*args).run_id))
    endpoint.__name__ = f"run_{method}"
    return endpoint


for _path, _method, _perms in (("submit", "submit", PREPARE_PERMISSIONS), ("cancel", "cancel", PREPARE_PERMISSIONS),
                               ("approve", "approve", APPROVE_PERMISSIONS), ("reject", "reject", APPROVE_PERMISSIONS),
                               ("mark-sent", "mark_sent", PREPARE_PERMISSIONS)):
    router.add_api_route(f"/{{run_id}}/{_path}", _step(_method, _perms), methods=["POST"],
                         dependencies=[Depends(permission_based_access(_perms))])


@router.get("/{run_id}/bank-file", dependencies=[Depends(permission_based_access(PREPARE_PERMISSIONS))])
def bank_file(run_id: int, request: Request, file_format: str = Query("GENERIC_CSV", pattern="^(GENERIC_CSV|HDFC_ENET)$")):
    """Bulk NEFT / RTGS file to upload to the bank portal."""
    try:
        name, content = PaymentRunService(request.state.db).bank_file(run_id, file_format, _user_id(request))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/{run_id}/confirm", dependencies=[Depends(permission_based_access(PREPARE_PERMISSIONS))])
def confirm(run_id: int, body: ConfirmBody, request: Request):
    """The bank's result per transfer: PAID with UTR, or FAILED with a reason."""
    return _call(PaymentRunService(request.state.db).confirm, run_id, [r.model_dump() for r in body.results], _user_id(request))


@router.post("/{run_id}/confirm-file", dependencies=[Depends(permission_based_access(PREPARE_PERMISSIONS))])
async def confirm_file(run_id: int, request: Request, file: UploadFile = File(...)):
    """The bank's response CSV (Customer Reference, UTR, Status[, Reason])."""
    content = await file.read()
    service = PaymentRunService(request.state.db)
    return _call(lambda: service.confirm(run_id, service.parse_response(content), _user_id(request)))
