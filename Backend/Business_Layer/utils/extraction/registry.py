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

import decimal
from typing import Dict, Tuple, Type

from Backend.API_Layer.interface.invoice_process_interface import (
    DocumentResult,
    ExtractedInvoice,
    FieldExtractionMeta,
)
from Backend.Business_Layer.utils.exceptions import FieldExtractionError
from Backend.Business_Layer.utils.extraction import scoring
from Backend.Business_Layer.utils.extraction.amounts import (
    CessExtractor,
    CGSTExtractor,
    GrandTotalExtractor,
    IGSTExtractor,
    SGSTExtractor,
    SubtotalExtractor,
    TaxAmountExtractor,
    TaxRateExtractor,
    TaxTypeExtractor,
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
    TaxTypeExtractor,
    TaxRateExtractor,
    TaxAmountExtractor,
    GrandTotalExtractor,
    PaymentTermsExtractor,
    CurrencyExtractor,
)

# Every extractor's field_name maps 1:1 onto a flat ExtractedInvoice
# attribute of the same name — this dict exists only to make that
# mapping explicit and easy to extend.
_MODEL_ATTRS = {cls.field_name for cls in EXTRACTOR_CLASSES}

_RECONCILE_TOLERANCE = decimal.Decimal("1.00")


def _reconcile_total(document: DocumentResult, metadata: Dict[str, FieldExtractionMeta]) -> None:
    """Prefer a `total` candidate that reconciles with subtotal + taxes.

    Every extractor runs independently and in isolation (see the
    module docstring), so the `total` field is picked purely on its
    own anchor/geometry score, with no visibility into subtotal/tax
    values. That's normally fine, but it means a strong-looking but
    wrong candidate (e.g. a mislabelled subtotal line) can beat the
    real grand total even though the *other* independently-extracted
    fields already prove it's wrong.

    This step never invents a value: it only swaps in an alternate
    that ``GrandTotalExtractor`` already found and ranked, and only
    when that alternate arithmetically reconciles and the current pick
    does not. If nothing reconciles, the original best-ranked
    candidate is kept unchanged — ``validators.py`` will surface the
    mismatch as before.
    """
    total_meta = metadata.get("total")
    subtotal_meta = metadata.get("subtotal")
    if total_meta is None or total_meta.value is None or subtotal_meta is None or subtotal_meta.value is None:
        return

    def _amount(name: str) -> decimal.Decimal:
        meta = metadata.get(name)
        return meta.value if meta is not None and meta.value is not None else decimal.Decimal("0")

    expected = (
        subtotal_meta.value
        + _amount("cgst")
        + _amount("sgst")
        + _amount("igst")
        + _amount("cess")
        + _amount("tax_amount")
    )

    def _reconciles(value: decimal.Decimal) -> bool:
        return abs(expected - value) <= _RECONCILE_TOLERANCE

    if _reconciles(total_meta.value):
        return

    for candidate in GrandTotalExtractor().extract_candidates(document):
        if candidate.value == total_meta.value or not _reconciles(candidate.value):
            continue
        metadata["total"] = FieldExtractionMeta(
            value=candidate.value,
            confidence=scoring.confidence_from_score(candidate.score),
            matched_anchor=candidate.anchor_text,
            page=candidate.page_number,
            method="+".join(candidate.method_tags + ["ARITHMETIC_RECONCILED"]),
        )
        return


def extract_invoice_fields(document: DocumentResult) -> ExtractedInvoice:
    """Run every registered extractor over a DocumentResult and assemble an ExtractedInvoice."""
    if not document.pages:
        raise FieldExtractionError("Document has no pages to extract fields from")

    metadata: Dict[str, FieldExtractionMeta] = {
        extractor_cls.field_name: extractor_cls().extract(document)
        for extractor_cls in EXTRACTOR_CLASSES
    }
    _reconcile_total(document, metadata)

    values = {name: meta.value for name, meta in metadata.items() if name in _MODEL_ATTRS}
    confidences = {name: meta.confidence for name, meta in metadata.items()}

    return ExtractedInvoice(field_confidences=confidences, field_metadata=metadata, **values)
