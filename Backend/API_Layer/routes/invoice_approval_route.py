# Backend/API_Layer/routes/invoice_approval_route.py
"""Single-level invoice approval (approve/reject/history).

Approver identity comes from the JWT payload (request.state.user), the
same 'user_id' (fallback 'sub') claim every other mutating route in
this backend uses for created_by/updated_by — no local user table.
"""
from fastapi import APIRouter, HTTPException, Request

from Backend.API_Layer.interface.approval_interface import (
    InvoiceApprovalActionResponse,
    InvoiceApprovalDTO,
    InvoiceApprovalDecisionRequest,
    InvoiceRejectionRequest,
)
from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService

router = APIRouter()


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


@router.post("/{invoice_id}/approve", response_model=InvoiceApprovalActionResponse)
def approve_invoice(
    invoice_id: int,
    payload: InvoiceApprovalDecisionRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        approver = _get_user_id(http_request)
        approval = InvoiceApprovalService(db).approve_invoice(invoice_id, approver, payload.comments)

        return InvoiceApprovalActionResponse(
            invoice_id=invoice_id,
            invoice_approval_id=approval.invoice_approval_id,
            status_code="APPROVED",
            message="Invoice approved",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{invoice_id}/reject", response_model=InvoiceApprovalActionResponse)
def reject_invoice(
    invoice_id: int,
    payload: InvoiceRejectionRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        approver = _get_user_id(http_request)
        approval = InvoiceApprovalService(db).reject_invoice(invoice_id, approver, payload.comments)

        return InvoiceApprovalActionResponse(
            invoice_id=invoice_id,
            invoice_approval_id=approval.invoice_approval_id,
            status_code="REJECTED",
            message="Invoice rejected",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{invoice_id}/approvals", response_model=list[InvoiceApprovalDTO])
def get_invoice_approval_history(invoice_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return InvoiceApprovalService(db).get_approval_history(invoice_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
