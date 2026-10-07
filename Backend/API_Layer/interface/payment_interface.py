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


class InvoiceReadyForPaymentResponse(BaseModel):
    invoice_id: int
    status_code: str
    message: str


# =========================================================
# Payment Management screens (see PaymentTrackingService)
# =========================================================

class RecordPaymentRequest(BaseModel):
    """Record a payment Finance has ALREADY made to the vendor outside this
    system. The invoice status (PARTIALLY_PAID / PAID) is set by the backend."""
    payment_date: datetime.date
    amount: decimal.Decimal
    payment_mode: str                 # one of GET /payment/metadata payment_modes[].value
    reference_number: str             # UTR / transaction / cheque number
    remarks: Optional[str] = None


class PaymentDocumentDTO(BaseModel):
    id: int
    payment_id: int
    document_type: str
    file_name: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[str] = None
    uploaded_at: datetime.datetime


class PaymentRecordDTO(BaseModel):
    payment_id: int
    payment_date: Optional[datetime.date] = None
    scheduled_date: datetime.date
    amount: decimal.Decimal           # amount of THIS payment applied to the invoice
    payment_total: decimal.Decimal    # whole payment (may cover other invoices)
    payment_mode: str
    reference_number: Optional[str] = None
    remarks: Optional[str] = None
    status_code: Optional[str] = None  # SCHEDULED / SENT / CLEARED / FAILED
    status_name: Optional[str] = None
    recorded_by: Optional[str] = None
    recorded_at: datetime.datetime
    documents: List[PaymentDocumentDTO] = []


class InvoicePaymentSummaryDTO(BaseModel):
    invoice_id: int
    invoice_number: str
    vendor_id: int
    vendor_name: str
    invoice_date: datetime.date
    due_date: datetime.date
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    gross_amount: decimal.Decimal
    discount_amount: decimal.Decimal
    tax_amount: decimal.Decimal
    invoice_amount: decimal.Decimal    # invoice.net_amount - what the vendor billed
    tds_applicable: bool
    tds_amount: decimal.Decimal
    tds_determination_status: Optional[str] = None
    net_payable: decimal.Decimal       # invoice_amount - tds_amount
    amount_paid: decimal.Decimal
    pending_amount: decimal.Decimal    # reserved by SCHEDULED/SENT payments
    remaining_amount: decimal.Decimal
    status_code: Optional[str] = None
    status_name: Optional[str] = None
    is_overdue: bool
    payment_count: int
    last_payment_date: Optional[datetime.date] = None
    last_payment_mode: Optional[str] = None
    last_payment_reference: Optional[str] = None
    receipt_count: int


class InvoicePaymentPageDTO(BaseModel):
    items: List[InvoicePaymentSummaryDTO]
    total: int
    page: int
    page_size: int


class InvoicePaymentDetailDTO(InvoicePaymentSummaryDTO):
    tds_tracking_status: Optional[str] = None
    can_record_payment: bool
    payments: List[PaymentRecordDTO] = []
    recorded_payment_id: Optional[int] = None  # set only in the record-payment response


class PaymentOptionDTO(BaseModel):
    value: str
    label: str
    reference_label: Optional[str] = None
    reference_pattern: Optional[str] = None  # payment modes: full-match regex for reference_number (null = free text)
    reference_hint: Optional[str] = None     # payment modes: human-readable form of reference_pattern


class PaymentMetadataDTO(BaseModel):
    payment_modes: List[PaymentOptionDTO]
    document_types: List[PaymentOptionDTO]
    reference_required: bool
    receipt_required: bool
    allowed_file_extensions: List[str]
    max_file_size_bytes: int
    ready_for_payment_statuses: List[str]
