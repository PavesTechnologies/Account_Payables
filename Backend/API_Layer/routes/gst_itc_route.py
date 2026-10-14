# Backend/API_Layer/routes/gst_itc_route.py
"""GST input tax credit register (mounted at /apm/gst/itc).

View: GST_ITC_VIEW / GST_ITC_MANAGE / PAYMENT_VIEW / PAYMENT_PROCESS / AP_AUTOMATION_MANAGE.
Manage (eligibility, IRN, claim, reverse, re-claim, sync): GST_ITC_MANAGE or AP_AUTOMATION_MANAGE.
"""
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.gst_itc_service import MANAGE_PERMISSIONS, VIEW_PERMISSIONS, GstItcService

router = APIRouter()


class EligibilityBody(BaseModel):
    eligibility: str
    reason: str = Field(..., min_length=5, max_length=1000)


class IrnBody(BaseModel):
    irn: str = Field(..., min_length=64, max_length=64)
    ack_no: Optional[str] = Field(None, max_length=30)


class PeriodBody(BaseModel):
    period: datetime.date


class InvoicesPeriodBody(PeriodBody):
    invoice_ids: List[int] = Field(..., min_length=1)


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


def _row(g) -> dict:
    return {"invoice_id": g.invoice_id, "itc_eligibility": g.itc_eligibility, "itc_status": g.itc_status, "irn_status": g.irn_status}


@router.get("", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def register(request: Request, month: Optional[datetime.date] = Query(None, description="Any day of the month to list")):
    """The month's purchase invoices with their GST split and ITC status, what needs attention
    (IRN missing, eligibility review, 180-day risk) and the last six returns' claimed credit."""
    return _call(GstItcService(request.state.db).register, month)


@router.post("/sync", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def sync(request: Request):
    """Builds / refreshes the ITC row of every invoice (e.g. right after the migration)."""
    return {"synced": GstItcService(request.state.db).sync_all()}


@router.put("/{invoice_id}/eligibility", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def set_eligibility(invoice_id: int, body: EligibilityBody, request: Request):
    return _call(lambda: _row(GstItcService(request.state.db).set_eligibility(invoice_id, body.eligibility, body.reason, _user_id(request))))


@router.put("/{invoice_id}/irn", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def set_irn(invoice_id: int, body: IrnBody, request: Request):
    return _call(lambda: _row(GstItcService(request.state.db).set_irn(invoice_id, body.irn, body.ack_no, _user_id(request))))


@router.post("/claim", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def claim(body: PeriodBody, request: Request):
    """Marks the period's claimable credit as taken in that month's GSTR-3B."""
    return _call(GstItcService(request.state.db).claim, body.period, _user_id(request))


@router.post("/reverse", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def reverse(body: InvoicesPeriodBody, request: Request):
    return _call(lambda: {"reversed": GstItcService(request.state.db).reverse(body.invoice_ids, body.period, _user_id(request))})


@router.post("/reclaim", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def reclaim(body: InvoicesPeriodBody, request: Request):
    return _call(lambda: {"reclaimed": GstItcService(request.state.db).reclaim(body.invoice_ids, body.period, _user_id(request))})
