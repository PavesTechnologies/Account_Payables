# Backend/API_Layer/routes/payment_route.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from Backend.API_Layer.interface.payment_interface import (
    InvoicePaymentDetailDTO,
    InvoicePaymentPageDTO,
    InvoiceReadyForPaymentResponse,
    PaymentCreateRequest,
    PaymentDocumentDTO,
    PaymentDTO,
    PaymentMetadataDTO,
    PaymentResponse,
    PaymentStatusUpdateRequest,
    RecordPaymentRequest,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import download_from_s3, view_from_s3
from Backend.Business_Layer.services.payment_service import PaymentService
from Backend.Business_Layer.services.payment_tracking_service import PaymentNotFoundError, PaymentTrackingService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()

# This router previously had zero permission checks on any endpoint — any authenticated user
# could create/list/update payments. PAYMENT_VIEW/PAYMENT_PROCESS follow the exact
# Depends(permission_based_access([...])) pattern already used on invoice_approval_route.py
# (e.g. INVOICE_SEND_FOR_APPROVAL/INVOICE_APPROVE/INVOICE_REJECT) rather than inventing a new
# authorization mechanism.


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


@router.post(
    "",
    response_model=PaymentResponse,
    dependencies=[Depends(permission_based_access(["PAYMENT_PROCESS"]))],
)
def create_payment(payload: PaymentCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        payment = PaymentService(db).create_payment(payload, user_id)

        return PaymentResponse(
            payment_id=payment.payment_id,
            message="Payment created (status SCHEDULED)",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# Payment Management screens (PaymentTrackingService). Declared BEFORE the
# GET "/{payment_id}" route below so "/metadata", "/history", ... are not
# captured by it.
# =========================================================

_PAYMENT_READ_PERMISSIONS = ["PAYMENT_VIEW", "PAYMENT_PROCESS"]


def _tracking_error(e: Exception, db, rollback: bool = True):
    if rollback:
        db.rollback()
    if isinstance(e, PaymentNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(e, HTTPException):
        raise e
    raise HTTPException(status_code=500, detail="Payment request failed")


@router.get(
    "/metadata",
    response_model=PaymentMetadataDTO,
    dependencies=[Depends(permission_based_access(_PAYMENT_READ_PERMISSIONS))],
)
def get_payment_metadata():
    """Payment modes, document types and upload limits for the Record Payment form."""
    return PaymentTrackingService.metadata()


@router.get(
    "/ready-for-payment",
    response_model=InvoicePaymentPageDTO,
    dependencies=[Depends(permission_based_access(_PAYMENT_READ_PERMISSIONS))],
)
def list_ready_for_payment(
    http_request: Request,
    search: Optional[str] = Query(None, description="Invoice number or vendor name"),
    status: Optional[str] = Query(None, description="Comma-separated invoice status codes; default READY_FOR_PAYMENT,PARTIALLY_PAID"),
    vendor_id: Optional[int] = Query(None),
    due_from: Optional[date] = Query(None),
    due_to: Optional[date] = Query(None),
    overdue: bool = Query(False, description="Only invoices past their due date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    db = http_request.state.db
    try:
        return PaymentTrackingService(db).list_ready_for_payment(search, status, vendor_id, due_from, due_to, overdue, page, page_size)
    except Exception as e:
        _tracking_error(e, db, rollback=False)


@router.get(
    "/history",
    response_model=InvoicePaymentPageDTO,
    dependencies=[Depends(permission_based_access(_PAYMENT_READ_PERMISSIONS))],
)
def list_payment_history(
    http_request: Request,
    search: Optional[str] = Query(None, description="Invoice number or vendor name"),
    status: Optional[str] = Query(None, description="Comma-separated invoice status codes, e.g. PAID,PARTIALLY_PAID"),
    vendor_id: Optional[int] = Query(None),
    payment_mode: Optional[str] = Query(None),
    paid_from: Optional[date] = Query(None),
    paid_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Invoices that have at least one payment, most recently paid first."""
    db = http_request.state.db
    try:
        return PaymentTrackingService(db).list_payment_history(search, status, vendor_id, payment_mode, paid_from, paid_to, page, page_size)
    except Exception as e:
        _tracking_error(e, db, rollback=False)


@router.get(
    "/invoice/{invoice_id}",
    response_model=InvoicePaymentDetailDTO,
    dependencies=[Depends(permission_based_access(_PAYMENT_READ_PERMISSIONS))],
)
def get_invoice_payments(invoice_id: int, http_request: Request):
    """Invoice payment summary + every payment (with receipts) applied to it."""
    db = http_request.state.db
    try:
        return PaymentTrackingService(db).get_invoice_payments(invoice_id)
    except Exception as e:
        _tracking_error(e, db, rollback=False)


@router.post(
    "/invoice/{invoice_id}/record",
    response_model=InvoicePaymentDetailDTO,
    status_code=201,
    dependencies=[Depends(permission_based_access(["PAYMENT_PROCESS"]))],
)
def record_payment(invoice_id: int, payload: RecordPaymentRequest, http_request: Request):
    """Record a completed payment (partial or full). Returns the refreshed
    invoice payment detail; recorded_payment_id identifies the new payment
    (use it to upload the receipt)."""
    db = http_request.state.db
    try:
        return PaymentTrackingService(db).record_payment(invoice_id, payload, _get_user_id(http_request))
    except Exception as e:
        _tracking_error(e, db)


@router.post(
    "/{payment_id}/documents",
    response_model=PaymentDocumentDTO,
    status_code=201,
    dependencies=[Depends(permission_based_access(["PAYMENT_PROCESS"]))],
)
async def upload_payment_document(
    payment_id: int,
    http_request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("RECEIPT"),
):
    db = http_request.state.db
    content = await file.read()
    try:
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as e:
        raise HTTPException(status_code=415 if isinstance(e, UnsupportedFileType) else 400, detail=str(e))
    try:
        return PaymentTrackingService(db).upload_document(
            payment_id, file.filename, content, file.content_type, document_type, _get_user_id(http_request)
        )
    except Exception as e:
        _tracking_error(e, db)


@router.get(
    "/{payment_id}/documents/{document_id}/view",
    dependencies=[Depends(permission_based_access(_PAYMENT_READ_PERMISSIONS))],
)
def view_payment_document(payment_id: int, document_id: int, http_request: Request):
    db = http_request.state.db
    try:
        document = PaymentTrackingService(db).get_document(payment_id, document_id)
    except Exception as e:
        _tracking_error(e, db, rollback=False)
    return view_from_s3(document.file_path)


@router.get(
    "/{payment_id}/documents/{document_id}/download",
    dependencies=[Depends(permission_based_access(_PAYMENT_READ_PERMISSIONS))],
)
def download_payment_document(payment_id: int, document_id: int, http_request: Request):
    db = http_request.state.db
    try:
        document = PaymentTrackingService(db).get_document(payment_id, document_id)
    except Exception as e:
        _tracking_error(e, db, rollback=False)
    return download_from_s3(document.file_path)


@router.post(
    "/invoice/{invoice_id}/ready-for-payment",
    response_model=InvoiceReadyForPaymentResponse,
    dependencies=[Depends(permission_based_access(["PAYMENT_PROCESS"]))],
)
def mark_invoice_ready_for_payment(invoice_id: int, http_request: Request):
    """APPROVED -> READY_FOR_PAYMENT — the explicit Finance action a merely-approved invoice
    needs before any payment can be created against it (PaymentService._INVOICE_PAYABLE_STATUSES)."""
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        invoice = PaymentService(db).mark_ready_for_payment(invoice_id, user_id)
        return InvoiceReadyForPaymentResponse(
            invoice_id=invoice.invoice_id,
            status_code="READY_FOR_PAYMENT",
            message="Invoice marked ready for payment",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=list[PaymentDTO],
    dependencies=[Depends(permission_based_access(["PAYMENT_VIEW"]))],
)
def get_all_payments(
    http_request: Request,
    vendor_id: Optional[int] = None,
    status_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        return PaymentService(db).list_payments(vendor_id, status_id, skip, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{payment_id}",
    response_model=PaymentDTO,
    dependencies=[Depends(permission_based_access(["PAYMENT_VIEW"]))],
)
def get_payment_by_id(payment_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return PaymentService(db).get_payment(payment_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/{payment_id}/status",
    response_model=PaymentDTO,
    dependencies=[Depends(permission_based_access(["PAYMENT_PROCESS"]))],
)
def update_payment_status(
    payment_id: int,
    payload: PaymentStatusUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return PaymentService(db).update_status(
            payment_id,
            payload.status_code,
            payload.payment_date,
            payload.reference_number,
            user_id,
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
