# Backend/Data_Access_Layer/dao/role_dashboard_dao.py
"""Queries behind the role dashboards (Approvals, My work, Management) -
Business_Layer/services/role_dashboard_service.py. Plain tuples only; the
service derives every figure."""
import datetime
from typing import List, Optional, Sequence

from sqlalchemy import func

from Backend.Data_Access_Layer.models.approval import (
    InvoiceApproval,
    InvoiceApprovalStep,
    InvoiceApprovalStepApprover,
)
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice
from Backend.Data_Access_Layer.models.purchase import Department
from Backend.Data_Access_Layer.models.tds import InvoiceTds
from Backend.Data_Access_Layer.models.vendor import Vendor


class RoleDashboardDAO:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------
    def approver_queue(self, user_uuid) -> List[tuple]:
        """Invoices whose current step lists this user as a pending approver (the same assignment
        InvoiceApprovalService checks before approve/reject):
        (Invoice, vendor_name, department_name, level_number, step_started_at, currency_code)."""
        if user_uuid is None:
            return []
        return (
            self.db.query(Invoice, Vendor.vendor_name, Department.name, InvoiceApprovalStep.level_number,
                          InvoiceApprovalStep.started_at, Currency.currency_code)
            .select_from(InvoiceApprovalStepApprover)
            .join(InvoiceApprovalStep, InvoiceApprovalStep.id == InvoiceApprovalStepApprover.approval_step_id)
            .join(InvoiceApproval, InvoiceApproval.invoice_approval_id == InvoiceApprovalStep.invoice_approval_id)
            .join(Invoice, Invoice.invoice_id == InvoiceApproval.invoice_id)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(Department, Department.id == Invoice.department_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .filter(
                InvoiceApprovalStepApprover.user_uuid == user_uuid,
                InvoiceApprovalStepApprover.status == "PENDING",
                InvoiceApprovalStep.status == "PENDING",
                InvoiceApproval.status == "IN_PROGRESS",
            )
            .order_by(InvoiceApprovalStep.started_at.asc().nullslast())
            .all()
        )

    def approver_decisions(self, user_uuid, since: datetime.datetime) -> List[tuple]:
        """This user's decisions since a date: (decided_at, approver_status, step_status,
        step_started_at, invoice_id, net_amount, currency_code). A send-back is recorded as an
        approver REJECTED on a step that ended CANCELLED."""
        if user_uuid is None:
            return []
        return (
            self.db.query(InvoiceApprovalStepApprover.decided_at, InvoiceApprovalStepApprover.status,
                          InvoiceApprovalStep.status, InvoiceApprovalStep.started_at, Invoice.invoice_id,
                          Invoice.net_amount, Currency.currency_code)
            .join(InvoiceApprovalStep, InvoiceApprovalStep.id == InvoiceApprovalStepApprover.approval_step_id)
            .join(InvoiceApproval, InvoiceApproval.invoice_approval_id == InvoiceApprovalStep.invoice_approval_id)
            .join(Invoice, Invoice.invoice_id == InvoiceApproval.invoice_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .filter(
                InvoiceApprovalStepApprover.user_uuid == user_uuid,
                InvoiceApprovalStepApprover.decided_at.isnot(None),
                InvoiceApprovalStepApprover.decided_at >= since,
                InvoiceApprovalStepApprover.status.in_(("APPROVED", "REJECTED")),
            )
            .all()
        )

    # ------------------------------------------------------------------
    # Management: bottlenecks and cycle times
    # ------------------------------------------------------------------
    def pending_steps(self) -> List[tuple]:
        """Every approval step currently waiting for a decision, org-wide:
        (level_number, department_name, step_started_at, net_amount, currency_code)."""
        return (
            self.db.query(InvoiceApprovalStep.level_number, Department.name, InvoiceApprovalStep.started_at,
                          Invoice.net_amount, Currency.currency_code)
            .join(InvoiceApproval, InvoiceApproval.invoice_approval_id == InvoiceApprovalStep.invoice_approval_id)
            .join(Invoice, Invoice.invoice_id == InvoiceApproval.invoice_id)
            .outerjoin(Department, Department.id == Invoice.department_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .filter(InvoiceApprovalStep.status == "PENDING", InvoiceApproval.status == "IN_PROGRESS")
            .all()
        )

    def cycle_rows(self, since: datetime.datetime) -> List[tuple]:
        """Invoices received since a date: (invoice_id, created_at, approval_completed_at,
        first_cleared_payment_date). Approval and payment columns are NULL until they happen."""
        approved = (
            self.db.query(InvoiceApproval.invoice_id.label("invoice_id"),
                          func.max(InvoiceApproval.completed_at).label("approved_at"))
            .filter(InvoiceApproval.status == "APPROVED")
            .group_by(InvoiceApproval.invoice_id)
            .subquery()
        )
        paid_on = func.coalesce(Payment.payment_date, Payment.scheduled_date)
        paid = (
            self.db.query(PaymentInvoice.invoice_id.label("invoice_id"), func.min(paid_on).label("paid_on"))
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .filter(StatusMaster.status_code == "CLEARED")
            .group_by(PaymentInvoice.invoice_id)
            .subquery()
        )
        return (
            self.db.query(Invoice.invoice_id, Invoice.created_at, approved.c.approved_at, paid.c.paid_on)
            .outerjoin(approved, approved.c.invoice_id == Invoice.invoice_id)
            .outerjoin(paid, paid.c.invoice_id == Invoice.invoice_id)
            .filter(Invoice.created_at >= since)
            .all()
        )

    # ------------------------------------------------------------------
    # My work (AP Executive)
    # ------------------------------------------------------------------
    def work_queue(self, statuses: Sequence[str]) -> List[tuple]:
        """(Invoice, vendor_name, status_code, InvoiceTds|None, currency_code) for intake-stage invoices."""
        return (
            self.db.query(Invoice, Vendor.vendor_name, StatusMaster.status_code, InvoiceTds, Currency.currency_code)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .outerjoin(InvoiceTds, InvoiceTds.invoice_id == Invoice.invoice_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .filter(StatusMaster.status_code.in_(list(statuses)))
            .order_by(Invoice.created_at.asc())
            .all()
        )

    def intake_rows(self, since: datetime.datetime) -> List[tuple]:
        """(created_at, created_by, status_code) of invoices received since a date."""
        return (
            self.db.query(Invoice.created_at, Invoice.created_by, StatusMaster.status_code)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .filter(Invoice.created_at >= since)
            .all()
        )

    def status_counts(self) -> List[tuple]:
        return (
            self.db.query(StatusMaster.status_code, func.count(Invoice.invoice_id))
            .select_from(Invoice)
            .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .group_by(StatusMaster.status_code)
            .all()
        )
