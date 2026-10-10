# Backend/API_Layer/routes/ap_automation_route.py
"""Touchless PO-invoice automation (Step B). Settings, statistics and "run now" need
AP_AUTOMATION_MANAGE (Finance Manager). Re-checking a single waiting invoice is also open to the
AP Executive (INVOICE_OCR_REVIEW) - it runs the same controls, never weaker ones."""
import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.ap_automation_service import APAutomationService
from Backend.Business_Layer.services.ap_automation_settings_service import AP_AUTOMATION_MANAGE, APAutomationSettingsService

router = APIRouter()

_MANAGE = [AP_AUTOMATION_MANAGE]
_RECHECK = [AP_AUTOMATION_MANAGE, "INVOICE_OCR_REVIEW"]


class Settings(BaseModel):
    enabled: bool
    price_tolerance_pct: Decimal
    price_tolerance_amount: Decimal
    quantity_tolerance: Decimal
    require_grn: bool
    auto_approve_max_amount: Decimal
    updated_by: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None


class SettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    price_tolerance_pct: Optional[Decimal] = None
    price_tolerance_amount: Optional[Decimal] = None
    quantity_tolerance: Optional[Decimal] = None
    require_grn: Optional[bool] = None
    auto_approve_max_amount: Optional[Decimal] = None


class ExceptionCount(BaseModel):
    reason: str
    count: int


class Stats(BaseModel):
    days: int
    processed: int
    auto_approved: int
    auto_sent: int
    reviewed_not_sent: int
    exceptions: int
    touchless_rate: Optional[float] = None
    top_exceptions: List[ExceptionCount]


class RunResult(BaseModel):
    invoice_id: int
    outcome: Optional[str] = None
    reasons: List[str] = []
    po_number: Optional[str] = None


def _user(request: Request):
    user = request.state.user or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id), user.get("name") or user.get("email")


def _settings_body(db) -> dict:
    service = APAutomationSettingsService(db)
    return {**service.get().as_dict(), **service.last_change()}


@router.get("/settings", response_model=Settings, dependencies=[Depends(permission_based_access(_MANAGE))])
def get_settings(request: Request):
    return _settings_body(request.state.db)


@router.put("/settings", response_model=Settings, dependencies=[Depends(permission_based_access(_MANAGE))])
def update_settings(body: SettingsUpdate, request: Request):
    user_id, name = _user(request)
    try:
        APAutomationSettingsService(request.state.db).update(body.model_dump(), user_id, name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _settings_body(request.state.db)


@router.get("/stats", response_model=Stats, dependencies=[Depends(permission_based_access(_MANAGE))])
def get_stats(request: Request, days: int = Query(30, ge=1, le=365)):
    return APAutomationService(request.state.db).stats(days)


@router.post("/run", response_model=List[RunResult], dependencies=[Depends(permission_based_access(_MANAGE))])
def run_now(request: Request):
    """Re-check every waiting bulk / email PO invoice now (only while automation is on)."""
    service = APAutomationService(request.state.db)
    if not service.settings.enabled:
        raise HTTPException(status_code=409, detail="AP automation is switched off.")
    return service.sweep()


@router.post("/invoices/{invoice_id}/run", response_model=RunResult, dependencies=[Depends(permission_based_access(_RECHECK))])
def run_invoice(invoice_id: int, request: Request):
    service = APAutomationService(request.state.db)
    if not service.settings.enabled:
        raise HTTPException(status_code=409, detail="AP automation is switched off.")
    result = service.run(invoice_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Only PO invoices waiting for review can be re-checked.")
    return result
