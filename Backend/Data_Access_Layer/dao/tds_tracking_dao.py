# Backend/Data_Access_Layer/dao/tds_tracking_dao.py
"""Reads/writes for TDS Tracking (ap.invoice_tds_tracking / invoice_tds_document)
plus the TDS-applicable invoice list. DAOs add/flush only - TdsTrackingService
owns commit/rollback."""
import datetime
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster, TaxRule
from Backend.Data_Access_Layer.models.tds import (
    InvoiceTds,
    InvoiceTdsDocument,
    InvoiceTdsTracking,
    TdsPaymentNature,
)
from Backend.Data_Access_Layer.models.vendor import Vendor

TRACKING_STATUS_PENDING = "TDS_PENDING"


class TdsTrackingDAO:
    def __init__(self, db):
        self.db = db

    def _query(self):
        return (
            self.db.query(Invoice, Vendor.vendor_name, StatusMaster, InvoiceTds, TdsPaymentNature, TaxRule, InvoiceTdsTracking)
            .join(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .outerjoin(TdsPaymentNature, TdsPaymentNature.id == InvoiceTds.payment_nature_id)
            .outerjoin(TaxRule, TaxRule.tax_rule_id == InvoiceTds.tds_rule_id)
            .outerjoin(InvoiceTdsTracking, InvoiceTdsTracking.invoice_id == Invoice.invoice_id)
            .options(selectinload(Invoice.currency))
            .filter(InvoiceTds.tds_applicable.is_(True))
        )

    def list_tds_invoices(
        self,
        search: Optional[str] = None,
        tracking_statuses: Optional[Sequence[str]] = None,
        payment_nature_code: Optional[str] = None,
        determination_status: Optional[str] = None,
        invoice_statuses: Optional[Sequence[str]] = None,
        vendor_id: Optional[int] = None,
        invoice_date_from: Optional[datetime.date] = None,
        invoice_date_to: Optional[datetime.date] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[list, int]:
        query = self._query()
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(Invoice.invoice_number.ilike(pattern), Vendor.vendor_name.ilike(pattern)))
        if tracking_statuses:
            condition = InvoiceTdsTracking.tracking_status.in_(list(tracking_statuses))
            if TRACKING_STATUS_PENDING in tracking_statuses:
                condition = or_(condition, InvoiceTdsTracking.id.is_(None))
            query = query.filter(condition)
        if payment_nature_code:
            query = query.filter(TdsPaymentNature.code == payment_nature_code.strip().upper())
        if determination_status:
            query = query.filter(InvoiceTds.determination_status == determination_status.strip().upper())
        if invoice_statuses:
            query = query.filter(StatusMaster.status_code.in_(list(invoice_statuses)))
        if vendor_id is not None:
            query = query.filter(Invoice.vendor_id == vendor_id)
        if invoice_date_from is not None:
            query = query.filter(Invoice.invoice_date >= invoice_date_from)
        if invoice_date_to is not None:
            query = query.filter(Invoice.invoice_date <= invoice_date_to)
        total = query.order_by(None).count()
        rows = query.order_by(Invoice.invoice_date.desc(), Invoice.invoice_id.desc()).offset(offset).limit(limit).all()
        return rows, total

    def get_tds_invoice(self, invoice_id: int):
        """Same tuple as list_tds_invoices, or None if the invoice has no
        TDS-applicable determination."""
        return self._query().filter(Invoice.invoice_id == invoice_id).first()

    def get_tracking_locked(self, invoice_id: int) -> Optional[InvoiceTdsTracking]:
        return (
            self.db.query(InvoiceTdsTracking)
            .filter(InvoiceTdsTracking.invoice_id == invoice_id)
            .with_for_update()
            .first()
        )

    def get_tracking(self, invoice_id: int) -> Optional[InvoiceTdsTracking]:
        return (
            self.db.query(InvoiceTdsTracking)
            .options(selectinload(InvoiceTdsTracking.documents))
            .filter(InvoiceTdsTracking.invoice_id == invoice_id)
            .first()
        )

    def add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    def get_document(self, invoice_id: int, document_id: int) -> Optional[InvoiceTdsDocument]:
        return (
            self.db.query(InvoiceTdsDocument)
            .join(InvoiceTdsTracking, InvoiceTdsTracking.id == InvoiceTdsDocument.invoice_tds_tracking_id)
            .filter(InvoiceTdsTracking.invoice_id == invoice_id, InvoiceTdsDocument.id == document_id)
            .first()
        )

    def list_tds_audit(self, invoice_id: int) -> List[AuditLog]:
        return (
            self.db.query(AuditLog)
            .filter(
                AuditLog.table_name == "invoice",
                AuditLog.record_id == invoice_id,
                AuditLog.action.like("INVOICE_TDS_%"),
            )
            .order_by(AuditLog.changed_at.asc(), AuditLog.audit_log_id.asc())
            .all()
        )

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
