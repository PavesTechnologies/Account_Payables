# Backend/Data_Access_Layer/dao/dashboard_dao.py
"""Aggregate (GROUP BY) queries for the AP dashboard. Every method returns
small grouped rows - nothing here loads invoices/PRs/vendors into Python to be
counted. Status codes are the existing ap.status_master codes; nothing is
re-defined. DashboardService decides which of these a user may receive.
"""
import datetime
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import and_, case, func, literal, or_

from Backend.Data_Access_Layer.models.approval import (
    InvoiceApproval,
    InvoiceApprovalStep,
    InvoiceApprovalStepApprover,
)
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice
from Backend.Data_Access_Layer.models.purchase import PurchaseRequisition
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder
from Backend.Data_Access_Layer.models.rfq import RFQ
from Backend.Data_Access_Layer.models.tds import InvoiceTds, InvoiceTdsTracking
from Backend.Data_Access_Layer.models.vendor import Vendor
from Backend.Data_Access_Layer.models.vendor_onboarding import VendorOnboardingRequest

_ZERO = Decimal("0")

# TDS withheld on an invoice - the SQL form of tds_determination_service.
# compute_payable_amount (net_amount - tds_amount when tds_applicable).
_TDS_WITHHELD = case(
    (InvoiceTds.tds_applicable.is_(True), func.coalesce(InvoiceTds.tds_amount, 0)),
    else_=0,
)


class DashboardDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Status master
    # =====================================================

    def status_labels(self, modules: Iterable[str]) -> dict:
        """{(module, code): (status_name, display_order)}"""
        rows = (
            self.db.query(StatusMaster.module_name, StatusMaster.status_code, StatusMaster.status_name, StatusMaster.display_order)
            .filter(StatusMaster.module_name.in_(list(modules)))
            .all()
        )
        return {(m, c): (n, o) for m, c, n, o in rows}

    # =====================================================
    # Invoices
    # =====================================================

    def invoice_status_totals(self, date_from: Optional[datetime.date] = None, date_to: Optional[datetime.date] = None) -> List[tuple]:
        """Per (status_code, currency_code): count, net_amount, amount_paid,
        TDS withheld. Optional invoice_date range."""
        query = (
            self.db.query(
                StatusMaster.status_code,
                Currency.currency_code,
                Currency.symbol,
                func.count(Invoice.invoice_id),
                func.coalesce(func.sum(Invoice.net_amount), 0),
                func.coalesce(func.sum(Invoice.amount_paid), 0),
                func.coalesce(func.sum(_TDS_WITHHELD), 0),
            )
            .select_from(Invoice)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .outerjoin(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
        )
        if date_from is not None:
            query = query.filter(Invoice.invoice_date >= date_from)
        if date_to is not None:
            query = query.filter(Invoice.invoice_date <= date_to)
        return query.group_by(StatusMaster.status_code, Currency.currency_code, Currency.symbol).all()

    def pending_payment_allocations(self, invoice_statuses: Iterable[str]) -> List[tuple]:
        """Per currency: amount reserved by SCHEDULED/SENT payments on invoices
        in these statuses (not yet in amount_paid - see payment_service)."""
        invoice_status = StatusMaster
        rows = (
            self.db.query(Currency.currency_code, func.coalesce(func.sum(PaymentInvoice.allocated_amount), 0))
            .select_from(PaymentInvoice)
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(Invoice, Invoice.invoice_id == PaymentInvoice.invoice_id)
            .join(invoice_status, invoice_status.status_id == Invoice.status_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .filter(
                invoice_status.status_code.in_(list(invoice_statuses)),
                Payment.status_id.in_(
                    self.db.query(StatusMaster.status_id).filter(
                        StatusMaster.module_name == "PAYMENT", StatusMaster.status_code.in_(("SCHEDULED", "SENT"))
                    )
                ),
            )
            .group_by(Currency.currency_code)
            .all()
        )
        return rows

    def payment_status_counts(self) -> List[tuple]:
        return (
            self.db.query(StatusMaster.status_code, func.count(Payment.payment_id))
            .select_from(Payment)
            .outerjoin(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .group_by(StatusMaster.status_code)
            .all()
        )

    def cleared_payments_total(self, date_from, date_to) -> List[tuple]:
        """Per currency: CLEARED payment allocations with payment_date in range."""
        paid_on = func.coalesce(Payment.payment_date, Payment.scheduled_date)
        return (
            self.db.query(Currency.currency_code, Currency.symbol, func.coalesce(func.sum(PaymentInvoice.allocated_amount), 0))
            .select_from(PaymentInvoice)
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .outerjoin(Currency, Currency.currency_id == Payment.currency_id)
            .filter(StatusMaster.status_code == "CLEARED", paid_on >= date_from, paid_on <= date_to)
            .group_by(Currency.currency_code, Currency.symbol)
            .all()
        )

    def approvals_pending_for_user(self, user_uuid) -> int:
        """Invoices whose CURRENT approval step lists this user as a still-
        pending approver - the same assignment InvoiceApprovalService.
        _require_assigned_approver checks before approve/reject."""
        if user_uuid is None:
            return 0
        return (
            self.db.query(func.count(func.distinct(InvoiceApproval.invoice_id)))
            .select_from(InvoiceApprovalStepApprover)
            .join(InvoiceApprovalStep, InvoiceApprovalStep.id == InvoiceApprovalStepApprover.approval_step_id)
            .join(InvoiceApproval, InvoiceApproval.invoice_approval_id == InvoiceApprovalStep.invoice_approval_id)
            .filter(
                InvoiceApprovalStepApprover.user_uuid == user_uuid,
                InvoiceApprovalStepApprover.status == "PENDING",
                InvoiceApprovalStep.status == "PENDING",
                InvoiceApproval.status == "IN_PROGRESS",
            )
            .scalar()
            or 0
        )

    # =====================================================
    # TDS
    # =====================================================

    def tds_determination_totals(self) -> List[tuple]:
        """Per (determination_status, tds_applicable, currency): count, TDS amount."""
        return (
            self.db.query(
                InvoiceTds.determination_status,
                InvoiceTds.tds_applicable,
                Currency.currency_code,
                Currency.symbol,
                func.count(InvoiceTds.id),
                func.coalesce(func.sum(InvoiceTds.tds_amount), 0),
            )
            .select_from(InvoiceTds)
            .join(Invoice, Invoice.invoice_id == InvoiceTds.invoice_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .group_by(InvoiceTds.determination_status, InvoiceTds.tds_applicable, Currency.currency_code, Currency.symbol)
            .all()
        )

    def tds_determination_incomplete_count(self, invoice_statuses: Iterable[str]) -> int:
        """Invoices in these statuses whose TDS determination is missing or
        incomplete - the SQL form of tds_determination_service.
        tds_determination_problem (what blocks send-for-approval)."""
        incomplete = or_(
            InvoiceTds.id.is_(None),
            InvoiceTds.determination_status.notin_(("DETERMINED", "VERIFIED")),
            InvoiceTds.payment_nature_id.is_(None),
            and_(InvoiceTds.tds_rule_id.isnot(None), InvoiceTds.tds_rate_rule_id.is_(None)),
        )
        return (
            self.db.query(func.count(Invoice.invoice_id))
            .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .outerjoin(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .filter(StatusMaster.status_code.in_(list(invoice_statuses)), incomplete)
            .scalar()
            or 0
        )

    def tds_verification_pending_count(self) -> int:
        """Complete determinations not yet VERIFIED (what Finance verifies)."""
        return (
            self.db.query(func.count(InvoiceTds.id))
            .filter(
                InvoiceTds.determination_status == "DETERMINED",
                InvoiceTds.payment_nature_id.isnot(None),
                or_(InvoiceTds.tds_rule_id.is_(None), InvoiceTds.tds_rate_rule_id.isnot(None)),
            )
            .scalar()
            or 0
        )

    def approved_awaiting_ready_count(self) -> int:
        """APPROVED invoices with VERIFIED TDS - can be marked Ready for Payment."""
        return (
            self.db.query(func.count(Invoice.invoice_id))
            .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .join(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .filter(StatusMaster.status_code == "APPROVED", InvoiceTds.determination_status == "VERIFIED")
            .scalar()
            or 0
        )

    def tds_tracking_status_counts(self) -> List[tuple]:
        """Verified, TDS-applicable invoices per tracking status (no tracking
        row = TDS_PENDING, as in TdsTrackingService)."""
        status = func.coalesce(InvoiceTdsTracking.tracking_status, literal("TDS_PENDING"))
        return (
            self.db.query(status, func.count(InvoiceTds.id))
            .select_from(InvoiceTds)
            .outerjoin(InvoiceTdsTracking, InvoiceTdsTracking.invoice_id == InvoiceTds.invoice_id)
            .filter(InvoiceTds.tds_applicable.is_(True), InvoiceTds.determination_status == "VERIFIED")
            .group_by(status)
            .all()
        )

    # =====================================================
    # Trends
    # =====================================================

    def invoice_trend(self, bucket: str, date_from, date_to) -> List[tuple]:
        """Per (period, currency): invoice count, net_amount, TDS withheld - by invoice_date."""
        period = func.date_trunc(bucket, Invoice.invoice_date)
        return (
            self.db.query(
                period,
                Currency.currency_code,
                func.count(Invoice.invoice_id),
                func.coalesce(func.sum(Invoice.net_amount), 0),
                func.coalesce(func.sum(_TDS_WITHHELD), 0),
            )
            .select_from(Invoice)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .outerjoin(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .filter(Invoice.invoice_date >= date_from, Invoice.invoice_date <= date_to)
            .group_by(period, Currency.currency_code)
            .all()
        )

    def payment_trend(self, bucket: str, date_from, date_to) -> List[tuple]:
        """Per (period, currency): CLEARED payment allocations - by payment_date."""
        paid_on = func.coalesce(Payment.payment_date, Payment.scheduled_date)
        period = func.date_trunc(bucket, paid_on)
        return (
            self.db.query(period, Currency.currency_code, func.coalesce(func.sum(PaymentInvoice.allocated_amount), 0))
            .select_from(PaymentInvoice)
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .outerjoin(Currency, Currency.currency_id == Payment.currency_id)
            .filter(StatusMaster.status_code == "CLEARED", paid_on >= date_from, paid_on <= date_to)
            .group_by(period, Currency.currency_code)
            .all()
        )

    # =====================================================
    # Procurement
    # =====================================================

    def pr_status_counts(self, user_id: Optional[str]) -> List[tuple]:
        """Per (status_code, is_mine): count. is_mine = created_by is the caller."""
        mine = case((PurchaseRequisition.created_by == (user_id or ""), True), else_=False)
        return (
            self.db.query(StatusMaster.status_code, mine, func.count(PurchaseRequisition.id))
            .select_from(PurchaseRequisition)
            .outerjoin(StatusMaster, StatusMaster.status_id == PurchaseRequisition.status_id)
            .group_by(StatusMaster.status_code, mine)
            .all()
        )

    def pr_vendor_selected_awaiting_po_count(self) -> int:
        """PRs in VENDOR_SELECTION with a vendor already selected - next step is PO generation."""
        return (
            self.db.query(func.count(PurchaseRequisition.id))
            .join(StatusMaster, StatusMaster.status_id == PurchaseRequisition.status_id)
            .filter(StatusMaster.status_code == "VENDOR_SELECTION", PurchaseRequisition.selected_vendor_id.isnot(None))
            .scalar()
            or 0
        )

    def rfq_status_counts(self) -> List[tuple]:
        return (
            self.db.query(StatusMaster.status_code, func.count(RFQ.id))
            .select_from(RFQ)
            .outerjoin(StatusMaster, StatusMaster.status_id == RFQ.status_id)
            .group_by(StatusMaster.status_code)
            .all()
        )

    def po_status_counts(self) -> List[tuple]:
        return (
            self.db.query(StatusMaster.status_code, func.count(PurchaseOrder.po_id))
            .select_from(PurchaseOrder)
            .outerjoin(StatusMaster, StatusMaster.status_id == PurchaseOrder.status_id)
            .group_by(StatusMaster.status_code)
            .all()
        )

    # =====================================================
    # Vendors
    # =====================================================

    def vendor_status_counts(self) -> List[tuple]:
        return (
            self.db.query(StatusMaster.status_code, func.count(Vendor.vendor_id))
            .select_from(Vendor)
            .outerjoin(StatusMaster, StatusMaster.status_id == Vendor.status_id)
            .group_by(StatusMaster.status_code)
            .all()
        )

    def onboarding_status_counts(self, user_id: Optional[str]) -> List[tuple]:
        """Per (status_code, assigned_to_me, unassigned): count."""
        mine = case((VendorOnboardingRequest.assigned_to == (user_id or ""), True), else_=False)
        unassigned = case((VendorOnboardingRequest.assigned_to.is_(None), True), else_=False)
        return (
            self.db.query(StatusMaster.status_code, mine, unassigned, func.count(VendorOnboardingRequest.id))
            .select_from(VendorOnboardingRequest)
            .outerjoin(StatusMaster, StatusMaster.status_id == VendorOnboardingRequest.status_id)
            .group_by(StatusMaster.status_code, mine, unassigned)
            .all()
        )

    # =====================================================
    # Recent activity (ap.audit_log - the existing activity source)
    # =====================================================

    def _audit_query(self, table_actions: dict, date_from, date_to):
        conditions = [and_(AuditLog.table_name == t, AuditLog.action.in_(list(a))) for t, a in table_actions.items()]
        start = datetime.datetime.combine(date_from, datetime.time.min)
        end = datetime.datetime.combine(date_to, datetime.time.max)
        return self.db.query(AuditLog).filter(or_(*conditions), AuditLog.changed_at >= start, AuditLog.changed_at <= end)

    def recent_audit(self, table_actions: dict, date_from, date_to, limit: int) -> List[AuditLog]:
        """Latest audit rows whose (table_name, action) is in table_actions
        ({table_name: [actions]}) within [date_from, date_to]."""
        if not table_actions:
            return []
        return (
            self._audit_query(table_actions, date_from, date_to)
            .order_by(AuditLog.changed_at.desc(), AuditLog.audit_log_id.desc())
            .limit(limit)
            .all()
        )

    def search_audit(self, table_actions: dict, date_from, date_to, search: Optional[str],
                     matched_actions: Iterable[str], offset: int, limit: int):
        """Paged recent_audit with an optional free-text search over the
        record's reference (invoice number / PR number / vendor name) plus
        any action whose label matched (matched_actions, resolved by the
        caller). Returns (rows, total)."""
        if not table_actions:
            return [], 0
        query = self._audit_query(table_actions, date_from, date_to)
        if search:
            pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = (
                query
                .outerjoin(Invoice, and_(AuditLog.table_name == "invoice", Invoice.invoice_id == AuditLog.record_id))
                .outerjoin(PurchaseRequisition, and_(AuditLog.table_name == "purchase_requisition",
                                                     PurchaseRequisition.id == AuditLog.record_id))
                .outerjoin(Vendor, and_(AuditLog.table_name == "vendor", Vendor.vendor_id == AuditLog.record_id))
                .filter(or_(
                    Invoice.invoice_number.ilike(pattern, escape="\\"),
                    PurchaseRequisition.pr_number.ilike(pattern, escape="\\"),
                    Vendor.vendor_name.ilike(pattern, escape="\\"),
                    AuditLog.action.in_(list(matched_actions)),
                ))
            )
        total = query.order_by(None).count()
        rows = (
            query.order_by(AuditLog.changed_at.desc(), AuditLog.audit_log_id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, total

    def invoice_numbers(self, ids: Iterable[int]) -> dict:
        ids = list(set(ids))
        if not ids:
            return {}
        return dict(self.db.query(Invoice.invoice_id, Invoice.invoice_number).filter(Invoice.invoice_id.in_(ids)).all())

    def pr_numbers(self, ids: Iterable[int]) -> dict:
        ids = list(set(ids))
        if not ids:
            return {}
        return dict(self.db.query(PurchaseRequisition.id, PurchaseRequisition.pr_number).filter(PurchaseRequisition.id.in_(ids)).all())

    def vendor_names(self, ids: Iterable[int]) -> dict:
        ids = list(set(ids))
        if not ids:
            return {}
        return dict(self.db.query(Vendor.vendor_id, Vendor.vendor_name).filter(Vendor.vendor_id.in_(ids)).all())
