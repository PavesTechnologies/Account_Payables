# Backend/API_Layer/interface/invoice_extraction_interface.py

from datetime import date
from typing import Any, Dict, List, Optional
from decimal import Decimal
import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Generic field metadata
# ============================================================

class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Optional[Any] = None

    confidence: Optional[float] = None

    source: Optional[str] = None


# ============================================================
# Document
# ============================================================

class InvoiceDocument(BaseModel):
    document_type: str = "invoice"

    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None

    invoice_type: Optional[str] = None

    currency: Optional[str] = "INR"

    original_filename: Optional[str] = None


# ============================================================
# Vendor
# ============================================================

class InvoiceVendor(BaseModel):

    name: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None

    gstin: Optional[str] = None
    pan: Optional[str] = None

    address: Optional[str] = None

    state: Optional[str] = None
    state_code: Optional[str] = None

    country: Optional[str] = None

    email: Optional[str] = None
    phone: Optional[str] = None

    website: Optional[str] = None


# ============================================================
# Buyer
# ============================================================

class InvoiceBuyer(BaseModel):

    name: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None

    gstin: Optional[str] = None
    pan: Optional[str] = None

    address: Optional[str] = None
    shipping_address: Optional[str] = None

    state: Optional[str] = None
    state_code: Optional[str] = None

    country: Optional[str] = None

    email: Optional[str] = None
    phone: Optional[str] = None


# ============================================================
# Reference information
# ============================================================

class InvoiceReference(BaseModel):

    po_number: Optional[str] = None
    po_date: Optional[date] = None

    delivery_note_number: Optional[str] = None
    delivery_note_date: Optional[date] = None

    quotation_number: Optional[str] = None
    quotation_date: Optional[date] = None

    reference_number: Optional[str] = None

    contract_number: Optional[str] = None

    order_number: Optional[str] = None


# ============================================================
# Amounts
# ============================================================

class InvoiceAmounts(BaseModel):

    subtotal: Optional[float] = None

    taxable_amount: Optional[float] = None

    discount: Optional[float] = None

    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_amount: Optional[float] = None
    ugst_amount: Optional[float] = None
    cess_amount: Optional[float] = None

    total_tax: Optional[float] = None

    tds_amount: Optional[float] = None

    other_charges: Optional[float] = None
    shipping_charges: Optional[float] = None
    freight_charges: Optional[float] = None
    handling_charges: Optional[float] = None

    round_off: Optional[float] = None

    grand_total: Optional[float] = None

    amount_paid: Optional[float] = None
    balance_due: Optional[float] = None


# ============================================================
# Line item
# ============================================================

class InvoiceLine(BaseModel):

    line_number: int

    description: Optional[str] = None

    product_code: Optional[str] = None

    hsn_sac: Optional[str] = None

    quantity: Optional[float] = None

    unit: Optional[str] = None

    unit_price: Optional[float] = None

    discount: Optional[float] = None

    taxable_amount: Optional[float] = None

    tax_rate: Optional[float] = None

    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    igst_rate: Optional[float] = None
    ugst_rate: Optional[float] = None
    cess_rate: Optional[float] = None

    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_amount: Optional[float] = None
    ugst_amount: Optional[float] = None
    cess_amount: Optional[float] = None

    total_tax: Optional[float] = None

    line_total: Optional[float] = None


# ============================================================
# Payment
# ============================================================

class InvoicePayment(BaseModel):

    payment_terms: Optional[str] = None

    bank_name: Optional[str] = None

    account_name: Optional[str] = None

    account_number: Optional[str] = None

    ifsc_code: Optional[str] = None

    branch: Optional[str] = None

    swift_code: Optional[str] = None

    upi_id: Optional[str] = None


# ============================================================
# Tax
# ============================================================

class InvoiceTax(BaseModel):

    place_of_supply: Optional[str] = None

    reverse_charge: Optional[bool] = None

    tax_type: Optional[str] = None

    # Invoice-level (header) HSN/SAC - populated when an invoice states
    # one classification for the whole document instead of per line
    # (e.g. SaaS/cloud billing invoices). Falls back to this when a
    # line has no hsn_sac of its own.
    hsn_sac: Optional[str] = None

    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    igst_rate: Optional[float] = None
    ugst_rate: Optional[float] = None
    cess_rate: Optional[float] = None


