# Backend/API_Layer/routes/payment_route.py
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from Backend.API_Layer.interface.payment_interface import (
    PaymentCreateRequest,
    PaymentDTO,
    PaymentResponse,
    PaymentStatusUpdateRequest,
)
from Backend.Business_Layer.services.payment_service import PaymentService

router = APIRouter()


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


@router.post("", response_model=PaymentResponse)
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


@router.get("", response_model=list[PaymentDTO])
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


@router.get("/{payment_id}", response_model=PaymentDTO)
def get_payment_by_id(payment_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return PaymentService(db).get_payment(payment_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{payment_id}/status", response_model=PaymentDTO)
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
