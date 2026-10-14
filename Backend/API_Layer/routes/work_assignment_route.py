# Backend/API_Layer/routes/work_assignment_route.py
"""Work assignment (mounted at /apm/work-assignment).

Team / rules (read): AP Executives and the AP lead. Claim: INVOICE_OCR_REVIEW / SEND_FOR_APPROVAL /
INVOICE_CREATE. Rules, reassign and workload: AP_WORK_ASSIGN or AP_AUTOMATION_MANAGE (the AP lead /
Finance Manager).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.work_assignment_service import (
    LEAD_PERMISSIONS,
    VIEW_PERMISSIONS,
    WORK_PERMISSIONS,
    WorkAssignmentService,
)

router = APIRouter()


class RuleBody(BaseModel):
    scope: str = Field(..., pattern="^(VENDOR|DEPARTMENT)$")
    target_id: int
    assignee_user_id: str


class ClaimBody(BaseModel):
    invoice_ids: List[int] = Field(..., min_length=1, max_length=100)


class ReassignBody(ClaimBody):
    to_user_id: str
    note: Optional[str] = Field(None, max_length=300)


class ReassignAllBody(BaseModel):
    from_user_id: str
    to_user_id: str
    note: Optional[str] = Field(None, max_length=300)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


def _call(fn, *args):
    try:
        return JSONResponse(jsonable_encoder(fn(*args)))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/team", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def team(request: Request):
    """The active AP Executives (UMS role AP_EXECUTIVE) - who work can be assigned to."""
    return _call(WorkAssignmentService(request.state.db).team)


@router.get("/rules", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def rules(request: Request):
    return _call(WorkAssignmentService(request.state.db).rules)


@router.put("/rules", dependencies=[Depends(permission_based_access(LEAD_PERMISSIONS))])
def set_rule(body: RuleBody, request: Request):
    """Vendor (or department) -> AP Executive. Replaces the target's existing rule."""
    return _call(lambda: {"rule_id": WorkAssignmentService(request.state.db).set_rule(
        body.scope, body.target_id, body.assignee_user_id, _user_id(request)).rule_id})


@router.delete("/rules/{rule_id}", dependencies=[Depends(permission_based_access(LEAD_PERMISSIONS))])
def remove_rule(rule_id: int, request: Request):
    return _call(lambda: WorkAssignmentService(request.state.db).remove_rule(rule_id, _user_id(request)) or {"removed": rule_id})


@router.get("/workload", dependencies=[Depends(permission_based_access(LEAD_PERMISSIONS))])
def workload(request: Request):
    """Open AP work per executive (to review / returned / reviewed / in approval), oldest item and the
    unassigned pool - for balancing the team and covering leave."""
    return _call(WorkAssignmentService(request.state.db).workload)


@router.post("/claim", dependencies=[Depends(permission_based_access(WORK_PERMISSIONS))])
def claim(body: ClaimBody, request: Request):
    return _call(WorkAssignmentService(request.state.db).claim, body.invoice_ids, _user_id(request))


@router.post("/reassign", dependencies=[Depends(permission_based_access(LEAD_PERMISSIONS))])
def reassign(body: ReassignBody, request: Request):
    return _call(WorkAssignmentService(request.state.db).reassign, body.invoice_ids, body.to_user_id, _user_id(request), body.note)


@router.post("/reassign-all", dependencies=[Depends(permission_based_access(LEAD_PERMISSIONS))])
def reassign_all(body: ReassignAllBody, request: Request):
    """Move everything a person holds that is still with AP (leave / role change)."""
    return _call(WorkAssignmentService(request.state.db).reassign_all, body.from_user_id, body.to_user_id,
                 _user_id(request), body.note)
