# Backend/Data_Access_Layer/dao/payment_dao.py
import datetime
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.payment import Payment, PaymentDocument, PaymentInvoice
from Backend.Data_Access_Layer.models.tds import InvoiceTds
from Backend.Data_Access_Layer.models.vendor import Vendor

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

    # =====================================================
    # Payment Management screens (invoice-centric views)
    # =====================================================

    def _invoice_list_query(self, statuses, search, vendor_id):
        query = (
            self.db.query(Invoice, Vendor.vendor_name, StatusMaster, InvoiceTds)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .outerjoin(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .options(selectinload(Invoice.currency))
        )
        if statuses:
            query = query.filter(StatusMaster.status_code.in_(statuses))
        if vendor_id is not None:
            query = query.filter(Invoice.vendor_id == vendor_id)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(Invoice.invoice_number.ilike(pattern), Vendor.vendor_name.ilike(pattern)))
        return query

    def list_invoices_for_payment(
        self,
        statuses: Sequence[str],
        search: Optional[str] = None,
        vendor_id: Optional[int] = None,
        due_from: Optional[datetime.date] = None,
        due_to: Optional[datetime.date] = None,
        overdue_as_of: Optional[datetime.date] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[list, int]:
        """(rows, total) of (Invoice, vendor_name, StatusMaster, InvoiceTds|None)
        in the given invoice statuses, oldest due date first."""
        query = self._invoice_list_query(statuses, search, vendor_id)
        if due_from is not None:
            query = query.filter(Invoice.due_date >= due_from)
        if due_to is not None:
            query = query.filter(Invoice.due_date <= due_to)
        if overdue_as_of is not None:
            query = query.filter(Invoice.due_date < overdue_as_of)
        total = query.order_by(None).count()
        rows = query.order_by(Invoice.due_date.asc(), Invoice.invoice_id.asc()).offset(offset).limit(limit).all()
        return rows, total

    def list_invoices_with_payments(
        self,
        statuses: Optional[Sequence[str]] = None,
        search: Optional[str] = None,
        vendor_id: Optional[int] = None,
        payment_mode: Optional[str] = None,
        paid_from: Optional[datetime.date] = None,
        paid_to: Optional[datetime.date] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[list, int]:
        """(rows, total) of invoices that have at least one payment allocation
        matching the payment filters, most recently paid first."""
        payment_filter = (
            self.db.query(PaymentInvoice.invoice_id.label("invoice_id"), func.max(func.coalesce(Payment.payment_date, Payment.scheduled_date)).label("last_date"))
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
        )
        if payment_mode:
            payment_filter = payment_filter.filter(Payment.payment_method == payment_mode)
        if paid_from is not None:
            payment_filter = payment_filter.filter(func.coalesce(Payment.payment_date, Payment.scheduled_date) >= paid_from)
        if paid_to is not None:
            payment_filter = payment_filter.filter(func.coalesce(Payment.payment_date, Payment.scheduled_date) <= paid_to)
        paid = payment_filter.group_by(PaymentInvoice.invoice_id).subquery()

        query = self._invoice_list_query(statuses, search, vendor_id).join(paid, paid.c.invoice_id == Invoice.invoice_id)
        total = query.order_by(None).count()
        rows = query.order_by(paid.c.last_date.desc(), Invoice.invoice_id.desc()).offset(offset).limit(limit).all()
        return rows, total

    def get_invoice_with_context(self, invoice_id: int):
        return self._invoice_list_query(None, None, None).filter(Invoice.invoice_id == invoice_id).first()

    def get_allocations_for_invoices(self, invoice_ids: Sequence[int]) -> List[PaymentInvoice]:
        """Every payment allocation for these invoices, with the payment, its
        status and documents loaded - oldest payment first."""
        if not invoice_ids:
            return []
        return (
            self.db.query(PaymentInvoice)
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .options(
                selectinload(PaymentInvoice.payment).selectinload(Payment.status),
                selectinload(PaymentInvoice.payment).selectinload(Payment.documents),
            )
            .filter(PaymentInvoice.invoice_id.in_(list(invoice_ids)))
            .order_by(func.coalesce(Payment.payment_date, Payment.scheduled_date).asc(), Payment.payment_id.asc())
            .all()
        )

    def reference_used_for_invoice(self, invoice_id: int, reference_number: str) -> bool:
        """Same UTR/reference already recorded against THIS invoice (not FAILED).
        One bank transfer may legitimately settle several invoices, so the
        same reference on a different invoice is allowed."""
        return (
            self.db.query(Payment.payment_id)
            .join(PaymentInvoice, PaymentInvoice.payment_id == Payment.payment_id)
            .outerjoin(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .filter(
                PaymentInvoice.invoice_id == invoice_id,
                func.upper(Payment.reference_number) == reference_number.upper(),
                or_(StatusMaster.status_code.is_(None), StatusMaster.status_code != "FAILED"),
            )
            .first()
            is not None
        )

    def add_document(self, document: PaymentDocument) -> PaymentDocument:
        self.db.add(document)
        self.db.flush()
        return document

    def get_document(self, payment_id: int, document_id: int) -> Optional[PaymentDocument]:
        return (
            self.db.query(PaymentDocument)
            .filter(PaymentDocument.payment_id == payment_id, PaymentDocument.payment_document_id == document_id)
            .first()
        )
