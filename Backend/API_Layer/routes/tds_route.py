# Backend/API_Layer/routes/tds_route.py
from fastapi import APIRouter, Depends, HTTPException, Request

from Backend.API_Layer.interface.tds_interface import (
    InvoiceTdsDTO,
    TdsDetermineRequest,
    TdsUpdateRequest,
    TdsVerifyRequest,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.tds_determination_service import TDSDeterminationService

router = APIRouter()

# Any-of view permissions, same pattern as invoice_approval_route.py's
# _APPROVAL_VIEW_PERMISSIONS / invoice_details_route.py's _HISTORY_VIEW_PERMISSIONS:
# anyone who can act on TDS can also read it, plus a general INVOICE_VIEW grant.
_TDS_VIEW_PERMISSIONS = [
    "INVOICE_TDS_VIEW",
    "INVOICE_TDS_DETERMINE",
    "INVOICE_TDS_EDIT",
    "INVOICE_TDS_VERIFY",
    "INVOICE_VIEW",
]


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _status_code_for(message: str) -> int:
    return 404 if "not found" in message else 422


@router.post(
    "/{invoice_id}/tds/determine",
    response_model=InvoiceTdsDTO,
    dependencies=[Depends(permission_based_access(["INVOICE_TDS_DETERMINE"]))],
)
def determine_tds(invoice_id: int, payload: TdsDetermineRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return TDSDeterminationService(db).determine(invoice_id, user_id, payload.payment_nature_code)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{invoice_id}/tds",
    response_model=InvoiceTdsDTO,
    dependencies=[Depends(permission_based_access(_TDS_VIEW_PERMISSIONS))],
)
def get_tds(invoice_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return TDSDeterminationService(db).get(invoice_id)

    except ValueError as e:
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/{invoice_id}/tds",
    response_model=InvoiceTdsDTO,
    dependencies=[Depends(permission_based_access(["INVOICE_TDS_EDIT"]))],
)
def update_tds(invoice_id: int, payload: TdsUpdateRequest, http_request: Request):
    """AP Executive correction of the payment nature before submission - always
    recalculates server-side (TDSDeterminationService.update_inputs), never accepts
    a client-supplied amount/rate directly."""
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return TDSDeterminationService(db).update_inputs(invoice_id, user_id, payload.payment_nature_code)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{invoice_id}/tds/verify",
    response_model=InvoiceTdsDTO,
    dependencies=[Depends(permission_based_access(["INVOICE_TDS_VERIFY"]))],
)
def verify_tds(invoice_id: int, payload: TdsVerifyRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return TDSDeterminationService(db).verify(invoice_id, user_id, payload.remarks)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e)), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
