# Backend/Business_Layer/utils/exceptions.py
"""Custom exceptions for the invoice processing pipeline.

Routes translate these into HTTP status codes; utilities and the
service layer should raise these instead of bare Exception/ValueError
so callers can distinguish failure modes.
"""


class InvoiceProcessingError(Exception):
    """Base class for all invoice processing errors."""


class UnsupportedFileType(InvoiceProcessingError):
    """Raised when the uploaded file's type cannot be handled by the pipeline."""


class OCRFailure(InvoiceProcessingError):
    """Raised when text/word extraction (native or OCR) fails outright."""


class FieldExtractionError(InvoiceProcessingError):
    """Raised when field extraction cannot proceed (e.g. no pages/text available)."""


class ValidationFailure(InvoiceProcessingError):
    """Raised when business validation cannot be performed (not for validation failures,

    which are reported via ValidationResult, but for structural problems such as a
    missing/invalid ExtractedInvoice).
    """


class VendorNotFound(InvoiceProcessingError):
    """Raised when vendor matching cannot find any candidate vendor."""


class InvalidUploadFile(InvoiceProcessingError):
    """Raised when an uploaded file fails basic validation (empty, oversized, no filename)."""


class DuplicateInvoiceError(InvoiceProcessingError):
    """Raised when a matched vendor already has an invoice with the same invoice_number."""
