import datetime
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InvoiceDetailsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    invoice_number: str
    vendor_id: int | None
    vendor_name: str | None
    inbound_document_id: int | None
    invoice_type: str
    invoice_date: date
    due_date: date
    currency_id: int | None
    gross_amount: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    # Present on the Invoice model since before this response was first built, but never
    # surfaced here — every consumer (payment balance calc, the invoice-detail editable review
    # form) had to default this to 0/blank client-side. See PaymentMarkAsPaidPage.jsx and
    # InvoiceReviewEditor.jsx in the frontend for the workarounds this closes.
    amount_paid: Decimal
    po_id: int | None
    payment_term_id: int | None
    department_id: int | None
    purchase_category_id: int | None
    status_code: str | None
    # TDS-adjusted figures - never derived by mutating net_amount (that stays the
    # invoice's own accounting face value: gross - discount + tax). tds_amount is
    # the withheld amount when applicable; payable_amount is what's actually owed
    # to the vendor (net_amount - tds_amount when applicable, else net_amount
    # unchanged) - same figure PaymentService._net_payable() enforces at payment
    # time, exposed here so list/detail views don't have to recompute it.
    tds_applicable: bool | None = None
    tds_amount: Decimal | None = None
    payable_amount: Decimal


class InvoiceHistoryEventDTO(BaseModel):
    """One ap.audit_log row for this invoice (table_name='invoice', record_id=invoice_id) —
    covers INVOICE_CREATED/INVOICE_OCR_REVIEWED/INVOICE_RESUBMITTED (invoice_process_service.py),
    INVOICE_SENT_FOR_APPROVAL/INVOICE_APPROVAL_STEP_DECISION/INVOICE_REJECTED/INVOICE_SENT_BACK/
    INVOICE_APPROVED (invoice_approval_service.py), and INVOICE_PAYMENT_SCHEDULED/_SENT/_CLEARED/
    _FAILED (payment_service.py — each written against the invoice's own record_id in addition
    to that payment's separate table_name='payment' trail, so a payment covering several
    invoices shows up on each one's own history individually)."""

    model_config = ConfigDict(from_attributes=True)

    action: str
    changed_by: Optional[str] = None
    changed_at: datetime.datetime
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None