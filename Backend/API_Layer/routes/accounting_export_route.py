# Backend/API_Layer/routes/accounting_export_route.py
"""Accounting export (mounted at /apm/accounting-export).

Preview / export / history: ACCOUNTING_EXPORT, PAYMENT_PROCESS or AP_AUTOMATION_MANAGE.
Ledger names: ACCOUNTING_EXPORT or AP_AUTOMATION_MANAGE.
"""
import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.accounting_export_service import (EXPORT_PERMISSIONS, LEDGER_PERMISSIONS,
                                                                       AccountingExportService)

router = APIRouter()


class LedgerBody(BaseModel):
    ledgers: Dict[str, str] = Field(default_factory=dict)
    categories: Dict[int, str] = Field(default_factory=dict)
    company: Optional[str] = Field(None, max_length=200)


class ExportBody(BaseModel):
    date_from: datetime.date
    date_to: datetime.date
    export_format: str = "TALLY_XML"
    types: Optional[List[str]] = None
    include_exported: bool = False
    include_masters: bool = True


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


def _call(request: Request, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        request.state.db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _file(name: str, content: bytes, ctype: str, extra: Optional[dict] = None) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{name}"', "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Id, X-Voucher-Count"}
    for k, v in (extra or {}).items():
        headers[k] = str(v)
    return Response(content, media_type=ctype, headers=headers)


@router.get("/ledgers", dependencies=[Depends(permission_based_access(EXPORT_PERMISSIONS))])
def ledgers(request: Request):
    return JSONResponse(jsonable_encoder(AccountingExportService(request.state.db).describe_ledgers()))


@router.put("/ledgers", dependencies=[Depends(permission_based_access(LEDGER_PERMISSIONS))])
def update_ledgers(body: LedgerBody, request: Request):
    """Ledger names as they are in Tally / Zoho Books (exact spelling - the import matches by name)."""
    return JSONResponse(jsonable_encoder(_call(request, AccountingExportService(request.state.db).update_ledgers,
                                               body.ledgers, body.categories, body.company, _user_id(request))))


@router.get("/preview", dependencies=[Depends(permission_based_access(EXPORT_PERMISSIONS))])
def preview(request: Request, date_from: datetime.date = Query(...), date_to: datetime.date = Query(...),
            types: Optional[List[str]] = Query(None), include_exported: bool = Query(False)):
    """The vouchers an export would contain (debits / credits per ledger), and how many are already exported."""
    return JSONResponse(jsonable_encoder(_call(request, AccountingExportService(request.state.db).preview,
                                               date_from, date_to, types, include_exported)))


@router.post("/export", dependencies=[Depends(permission_based_access(EXPORT_PERMISSIONS))])
def export(body: ExportBody, request: Request):
    """Builds the file (Tally XML / Zoho Books CSV / CSV), records the vouchers as exported and returns it."""
    name, content, ctype, info = _call(request, AccountingExportService(request.state.db).export, body.date_from, body.date_to,
                                       body.export_format, _user_id(request), body.types, body.include_exported, body.include_masters)
    return _file(name, content, ctype, {"X-Export-Id": info["export_id"], "X-Voucher-Count": info["vouchers"]})


@router.get("/history", dependencies=[Depends(permission_based_access(EXPORT_PERMISSIONS))])
def history(request: Request):
    return JSONResponse(jsonable_encoder(AccountingExportService(request.state.db).history()))


@router.get("/{export_id}/file", dependencies=[Depends(permission_based_access(EXPORT_PERMISSIONS))])
def download(export_id: int, request: Request):
    name, content, ctype = _call(request, AccountingExportService(request.state.db).file, export_id)
    return _file(name, content, ctype)
