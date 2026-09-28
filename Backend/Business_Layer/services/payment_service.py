# Backend/Business_Layer/services/payment_service.py
"""Payment creation, allocation, and status lifecycle on top of the
existing Payment/PaymentInvoice schema (no schema changes).

Lifecycle (ap.status_master, module=PAYMENT): SCHEDULED -> SENT -> CLEARED,
or SCHEDULED/SENT -> FAILED. invoice.amount_paid is only incremented when
a payment reaches CLEARED — SCHEDULED/SENT allocations are "reserved"
(see PaymentDAO.get_pending_committed_amount_for_invoice) but don't move
money yet, so a FAILED payment never has to be unwound.

The amount actually payable to a vendor is invoice.net_amount minus TDS
when applicable (see _net_payable) — the withheld amount is remitted to
the tax authority, never paid to the vendor, so it's excluded both from
the allocation ceiling in create_payment and from the amount_paid >= X
check that flips an invoice to PAID in update_status.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import List, Optional

from Backend.API_Layer.interface.payment_interface import PaymentCreateRequest
from Backend.Business_Layer.services.tds_determination_service import compute_payable_amount
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.payment_dao import PaymentDAO
from Backend.Data_Access_Layer.dao.tds_dao import TdsDAO
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice

PAYMENT_STATUS_MODULE = "PAYMENT"
INVOICE_STATUS_MODULE = "INVOICE"

STATUS_CODE_SCHEDULED = "SCHEDULED"
STATUS_CODE_SENT = "SENT"
STATUS_CODE_CLEARED = "CLEARED"
STATUS_CODE_FAILED = "FAILED"

STATUS_CODE_APPROVED = "APPROVED"
STATUS_CODE_READY_FOR_PAYMENT = "READY_FOR_PAYMENT"
STATUS_CODE_PARTIALLY_PAID = "PARTIALLY_PAID"
STATUS_CODE_PAID = "PAID"

_ALLOWED_TRANSITIONS = {
    STATUS_CODE_SCHEDULED: {STATUS_CODE_SENT, STATUS_CODE_FAILED},
    STATUS_CODE_SENT: {STATUS_CODE_CLEARED, STATUS_CODE_FAILED},
    STATUS_CODE_CLEARED: set(),
    STATUS_CODE_FAILED: set(),
}

# An invoice must be explicitly marked READY_FOR_PAYMENT by Finance (mark_ready_for_payment)
# before it can receive a payment — a merely-APPROVED invoice is not yet payable. This was
# previously {APPROVED, PARTIALLY_PAID}, which let a payment be created straight off approval
# with no Finance readiness review step; READY_FOR_PAYMENT now sits between them.
_INVOICE_PAYABLE_STATUSES = {STATUS_CODE_READY_FOR_PAYMENT, STATUS_CODE_PARTIALLY_PAID}


class PaymentService:
    def __init__(self, db):
        self.db = db
        self.payment_dao = PaymentDAO(db)
        self.invoice_dao = InvoiceDAO(db)
        self.vendor_dao = VendorDAO(db)
        self.tds_dao = TdsDAO(db)

    def _net_payable(self, invoice) -> Decimal:
        """What the vendor is actually owed for this invoice - see
        tds_determination_service.compute_payable_amount. Regardless of whether
        Finance has clicked Verify yet (verification confirms the calculated
        numbers; it doesn't gate whether a determined deduction applies)."""
        tds = self.tds_dao.get_invoice_tds_by_invoice_id(invoice.invoice_id)
        return compute_payable_amount(invoice.net_amount, tds)

    def create_payment(self, request: PaymentCreateRequest, user_id: str) -> Payment:
        try:
            if not self.vendor_dao.vendor_exists(request.vendor_id):
                raise ValueError(f"Vendor {request.vendor_id} not found")

            scheduled_status = self.payment_dao.get_status_by_module_code(
                PAYMENT_STATUS_MODULE, STATUS_CODE_SCHEDULED
            )
            if scheduled_status is None:
                raise ValueError(f"Status '{STATUS_CODE_SCHEDULED}' is not configured for the PAYMENT module")

            invoices = []
            for allocation in request.allocations:
                invoice = self.invoice_dao.get_invoice_by_id_locked(allocation.invoice_id)
                if invoice is None:
                    raise ValueError(f"Invoice {allocation.invoice_id} not found")
                if invoice.vendor_id != request.vendor_id:
                    raise ValueError(
                        f"Invoice {allocation.invoice_id} does not belong to vendor {request.vendor_id}"
                    )

                current_code = invoice.status.status_code if invoice.status else None
                if current_code not in _INVOICE_PAYABLE_STATUSES:
                    raise ValueError(
                        f"Invoice {allocation.invoice_id} is not payable (current status: {current_code})"
                    )

                pending_committed = self.payment_dao.get_pending_committed_amount_for_invoice(
                    allocation.invoice_id
                )
                remaining = self._net_payable(invoice) - invoice.amount_paid - pending_committed
                if allocation.allocated_amount <= 0:
                    raise ValueError("allocated_amount must be greater than zero")
                if allocation.allocated_amount > remaining:
                    raise ValueError(
                        f"Allocated amount {allocation.allocated_amount} exceeds the remaining payable "
                        f"amount ({remaining}) for invoice {allocation.invoice_id}"
                    )

                invoices.append(invoice)

            total_amount = sum((a.allocated_amount for a in request.allocations), Decimal("0"))

            payment = Payment(
                vendor_id=request.vendor_id,
                vendor_bank_id=request.vendor_bank_id,
                scheduled_date=request.scheduled_date,
                total_amount=total_amount,
                currency_id=request.currency_id,
                payment_method=request.payment_method,
                reference_number=request.reference_number,
                status_id=scheduled_status.status_id,
                created_by=user_id,
                updated_by=user_id,
            )
            self.payment_dao.create_payment(payment)

            for allocation in request.allocations:
                self.payment_dao.create_payment_invoice(
                    PaymentInvoice(
                        payment_id=payment.payment_id,
                        invoice_id=allocation.invoice_id,
                        allocated_amount=allocation.allocated_amount,
                    )
                )

            self.payment_dao.create_audit_log(
                AuditLog(
                    table_name="payment",
                    record_id=payment.payment_id,
                    action="CREATE",
                    changed_by=user_id,
                    new_values={
                        "vendor_id": request.vendor_id,
                        "total_amount": str(total_amount),
                        "status_code": STATUS_CODE_SCHEDULED,
                        "invoice_ids": [a.invoice_id for a in request.allocations],
                    },
                )
            )

            # A payment's own audit trail (table_name="payment" above) doesn't surface on the
            # invoice's own Activity view (get_invoice_history filters by table_name="invoice") —
            # without this, an invoice that received a payment showed no trace of it at all on
            # its own history. One entry per allocated invoice, since one payment can cover several.
            for allocation in request.allocations:
                self.invoice_dao.create_audit_log(
                    AuditLog(
                        table_name="invoice",
                        record_id=allocation.invoice_id,
                        action="INVOICE_PAYMENT_SCHEDULED",
                        changed_by=user_id,
                        new_values={
                            "payment_id": payment.payment_id,
                            "allocated_amount": str(allocation.allocated_amount),
                        },
                    )
                )

            self.db.commit()
            self.db.refresh(payment)
            return payment
        except Exception:
            self.db.rollback()
            raise

    def mark_ready_for_payment(self, invoice_id: int, user_id: str) -> "Invoice":
        """APPROVED -> READY_FOR_PAYMENT: the explicit Finance action that gates whether an
        invoice can receive a payment at all (see _INVOICE_PAYABLE_STATUSES). Deliberately not
        automatic on approval (spec section 16/28: "Do not automatically mark an invoice as paid
        merely because it became approved") — this is the one manual step in between.
        """
        try:
            invoice = self.invoice_dao.get_invoice_by_id_locked(invoice_id)
            if invoice is None:
                raise ValueError(f"Invoice {invoice_id} not found")

            current_code = invoice.status.status_code if invoice.status else None
            if current_code != STATUS_CODE_APPROVED:
                raise ValueError(
                    f"Invoice {invoice_id} cannot be marked ready for payment while in status {current_code}"
                )

            ready_status = self.invoice_dao.get_status_by_code(STATUS_CODE_READY_FOR_PAYMENT)
            if ready_status is None:
                raise ValueError(f"Status '{STATUS_CODE_READY_FOR_PAYMENT}' is not configured for the INVOICE module")

            invoice.status_id = ready_status.status_id
            invoice.updated_by = user_id

            self.invoice_dao.create_audit_log(
                AuditLog(
                    table_name="invoice",
                    record_id=invoice.invoice_id,
                    action="INVOICE_READY_FOR_PAYMENT",
                    changed_by=user_id,
                    old_values={"status_code": current_code},
                    new_values={"status_code": STATUS_CODE_READY_FOR_PAYMENT},
                )
            )

            self.db.commit()
            self.db.refresh(invoice)
            return invoice
        except Exception:
            self.db.rollback()
            raise

    def get_payment(self, payment_id: int) -> Payment:
        payment = self.payment_dao.get_payment_by_id(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")
        return payment

    def list_payments(
        self,
        vendor_id: Optional[int] = None,
        status_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Payment]:
        return self.payment_dao.get_all_payments(vendor_id, status_id, skip, limit)

    def update_status(
        self,
        payment_id: int,
        status_code: str,
        payment_date: Optional[datetime.date],
        reference_number: Optional[str],
        user_id: str,
    ) -> Payment:
        try:
            payment = self.payment_dao.get_payment_by_id(payment_id)
            if payment is None:
                raise ValueError(f"Payment {payment_id} not found")

            current_code = self._status_code(payment)

            allowed_next = _ALLOWED_TRANSITIONS.get(current_code, set())
            if status_code not in allowed_next:
                raise ValueError(
                    f"Cannot transition payment {payment_id} from '{current_code}' to '{status_code}'"
                )

            target_status = self.payment_dao.get_status_by_module_code(PAYMENT_STATUS_MODULE, status_code)
            if target_status is None:
                raise ValueError(f"Status '{status_code}' is not configured for the PAYMENT module")

            if status_code == STATUS_CODE_CLEARED:
                for allocation in payment.payment_invoice:
                    invoice = self.invoice_dao.get_invoice_by_id_locked(allocation.invoice_id)
                    if invoice is None:
                        continue
                    invoice_status_before = invoice.status.status_code if invoice.status else None
                    invoice.amount_paid = invoice.amount_paid + allocation.allocated_amount

                    if invoice.amount_paid >= self._net_payable(invoice):
                        new_status_code = STATUS_CODE_PAID
                    else:
                        new_status_code = STATUS_CODE_PARTIALLY_PAID
                    new_status = self.invoice_dao.get_status_by_code(new_status_code)
                    if new_status is not None:
                        invoice.status_id = new_status.status_id
                    invoice.updated_by = user_id

                    # Same reasoning as create_payment's per-invoice entry below — this is the
                    # one event that actually changes the invoice itself (amount_paid/status),
                    # so it belongs on that invoice's own Activity view, not just the payment's.
                    self.invoice_dao.create_audit_log(
                        AuditLog(
                            table_name="invoice",
                            record_id=allocation.invoice_id,
                            action="INVOICE_PAYMENT_CLEARED",
                            changed_by=user_id,
                            old_values={"status_code": invoice_status_before},
                            new_values={
                                "status_code": new_status_code,
                                "payment_id": payment.payment_id,
                                "allocated_amount": str(allocation.allocated_amount),
                                "amount_paid": str(invoice.amount_paid),
                            },
                        )
                    )

                payment.payment_date = payment_date or datetime.date.today()

            elif status_code in (STATUS_CODE_SENT, STATUS_CODE_FAILED):
                # Neither moves any money (see module docstring — SCHEDULED/SENT allocations are
                # only reserved) or changes the invoice's own status/amount_paid, but "sent to
                # the bank" and "this attempt failed" are still real invoice-relevant history.
                action = "INVOICE_PAYMENT_SENT" if status_code == STATUS_CODE_SENT else "INVOICE_PAYMENT_FAILED"
                for allocation in payment.payment_invoice:
                    self.invoice_dao.create_audit_log(
                        AuditLog(
                            table_name="invoice",
                            record_id=allocation.invoice_id,
                            action=action,
                            changed_by=user_id,
                            new_values={
                                "payment_id": payment.payment_id,
                                "allocated_amount": str(allocation.allocated_amount),
                            },
                        )
                    )

            if reference_number is not None:
                payment.reference_number = reference_number

            payment.status_id = target_status.status_id
            payment.updated_by = user_id

            self.payment_dao.create_audit_log(
                AuditLog(
                    table_name="payment",
                    record_id=payment.payment_id,
                    action="STATUS_CHANGE",
                    changed_by=user_id,
                    old_values={"status_code": current_code},
                    new_values={"status_code": status_code},
                )
            )

            self.db.commit()
            self.db.refresh(payment)
            return payment
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _status_code(payment: Payment) -> Optional[str]:
        return payment.status.status_code if payment.status else None