# ============================================================
# E-invoice / compliance
# ============================================================

class InvoiceCompliance(BaseModel):

    irn: Optional[str] = None

    acknowledgement_number: Optional[str] = None

    acknowledgement_date: Optional[date] = None

    einvoice_status: Optional[str] = None

    qr_code_data: Optional[str] = None

    reverse_charge: Optional[bool] = None

    export_invoice: Optional[bool] = None


# ============================================================
# Extraction metadata
# ============================================================

class ExtractionMetadata(BaseModel):

    status: str

    provider: str = "AWS_TEXTRACT"

    job_id: Optional[str] = None

    confidence: Optional[float] = None

    field_confidence: Dict[str, float] = Field(
        default_factory=dict
    )

    field_sources: Dict[str, str] = Field(
        default_factory=dict
    )

    field_details: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )

    warnings: List[str] = Field(
        default_factory=list
    )

    pages_processed: int = 0


# ============================================================
# Validation
# ============================================================

class InvoiceIssue(BaseModel):

    field: Optional[str] = None

    code: str

    message: str


class InvoiceValidation(BaseModel):

    status: str

    is_valid: bool = True

    issues: List[str] = Field(
        default_factory=list
    )

    warnings: List[str] = Field(
        default_factory=list
    )

    field_issues: List[InvoiceIssue] = Field(
        default_factory=list
    )

    total_difference: Optional[float] = None

    tax_difference: Optional[float] = None


# ============================================================
# Final response
# ============================================================

class ExtractedInvoiceResponse(BaseModel):

    document: InvoiceDocument

    vendor: InvoiceVendor

    buyer: InvoiceBuyer

    reference: InvoiceReference

    amounts: InvoiceAmounts

    payment: InvoicePayment

    tax: InvoiceTax

    compliance: InvoiceCompliance

    invoice_lines: List[InvoiceLine] = Field(
        default_factory=list
    )

    extraction: ExtractionMetadata

    validation: InvoiceValidation

    raw_fields: Dict[str, Any] = Field(
        default_factory=dict
    )
class ExtractedInvoiceResult(BaseModel):
    extracted_invoice: ExtractedInvoiceResponse
    file_path: str

    # Populated once /extract-fields has cached this extraction (see
    # extraction_cache.py). Optional so callers that build this model
    # directly (existing tests, back-compat callers) are unaffected.
    extraction_id: Optional[str] = None


# ============================================================
# Stage 1 - Vendor & Buyer validation: bounding boxes, field-level
# comparisons, and the correction/confirmation trail kept in the
# extraction cache (see Backend/API_Layer/utils/extraction_cache.py).
# ============================================================

class BoundingBox(BaseModel):
    page: int
    left: float
    top: float
    width: float
    height: float


class CorrectionEvent(BaseModel):
    field: str
    before: Optional[Any] = None
    after: Optional[Any] = None
    corrected_by: str
    corrected_at: str


class FieldComparisonStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MISSING_EXTRACTED = "MISSING_EXTRACTED"
    MISSING_MASTER = "MISSING_MASTER"
    NOT_COMPARED = "NOT_COMPARED"


class FieldComparison(BaseModel):
    field: str
    extracted_value: Optional[str] = None
    master_value: Optional[str] = None
    status: FieldComparisonStatus
    corrected_value: Optional[str] = None


class VendorCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None


class BuyerCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None


class TaxCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    place_of_supply: Optional[str] = None
    reverse_charge: Optional[bool] = None
    tax_type: Optional[str] = None
    hsn_sac: Optional[str] = None
    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    igst_rate: Optional[float] = None
    ugst_rate: Optional[float] = None
    cess_rate: Optional[float] = None


class AmountsCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subtotal: Optional[float] = None
    taxable_amount: Optional[float] = None
    discount: Optional[float] = None
    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_amount: Optional[float] = None
    ugst_amount: Optional[float] = None
    cess_amount: Optional[float] = None
    total_tax: Optional[float] = None
    grand_total: Optional[float] = None


