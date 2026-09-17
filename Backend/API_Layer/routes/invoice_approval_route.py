# Backend/API_Layer/routes/invoice_approval_route.py
"""Policy-driven, multi-level invoice approval (send-for-approval /
approve / reject / status).

Approver identity comes from the JWT payload (request.state.user), the
same 'user_id' (fallback 'sub') claim every other mutating route in this
backend uses - InvoiceApprovalService resolves it to a user_uuid via
ap.ums_user_cache before matching it against the assigned approvers.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.interface.approval_interface import (
    InvoiceApprovalDTO,
    InvoiceApprovalDecisionRequest,
    InvoiceApprovalStepDTO,
    InvoiceRejectionRequest,
    InvoiceSendBackRequest,
    StatusResponse,
)
from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService

router = APIRouter()

_INVOICE_NOT_FOUND = "not found"

# Viewing the approval status/timeline is broader than deciding on it — per the role matrix, an
# AP Executive tracking what they submitted and a Finance user checking why an invoice isn't
# Approved yet both need read access here too, not just an actual approver. INVOICE_VIEW is the
# one permission every AP Invoice group (Intake/Approver/Finance) carries, so it alone covers all
# three; INVOICE_APPROVE/INVOICE_REJECT stay listed for a caller who somehow holds those without
# INVOICE_VIEW.
_APPROVAL_VIEW_PERMISSIONS = ["INVOICE_VIEW", "INVOICE_APPROVAL_VIEW", "INVOICE_APPROVE", "INVOICE_REJECT"]


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _status_code_for(message: str) -> int:
    return 404 if _INVOICE_NOT_FOUND in message.lower() else 422


@router.post(
    "/{invoice_id}/send-for-approval",
    response_model=InvoiceApprovalDTO,
    dependencies=[
        Depends(permission_based_access(["INVOICE_SEND_FOR_APPROVAL"]))
    ],
)
def send_invoice_for_approval(invoice_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return InvoiceApprovalService(db).send_for_approval(invoice_id, user_id)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{invoice_id}/approve",
    response_model=InvoiceApprovalDTO,
    dependencies=[
        Depends(permission_based_access(["INVOICE_APPROVE"]))
    ],
)
def approve_invoice(invoice_id: int, payload: InvoiceApprovalDecisionRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return InvoiceApprovalService(db).approve(invoice_id, user_id, payload.comments)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{invoice_id}/reject",
    response_model=InvoiceApprovalDTO,
    dependencies=[
        Depends(permission_based_access(["INVOICE_REJECT"]))
    ],
)
def reject_invoice(invoice_id: int, payload: InvoiceRejectionRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return InvoiceApprovalService(db).reject(invoice_id, user_id, payload.comments)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{invoice_id}/send-back",
    response_model=InvoiceApprovalDTO,
    dependencies=[
        Depends(permission_based_access(["INVOICE_SEND_BACK"]))
    ],
)
def send_invoice_back(invoice_id: int, payload: InvoiceSendBackRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return InvoiceApprovalService(db).send_back(invoice_id, user_id, payload.comments)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{invoice_id}/approval",
    response_model=InvoiceApprovalDTO,
    dependencies=[Depends(permission_based_access(_APPROVAL_VIEW_PERMISSIONS))],
)
def get_invoice_approval(invoice_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return InvoiceApprovalService(db).get_approval_detail(invoice_id)

    except ValueError as e:
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{invoice_id}/approval/steps",
    response_model=List[InvoiceApprovalStepDTO],
    dependencies=[Depends(permission_based_access(_APPROVAL_VIEW_PERMISSIONS))],
)
def get_invoice_approval_steps(invoice_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return InvoiceApprovalService(db).get_steps(invoice_id)

    except ValueError as e:
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-all-statuses", response_model=List[StatusResponse])
def get_all_statuses(http_request: Request):
    db = http_request.state.db

    try:
        return InvoiceApprovalService(db).get_all_statuses()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
