# Backend/API_Layer/routes/email_intake_route.py
"""Email invoice intake switch (Phase 3b). Reading the status needs INVOICE_BULK_UPLOAD or
EMAIL_INTAKE_MANAGE; switching it on/off needs EMAIL_INTAKE_MANAGE. The mailbox itself is read
by Backend/scripts/run_email_intake.py, never by this API."""
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from Backend.API_Layer.middleware.permission_base_access import has_permissions, permission_based_access
from Backend.Business_Layer.services.email_intake_settings_service import EMAIL_INTAKE_MANAGE, EmailIntakeSettingsService

router = APIRouter()

_VIEW = [EMAIL_INTAKE_MANAGE, "INVOICE_BULK_UPLOAD"]
_MANAGE = [EMAIL_INTAKE_MANAGE]


class EmailIntakeStatus(BaseModel):
    enabled: bool
    updated_by: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None
    mailbox: Optional[str] = None
    sender_filter: List[str] = []
    start_date: Optional[str] = None
    interval_minutes: int
    last_run: Optional[dict] = None
    can_manage: bool


class EmailIntakeToggle(BaseModel):
    enabled: bool


def _user_id(request: Request) -> str:
    user = request.state.user or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


@router.get("/status", response_model=EmailIntakeStatus, dependencies=[Depends(permission_based_access(_VIEW))])
def get_status(request: Request):
    return EmailIntakeSettingsService(request.state.db).status(can_manage=has_permissions(request.state.user, _MANAGE))


@router.put("/status", response_model=EmailIntakeStatus, dependencies=[Depends(permission_based_access(_MANAGE))])
def set_status(body: EmailIntakeToggle, request: Request):
    service = EmailIntakeSettingsService(request.state.db)
    user = request.state.user or {}
    service.set_enabled(body.enabled, _user_id(request), user.get("name") or user.get("email"))
    return service.status(can_manage=True)
