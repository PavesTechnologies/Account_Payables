# Backend/Data_Access_Layer/dao/payment_dao.py
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice

PAYMENT_STATUS_MODULE = "PAYMENT"
PAYMENT_PENDING_CODES = ("SCHEDULED", "SENT")


class PaymentDAO:
    def __init__(self, db):
        self.db = db

    def create_payment(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        return payment

    def create_payment_invoice(self, allocation: PaymentInvoice) -> PaymentInvoice:
        self.db.add(allocation)
        self.db.flush()
        return allocation

    def get_payment_by_id(self, payment_id: int) -> Optional[Payment]:
        return (
            self.db.query(Payment)
            .options(selectinload(Payment.payment_invoice))
            .filter(Payment.payment_id == payment_id)
            .first()
        )

    def get_all_payments(
        self,
        vendor_id: Optional[int] = None,
        status_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Payment]:

        query = self.db.query(Payment).options(selectinload(Payment.payment_invoice))

        if vendor_id is not None:
            query = query.filter(Payment.vendor_id == vendor_id)
        if status_id is not None:
            query = query.filter(Payment.status_id == status_id)

        return (
            query.order_by(Payment.payment_id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_pending_committed_amount_for_invoice(self, invoice_id: int) -> Decimal:
        """Sum of allocated_amount for this invoice across payments still
        SCHEDULED or SENT (not yet CLEARED, not FAILED). This is the amount
        "reserved" by in-flight payments that hasn't yet been folded into
        invoice.amount_paid (that only happens on CLEARED) — subtracting it
        from net_amount - amount_paid prevents the same balance being
        allocated to two payments at once."""
        result = (
            self.db.query(func.coalesce(func.sum(PaymentInvoice.allocated_amount), 0))
            .join(Payment, PaymentInvoice.payment_id == Payment.payment_id)
            .join(StatusMaster, Payment.status_id == StatusMaster.status_id)
            .filter(
                PaymentInvoice.invoice_id == invoice_id,
                StatusMaster.status_code.in_(PAYMENT_PENDING_CODES),
            )
            .scalar()
        )
        return Decimal(result or 0)

    def get_status_by_module_code(
        self,
        module_name: str,
        status_code: str,
    ) -> Optional[StatusMaster]:

        return (
            self.db.query(StatusMaster)
            .filter(
                StatusMaster.module_name == module_name,
                StatusMaster.status_code == status_code,
            )
            .first()
        )

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
