# Backend/API_Layer/routes/vendor_onboarding_route.py
"""Vendor Onboarding Request endpoints (PR Officer -> Vendor Intaker handoff).

Permissions follow the "new string OR existing grant" convention:
``permission_based_access`` is any-of by default, so a real PR Officer /
Vendor Intaker keeps working with the grants they already hold today, while
the new ONBOARDING_* strings work as soon as UMS provisions them. This avoids
repeating the RFQ_VIEW/RFQ_CREATE incident documented in
tests/test_rfq_authorization.py, where newly invented permission strings
locked existing users out with 403s.

Literal paths are declared before the dynamic /{request_id} paths - see the
same note in vendor_intake_route.py.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.vendor_onboarding_interface import (
    VendorOnboardingAssignRequest,
    VendorOnboardingPreScreenResponse,
    VendorOnboardingRequestCreate,
    VendorOnboardingRequestDTO,
    VendorOnboardingResponse,
    VendorOnboardingStartRequest,
    VendorOnboardingStartResponse,
    VendorOnboardingStatusUpdateRequest,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.vendor_onboarding_service import VendorOnboardingService
from Backend.Data_Access_Layer.models.vendor_onboarding import VendorOnboardingRequest

router = APIRouter()

ONBOARDING_VIEW = ["ONBOARDING_VIEW", "QUOTATION_VIEW"]
ONBOARDING_CREATE = ["ONBOARDING_CREATE", "QUOTATION_CREATE"]
ONBOARDING_ASSIGN = ["ONBOARDING_ASSIGN", "QUOTATION_CREATE"]
ONBOARDING_PROCESS = ["ONBOARDING_PROCESS", "QUOTATION_CREATE"]


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _to_dto(request: VendorOnboardingRequest) -> VendorOnboardingRequestDTO:
    return VendorOnboardingRequestDTO(
        id=request.id,
        pr_id=request.pr_id,
        department_id=request.department_id,
        purchase_category_id=request.purchase_category_id,
        status_id=request.status_id,
        status_code=request.status.status_code if request.status is not None else None,
        business_requirement=request.business_requirement,
        purpose_of_onboarding=request.purpose_of_onboarding,
        requested_vendor_name=request.requested_vendor_name,
        requested_vendor_email=request.requested_vendor_email,
        vendor_id=request.vendor_id,
        engagement_id=request.engagement_id,
        assigned_to=request.assigned_to,
        closed_at=request.closed_at,
        created_by=request.created_by,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _status_code(request: VendorOnboardingRequest) -> Optional[str]:
    return request.status.status_code if request.status is not None else None


def _raise_for_value_error(exc: ValueError):
    message = str(exc)
    status_code = 404 if "not found" in message.lower() else 422
    raise HTTPException(status_code=status_code, detail=message)


# ---------------------------------------------------------
# Create / list (literal paths)
# ---------------------------------------------------------
@router.post(
    "",
    response_model=VendorOnboardingResponse,
    dependencies=[Depends(permission_based_access(ONBOARDING_CREATE))],
)
def create_onboarding_request(payload: VendorOnboardingRequestCreate, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        service = VendorOnboardingService(db)
        request = service.create_request(payload, user_id)

        return VendorOnboardingResponse(
            id=request.id,
            status_code=_status_code(request),
            message="Vendor onboarding request created successfully",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An open vendor onboarding request already exists for this purchase requisition",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=list[VendorOnboardingRequestDTO],
    dependencies=[Depends(permission_based_access(ONBOARDING_VIEW))],
)
def list_onboarding_requests(
    http_request: Request,
    pr_id: Optional[int] = None,
    status_id: Optional[int] = None,
    assigned_to: Optional[str] = None,
    vendor_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = VendorOnboardingService(db)
        requests = service.list_requests(
            pr_id=pr_id, status_id=status_id, assigned_to=assigned_to,
            vendor_id=vendor_id, skip=skip, limit=limit,
        )
        return [_to_dto(request) for request in requests]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Single request (dynamic paths - keep last)
# ---------------------------------------------------------
@router.get(
    "/{request_id}",
    response_model=VendorOnboardingRequestDTO,
    dependencies=[Depends(permission_based_access(ONBOARDING_VIEW))],
)
def get_onboarding_request(request_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorOnboardingService(db)
        return _to_dto(service.get_request(request_id))

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/{request_id}/assign",
    response_model=VendorOnboardingResponse,
    dependencies=[Depends(permission_based_access(ONBOARDING_ASSIGN))],
)
def assign_onboarding_request(
    request_id: int,
    payload: VendorOnboardingAssignRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        service = VendorOnboardingService(db)
        request = service.assign(request_id, payload.assigned_to, user_id)

        return VendorOnboardingResponse(
            id=request.id,
            status_code=_status_code(request),
            message="Vendor onboarding request assigned successfully",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/{request_id}/status",
    response_model=VendorOnboardingResponse,
    dependencies=[Depends(permission_based_access(ONBOARDING_PROCESS))],
)
def update_onboarding_status(
    request_id: int,
    payload: VendorOnboardingStatusUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        service = VendorOnboardingService(db)
        request = service.update_status(request_id, payload.status_code, user_id, payload.reason)

        return VendorOnboardingResponse(
            id=request.id,
            status_code=_status_code(request),
            message="Vendor onboarding request status updated successfully",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{request_id}/start",
    response_model=VendorOnboardingStartResponse,
    dependencies=[Depends(permission_based_access(ONBOARDING_PROCESS))],
)
def start_onboarding(
    request_id: int,
    payload: VendorOnboardingStartRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        service = VendorOnboardingService(db)
        request, intake_result = service.start(request_id, payload, user_id)

        return VendorOnboardingStartResponse(
            id=request.id,
            status_code=_status_code(request),
            vendor_id=request.vendor_id,
            engagement_id=request.engagement_id,
            vendor_created=intake_result.vendor_created,
            gst_status=intake_result.gst_status,
            message="Vendor intake completed for this onboarding request",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An engagement already exists for this vendor, department and category",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{request_id}/pre-screen",
    response_model=VendorOnboardingPreScreenResponse,
    dependencies=[Depends(permission_based_access(ONBOARDING_PROCESS))],
)
def run_onboarding_pre_screen(request_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        service = VendorOnboardingService(db)
        request, outcome = service.run_pre_screen(request_id, user_id)

        return VendorOnboardingPreScreenResponse(
            id=request.id,
            status_code=_status_code(request),
            engagement_id=request.engagement_id,
            result=outcome.result,
            reason=outcome.reason,
            nda_recommended=outcome.nda_recommended,
            message="Pre-Screen completed for this onboarding request",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{request_id}/complete",
    response_model=VendorOnboardingResponse,
    dependencies=[Depends(permission_based_access(ONBOARDING_PROCESS))],
)
def complete_onboarding(request_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        service = VendorOnboardingService(db)
        request = service.complete(request_id, user_id)

        return VendorOnboardingResponse(
            id=request.id,
            status_code=_status_code(request),
            message="Vendor onboarding completed successfully",
        )

    except ValueError as e:
        db.rollback()
        _raise_for_value_error(e)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
