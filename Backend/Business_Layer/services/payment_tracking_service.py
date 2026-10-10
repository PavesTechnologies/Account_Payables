# Backend/Business_Layer/services/payment_tracking_service.py
"""Payment Management screens: Ready for Payment, Payment History, an
invoice's payment detail, recording an externally completed payment, and
payment receipts.

Builds on PaymentService rather than duplicating it:
  - the TDS-adjusted payable is PaymentService._net_payable
    (tds_determination_service.compute_payable_amount) - never recomputed
    here or in the UI;
  - "money reached the vendor" (amount_paid + PAID/PARTIALLY_PAID) is
    PaymentService._apply_cleared_allocation, the same code the
    SCHEDULED->SENT->CLEARED flow uses.

A recorded payment is an ordinary ap.payment row (single allocation) that is
created directly in CLEARED - Finance has already paid the vendor outside this
system and is recording it (date, amount, mode, UTR, remarks, receipt).

Every amount the UI shows comes from invoice_payment_summary():
    invoice_amount   = invoice.net_amount (what the vendor billed, incl. GST)
    tds_amount       = invoice_tds.tds_amount when tds_applicable
    net_payable      = invoice_amount - tds_amount
    amount_paid      = invoice.amount_paid (CLEARED payments only)
    pending_amount   = allocations on SCHEDULED/SENT payments (reserved)
    remaining_amount = net_payable - amount_paid - pending_amount (>= 0)
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from Backend.Business_Layer.services.payment_service import (
    PAYMENT_STATUS_MODULE,
    STATUS_CODE_CLEARED,
    STATUS_CODE_PARTIALLY_PAID,
    STATUS_CODE_READY_FOR_PAYMENT,
    PaymentService,
    _INVOICE_PAYABLE_STATUSES,
)
from Backend.Business_Layer.services.tds_determination_service import require_tds_verified
from Backend.Data_Access_Layer.dao.payment_term_dao import PaymentTermDAO
from Backend.Data_Access_Layer.dao.payment_dao import PAYMENT_PENDING_CODES
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.payment import Payment, PaymentDocument, PaymentInvoice
from Backend.Data_Access_Layer.models.tds import InvoiceTdsTracking

# Payment modes for recorded payments - the backend is the source of truth
# (exposed through GET /payment/metadata; validated in record_payment).
# reference_pattern: full-match regex for reference_number, written in the
# subset Python and JavaScript agree on ([0-9], not \d - Python's \d also
# matches non-ASCII digits) so the frontend can use it verbatim. These are the
# standard Indian banking conventions (UTR / RRN / cheque & DD number), not yet
# confirmed against this org's bank data - None means only the generic
# _REFERENCE_RE check applies.
PAYMENT_MODES = [
    {"value": "NEFT", "label": "NEFT", "reference_label": "UTR Number",
     "reference_pattern": "^[A-Za-z0-9]{16}$", "reference_hint": "16 letters or digits"},
    {"value": "RTGS", "label": "RTGS", "reference_label": "UTR Number",
     "reference_pattern": "^[A-Za-z0-9]{16}$", "reference_hint": "16 letters or digits"},
    {"value": "IMPS", "label": "IMPS", "reference_label": "IMPS Reference Number",
     "reference_pattern": "^[0-9]{12}$", "reference_hint": "12 digits"},
    {"value": "UPI", "label": "UPI", "reference_label": "UPI Transaction ID",
     "reference_pattern": "^[0-9]{12}$", "reference_hint": "12 digits"},
    {"value": "BANK_TRANSFER", "label": "Bank Transfer", "reference_label": "Transaction Reference",
     "reference_pattern": None, "reference_hint": None},
    {"value": "CHEQUE", "label": "Cheque", "reference_label": "Cheque Number",
     "reference_pattern": "^[0-9]{6}$", "reference_hint": "6 digits"},
    {"value": "DEMAND_DRAFT", "label": "Demand Draft", "reference_label": "DD Number",
     "reference_pattern": "^[0-9]{6}$", "reference_hint": "6 digits"},
]
_PAYMENT_MODE_VALUES = {m["value"] for m in PAYMENT_MODES}
_PAYMENT_MODE_BY_VALUE = {m["value"]: m for m in PAYMENT_MODES}
_REFERENCE_PATTERNS = {m["value"]: re.compile(m["reference_pattern"]) for m in PAYMENT_MODES if m["reference_pattern"]}

PAYMENT_DOCUMENT_TYPES = [
    {"value": "RECEIPT", "label": "Payment Receipt / Proof"},
    {"value": "OTHER", "label": "Other"},
]
_PAYMENT_DOCUMENT_TYPE_VALUES = {d["value"] for d in PAYMENT_DOCUMENT_TYPES}

READY_FOR_PAYMENT_STATUSES = (STATUS_CODE_READY_FOR_PAYMENT, STATUS_CODE_PARTIALLY_PAID)

_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/\-_. ]*$")
_CENTS = Decimal("0.01")
MAX_PAGE_SIZE = 100


class PaymentNotFoundError(ValueError):
    """-> 404"""


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(_CENTS)


def _page_bounds(page: int, page_size: int) -> tuple[int, int, int, int]:
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
    return page, page_size, (page - 1) * page_size, page_size


def payment_status_code(payment: Payment) -> Optional[str]:
    return payment.status.status_code if payment.status else None


def invoice_payment_summary(invoice, vendor_name, status, tds, allocations, net_payable: Decimal, today=None) -> dict:
    """Server-computed amounts for one invoice (see module docstring)."""
    today = today or datetime.date.today()
    invoice_amount = _money(invoice.net_amount)
    tds_applicable = bool(tds is not None and tds.tds_applicable)
    tds_amount = _money(tds.tds_amount) if tds_applicable and tds.tds_amount is not None else Decimal("0.00")
    amount_paid = _money(invoice.amount_paid)
    pending = sum(
        (_money(a.allocated_amount) for a in allocations if payment_status_code(a.payment) in PAYMENT_PENDING_CODES),
        Decimal("0.00"),
    )
    net_payable = _money(net_payable)
    remaining = max(net_payable - amount_paid - pending, Decimal("0.00"))

    cleared = [a for a in allocations if payment_status_code(a.payment) == STATUS_CODE_CLEARED]
    last = cleared[-1].payment if cleared else None
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_number": invoice.invoice_number,
        "vendor_id": invoice.vendor_id,
        "vendor_name": vendor_name,
        "invoice_date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "currency_code": invoice.currency.currency_code if invoice.currency else None,
        "currency_symbol": invoice.currency.symbol if invoice.currency else None,
        "gross_amount": _money(invoice.gross_amount),
        "discount_amount": _money(invoice.discount_amount),
        "tax_amount": _money(invoice.tax_amount),
        "invoice_amount": invoice_amount,
        "tds_applicable": tds_applicable,
        "tds_amount": tds_amount,
        "tds_determination_status": tds.determination_status if tds is not None else None,
        "net_payable": net_payable,
        "amount_paid": amount_paid,
        "pending_amount": pending,
        "remaining_amount": remaining,
        "status_code": status.status_code if status else None,
        "status_name": status.status_name if status else None,
        "is_overdue": bool(remaining > 0 and invoice.due_date is not None and invoice.due_date < today),
        "payment_count": len(cleared),
        "last_payment_date": (last.payment_date or last.scheduled_date) if last else None,
        "last_payment_mode": last.payment_method if last else None,
        "last_payment_reference": last.reference_number if last else None,
        "receipt_count": sum(len(a.payment.documents or []) for a in cleared),
    }


def payment_document_view(doc: PaymentDocument) -> dict:
    return {
        "id": doc.payment_document_id,
        "payment_id": doc.payment_id,
        "document_type": doc.document_type,
        "file_name": doc.file_name,
        "content_type": doc.content_type,
        "file_size": doc.file_size,
        "uploaded_by": doc.uploaded_by,
        "uploaded_at": doc.uploaded_at,
    }


def payment_record_view(allocation: PaymentInvoice) -> dict:
    payment = allocation.payment
    return {
        "payment_id": payment.payment_id,
        "payment_date": payment.payment_date,
        "scheduled_date": payment.scheduled_date,
        "amount": _money(allocation.allocated_amount),
        "payment_total": _money(payment.total_amount),
        "payment_mode": payment.payment_method,
        "reference_number": payment.reference_number,
        "remarks": payment.remarks,
        "status_code": payment_status_code(payment),
        "status_name": payment.status.status_name if payment.status else None,
        "recorded_by": payment.created_by,
        "recorded_at": payment.created_at,
        "documents": [payment_document_view(d) for d in payment.documents or []],
    }


class PaymentTrackingService:
    def __init__(self, db):
        self.db = db
        self.payment_service = PaymentService(db)
        self.payment_dao = self.payment_service.payment_dao
        self.invoice_dao = self.payment_service.invoice_dao
        self.tds_dao = self.payment_service.tds_dao

    # =========================================================
    # Metadata
    # =========================================================

    @staticmethod
    def metadata() -> dict:
        from Backend.API_Layer.utils.file_validation import MAX_UPLOAD_SIZE_BYTES, _ALLOWED_EXTENSIONS

        return {
            "payment_modes": PAYMENT_MODES,
            "document_types": PAYMENT_DOCUMENT_TYPES,
            "reference_required": True,
            "receipt_required": False,
            "allowed_file_extensions": sorted(_ALLOWED_EXTENSIONS),
            "max_file_size_bytes": MAX_UPLOAD_SIZE_BYTES,
            "ready_for_payment_statuses": list(READY_FOR_PAYMENT_STATUSES),
        }

    # =========================================================
    # Lists
    # =========================================================

    def _summaries(self, rows) -> list[dict]:
        allocations = self.payment_dao.get_allocations_for_invoices([r[0].invoice_id for r in rows])
        by_invoice: dict[int, list] = {}
        for allocation in allocations:
            by_invoice.setdefault(allocation.invoice_id, []).append(allocation)
        today = datetime.date.today()
        result = []
        for invoice, vendor_name, status, tds in rows:
            net_payable = self.payment_service._net_payable(invoice)
            result.append(invoice_payment_summary(invoice, vendor_name, status, tds, by_invoice.get(invoice.invoice_id, []), net_payable, today))
        self._attach_payment_terms(result)
        return result

    def _attach_payment_terms(self, summaries: list[dict]) -> None:
        """Adds each invoice's payment-term compliance status (PaymentTermComplianceService) so the
        payment screens can badge exceptions and explain a blocked Mark Ready for Payment."""
        records = PaymentTermDAO(self.db).get_records([s["invoice_id"] for s in summaries])
        for summary in summaries:
            record = records.get(summary["invoice_id"])
            summary["payment_term_status"] = record.validation_status if record else None
            summary["payment_term_reason"] = record.reason_code if record else None
            summary["due_date_verified"] = bool(record.due_date_verified) if record else None
            summary["contractual_due_date"] = record.contractual_due_date if record else None
            summary["statutory_due_date"] = record.statutory_due_date if record else None

    def list_ready_for_payment(self, search=None, status=None, vendor_id=None, due_from=None, due_to=None,
                               overdue_only=False, page=1, page_size=20) -> dict:
        statuses = self._statuses(status, READY_FOR_PAYMENT_STATUSES)
        page, page_size, offset, limit = _page_bounds(page, page_size)
        rows, total = self.payment_dao.list_invoices_for_payment(
            statuses, search, vendor_id, due_from, due_to, datetime.date.today() if overdue_only else None, offset, limit
        )
        return {"items": self._summaries(rows), "total": total, "page": page, "page_size": page_size}

    def list_payment_history(self, search=None, status=None, vendor_id=None, payment_mode=None,
                             paid_from=None, paid_to=None, page=1, page_size=20) -> dict:
        statuses = self._statuses(status, None)
        if payment_mode and payment_mode not in _PAYMENT_MODE_VALUES:
            raise ValueError(f"payment_mode must be one of {', '.join(sorted(_PAYMENT_MODE_VALUES))}")
        page, page_size, offset, limit = _page_bounds(page, page_size)
        rows, total = self.payment_dao.list_invoices_with_payments(
            statuses, search, vendor_id, payment_mode, paid_from, paid_to, offset, limit
        )
        return {"items": self._summaries(rows), "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def _statuses(status: Optional[str], default):
        if not status:
            return list(default) if default else None
        codes = [s.strip().upper() for s in status.split(",") if s.strip()]
        return codes or (list(default) if default else None)

    # =========================================================
    # Invoice payment detail
    # =========================================================

    def get_invoice_payments(self, invoice_id: int) -> dict:
        row = self.payment_dao.get_invoice_with_context(invoice_id)
        if row is None:
            raise PaymentNotFoundError(f"Invoice {invoice_id} not found")
        invoice, vendor_name, status, tds = row
        allocations = self.payment_dao.get_allocations_for_invoices([invoice_id])
        summary = invoice_payment_summary(invoice, vendor_name, status, tds, allocations, self.payment_service._net_payable(invoice))
        tracking = self.db.query(InvoiceTdsTracking).filter(InvoiceTdsTracking.invoice_id == invoice_id).first()
        summary["tds_tracking_status"] = (
            (tracking.tracking_status if tracking else "TDS_PENDING") if summary["tds_applicable"] else None
        )
        summary["can_record_payment"] = bool(
            summary["status_code"] in _INVOICE_PAYABLE_STATUSES and summary["remaining_amount"] > 0
        )
        summary["payments"] = [payment_record_view(a) for a in allocations]
        self._attach_payment_terms([summary])
        return summary

    # =========================================================
    # Record payment
    # =========================================================

    def record_payment(self, invoice_id: int, data, user_id) -> dict:
        """data: payment_date, amount, payment_mode, reference_number, remarks."""
        try:
            invoice = self.invoice_dao.get_invoice_by_id_locked(invoice_id)
            if invoice is None:
                raise PaymentNotFoundError(f"Invoice {invoice_id} not found")

            current_code = invoice.status.status_code if invoice.status else None
            if current_code not in _INVOICE_PAYABLE_STATUSES:
                raise ValueError(
                    f"Payment cannot be recorded for invoice {invoice.invoice_number} in status {current_code} - "
                    f"only Ready for Payment / Partially Paid invoices can be paid"
                )
            # Defence in depth: a payable invoice always has VERIFIED TDS, but
            # if that snapshot were ever missing the vendor would be overpaid.
            tds = self.tds_dao.get_invoice_tds_by_invoice_id(invoice_id)
            try:
                require_tds_verified(invoice_id, tds)
            except ValueError as e:
                raise ValueError(str(e).replace("cannot be marked ready for payment", "cannot be paid"))

            errors = []
            payment_date = data.payment_date
            if payment_date is None:
                errors.append("Payment Date is required")
            elif payment_date > datetime.date.today():
                errors.append("Payment Date cannot be in the future")

            amount = data.amount
            try:
                amount = Decimal(str(amount)) if amount is not None else None
            except InvalidOperation:
                amount = None
                errors.append("Payment Amount must be numeric")
            if amount is None:
                if "Payment Amount must be numeric" not in errors:
                    errors.append("Payment Amount is required")
            elif amount <= 0:
                errors.append("Payment Amount must be greater than zero")
            elif amount != amount.quantize(_CENTS):
                errors.append("Payment Amount can have at most 2 decimal places")

            mode = (data.payment_mode or "").strip().upper()
            if mode not in _PAYMENT_MODE_VALUES:
                errors.append(f"Payment Mode must be one of {', '.join(m['value'] for m in PAYMENT_MODES)}")

            reference = (data.reference_number or "").strip()
            if not reference:
                errors.append("UTR / Transaction Reference is required")
            elif mode in _REFERENCE_PATTERNS:
                if not _REFERENCE_PATTERNS[mode].fullmatch(reference):
                    spec = _PAYMENT_MODE_BY_VALUE[mode]
                    errors.append(f"{spec['reference_label']} for {spec['label']} must be exactly {spec['reference_hint']}")
            elif len(reference) > 100 or not _REFERENCE_RE.match(reference):
                errors.append("UTR / Transaction Reference may contain only letters, digits, spaces and / - _ . (max 100)")

            remarks = (data.remarks or "").strip() or None
            if remarks and len(remarks) > 1000:
                errors.append("Remarks cannot exceed 1000 characters")
            if errors:
                raise ValueError("; ".join(errors))

            pending = self.payment_dao.get_pending_committed_amount_for_invoice(invoice_id)
            remaining = max(_money(self.payment_service._net_payable(invoice)) - _money(invoice.amount_paid) - _money(pending), Decimal("0.00"))
            if amount > remaining:
                raise ValueError(f"Payment Amount {amount} exceeds the remaining payable amount {remaining}")
            if self.payment_dao.reference_used_for_invoice(invoice_id, reference):
                raise ValueError(f"A payment with reference '{reference}' is already recorded for this invoice")

            cleared = self.payment_dao.get_status_by_module_code(PAYMENT_STATUS_MODULE, STATUS_CODE_CLEARED)
            if cleared is None:
                raise ValueError(f"Status '{STATUS_CODE_CLEARED}' is not configured for the PAYMENT module")

            payment = Payment(
                vendor_id=invoice.vendor_id,
                scheduled_date=payment_date,
                payment_date=payment_date,
                total_amount=amount,
                currency_id=invoice.currency_id,
                payment_method=mode,
                reference_number=reference,
                remarks=remarks,
                status_id=cleared.status_id,
                created_by=str(user_id),
                updated_by=str(user_id),
            )
            self.payment_dao.create_payment(payment)
            self.payment_dao.create_payment_invoice(
                PaymentInvoice(payment_id=payment.payment_id, invoice_id=invoice_id, allocated_amount=amount)
            )
            self.payment_dao.create_audit_log(AuditLog(
                table_name="payment",
                record_id=payment.payment_id,
                action="RECORD",
                changed_by=str(user_id),
                new_values={
                    "vendor_id": invoice.vendor_id,
                    "invoice_id": invoice_id,
                    "total_amount": str(amount),
                    "payment_date": payment_date.isoformat(),
                    "payment_mode": mode,
                    "reference_number": reference,
                    "status_code": STATUS_CODE_CLEARED,
                    "entry_mode": getattr(data, "entry_mode", None) or "MANUAL",
                    **({"edited_fields": list(data.edited_fields)[:10]} if getattr(data, "edited_fields", None) else {}),
                },
            ))
            self.payment_service._apply_cleared_allocation(
                invoice, amount, payment.payment_id, str(user_id), "INVOICE_PAYMENT_RECORDED",
                extra={"payment_date": payment_date.isoformat(), "payment_mode": mode, "reference_number": reference},
            )

            self.db.commit()
            return self.get_invoice_payments(invoice_id) | {"recorded_payment_id": payment.payment_id}
        except Exception:
            self.db.rollback()
            raise

    # =========================================================
    # Documents (receipts)
    # =========================================================

    def upload_document(self, payment_id: int, filename: str, content: bytes, content_type: Optional[str],
                        document_type: str, user_id) -> dict:
        from Backend.API_Layer.utils.s3_utils import upload_to_s3

        try:
            payment = self.payment_dao.get_payment_by_id(payment_id)
            if payment is None:
                raise PaymentNotFoundError(f"Payment {payment_id} not found")
            document_type = (document_type or "RECEIPT").strip().upper()
            if document_type not in _PAYMENT_DOCUMENT_TYPE_VALUES:
                raise ValueError(f"document_type must be one of {', '.join(sorted(_PAYMENT_DOCUMENT_TYPE_VALUES))}")

            upload = upload_to_s3(filename, content, content_type, prefix="payments/")
            document = self.payment_dao.add_document(PaymentDocument(
                payment_id=payment_id,
                document_type=document_type,
                file_name=filename,
                file_path=upload["filepath"],
                content_type=content_type,
                file_size=len(content),
                uploaded_by=str(user_id),
            ))
            for allocation in payment.payment_invoice:
                self.invoice_dao.create_audit_log(AuditLog(
                    table_name="invoice",
                    record_id=allocation.invoice_id,
                    action="INVOICE_PAYMENT_DOCUMENT_UPLOADED",
                    changed_by=str(user_id),
                    new_values={"payment_id": payment_id, "document_type": document_type, "file_name": filename},
                ))
            self.db.commit()
            self.db.refresh(document)
            return payment_document_view(document)
        except Exception:
            self.db.rollback()
            raise

    def get_document(self, payment_id: int, document_id: int) -> PaymentDocument:
        document = self.payment_dao.get_document(payment_id, document_id)
        if document is None:
            raise PaymentNotFoundError(f"Document {document_id} not found for payment {payment_id}")
        return document
