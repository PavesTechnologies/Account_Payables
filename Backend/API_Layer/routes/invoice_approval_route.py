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
    StatusResponse
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
    payload: InvoiceApprovalDecisionRequest,  # FastAPI automatically parses the JSON body here
    http_request: Request,
):
    db = http_request.state.db
    user_id = _get_user_id(http_request)

    try:
        # Access the comments sent by the frontend using payload.comments
        comments = payload.comments 

        # Update the invoice status
        InvoiceApprovalService(db).update_invoice_status(
            invoice_id=invoice_id, 
            status_id=9, 
            user_id=user_id
        )

        # CRITICAL: Commit the changes to the database
        db.commit() 

        return InvoiceApprovalActionResponse(
            invoice_id=invoice_id,
            status_id=9,
            message=f"Invoice approved. Comments: {comments}",
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

@router.get("/get-all-statuses", response_model=list[StatusResponse])
def get_all_statuses(http_request: Request):
    db = http_request.state.db

    try:
        return InvoiceApprovalService(db).get_all_statuses()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/status-update/{invoice_id}", response_model=InvoiceApprovalActionResponse)
def update_invoice_status(invoice_id: int, status_id: int, http_request: Request):
    db = http_request.state.db
    user_id = _get_user_id(http_request)

    try:
        approver = _get_user_id(http_request)
        approval = InvoiceApprovalService(db).update_invoice_status(invoice_id, status_id, user_id)

        return InvoiceApprovalActionResponse(
            invoice_id=invoice_id,
            status_id=approval.status_id,
            message="Invoice status updated",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
