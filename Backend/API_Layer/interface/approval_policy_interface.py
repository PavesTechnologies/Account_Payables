# Backend/API_Layer/interface/approval_policy_interface.py
import datetime
import decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApprovalPolicyLevelRequest(BaseModel):
    level_number: int
    approver_type: str
    approval_rule: str = "ANY_ONE"
    role_code: Optional[str] = None
    user_uuid: Optional[UUID] = None
    is_active: Optional[bool] = None


class ApprovalPolicyCreateRequest(BaseModel):
    """department_id/purchase_category_id are required UNLESS is_default
    is true - a default (catch-all fallback) policy has no scoping at
    all, and min_amount/max_amount must also be omitted for it."""

    name: str
    levels: List[ApprovalPolicyLevelRequest]
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    is_default: Optional[bool] = None
    description: Optional[str] = None
    min_amount: Optional[decimal.Decimal] = None
    max_amount: Optional[decimal.Decimal] = None
    is_active: Optional[bool] = None


class ApprovalPolicyUpdateRequest(BaseModel):
    name: Optional[str] = None
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    description: Optional[str] = None
    min_amount: Optional[decimal.Decimal] = None
    max_amount: Optional[decimal.Decimal] = None
    levels: Optional[List[ApprovalPolicyLevelRequest]] = None


class ApprovalPolicyStatusRequest(BaseModel):
    is_active: bool


class ApprovalPolicyLevelDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level_number: int
    approver_type: str
    approval_rule: str
    role_code: Optional[str] = None
    user_uuid: Optional[UUID] = None
    is_active: bool


class ApprovalPolicyDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_default: bool
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    description: Optional[str] = None
    min_amount: Optional[decimal.Decimal] = None
    max_amount: Optional[decimal.Decimal] = None
    levels: List[ApprovalPolicyLevelDTO] = []


class ApprovalPolicyResponse(BaseModel):
    id: int
    message: str


class DeleteApprovalPolicyResponse(BaseModel):
    id: int
    message: str


class ApproverLookupDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_uuid: UUID
    employee_uuid: UUID
    department_uuid: Optional[UUID] = None
    department_name: Optional[str] = None
    is_user_active: bool


class DepartmentApproverCreateRequest(BaseModel):
    department_id: int
    user_uuid: UUID


class DepartmentApproverDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    user_uuid: UUID
    is_active: bool
    created_at: datetime.datetime
    created_by: Optional[str] = None
