# Backend/API_Layer/routes/payment_route.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from Backend.API_Layer.interface.payment_interface import (
    InvoiceReadyForPaymentResponse,
    PaymentCreateRequest,
    PaymentDTO,
    PaymentResponse,
    PaymentStatusUpdateRequest,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.payment_service import PaymentService

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
