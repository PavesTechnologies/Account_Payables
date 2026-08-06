# Backend/Business_Layer/utils/extraction/registry.py
"""Extractor registry and orchestration entry point.

This is the single place that knows about every concrete extractor
class. Adding a new field means adding one extractor class and one
line here — nothing else in the engine changes.
Backend.Business_Layer.utils.field_extractors re-exports
``extract_invoice_fields`` from this module so the service layer's
integration point (`field_extractors.extract_invoice_fields`) never
changes shape.
"""
from __future__ import annotations

from typing import Dict, Tuple, Type

from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoice,
    FieldExtractionMeta,
)
from Backend.Business_Layer.utils.exceptions import FieldExtractionError
from Backend.Business_Layer.utils.extraction.amounts import (
    CessExtractor,
    CGSTExtractor,
    GrandTotalExtractor,
    IGSTExtractor,
    SGSTExtractor,
    SubtotalExtractor,
)
from Backend.Business_Layer.utils.extraction.base import BaseFieldExtractor
from Backend.Business_Layer.utils.extraction.currency import CurrencyExtractor
from Backend.Business_Layer.utils.extraction.dates import DueDateExtractor, InvoiceDateExtractor
from Backend.Business_Layer.utils.extraction.gstin import BuyerGSTINExtractor, VendorGSTINExtractor
from Backend.Business_Layer.utils.extraction.identifiers import InvoiceNumberExtractor, PONumberExtractor
from Backend.Business_Layer.utils.extraction.payment_terms import PaymentTermsExtractor
from Backend.Business_Layer.utils.extraction.vendor import VendorNameExtractor

# Every extractor the pipeline runs, in no particular order — each is
# fully independent, so run order never affects the result.
EXTRACTOR_CLASSES: Tuple[Type[BaseFieldExtractor], ...] = (
    InvoiceNumberExtractor,
    PONumberExtractor,
    InvoiceDateExtractor,
    DueDateExtractor,
    VendorGSTINExtractor,
    BuyerGSTINExtractor,
    VendorNameExtractor,
    SubtotalExtractor,
    CGSTExtractor,
    SGSTExtractor,
    IGSTExtractor,
    CessExtractor,
    GrandTotalExtractor,
    PaymentTermsExtractor,
    CurrencyExtractor,
)

# Every extractor's field_name maps 1:1 onto a flat ExtractedInvoice
# attribute of the same name — this dict exists only to make that
# mapping explicit and easy to extend.
_MODEL_ATTRS = {cls.field_name for cls in EXTRACTOR_CLASSES}


def extract_invoice_fields(document: DocumentResult) -> ExtractedInvoice:
    """Run every registered extractor over a DocumentResult and assemble an ExtractedInvoice."""
    if not document.pages:
        raise FieldExtractionError("Document has no pages to extract fields from")

    metadata: Dict[str, FieldExtractionMeta] = {
        extractor_cls.field_name: extractor_cls().extract(document)
        for extractor_cls in EXTRACTOR_CLASSES
    }

    values = {name: meta.value for name, meta in metadata.items() if name in _MODEL_ATTRS}
    confidences = {name: meta.confidence for name, meta in metadata.items()}

    return ExtractedInvoice(field_confidences=confidences, field_metadata=metadata, **values)
