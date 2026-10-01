# Backend/API_Layer/routes/tds_tracking_route.py
"""TDS Tracking APIs (mounted at /apm/tds/tracking): the TDS-applicable invoice
list, per-invoice TDS detail, and recording TDS activity Finance performed
outside this system (deduction, challan deposit, return filing) plus
supporting documents. Server-side permissions:
    TDS_TRACKING_VIEW   - list / detail / metadata / view documents
    TDS_TRACKING_UPDATE - record activity / upload documents (+ read)
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.tds_tracking_interface import (
    RecordTdsDeductionRequest,
    RecordTdsDepositRequest,
    RecordTdsFilingRequest,
    TdsDocumentDTO,
    TdsTrackingDetailDTO,
    TdsTrackingMetadataDTO,
    TdsTrackingPageDTO,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import download_from_s3, view_from_s3
from Backend.Business_Layer.services.tds_tracking_service import TdsTrackingNotFoundError, TdsTrackingService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()

TDS_TRACKING_VIEW = "TDS_TRACKING_VIEW"
TDS_TRACKING_UPDATE = "TDS_TRACKING_UPDATE"
_READ = [TDS_TRACKING_VIEW, TDS_TRACKING_UPDATE]


def _get_user_id(http_request: Request) -> str:
    user_id = http_request.state.user.get("user_id") or http_request.state.user.get("sub")
    if user_id is None:
        raise ValueError("Token payload missing user identifier")
    return user_id


def _raise_http(e: Exception, db, rollback: bool = True):
    if rollback:
        db.rollback()
    if isinstance(e, TdsTrackingNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(e, IntegrityError):
        raise HTTPException(status_code=409, detail="TDS tracking was changed by another request - reload and try again")
    if isinstance(e, HTTPException):
        raise e
    raise HTTPException(status_code=500, detail="TDS tracking request failed")


@router.get("/metadata", response_model=TdsTrackingMetadataDTO, dependencies=[Depends(permission_based_access(_READ))])
def get_metadata():
    return TdsTrackingService.metadata()


@router.get("", response_model=TdsTrackingPageDTO, dependencies=[Depends(permission_based_access(_READ))])
def list_tds_invoices(
    http_request: Request,
    search: Optional[str] = Query(None, description="Invoice number or vendor name"),
    tds_status: Optional[str] = Query(None, description="Comma-separated TDS tracking statuses"),
    payment_nature: Optional[str] = Query(None, description="Payment nature code"),
    determination_status: Optional[str] = Query(None, description="PENDING / DETERMINED / VERIFIED"),
    invoice_status: Optional[str] = Query(None, description="Comma-separated invoice status codes"),
    vendor_id: Optional[int] = Query(None),
    invoice_date_from: Optional[date] = Query(None),
    invoice_date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Invoices whose TDS determination says TDS is applicable."""
    db = http_request.state.db
    try:
        return TdsTrackingService(db).list_tds_invoices(
            search, tds_status, payment_nature, determination_status, invoice_status, vendor_id,
            invoice_date_from, invoice_date_to, page, page_size,
        )
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.get("/{invoice_id}", response_model=TdsTrackingDetailDTO, dependencies=[Depends(permission_based_access(_READ))])
def get_tds_detail(invoice_id: int, http_request: Request):
    db = http_request.state.db
    try:
        return TdsTrackingService(db).get_tds_detail(invoice_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.post("/{invoice_id}/deduction", response_model=TdsTrackingDetailDTO,
             dependencies=[Depends(permission_based_access([TDS_TRACKING_UPDATE]))])
def record_deduction(invoice_id: int, payload: RecordTdsDeductionRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsTrackingService(db).record_deduction(invoice_id, payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.post("/{invoice_id}/deposit", response_model=TdsTrackingDetailDTO,
             dependencies=[Depends(permission_based_access([TDS_TRACKING_UPDATE]))])
def record_deposit(invoice_id: int, payload: RecordTdsDepositRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsTrackingService(db).record_deposit(invoice_id, payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.post("/{invoice_id}/filing", response_model=TdsTrackingDetailDTO,
             dependencies=[Depends(permission_based_access([TDS_TRACKING_UPDATE]))])
def record_filing(invoice_id: int, payload: RecordTdsFilingRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsTrackingService(db).record_filing(invoice_id, payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.post("/{invoice_id}/documents", response_model=TdsDocumentDTO, status_code=201,
             dependencies=[Depends(permission_based_access([TDS_TRACKING_UPDATE]))])
async def upload_document(
    invoice_id: int,
    http_request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("OTHER"),
):
    db = http_request.state.db
    content = await file.read()
    try:
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as e:
        raise HTTPException(status_code=415 if isinstance(e, UnsupportedFileType) else 400, detail=str(e))
    try:
        return TdsTrackingService(db).upload_document(
            invoice_id, file.filename, content, file.content_type, document_type, _get_user_id(http_request)
        )
    except Exception as e:
        _raise_http(e, db)


@router.get("/{invoice_id}/documents/{document_id}/view", dependencies=[Depends(permission_based_access(_READ))])
def view_document(invoice_id: int, document_id: int, http_request: Request):
    db = http_request.state.db
    try:
        document = TdsTrackingService(db).get_document(invoice_id, document_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)
    return view_from_s3(document.file_path)


@router.get("/{invoice_id}/documents/{document_id}/download", dependencies=[Depends(permission_based_access(_READ))])
def download_document(invoice_id: int, document_id: int, http_request: Request):
    db = http_request.state.db
    try:
        document = TdsTrackingService(db).get_document(invoice_id, document_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)
    return download_from_s3(document.file_path)
