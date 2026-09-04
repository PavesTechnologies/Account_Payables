# Backend/API_Layer/routes/rfq_route.py

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.procurement_interface import QuotationDTO
from Backend.API_Layer.interface.rfq_interface import (
    CreateRFQRequest,
    InviteVendorsRequest,
    RFQDTO,
    RFQResponse,
    RFQVendorDTO,
    RFQVendorSendResultDTO,
    SendRFQResponse,
)
from Backend.Business_Layer.services.rfq_service import RFQService

router = APIRouter()

_RFQ_NOT_FOUND = "RFQ not found"


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _status_code_for(message: str, not_found_message: str) -> int:
    return 404 if message == not_found_message else 422


# ---------------------------------------------------------
# Create RFQ
# ---------------------------------------------------------
@router.post("/", response_model=RFQResponse)
def create_rfq(payload: CreateRFQRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = RFQService(db)
        rfq = service.create_rfq(payload.pr_id, payload.due_date, user_id)

        return RFQResponse(id=rfq.id, message="RFQ created successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), "Purchase requisition not found"), detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create RFQ")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# List RFQs
# ---------------------------------------------------------
@router.get("/", response_model=list[RFQDTO])
def get_all_rfqs(
    http_request: Request,
    pr_id: Optional[int] = None,
    status_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = RFQService(db)
        return service.list_rfqs(pr_id, status_id, skip, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get RFQ By ID
# ---------------------------------------------------------
@router.get("/{rfq_id}", response_model=RFQDTO)
def get_rfq_by_id(rfq_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = RFQService(db)
        return service.get_rfq(rfq_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Invite / List Vendors
# ---------------------------------------------------------
@router.post("/{rfq_id}/vendors", response_model=RFQDTO)
def invite_vendors(rfq_id: int, payload: InviteVendorsRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = RFQService(db)
        return service.invite_vendors(rfq_id, payload.vendor_ids, user_id)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _RFQ_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{rfq_id}/vendors", response_model=list[RFQVendorDTO])
def get_rfq_vendors(rfq_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = RFQService(db)
        return service.list_vendors(rfq_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Send / Close RFQ
# ---------------------------------------------------------
@router.post("/{rfq_id}/send", response_model=SendRFQResponse)
def send_rfq(rfq_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = RFQService(db)
        rfq, results = service.send_rfq(rfq_id, user_id)

        failures = [r for r in results if not r.success]
        message = (
            "RFQ sent successfully to all invited vendors"
            if not failures
            else f"RFQ sent, but email delivery failed for {len(failures)} of {len(results)} vendor(s)"
        )
        results_dto = [
            RFQVendorSendResultDTO(
                vendor_id=r.vendor_id, email=r.email, success=r.success, sent_at=r.sent_at, error=r.error
            )
            for r in results
        ]

        return SendRFQResponse(id=rfq.id, status_id=rfq.status_id, message=message, results=results_dto)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _RFQ_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rfq_id}/close", response_model=RFQDTO)
def close_rfq(rfq_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = RFQService(db)
        return service.close_rfq(rfq_id, user_id)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _RFQ_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Quotations for an RFQ
# ---------------------------------------------------------
@router.get("/{rfq_id}/quotations", response_model=list[QuotationDTO])
def get_quotations_for_rfq(rfq_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = RFQService(db)
        return service.list_quotations(rfq_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
