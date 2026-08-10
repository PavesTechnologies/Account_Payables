# Backend/Business_Layer/utils/validators.py
"""Business validation for extracted invoice fields.

Deliberately independent of extraction and vendor matching: it only
looks at the values already present on an ExtractedInvoice and reports
structured errors. It never re-reads document text and never queries
a vendor master.
"""
from __future__ import annotations

import datetime
import decimal
import re
from typing import List, Optional

from Backend.API_Layer.interface.invoice_process_interface import ExtractedInvoice, ValidationResult

_GSTIN_FORMAT = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9]Z[A-Z0-9]$")
TOTAL_TOLERANCE = decimal.Decimal("1.00")
MAX_INVOICE_NUMBER_LENGTH = 30


def validate_gstin(gstin: Optional[str]) -> List[str]:
    errors: List[str] = []

    if not gstin:
        errors.append("GSTIN is required")
    elif not _GSTIN_FORMAT.match(gstin.strip().upper()):
        errors.append(f"GSTIN '{gstin}' does not match the expected 15-character format")

    return errors


def validate_invoice_number(invoice_number: Optional[str]) -> List[str]:
    errors: List[str] = []

    if not invoice_number or not invoice_number.strip():
        errors.append("Invoice number is required")
    elif len(invoice_number) > MAX_INVOICE_NUMBER_LENGTH:
        errors.append(
            f"Invoice number '{invoice_number}' exceeds {MAX_INVOICE_NUMBER_LENGTH} characters"
        )

    return errors


def validate_invoice_date(
    invoice_date: Optional[datetime.date],
    due_date: Optional[datetime.date],
) -> List[str]:
    errors: List[str] = []
    today = datetime.date.today()

    if invoice_date is None:
        errors.append("Invoice date is required")
    elif invoice_date > today:
        errors.append(f"Invoice date {invoice_date} is in the future")

    if due_date is not None and invoice_date is not None and due_date < invoice_date:
        errors.append(f"Due date {due_date} is before invoice date {invoice_date}")

    return errors


def validate_totals(
    subtotal: Optional[decimal.Decimal],
    cgst: Optional[decimal.Decimal],
    sgst: Optional[decimal.Decimal],
    igst: Optional[decimal.Decimal],
    total: Optional[decimal.Decimal],
    cess: Optional[decimal.Decimal] = None,
    tax_amount: Optional[decimal.Decimal] = None,
) -> List[str]:
    errors: List[str] = []

    if subtotal is None:
        errors.append("Subtotal is required")
    if total is None:
        errors.append("Total is required")

    amounts = {
        "subtotal": subtotal,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "tax_amount": tax_amount,
        "total": total,
    }
    for name, value in amounts.items():
        if value is not None and value < 0:
            errors.append(f"{name} cannot be negative ({value})")

    has_cgst_sgst = bool((cgst or 0) > 0 or (sgst or 0) > 0)
    has_igst = bool((igst or 0) > 0)
    if has_cgst_sgst and has_igst:
        errors.append("Invoice cannot have both CGST/SGST and IGST applied")

    if subtotal is not None and total is not None:
        expected_total = (
            (subtotal or 0)
            + (cgst or 0)
            + (sgst or 0)
            + (igst or 0)
            + (cess or 0)
            + (tax_amount or 0)
        )
        if abs(expected_total - total) > TOTAL_TOLERANCE:
            errors.append(
                f"Total {total} does not match subtotal + taxes {expected_total} "
                f"(tolerance {TOTAL_TOLERANCE})"
            )

    return errors


def validate_invoice(extracted: ExtractedInvoice) -> ValidationResult:
    """Run every business validation rule against an ExtractedInvoice."""
    errors: List[str] = []

    errors.extend(validate_invoice_number(extracted.invoice_number))
    errors.extend(validate_gstin(extracted.gstin))
    errors.extend(validate_invoice_date(extracted.invoice_date, extracted.due_date))
    errors.extend(
        validate_totals(
            extracted.subtotal, extracted.cgst, extracted.sgst, extracted.igst,
            extracted.total, extracted.cess, extracted.tax_amount,
        )
    )

    return ValidationResult(valid=not errors, errors=errors)
