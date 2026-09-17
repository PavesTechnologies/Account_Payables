# Backend/API_Layer/interface/approval_interface.py
import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InvoiceApprovalDecisionRequest(BaseModel):
    comments: Optional[str] = None


class InvoiceRejectionRequest(BaseModel):
    comments: str


class InvoiceSendBackRequest(BaseModel):
    """Distinct from InvoiceRejectionRequest even though the shape is identical today (spec
    section 10: Send Back and Reject are different actions and must remain separately
    modelable) — comments here is the required return reason, not a rejection reason."""

    comments: str


class InvoiceApprovalStepApproverDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_uuid: UUID
    status: str
    decided_at: Optional[datetime.datetime] = None
    comments: Optional[str] = None


class InvoiceApprovalStepDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level_number: int
    approver_type: str
    role_code: Optional[str] = None
    approval_rule: str
    status: str
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    approvers: List[InvoiceApprovalStepApproverDTO] = []


class InvoiceApprovalDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_approval_id: int
    invoice_id: int
    approval_policy_id: int
    status: str
    created_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None
    steps: List[InvoiceApprovalStepDTO] = []


class StatusResponse(BaseModel):
    status_id: int
    status_name: str
