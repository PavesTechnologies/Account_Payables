# Backend/Business_Layer/utils/field_extractors.py
"""Public entry point for rule-based invoice field extraction — no AI/ML.

The actual engine lives in Backend.Business_Layer.utils.extraction
(one module per concern: geometry, anchors, normalizers, scoring, and
one extractor module per field group). This module only re-exports
the stable integration surface so
Backend.Business_Layer.services.invoice_process_service and anything
else that imports ``field_extractors`` keeps working unchanged:

    field_extractors.extract_invoice_fields(document) -> ExtractedInvoice

Every extractor class is also re-exported here for discoverability and
backward-compatible imports (e.g. ``field_extractors.VendorNameExtractor``).
"""
from __future__ import annotations

from Backend.Business_Layer.utils.extraction.amounts import (
    CessExtractor,
    CGSTExtractor,
    GrandTotalExtractor,
    IGSTExtractor,
    SGSTExtractor,
    SubtotalExtractor,
)
from Backend.Business_Layer.utils.extraction.base import BaseFieldExtractor, Candidate
from Backend.Business_Layer.utils.extraction.currency import CurrencyExtractor
from Backend.Business_Layer.utils.extraction.dates import DueDateExtractor, InvoiceDateExtractor
from Backend.Business_Layer.utils.extraction.gstin import BuyerGSTINExtractor, VendorGSTINExtractor
from Backend.Business_Layer.utils.extraction.identifiers import InvoiceNumberExtractor, PONumberExtractor
from Backend.Business_Layer.utils.extraction.payment_terms import PaymentTermsExtractor
from Backend.Business_Layer.utils.extraction.registry import EXTRACTOR_CLASSES, extract_invoice_fields
from Backend.Business_Layer.utils.extraction.vendor import VendorNameExtractor

# Backward-compatible alias: the old GSTINExtractor produced the
# "gstin" field, which is now VendorGSTINExtractor.
GSTINExtractor = VendorGSTINExtractor

__all__ = [
    "extract_invoice_fields",
    "EXTRACTOR_CLASSES",
    "BaseFieldExtractor",
    "Candidate",
    "InvoiceNumberExtractor",
    "PONumberExtractor",
    "InvoiceDateExtractor",
    "DueDateExtractor",
    "VendorGSTINExtractor",
    "BuyerGSTINExtractor",
    "GSTINExtractor",
    "VendorNameExtractor",
    "SubtotalExtractor",
    "CGSTExtractor",
    "SGSTExtractor",
    "IGSTExtractor",
    "CessExtractor",
    "GrandTotalExtractor",
    "PaymentTermsExtractor",
    "CurrencyExtractor",
]
