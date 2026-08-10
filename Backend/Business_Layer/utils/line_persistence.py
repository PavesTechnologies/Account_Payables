# Backend/Business_Layer/utils/line_persistence.py
"""Bridges the optional-everything ExtractedInvoiceLine to the NOT-NULL InvoiceLine ORM model.

Persistence has stricter requirements than extraction: invoice_line.description
and .unit_price are NOT NULL, .quantity defaults to 1, .line_amount is NOT
NULL. A line that can't meet that bar is skipped (never fabricated) rather
than written with a made-up value.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from Backend.API_Layer.interface.invoice_process_interface import (
    ExtractedInvoice,
    ExtractedInvoiceLine,
)
from Backend.Business_Layer.utils.invoice_status import LINE_TOTAL_MISMATCH_TOLERANCE
from Backend.Data_Access_Layer.models.invoice import InvoiceLine

_DEFAULT_QUANTITY = Decimal("1")
_UNIT_PRICE_QUANT = Decimal("0.0001")
_AMOUNT_QUANT = Decimal("0.01")


def build_invoice_line_models(lines: List[ExtractedInvoiceLine]) -> Tuple[List[InvoiceLine], int]:
    """Return (persistable InvoiceLine rows, count of lines skipped as incomplete)."""
    models: List[InvoiceLine] = []
    skipped = 0

    for extracted in lines:
        if not extracted.description or (extracted.line_amount is None and extracted.unit_price is None):
            skipped += 1
            continue

        quantity = extracted.quantity if extracted.quantity is not None else _DEFAULT_QUANTITY
        if quantity == 0:
            quantity = _DEFAULT_QUANTITY

        unit_price = extracted.unit_price
        line_amount = extracted.line_amount

        if unit_price is None:
            unit_price = (line_amount / quantity).quantize(_UNIT_PRICE_QUANT, rounding=ROUND_HALF_UP)
        if line_amount is None:
            line_amount = (unit_price * quantity).quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)

        models.append(
            InvoiceLine(
                line_number=extracted.line_number,
                description=extracted.description[:255],
                quantity=quantity,
                unit_price=unit_price,
                line_amount=line_amount,
                tax_amount=extracted.tax_amount if extracted.tax_amount is not None else Decimal("0"),
            )
        )

    return models, skipped


def sum_line_amounts(lines: List[ExtractedInvoiceLine]) -> Decimal:
    return sum((line.line_amount for line in lines if line.line_amount is not None), Decimal("0"))


def check_line_total_mismatch(
    lines: List[ExtractedInvoiceLine], extracted: ExtractedInvoice
) -> Optional[str]:
    """Cross-validate Σline_amount against the extracted subtotal, if both are known.

    Never a hard failure — the caller attaches the returned description to
    an InvoiceIssue and leaves the invoice in OCR_REVIEW_PENDING regardless.
    """
    if not lines or extracted.subtotal is None:
        return None

    total_lines = sum_line_amounts(lines)
    if total_lines == 0:
        return None

    difference = abs(total_lines - extracted.subtotal)
    if difference <= LINE_TOTAL_MISMATCH_TOLERANCE:
        return None

    return (
        f"Sum of line amounts ({total_lines}) does not reconcile with the "
        f"extracted subtotal ({extracted.subtotal}); difference {difference} "
        f"exceeds tolerance {LINE_TOTAL_MISMATCH_TOLERANCE}"
    )
