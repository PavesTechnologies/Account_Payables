# Backend/Data_Access_Layer/dao/ap_reporting_dao.py
"""Row-level queries behind the Finance dashboard and AP reports
(Business_Layer/services/ap_reporting_service.py). Each method is one query
returning plain tuples; amounts are derived in the service with the same rules
as payment_service / dashboard_service so every screen agrees."""
import datetime
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import func, or_

from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
from Backend.Data_Access_Layer.models.payment import Payment, PaymentDocument, PaymentInvoice
from Backend.Data_Access_Layer.models.payment_terms import InvoicePaymentTerm
from Backend.Data_Access_Layer.models.purchase import Department, PurchaseCategory
from Backend.Data_Access_Layer.models.tds import InvoiceTds, InvoiceTdsTracking, TdsPaymentNature
from Backend.Data_Access_Layer.models.master import TaxRule
from Backend.Data_Access_Layer.models.vendor import Vendor

PENDING_PAYMENT_CODES = ("SCHEDULED", "SENT")
CLEARED_PAYMENT_CODE = "CLEARED"


class APReportingDAO:
    def __init__(self, db):
        self.db = db

    def invoice_rows(
        self,
        statuses: Optional[Sequence[str]] = None,
        invoice_from: Optional[datetime.date] = None,
        invoice_to: Optional[datetime.date] = None,
        vendor_id: Optional[int] = None,
        department_id: Optional[int] = None,
        tds_only: bool = False,
    ) -> List[tuple]:
        """(Invoice, vendor_name, status_code, status_name, currency_code, symbol, InvoiceTds|None,
        InvoicePaymentTerm|None, InvoiceTdsTracking|None, department_name, category_name, nature_code,
        section)"""
        query = (
            self.db.query(
                Invoice,
                Vendor.vendor_name,
                StatusMaster.status_code,
                StatusMaster.status_name,
                Currency.currency_code,
                Currency.symbol,
                InvoiceTds,
                InvoicePaymentTerm,
                InvoiceTdsTracking,
                Department.name,
                PurchaseCategory.name,
                TdsPaymentNature.code,
                TaxRule.old_section,
            )
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .outerjoin(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .outerjoin(InvoicePaymentTerm, InvoicePaymentTerm.invoice_id == Invoice.invoice_id)
            .outerjoin(InvoiceTdsTracking, InvoiceTdsTracking.invoice_id == Invoice.invoice_id)
            .outerjoin(Department, Department.id == Invoice.department_id)
            .outerjoin(PurchaseCategory, PurchaseCategory.id == Invoice.purchase_category_id)
            .outerjoin(TdsPaymentNature, TdsPaymentNature.id == InvoiceTds.payment_nature_id)
            .outerjoin(TaxRule, TaxRule.tax_rule_id == InvoiceTds.tds_rule_id)
        )
        if statuses:
            query = query.filter(StatusMaster.status_code.in_(list(statuses)))
        if invoice_from is not None:
            query = query.filter(Invoice.invoice_date >= invoice_from)
        if invoice_to is not None:
            query = query.filter(Invoice.invoice_date <= invoice_to)
        if vendor_id is not None:
            query = query.filter(Invoice.vendor_id == vendor_id)
        if department_id is not None:
            query = query.filter(Invoice.department_id == department_id)
        if tds_only:
            query = query.filter(InvoiceTds.tds_applicable.is_(True))
        return query.order_by(Invoice.due_date.asc(), Invoice.invoice_id.asc()).all()

    def reserved_by_invoice(self, invoice_ids: Iterable[int]) -> dict:
        """{invoice_id: amount reserved by SCHEDULED/SENT payments} (not yet in amount_paid)."""
        ids = list(invoice_ids)
        if not ids:
            return {}
        rows = (
            self.db.query(PaymentInvoice.invoice_id, func.coalesce(func.sum(PaymentInvoice.allocated_amount), 0))
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .filter(PaymentInvoice.invoice_id.in_(ids), StatusMaster.status_code.in_(PENDING_PAYMENT_CODES))
            .group_by(PaymentInvoice.invoice_id)
            .all()
        )
        return {invoice_id: amount for invoice_id, amount in rows}

    def last_cleared_payment_date_by_invoice(self, invoice_ids: Iterable[int]) -> dict:
        ids = list(invoice_ids)
        if not ids:
            return {}
        paid_on = func.coalesce(Payment.payment_date, Payment.scheduled_date)
        rows = (
            self.db.query(PaymentInvoice.invoice_id, func.max(paid_on))
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .filter(PaymentInvoice.invoice_id.in_(ids), StatusMaster.status_code == CLEARED_PAYMENT_CODE)
            .group_by(PaymentInvoice.invoice_id)
            .all()
        )
        return dict(rows)

    def cleared_payment_rows(
        self,
        paid_from: Optional[datetime.date] = None,
        paid_to: Optional[datetime.date] = None,
        vendor_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[tuple]:
        """Per CLEARED allocation: (payment_id, paid_on, payment_method, reference_number, allocated_amount,
        invoice_id, invoice_number, invoice due_date, vendor_name, currency_code, symbol, receipt_count,
        invoice_date)."""
        paid_on = func.coalesce(Payment.payment_date, Payment.scheduled_date).label("paid_on")
        receipts = (
            self.db.query(PaymentDocument.payment_id, func.count(PaymentDocument.payment_document_id).label("n"))
            .group_by(PaymentDocument.payment_id)
            .subquery()
        )
        query = (
            self.db.query(
                Payment.payment_id,
                paid_on,
                Payment.payment_method,
                Payment.reference_number,
                PaymentInvoice.allocated_amount,
                Invoice.invoice_id,
                Invoice.invoice_number,
                Invoice.due_date,
                Vendor.vendor_name,
                Currency.currency_code,
                Currency.symbol,
                func.coalesce(receipts.c.n, 0),
                Invoice.invoice_date,
            )
            .select_from(PaymentInvoice)
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .join(Invoice, Invoice.invoice_id == PaymentInvoice.invoice_id)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(Currency, Currency.currency_id == Payment.currency_id)
            .outerjoin(receipts, receipts.c.payment_id == Payment.payment_id)
            .filter(StatusMaster.status_code == CLEARED_PAYMENT_CODE)
        )
        if paid_from is not None:
            query = query.filter(func.coalesce(Payment.payment_date, Payment.scheduled_date) >= paid_from)
        if paid_to is not None:
            query = query.filter(func.coalesce(Payment.payment_date, Payment.scheduled_date) <= paid_to)
        if vendor_id is not None:
            query = query.filter(Invoice.vendor_id == vendor_id)
        query = query.order_by(paid_on.desc(), Payment.payment_id.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def vendor_options(self, search: Optional[str] = None, limit: int = 50) -> List[tuple]:
        query = self.db.query(Vendor.vendor_id, Vendor.vendor_name)
        if search:
            query = query.filter(or_(Vendor.vendor_name.ilike(f"%{search}%"), Vendor.vendor_code.ilike(f"%{search}%")))
        return query.order_by(Vendor.vendor_name).limit(limit).all()