class ConfirmSectionRequest(BaseModel):
    section: str  # "vendor" | "buyer" | "tax" | "amounts"


class CorrectionResponse(BaseModel):
    extraction_id: str
    section: str
    updated: Dict[str, Any]
    corrections: List[CorrectionEvent] = Field(default_factory=list)


class ExtractionCacheResponse(BaseModel):
    extraction_id: str
    extracted_invoice: ExtractedInvoiceResponse
    file_path: str
    corrections: List[CorrectionEvent] = Field(default_factory=list)
    vendor_confirmed: bool = False
    buyer_confirmed: bool = False
    tax_confirmed: bool = False
    amounts_confirmed: bool = False


# Validation Model
# class FieldIssue(BaseModel):
#     field: str
#     code: str
#     message: str
class ValidationSummary(BaseModel):
    validation_type: str
    source: str

class ValidationResult(BaseModel):
    is_valid: bool
    requires_manual_review: bool
    issues:list[str]
    success:list[ValidationSummary]


# ============================================================
# Validation job - async progress tracking (Redis-backed)
# ============================================================

class ValidationJobQueued(BaseModel):
    job_id: str
    status: str


class ValidationStageStatus(BaseModel):
    label: Optional[str] = None
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    issues: List[str] = Field(default_factory=list)
    field_comparisons: List[FieldComparison] = Field(default_factory=list)


class ValidationJobStatus(BaseModel):
    job_id: str
    status: str
    current_stage: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    stages: Dict[str, ValidationStageStatus] = Field(
        default_factory=dict
    )

    # Populated once status is COMPLETED/FAILED - same shape as the
    # synchronous ValidationResult this replaces waiting on directly.
    is_valid: Optional[bool] = None
    requires_manual_review: Optional[bool] = None
    issues: List[str] = Field(default_factory=list)
    success: List[ValidationSummary] = Field(default_factory=list)


# ============================================================
# Invoice - final validated data to be stored
# ============================================================

class InvoiceType(str, Enum):
    PO = "PO"
    NON_PO = "NON_PO"

class InvoiceRequest(BaseModel):
    invoice_number: str
    invoice_type: InvoiceType = InvoiceType.NON_PO

    invoice_date: date
    due_date: Optional[date] = None

    payment_terms: Optional[str] = None
    currency: str

    grand_amount: Decimal
    discount_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    net_amount: Decimal

    amount_paid: Decimal = Decimal("0")


# ============================================================
# Invoice Lines
# ============================================================

class InvoiceLineRequest(BaseModel):
    invoice_id: Optional[int] = None

    line_number: int
    description: Optional[str] = None

    hsn_sac: Optional[str] = None

    quantity: Optional[Decimal] = None
    unit: Optional[str] = None

    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None

    taxable_amount: Optional[Decimal] = None
    tax_amount: Decimal = Decimal("0")

    tax_type_id: Optional[int] = None


# ============================================================
# Inbound Document - extraction/audit information
# ============================================================

class InboundDocumentRequest(BaseModel):
    source_type: str
    file_name: str
    file_path: str

    extraction_status: str
    extraction_confidence: Optional[Decimal] = None

    # Store the original custom extraction response
    # before/after validation for audit purposes.
    raw_extracted_data: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Invoice Attachment
# ============================================================

class InvoiceAttachmentRequest(BaseModel):
    invoice_id: Optional[int] = None

    file_name: str
    file_path: str


# ============================================================
# Final request used by DB persistence layer
# ============================================================

class CustomInvoiceRequest(BaseModel):
    invoice: InvoiceRequest
    invoice_lines: list[InvoiceLineRequest]

    inbound_document: InboundDocumentRequest

    invoice_attachment: Optional[InvoiceAttachmentRequest] = None


# ============================================================
# Create-invoice response
# ============================================================

class InvoiceCreationResult(BaseModel):
    invoice_id: int
    invoice_number: str
    vendor_id: int
    inbound_document_id: int
    invoice_attachment_id: Optional[int] = None

    status_code: str

    line_count: int
    skipped_line_count: int

    warnings: List[str] = Field(default_factory=list)