# from Backend.API_Layer.interface.intake_process_interface.py
"""Typed data contracts shared across the invoice processing pipeline.

Every stage of the pipeline (classification, OCR, quality assessment,
field extraction, validation, vendor matching, confidence scoring)
consumes and/or produces one of the models defined here. Keeping them
in one module means every utility and the orchestrating service agree
on the same shapes without importing each other.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =====================================================
# Technical Classification
# =====================================================


class TechnicalDocumentType(str, Enum):
    """Result of technical (non-business) document classification."""

    TEXT_PDF = "TEXT_PDF"
    SCANNED_PDF = "SCANNED_PDF"
    PNG = "PNG"
    JPEG = "JPEG"
    TIFF = "TIFF"
    UNKNOWN = "UNKNOWN"


# =====================================================
# Text Extraction (PDF text layer / OCR)
# =====================================================


class Word(BaseModel):
    """A single recognized word/token with its position and confidence."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: Optional[float] = None


class Page(BaseModel):
    """One page of a document after text extraction."""

    page_number: int
    width: float
    height: float
    text: str = ""
    words: List[Word] = Field(default_factory=list)
    is_scanned: bool = False
    ocr_confidence: Optional[float] = None


class DocumentResult(BaseModel):
    """Output of upload + technical classification + text extraction."""

    status: str = "success"
    source_filename: Optional[str] = None
    technical_document_type: TechnicalDocumentType = TechnicalDocumentType.UNKNOWN
    page_count: int = 0
    pages: List[Page] = Field(default_factory=list)


# =====================================================
# Document Quality
# =====================================================


class DocumentQuality(BaseModel):
    """Result of the quality assessment stage.

    ``score`` is a 0-100 composite of OCR confidence, word density and
    keyword presence. ``is_poor`` is the single boolean the orchestrator
    branches on to decide whether AWS Textract should be invoked.
    """

    score: float
    is_poor: bool
    reasons: List[str] = Field(default_factory=list)

    @property
    def poor(self) -> bool:
        return self.is_poor

    @property
    def good(self) -> bool:
        return not self.is_poor


# =====================================================
# Field Extraction
# =====================================================


class FieldExtractionMeta(BaseModel):
    """Provenance for one extracted field: what was found, and why it was trusted.

    Produced by the rule-based extraction engine in
    Backend.Business_Layer.utils.extraction — every extractor's winning
    candidate becomes one of these. ``method`` is a "+"-joined set of
    tags (e.g. "ANCHOR+SAME_LINE+GEOMETRY") describing how the value
    was located, for debugging and UI provenance display.
    """

    value: Optional[Any] = None
    confidence: float = 0.0
    matched_anchor: Optional[str] = None
    page: Optional[int] = None
    method: str = "NONE"


class ExtractedInvoiceLine(BaseModel):
    """One line item extracted from an invoice's item table.

    Produced by the geometry-based line-item extractor in
    Backend.Business_Layer.utils.extraction.line_items — every field is
    optional because a row may not expose every column (e.g. no
    quantity/unit price column). ``confidence`` reflects how many of
    description/quantity/unit_price/line_amount were actually found,
    never a fabricated estimate.
    """

    line_number: int
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    tax_type: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    confidence: float = 0.0


class ExtractedInvoice(BaseModel):
    """Business fields extracted from an invoice document.

    Each field is a plain value so this model can be used directly as
    a request body for the validation and vendor-matching endpoints.
    Per-field extraction confidence (0-100) is carried in
    ``field_confidences`` keyed by field name (kept for backward
    compatibility with Backend.Business_Layer.utils.confidence); full
    provenance (matched anchor, page, method) is in ``field_metadata``.
    """

    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    gstin: Optional[str] = None
    buyer_gstin: Optional[str] = None
    vendor_name: Optional[str] = None
    po_number: Optional[str] = None
    subtotal: Optional[Decimal] = None
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None
    cess: Optional[Decimal] = None
    tax_type: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total: Optional[Decimal] = None
    payment_terms: Optional[str] = None
    currency: Optional[str] = None
    lines: List[ExtractedInvoiceLine] = Field(default_factory=list)
    field_confidences: Dict[str, float] = Field(default_factory=dict)
    field_metadata: Dict[str, FieldExtractionMeta] = Field(default_factory=dict)


# =====================================================
# Business Validation
# =====================================================


class ValidationResult(BaseModel):
    """Result of business-rule validation over an ExtractedInvoice."""

    valid: bool
    errors: List[str] = Field(default_factory=list)


# =====================================================
# Vendor Matching
# =====================================================


class VendorMatch(BaseModel):
    """Result of matching an ExtractedInvoice against the vendor master."""

    matched: bool
    vendor_id: Optional[int] = None
    confidence: float = 0.0


# =====================================================
# Confidence Scoring
# =====================================================


class ConfidenceResult(BaseModel):
    """Composite confidence across every pipeline stage."""

    ocr_confidence: float
    extraction_confidence: float
    validation_confidence: float
    vendor_confidence: float
    overall_confidence: float


# =====================================================
# Final Orchestrated Response
# =====================================================

class InvoiceType(str, Enum):
    PO = "PO"
    NON_PO = "NON_PO"


class UploadInvoiceRequest(BaseModel):
    invoice_number: str
    vendor_id: int
    invoice_type: InvoiceType
    invoice_date: date
    due_date: date
    currency_id: int

    gross_amount: Decimal
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    net_amount: Decimal



class FinalResponse(BaseModel):
    """Response returned by the production /process-invoice endpoint."""

    status: str = "success"
    document: DocumentResult
    extracted_invoice: ExtractedInvoice
    validation: ValidationResult
    vendor_match: VendorMatch
    confidence: ConfidenceResult
    inbound_document_id: Optional[int] = None
    invoice_id: Optional[int] = None
    invoice_status: Optional[str] = None


# =====================================================
# Manual OCR Review
# =====================================================


class InvoiceLineReviewRequest(BaseModel):
    """AP Executive correction for one invoice line during OCR review.

    ``line_number`` identifies which extracted line this correction
    applies to; a ``line_number`` with no matching existing line is
    treated as a new line to add.
    """

    line_number: int
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    tax_type_id: Optional[int] = None


class InvoiceOCRReviewRequest(BaseModel):
    """AP Executive correction/confirmation of an OCR-extracted invoice.

    Submitted against PATCH /inbound-documents/{inbound_document_id}/ocr-review.
    ``vendor_id`` is required the first time this is submitted for a
    document whose vendor could not be auto-matched (Path B); optional
    thereafter, when merely confirming/correcting an already-matched invoice.
    """

    vendor_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_type: Optional[InvoiceType] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    currency_id: Optional[int] = None
    gross_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    po_id: Optional[int] = None
    payment_term_id: Optional[int] = None
    lines: Optional[List[InvoiceLineReviewRequest]] = None

class UploadDocumentResponse(BaseModel):
    status: str
    message: str
    source_filename: str
    technical_document_type: str
    page_count: int
    quality_score: float
    pages: list[UploadPageSummary]


class UploadPageSummary(BaseModel):
    page_number: int
    is_scanned: bool
    word_count: int
    ocr_confidence: float | None
