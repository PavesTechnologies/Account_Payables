# Backend/Business_Layer/services/payment_receipt_extraction_service.py
"""Payment receipt auto-fill (APM_AUTOMATION_PLAN.md 3.3, Phase 4).

Turns the Textract result for an uploaded receipt into suggested Record Payment values plus
warnings the person should look at. Read-only: a payment is only ever recorded by the existing
POST /payment/invoice/{id}/record after the user reviews the form, so every existing validation
(remaining payable, reference format, duplicate reference on the invoice) still applies.
"""
import datetime
import difflib
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from Backend.Business_Layer.services.payment_tracking_service import _REFERENCE_PATTERNS, PaymentTrackingService
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice

LOW_CONFIDENCE = 60.0
_COMPANY_WORDS = re.compile(r"\b(private|pvt|limited|ltd|llp|inc|co|company|corp|corporation|the|and|m/s|ms)\b")
_LABELS = {"payment_date": "payment date", "amount": "amount", "payment_mode": "payment mode", "reference_number": "reference number"}


def _warning(code: str, message: str, severity: str = "warning") -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _name_key(name: Optional[str]) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and "))
    return " ".join(_COMPANY_WORDS.sub(" ", text).split())


def names_look_alike(a: Optional[str], b: Optional[str]) -> bool:
    ka, kb = _name_key(a), _name_key(b)
    if not ka or not kb:
        return True  # nothing to compare - no warning
    if ka in kb or kb in ka or set(ka.split()) & set(kb.split()):
        return True
    return difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.6


class PaymentReceiptExtractionService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    def _reference_uses(self, reference: str, invoice_id: int) -> List[tuple]:
        """(invoice_id, invoice_number) of non-FAILED payments already carrying this reference."""
        return (self.db.query(Invoice.invoice_id, Invoice.invoice_number)
                .join(PaymentInvoice, PaymentInvoice.invoice_id == Invoice.invoice_id)
                .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
                .outerjoin(StatusMaster, StatusMaster.status_id == Payment.status_id)
                .filter(func.upper(Payment.reference_number) == reference.upper(),
                        or_(StatusMaster.status_code.is_(None), StatusMaster.status_code != "FAILED"))
                .distinct().all())

    def suggest(self, invoice_id: int, extracted: Dict[str, Any]) -> Dict[str, Any]:
        summary = PaymentTrackingService(self.db).get_invoice_payments(invoice_id)
        fields = extracted["fields"]
        warnings: List[Dict[str, str]] = []

        status = extracted.get("transaction_status")
        if status == "FAILED":
            warnings.append(_warning("FAILED", "The receipt says the transaction failed or was reversed - do not record it as paid.", "error"))
        elif status == "PENDING":
            warnings.append(_warning("PENDING", "The receipt shows the transfer as pending / in process - record it once it has cleared."))

        amount = Decimal(fields["amount"]["value"]) if fields["amount"]["value"] else None
        remaining = Decimal(summary["remaining_amount"])
        if amount is not None:
            if amount > remaining:
                warnings.append(_warning("AMOUNT_ABOVE_REMAINING",
                                         f"Receipt amount {amount:,.2f} is more than the remaining payable {remaining:,.2f}. "
                                         "If one transfer paid several invoices, enter only this invoice's share."))
            elif amount < remaining:
                warnings.append(_warning("PARTIAL", f"Partial payment - {remaining - amount:,.2f} will remain payable.", "info"))

        if fields["payment_date"]["value"]:
            paid_on = datetime.date.fromisoformat(fields["payment_date"]["value"])
            if paid_on > self.today:
                warnings.append(_warning("FUTURE_DATE", "The receipt date is in the future - check the date."))
            elif summary.get("invoice_date") and paid_on < summary["invoice_date"]:
                warnings.append(_warning("BEFORE_INVOICE", "The payment date is before the invoice date - check the receipt belongs to this invoice."))

        beneficiary = extracted.get("beneficiary_name")
        if beneficiary and not names_look_alike(beneficiary, summary.get("vendor_name")):
            warnings.append(_warning("BENEFICIARY_MISMATCH",
                                     f"Beneficiary '{beneficiary}' does not look like the vendor '{summary.get('vendor_name')}'.", "error"))

        reference = fields["reference_number"]["value"]
        mode = fields["payment_mode"]["value"]
        if reference:
            uses = self._reference_uses(reference, invoice_id)
            if any(i == invoice_id for i, _ in uses):
                warnings.append(_warning("REFERENCE_ON_INVOICE", f"Reference {reference} is already recorded for this invoice.", "error"))
            others = [n for i, n in uses if i != invoice_id]
            if others:
                warnings.append(_warning("REFERENCE_ELSEWHERE",
                                         f"Reference {reference} is also used for invoice(s) {', '.join(others[:5])} - fine when one transfer "
                                         "settled several invoices; check the amount split."))
            if mode in _REFERENCE_PATTERNS and not _REFERENCE_PATTERNS[mode].fullmatch(reference):
                warnings.append(_warning("REFERENCE_FORMAT", f"Reference {reference} does not look like a {mode} reference - check it."))

        low = [_LABELS[k] for k, v in fields.items() if v["value"] and v["confidence"] < LOW_CONFIDENCE]
        missing = [_LABELS[k] for k, v in fields.items() if not v["value"]]
        if low:
            warnings.append(_warning("LOW_CONFIDENCE", "Read with low confidence - please check: " + ", ".join(low) + ".", "info"))
        if missing:
            warnings.append(_warning("MISSING", "Not found on the receipt - enter manually: " + ", ".join(missing) + ".", "info"))

        return {
            "invoice_id": invoice_id,
            "fields": fields,
            "beneficiary_name": beneficiary,
            "beneficiary_account_masked": extracted.get("beneficiary_account_masked"),
            "beneficiary_ifsc": extracted.get("beneficiary_ifsc"),
            "transaction_status": status,
            "remaining_amount": remaining,
            "warnings": warnings,
        }
