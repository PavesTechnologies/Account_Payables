# Backend/API_Layer/routes/tds_challan_route.py
"""Shared TDS challan (/tds/challans) and quarterly return filing (/tds/filings) - Phase 5.
Reads need TDS_TRACKING_VIEW or TDS_TRACKING_UPDATE; extract / validate / confirm need
TDS_TRACKING_UPDATE (the same permission as the per-invoice deposit / filing actions)."""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import delete_from_s3, upload_to_s3, view_from_s3
from Backend.API_Layer.utils.tds_document_extraction import extract_challan_from_s3, extract_filing_from_s3
from Backend.Business_Layer.services.tds_challan_service import TdsChallanService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

challan_router = APIRouter()
filing_router = APIRouter()

_READ = ["TDS_TRACKING_VIEW", "TDS_TRACKING_UPDATE"]
_WRITE = ["TDS_TRACKING_UPDATE"]


class ChallanAllocationIn(BaseModel):
    invoice_id: int
    allocated_tds_amount: Optional[str] = None


class ChallanValidateRequest(BaseModel):
    header: Dict[str, Any]
    allocations: List[ChallanAllocationIn] = Field(default_factory=list)
    has_document: bool = False


class FilingValidateRequest(BaseModel):
    header: Dict[str, Any]
    invoice_ids: List[int] = Field(default_factory=list)
    has_document: bool = False


def _user_id(request: Request) -> str:
    user = request.state.user or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


async def _read_file(file: Optional[UploadFile]):
    if file is None or not file.filename:
        return None
    content = await file.read()
    try:
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as exc:
        raise HTTPException(status_code=415 if isinstance(exc, UnsupportedFileType) else 400, detail=str(exc))
    return file.filename, content, file.content_type


async def _extract(file: UploadFile, extractor, prefix: str):
    document = await _read_file(file)
    if document is None:
        raise HTTPException(status_code=400, detail="Select a file")
    stored = upload_to_s3(filename=document[0], content=document[1], content_type=document[2], prefix=prefix)
    try:
        return await extractor(stored["filepath"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The document could not be read. Enter the details manually.") from exc
    finally:
        try:
            delete_from_s3(stored["filepath"])
        except Exception:
            pass


def _payload(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="payload must be JSON") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    return data


def _write_error(exc: Exception, db):
    db.rollback()
    if isinstance(exc, IntegrityError):
        raise HTTPException(status_code=409, detail="This document or an invoice on it is already recorded") from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


# ======================================================================
# Challans
# ======================================================================
@challan_router.get("", dependencies=[Depends(permission_based_access(_READ))])
def list_challans(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return TdsChallanService(request.state.db).list_challans(page, page_size)


@challan_router.get("/candidates", dependencies=[Depends(permission_based_access(_READ))])
def challan_candidates(request: Request, period: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
                       section: Optional[str] = None):
    try:
        return TdsChallanService(request.state.db).challan_candidates(period, section)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@challan_router.post("/extract", dependencies=[Depends(permission_based_access(_WRITE))])
async def extract_challan(file: UploadFile = File(...)):
    """Read a challan counterfoil and return suggested values. Records nothing."""
    return await _extract(file, extract_challan_from_s3, "tds/challan-extraction/")


@challan_router.post("/validate", dependencies=[Depends(permission_based_access(_WRITE))])
def validate_challan(body: ChallanValidateRequest, request: Request):
    return TdsChallanService(request.state.db).validate_challan(
        body.header, [a.model_dump(exclude_none=True) for a in body.allocations], body.has_document)


@challan_router.post("", status_code=201, dependencies=[Depends(permission_based_access(_WRITE))])
async def create_challan(request: Request, payload: str = Form(...), file: Optional[UploadFile] = File(None)):
    """payload: JSON {header: {...}, allocations: [{invoice_id, allocated_tds_amount}]}; file: the challan."""
    data = _payload(payload)
    document = await _read_file(file)
    db = request.state.db
    try:
        return TdsChallanService(db).create_challan(data.get("header") or {}, data.get("allocations") or [],
                                                    _user_id(request), document)
    except Exception as exc:
        _write_error(exc, db)


@challan_router.get("/{challan_id}", dependencies=[Depends(permission_based_access(_READ))])
def get_challan(challan_id: int, request: Request):
    try:
        return TdsChallanService(request.state.db).challan_detail(challan_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@challan_router.get("/{challan_id}/document", dependencies=[Depends(permission_based_access(_READ))])
def challan_document(challan_id: int, request: Request):
    challan = TdsChallanService(request.state.db).dao.get_challan(challan_id)
    if challan is None or not challan.file_path:
        raise HTTPException(status_code=404, detail="No document attached")
    return view_from_s3(challan.file_path)


# ======================================================================
# Quarterly filings
# ======================================================================
@filing_router.get("", dependencies=[Depends(permission_based_access(_READ))])
def list_filings(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return TdsChallanService(request.state.db).list_filings(page, page_size)


@filing_router.get("/candidates", dependencies=[Depends(permission_based_access(_READ))])
def filing_candidates(request: Request, financial_year: str = Query(..., pattern=r"^20\d{2}-\d{2}$"),
                      quarter: int = Query(..., ge=1, le=4), revision: bool = False):
    try:
        return TdsChallanService(request.state.db).filing_candidates(financial_year, quarter, revision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@filing_router.post("/extract", dependencies=[Depends(permission_based_access(_WRITE))])
async def extract_filing(file: UploadFile = File(...)):
    return await _extract(file, extract_filing_from_s3, "tds/filing-extraction/")


@filing_router.post("/validate", dependencies=[Depends(permission_based_access(_WRITE))])
def validate_filing(body: FilingValidateRequest, request: Request):
    return TdsChallanService(request.state.db).validate_filing(body.header, body.invoice_ids, body.has_document)


@filing_router.post("", status_code=201, dependencies=[Depends(permission_based_access(_WRITE))])
async def create_filing(request: Request, payload: str = Form(...), file: Optional[UploadFile] = File(None)):
    """payload: JSON {header: {...}, invoice_ids: [...]}; file: the acknowledgement."""
    data = _payload(payload)
    document = await _read_file(file)
    db = request.state.db
    try:
        return TdsChallanService(db).create_filing(data.get("header") or {}, data.get("invoice_ids") or [],
                                                   _user_id(request), document)
    except Exception as exc:
        _write_error(exc, db)


@filing_router.get("/{filing_id}", dependencies=[Depends(permission_based_access(_READ))])
def get_filing(filing_id: int, request: Request):
    try:
        return TdsChallanService(request.state.db).filing_detail(filing_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@filing_router.get("/{filing_id}/document", dependencies=[Depends(permission_based_access(_READ))])
def filing_document(filing_id: int, request: Request):
    filing = TdsChallanService(request.state.db).dao.get_filing(filing_id)
    if filing is None or not filing.file_path:
        raise HTTPException(status_code=404, detail="No document attached")
    return view_from_s3(filing.file_path)
