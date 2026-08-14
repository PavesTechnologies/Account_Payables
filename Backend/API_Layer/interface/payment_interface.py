# Backend/API_Layer/interface/payment_interface.py
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PaymentAllocationRequest(BaseModel):
    invoice_id: int
    allocated_amount: decimal.Decimal


class PaymentCreateRequest(BaseModel):
    vendor_id: int
    scheduled_date: datetime.date
    currency_id: int
    payment_method: str
    vendor_bank_id: Optional[int] = None
    reference_number: Optional[str] = None
    allocations: List[PaymentAllocationRequest] = Field(min_length=1)


class PaymentStatusUpdateRequest(BaseModel):
    status_code: str  # SENT | CLEARED | FAILED (ap.status_master, module=PAYMENT)
    payment_date: Optional[datetime.date] = None
    reference_number: Optional[str] = None


class PaymentInvoiceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_invoice_id: int
    payment_id: int
    invoice_id: int
    allocated_amount: decimal.Decimal
    created_at: datetime.datetime


class PaymentDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: int
    vendor_id: int
    vendor_bank_id: Optional[int]
    scheduled_date: datetime.date
    payment_date: Optional[datetime.date]
    total_amount: decimal.Decimal
    currency_id: int
    payment_method: str
    reference_number: Optional[str]
    status_id: Optional[int]
    created_by: Optional[str]
    created_at: datetime.datetime
    updated_by: Optional[str]
    updated_at: datetime.datetime
    payment_invoice: List[PaymentInvoiceDTO] = []


class PaymentResponse(BaseModel):
    payment_id: int
    message: str
