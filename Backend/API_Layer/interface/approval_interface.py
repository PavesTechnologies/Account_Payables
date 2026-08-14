# Backend/API_Layer/interface/approval_interface.py
import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InvoiceApprovalDecisionRequest(BaseModel):
    comments: Optional[str] = None


class InvoiceRejectionRequest(BaseModel):
    comments: str


class InvoiceApprovalDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_approval_id: int
    invoice_id: int
    invoice_issue_id: Optional[int]
    approver_name: str
    decision: str
    comments: Optional[str]
    created_at: datetime.datetime
    decided_at: Optional[datetime.datetime]


class InvoiceApprovalActionResponse(BaseModel):
    invoice_id: int
    invoice_approval_id: Optional[int] = None
    status_code: str
    message: str
