# from Backend.API_Layer.interface.intake_process_interface.py
"""Typed data contracts shared across the invoice processing pipeline.

Every stage of the pipeline (classification, OCR, quality assessment,
field extraction, validation, vendor matching, confidence scoring)
consumes and/or produces one of the models defined here. Keeping them
in one module means every utility and the orchestrating service agree
on the same shapes without importing each other.
"""
from __future__ import annotations

import datetime
import decimal
import enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =====================================================
# Technical Classification
# =====================================================


class TechnicalDocumentType(str, enum.Enum):
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
    invoice_date: Optional[datetime.date] = None
    due_date: Optional[datetime.date] = None
    gstin: Optional[str] = None
    buyer_gstin: Optional[str] = None
    vendor_name: Optional[str] = None
    po_number: Optional[str] = None
    subtotal: Optional[decimal.Decimal] = None
    cgst: Optional[decimal.Decimal] = None
    sgst: Optional[decimal.Decimal] = None
    igst: Optional[decimal.Decimal] = None
    cess: Optional[decimal.Decimal] = None
    tax_type: Optional[str] = None
    tax_rate: Optional[decimal.Decimal] = None
    tax_amount: Optional[decimal.Decimal] = None
    total: Optional[decimal.Decimal] = None
    payment_terms: Optional[str] = None
    currency: Optional[str] = None
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


class FinalResponse(BaseModel):
    """Response returned by the production /process-invoice endpoint."""

    status: str = "success"
    document: DocumentResult
    extracted_invoice: ExtractedInvoice
    validation: ValidationResult
    vendor_match: VendorMatch
    confidence: ConfidenceResult

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
