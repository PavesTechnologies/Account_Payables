# Backend/API_Layer/routes/recurring_route.py
"""Recurring invoice schedules (mounted at /apm/recurring-schedules).

View: INVOICE_VIEW / PAYMENT_VIEW / PAYMENT_PROCESS / RECURRING_INVOICE_MANAGE / AP_AUTOMATION_MANAGE.
Manage (create, edit, skip a period, link an invoice): RECURRING_INVOICE_MANAGE or AP_AUTOMATION_MANAGE.
"""
import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.recurring_service import MANAGE_PERMISSIONS, VIEW_PERMISSIONS, RecurringService

router = APIRouter()


class ScheduleBody(BaseModel):
    vendor_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=200)
    frequency: Optional[str] = None
    expected_day: Optional[int] = Field(None, ge=1, le=28)
    expected_amount: Optional[Decimal] = Field(None, gt=0)
    tolerance_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    grace_days: Optional[int] = Field(None, ge=0, le=60)
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    agreement_id: Optional[int] = None
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    payment_nature_code: Optional[str] = Field(None, max_length=50)
    match_keyword: Optional[str] = Field(None, max_length=100)
    fast_track: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class SkipBody(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class LinkBody(BaseModel):
    invoice_id: int


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


def _call(fn, *args):
    try:
        return fn(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def overview(request: Request):
    """Every schedule with its recent periods (EXPECTED / DUE / MISSING / RECEIVED / SKIPPED),
    totals for the Action Center and the next three months' expected recurring spend."""
    return JSONResponse(jsonable_encoder(RecurringService(request.state.db).overview()))


@router.post("", status_code=201, dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def create_schedule(body: ScheduleBody, request: Request):
    data = body.model_dump(exclude_none=True)
    schedule = _call(RecurringService(request.state.db).create, data, _user_id(request))
    return {"schedule_id": schedule.schedule_id}


@router.put("/{schedule_id}", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def update_schedule(schedule_id: int, body: ScheduleBody, request: Request):
    data = body.model_dump(exclude_unset=True)
    data.pop("vendor_id", None)  # a schedule never moves to another vendor
    schedule = _call(RecurringService(request.state.db).update, schedule_id, data, _user_id(request))
    return {"schedule_id": schedule.schedule_id}


@router.post("/occurrences/{occurrence_id}/skip", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def skip_period(occurrence_id: int, body: SkipBody, request: Request):
    occ = _call(RecurringService(request.state.db).skip, occurrence_id, body.reason, _user_id(request))
    return {"occurrence_id": occ.occurrence_id, "status": occ.status}


@router.post("/occurrences/{occurrence_id}/link", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def link_invoice(occurrence_id: int, body: LinkBody, request: Request):
    occ = _call(RecurringService(request.state.db).link, occurrence_id, body.invoice_id, _user_id(request))
    return {"occurrence_id": occ.occurrence_id, "status": occ.status, "variance_status": occ.variance_status}
