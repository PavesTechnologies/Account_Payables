# Backend/API_Layer/routes/invoice_review_workbench_route.py
"""Review workbench (Step A): invoices waiting for review / send, with coding suggestions and
readiness checks, plus bulk review & send. Same permissions as doing it one at a time:
INVOICE_OCR_REVIEW to review, INVOICE_SEND_FOR_APPROVAL to send."""
import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import has_permissions, permission_based_access
from Backend.Business_Layer.services.invoice_review_automation_service import InvoiceReviewAutomationService

router = APIRouter()

OCR_REVIEW = "INVOICE_OCR_REVIEW"
SEND = "INVOICE_SEND_FOR_APPROVAL"


class Check(BaseModel):
    key: str
    ok: bool
    blocking: bool
    message: str


class WorkbenchRow(BaseModel):
    invoice_id: int
    inbound_document_id: Optional[int] = None
    invoice_number: str
    vendor_id: int
    vendor_name: Optional[str] = None
    invoice_type: str
    invoice_date: Optional[datetime.date] = None
    net_amount: Optional[Decimal] = None
    currency_code: str
    status_code: str
    created_at: Optional[datetime.datetime] = None
    source: str
    batch_id: Optional[int] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    purchase_category_id: Optional[int] = None
    purchase_category_name: Optional[str] = None
    coding_source: Optional[str] = None
    checks: List[Check]
    ready: bool
    automation: Optional[dict] = None


class WorkbenchCounts(BaseModel):
    total: int
    ready: int


class Workbench(BaseModel):
    stage: str
    items: List[WorkbenchRow]
    counts: WorkbenchCounts
    max_bulk: int
    can_review: bool = False
    can_send: bool = False


class BulkReviewItem(BaseModel):
    invoice_id: int
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None


class BulkReviewRequest(BaseModel):
    items: List[BulkReviewItem] = Field(..., min_length=1)
    send_for_approval: bool = True


class BulkSendRequest(BaseModel):
    invoice_ids: List[int] = Field(..., min_length=1)


class BulkResult(BaseModel):
    invoice_id: int
    invoice_number: Optional[str] = None
    status: str  # SENT | REVIEWED | SKIPPED | FAILED
    message: Optional[str] = None


class BulkResponse(BaseModel):
    results: List[BulkResult]
    summary: dict


def _user_id(request: Request) -> str:
    user = request.state.user or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


def _summary(results) -> dict:
    out = {"SENT": 0, "REVIEWED": 0, "SKIPPED": 0, "FAILED": 0}
    for r in results:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


@router.get("/workbench", response_model=Workbench, dependencies=[Depends(permission_based_access([OCR_REVIEW, SEND]))])
def get_workbench(request: Request, stage: str = Query("to_review", pattern="^(to_review|reviewed)$")):
    data = InvoiceReviewAutomationService(request.state.db).workbench(stage)
    user = request.state.user
    return {**data, "can_review": has_permissions(user, [OCR_REVIEW]), "can_send": has_permissions(user, [SEND])}


@router.post("/bulk-review", response_model=BulkResponse, dependencies=[Depends(permission_based_access([OCR_REVIEW]))])
def bulk_review(body: BulkReviewRequest, request: Request):
    """Review (and, with INVOICE_SEND_FOR_APPROVAL, send) up to 25 clean invoices."""
    send = body.send_for_approval and has_permissions(request.state.user, [SEND])
    try:
        results = InvoiceReviewAutomationService(request.state.db).bulk_review(
            [i.model_dump() for i in body.items], _user_id(request), send)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": results, "summary": _summary(results)}


@router.post("/bulk-send", response_model=BulkResponse, dependencies=[Depends(permission_based_access([SEND]))])
def bulk_send(body: BulkSendRequest, request: Request):
    try:
        results = InvoiceReviewAutomationService(request.state.db).bulk_send(body.invoice_ids, _user_id(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": results, "summary": _summary(results)}
