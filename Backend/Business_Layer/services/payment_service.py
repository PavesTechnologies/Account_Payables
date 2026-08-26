# Backend/Business_Layer/services/payment_service.py
"""Payment creation, allocation, and status lifecycle on top of the
existing Payment/PaymentInvoice schema (no schema changes).

Lifecycle (ap.status_master, module=PAYMENT): SCHEDULED -> SENT -> CLEARED,
or SCHEDULED/SENT -> FAILED. invoice.amount_paid is only incremented when
a payment reaches CLEARED — SCHEDULED/SENT allocations are "reserved"
(see PaymentDAO.get_pending_committed_amount_for_invoice) but don't move
money yet, so a FAILED payment never has to be unwound.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import List, Optional

from Backend.API_Layer.interface.payment_interface import PaymentCreateRequest
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.payment_dao import PaymentDAO
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
STATUS_CODE_PARTIALLY_PAID = "PARTIALLY_PAID"
STATUS_CODE_PAID = "PAID"

_ALLOWED_TRANSITIONS = {
    STATUS_CODE_SCHEDULED: {STATUS_CODE_SENT, STATUS_CODE_FAILED},
    STATUS_CODE_SENT: {STATUS_CODE_CLEARED, STATUS_CODE_FAILED},
    STATUS_CODE_CLEARED: set(),
    STATUS_CODE_FAILED: set(),
}

_INVOICE_PAYABLE_STATUSES = {STATUS_CODE_APPROVED, STATUS_CODE_PARTIALLY_PAID}


class PaymentService:
    def __init__(self, db):
        self.db = db
        self.payment_dao = PaymentDAO(db)
        self.invoice_dao = InvoiceDAO(db)
        self.vendor_dao = VendorDAO(db)

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
                remaining = invoice.net_amount - invoice.amount_paid - pending_committed
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

            self.db.commit()
            self.db.refresh(payment)
            return payment
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
                    invoice.amount_paid = invoice.amount_paid + allocation.allocated_amount

                    if invoice.amount_paid >= invoice.net_amount:
                        new_status = self.invoice_dao.get_status_by_code(STATUS_CODE_PAID)
                    else:
                        new_status = self.invoice_dao.get_status_by_code(STATUS_CODE_PARTIALLY_PAID)
                    if new_status is not None:
                        invoice.status_id = new_status.status_id
                    invoice.updated_by = user_id

                payment.payment_date = payment_date or datetime.date.today()

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
