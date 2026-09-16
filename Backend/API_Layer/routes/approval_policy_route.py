# Backend/API_Layer/routes/approval_policy_route.py
"""Admin CRUD for the configurable invoice approval policy, plus
approver-lookup endpoints the policy builder UI needs (backed by
ap.approver_directory / ap.approver_directory_role via
ApproverDirectoryDAO - never a local user table)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.interface.approval_policy_interface import (
    ApprovalPolicyCreateRequest,
    ApprovalPolicyDTO,
    ApprovalPolicyResponse,
    ApprovalPolicyStatusRequest,
    ApprovalPolicyUpdateRequest,
    ApproverLookupDTO,
    DeleteApprovalPolicyResponse,
    DepartmentApproverCreateRequest,
    DepartmentApproverDTO,
)
from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService
from Backend.Business_Layer.services.department_approver_service import DepartmentApproverService
from Backend.Data_Access_Layer.dao.approver_directory_dao import ApproverDirectoryDAO

router = APIRouter()

_POLICY_NOT_FOUND = "Approval policy not found"


def _status_code_for(message: str, not_found_message: str) -> int:
    return 404 if message == not_found_message else 422


# ---------------------------------------------------------
# List / Get
# ---------------------------------------------------------
@router.get(
    "/approval-policies",
    response_model=List[ApprovalPolicyDTO],
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def list_approval_policies(
    http_request: Request,
    department_id: Optional[int] = Query(None),
    purchase_category_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    db = http_request.state.db

    try:
        return ApprovalPolicyService(db).list_policies(department_id, purchase_category_id, is_active)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/approval-policies/{policy_id}",
    response_model=ApprovalPolicyDTO,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def get_approval_policy(policy_id: int, http_request: Request):
    db = http_request.state.db

    try:
        return ApprovalPolicyService(db).get_policy(policy_id)

    except ValueError as e:
        raise HTTPException(status_code=_status_code_for(str(e), _POLICY_NOT_FOUND), detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Create / Update / Status / Delete
# ---------------------------------------------------------
@router.post(
    "/approval-policies",
    response_model=ApprovalPolicyResponse,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def create_approval_policy(payload: ApprovalPolicyCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        policy = ApprovalPolicyService(db).create_policy(payload)
        return ApprovalPolicyResponse(id=policy.id, message="Approval policy created successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create approval policy")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/approval-policies/{policy_id}",
    response_model=ApprovalPolicyDTO,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def update_approval_policy(policy_id: int, payload: ApprovalPolicyUpdateRequest, http_request: Request):
    db = http_request.state.db

    try:
        return ApprovalPolicyService(db).update_policy(policy_id, payload)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _POLICY_NOT_FOUND), detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not update approval policy")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/approval-policies/{policy_id}/status",
    response_model=ApprovalPolicyDTO,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def set_approval_policy_status(policy_id: int, payload: ApprovalPolicyStatusRequest, http_request: Request):
    db = http_request.state.db

    try:
        return ApprovalPolicyService(db).set_policy_status(policy_id, payload.is_active)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _POLICY_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/approval-policies/{policy_id}",
    response_model=DeleteApprovalPolicyResponse,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def delete_approval_policy(policy_id: int, http_request: Request):
    db = http_request.state.db

    try:
        ApprovalPolicyService(db).delete_policy(policy_id)
        return DeleteApprovalPolicyResponse(id=policy_id, message="Approval policy deleted successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _POLICY_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# Approver lookups (for the policy builder UI)
# =========================================================

@router.get(
    "/approval/roles",
    response_model=List[str],
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def list_approver_roles(http_request: Request):
    db = http_request.state.db

    try:
        return ApproverDirectoryDAO(db).list_distinct_role_codes()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/approval/approvers",
    response_model=List[ApproverLookupDTO],
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def list_approvers(http_request: Request, role_code: Optional[str] = Query(None)):
    """Browse the approver directory for ROLE/USER-type level configuration.
    Not used for DEPARTMENT_APPROVER - that's configured via the
    department-approvers endpoints below, a dedicated admin mapping
    rather than a directory filter (see approval.py's DepartmentApprover
    docstring for why)."""
    db = http_request.state.db

    try:
        return ApproverDirectoryDAO(db).list_active_directory(role_code=role_code)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# Department approvers (DEPARTMENT_APPROVER mapping, admin-owned - not a
# UMS role, see approval.py's DepartmentApprover docstring)
# =========================================================

@router.get(
    "/approval/department-approvers",
    response_model=List[DepartmentApproverDTO],
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def list_department_approvers(
    http_request: Request,
    department_id: int = Query(...),
    is_active: Optional[bool] = Query(None),
):
    db = http_request.state.db

    try:
        return DepartmentApproverService(db).list_for_department(department_id, is_active)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/approval/department-approvers",
    response_model=DepartmentApproverDTO,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def add_department_approver(payload: DepartmentApproverCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = http_request.state.user.get("user_id") or http_request.state.user.get("sub")
        return DepartmentApproverService(db).add(payload.department_id, payload.user_uuid, str(user_id))

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not add department approver")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/approval/department-approvers/{mapping_id}",
    response_model=DeleteApprovalPolicyResponse,
    dependencies=[
        Depends(permission_based_access(["APPROVAL_POLICY_MANAGE"]))
    ],
)
def remove_department_approver(mapping_id: int, http_request: Request):
    db = http_request.state.db

    try:
        DepartmentApproverService(db).remove(mapping_id)
        return DeleteApprovalPolicyResponse(id=mapping_id, message="Department approver removed successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), "Department approver mapping not found"), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
