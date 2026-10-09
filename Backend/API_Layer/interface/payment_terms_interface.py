# Backend/API_Layer/interface/payment_terms_interface.py
"""DTOs for payment-term compliance and vendor agreements."""
import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InvoicePaymentTermDTO(BaseModel):
    invoice_id: int
    evaluated: bool
    invoice_status: Optional[str] = None
    due_date: Optional[datetime.date] = None
    validation_status: Optional[str] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    reference_source: Optional[str] = None
    invoice_terms_text: Optional[str] = None
    invoice_term_days: Optional[int] = None
    invoice_due_date_printed: Optional[datetime.date] = None
    po_terms_text: Optional[str] = None
    po_term_days: Optional[int] = None
    vendor_master_term_id: Optional[int] = None
    vendor_master_term_days: Optional[int] = None
    agreement_id: Optional[int] = None
    agreement_term_days: Optional[int] = None
    applied_term_days: Optional[int] = None
    suggested_term_days: Optional[int] = None
    due_basis: Optional[str] = None
    basis_date: Optional[datetime.date] = None
    contractual_due_date: Optional[datetime.date] = None
    statutory_due_date: Optional[datetime.date] = None
    statutory_rule: Optional[str] = None
    effective_due_date: Optional[datetime.date] = None
    due_date_verified: Optional[bool] = None
    days_to_due: Optional[int] = None
    is_overdue: bool = False
    is_exception: bool = False
    blocks_ready_for_payment: bool = False
    msme_statutory: bool = False
    checked_at: Optional[datetime.datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None
    verification_remarks: Optional[str] = None


class PaymentTermVerifyRequest(BaseModel):
    applied_term_days: Optional[int] = Field(None, ge=0, le=365)
    due_basis: Optional[str] = None
    remarks: str = Field(..., min_length=5, max_length=2000)


class PaymentTermExceptionDTO(InvoicePaymentTermDTO):
    invoice_number: str
    invoice_date: datetime.date
    invoice_type: Optional[str] = None
    vendor_id: int
    vendor_name: Optional[str] = None
    net_amount: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None


class PaymentTermExceptionPageDTO(BaseModel):
    items: List[PaymentTermExceptionDTO]
    total: int
    page: int
    page_size: int


class PaymentTermMetadataDTO(BaseModel):
    validation_statuses: List[str]
    exception_statuses: List[str]
    reference_sources: List[str]
    due_bases: List[str]
    reasons: Dict[str, str]
    agreement_types: List[str]
    agreement_statuses: List[str]
    msme_categories: List[str]


# ---------------------------------------------------------------------------
# Vendor agreements
# ---------------------------------------------------------------------------

class VendorAgreementDocumentDTO(BaseModel):
    document_id: int
    file_name: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[str] = None
    uploaded_at: Optional[datetime.datetime] = None


class VendorAgreementDTO(BaseModel):
    agreement_id: int
    vendor_id: int
    vendor_name: Optional[str] = None
    agreement_type: str
    reference_no: Optional[str] = None
    title: str
    valid_from: datetime.date
    valid_to: Optional[datetime.date] = None
    auto_renew: bool = False
    payment_term_id: Optional[int] = None
    payment_terms_text: Optional[str] = None
    term_days: Optional[int] = None
    due_basis: str
    status: str
    is_expired: bool
    is_effective: bool
    days_to_expiry: Optional[int] = None
    extraction_confidence: Optional[Decimal] = None
    remarks: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_at: Optional[datetime.datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None
    verification_remarks: Optional[str] = None
    documents: List[VendorAgreementDocumentDTO] = Field(default_factory=list)
    rechecked_invoice_count: Optional[int] = None


class VendorAgreementUpdateRequest(BaseModel):
    agreement_type: Optional[str] = None
    reference_no: Optional[str] = None
    title: Optional[str] = None
    valid_from: Optional[datetime.date] = None
    valid_to: Optional[datetime.date] = None
    auto_renew: Optional[bool] = None
    payment_term_id: Optional[int] = None
    payment_terms_text: Optional[str] = None
    term_days: Optional[int] = Field(None, ge=0, le=365)
    due_basis: Optional[str] = None
    remarks: Optional[str] = None
    submit_for_verification: bool = False


class VendorAgreementDecisionRequest(BaseModel):
    remarks: Optional[str] = Field(None, max_length=2000)


class VendorAgreementExtractionDTO(BaseModel):
    title: Optional[str] = None
    reference_no: Optional[str] = None
    agreement_type: str = "OTHER"
    valid_from: Optional[datetime.date] = None
    valid_to: Optional[datetime.date] = None
    payment_terms_text: Optional[str] = None
    term_days: Optional[int] = None
    due_basis: Optional[str] = None
    terms_kind: Optional[str] = None
    auto_renew: Optional[bool] = None
    vendor_name: Optional[str] = None
    vendor_gstin: Optional[str] = None
    confidence: Dict[str, Any] = Field(default_factory=dict)
    overall_confidence: float = 0.0
    warnings: List[str] = Field(default_factory=list)
