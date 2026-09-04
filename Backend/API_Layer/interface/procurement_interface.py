# Backend/API_Layer/interface/procurement_interface.py
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel, Field

# =====================================================
# Purchase Requisition Line
# =====================================================


class PurchaseRequisitionLineRequest(BaseModel):
    item_name: str
    description: Optional[str] = None
    quantity: decimal.Decimal
    uom: Optional[str] = None
    estimated_unit_price: Optional[decimal.Decimal] = None
    estimated_amount: Optional[decimal.Decimal] = None


class PurchaseRequisitionLineDTO(BaseModel):
    id: int
    pr_id: int
    item_name: str
    description: Optional[str]
    quantity: decimal.Decimal
    uom: Optional[str]
    estimated_unit_price: Optional[decimal.Decimal]
    estimated_amount: Optional[decimal.Decimal]


# =====================================================
# Quotation
# =====================================================


class QuotationDTO(BaseModel):
    id: int
    pr_id: int
    vendor_id: int
    file_url: str
    status_id: int
    quotation_number: Optional[str]
    quotation_date: Optional[datetime.date]
    valid_until: Optional[datetime.date]
    total_amount: Optional[decimal.Decimal]
    created_by: Optional[str]
    created_at: datetime.datetime
    rfq_id: Optional[int] = None
    delivery_days: Optional[int] = None
    payment_terms: Optional[str] = None


class QuotationResponse(BaseModel):
    id: int
    message: str


class DeleteQuotationResponse(BaseModel):
    message: str


# =====================================================
# Purchase Requisition
# =====================================================


class PurchaseRequisitionCreateRequest(BaseModel):
    department_id: int
    purchase_category_id: int
    priority: str = Field(default="NORMAL")
    required_by: Optional[datetime.date] = None
    delivery_location: Optional[str] = None
    justification: Optional[str] = None
    lines: List[PurchaseRequisitionLineRequest] = Field(default_factory=list)


class PurchaseRequisitionUpdateRequest(BaseModel):
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    priority: Optional[str] = None
    required_by: Optional[datetime.date] = None
    delivery_location: Optional[str] = None
    justification: Optional[str] = None


class PurchaseRequisitionResponse(BaseModel):
    id: int
    message: str


class DeletePurchaseRequisitionResponse(BaseModel):
    message: str


class PurchaseRequisitionDTO(BaseModel):
    id: int
    pr_number: str
    department_id: int
    purchase_category_id: int
    status_id: int
    priority: str
    estimated_total: decimal.Decimal
    created_by: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    required_by: Optional[datetime.date]
    delivery_location: Optional[str]
    justification: Optional[str]
    selected_vendor_id: Optional[int]
    selected_quotation_id: Optional[int]
    approved_by: Optional[str]
    approved_at: Optional[datetime.datetime]
    approval_comment: Optional[str]
    sourcing_type: Optional[str] = None
    selection_reason: Optional[str] = None
    # Field names match the PurchaseRequisition ORM relationship attributes
    # (purchase_requisition_line/quotation) so FastAPI can populate them
    # directly from the model instance.
    purchase_requisition_line: List[PurchaseRequisitionLineDTO] = Field(default_factory=list)
    quotation: List[QuotationDTO] = Field(default_factory=list)


# =====================================================
# PR Approval
# =====================================================


class ApprovePurchaseRequisitionRequest(BaseModel):
    comment: Optional[str] = None


class RejectPurchaseRequisitionRequest(BaseModel):
    comment: str


class ReturnPurchaseRequisitionRequest(BaseModel):
    reason: str


# =====================================================
# RFQ or Catalog decision
# =====================================================


class SourcingDecisionRequest(BaseModel):
    sourcing_type: str


# =====================================================
# Vendor Selection
# =====================================================


class SelectVendorRequest(BaseModel):
    quotation_id: int
    reason: Optional[str] = None


# =====================================================
# Purchase Order Generation
# =====================================================


class GeneratePurchaseOrderResponse(BaseModel):
    po_id: int
    pr_id: int
    message: str
