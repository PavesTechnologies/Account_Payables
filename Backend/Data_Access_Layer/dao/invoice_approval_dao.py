# Backend/Data_Access_Layer/dao/invoice_approval_dao.py
from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.approval import (
    InvoiceApproval,
    InvoiceApprovalStep,
    InvoiceApprovalStepApprover,
)
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import StatusMaster

INVOICE_STATUS_MODULE = "INVOICE"

_STEP_DETAIL_OPTIONS = (
    selectinload(InvoiceApproval.steps).selectinload(InvoiceApprovalStep.approvers),
)


class InvoiceApprovalDAO:
    def __init__(self, db):
        self.db = db

    # ---- invoice_approval -------------------------------------------------

    def create_invoice_approval(self, approval: InvoiceApproval) -> InvoiceApproval:
        self.db.add(approval)
        self.db.flush()
        return approval

    def get_invoice_approval_by_id(self, invoice_approval_id: int) -> Optional[InvoiceApproval]:
        return (
            self.db.query(InvoiceApproval)
            .options(*_STEP_DETAIL_OPTIONS)
            .filter(InvoiceApproval.invoice_approval_id == invoice_approval_id)
            .first()
        )

    def get_active_invoice_approval_for_invoice(self, invoice_id: int) -> Optional[InvoiceApproval]:
        """The one non-terminal approval instance for an invoice, if any -
        used both to render current status and to enforce "one active
        instance per invoice" (no DB constraint for this; see
        approval.py's InvoiceApproval docstring)."""
        return (
            self.db.query(InvoiceApproval)
            .options(*_STEP_DETAIL_OPTIONS)
            .filter(
                InvoiceApproval.invoice_id == invoice_id,
                InvoiceApproval.status.in_(["PENDING", "IN_PROGRESS"]),
            )
            .order_by(InvoiceApproval.invoice_approval_id.desc())
            .first()
        )

    def get_latest_invoice_approval_for_invoice(self, invoice_id: int) -> Optional[InvoiceApproval]:
        return (
            self.db.query(InvoiceApproval)
            .options(*_STEP_DETAIL_OPTIONS)
            .filter(InvoiceApproval.invoice_id == invoice_id)
            .order_by(InvoiceApproval.invoice_approval_id.desc())
            .first()
        )

    # ---- invoice_approval_step ---------------------------------------------

    def create_step(self, step: InvoiceApprovalStep) -> InvoiceApprovalStep:
        self.db.add(step)
        self.db.flush()
        return step

    def get_steps_for_approval(self, invoice_approval_id: int) -> List[InvoiceApprovalStep]:
        return (
            self.db.query(InvoiceApprovalStep)
            .filter(InvoiceApprovalStep.invoice_approval_id == invoice_approval_id)
            .order_by(InvoiceApprovalStep.level_number.asc())
            .all()
        )

    def get_active_step_locked(self, invoice_approval_id: int) -> Optional[InvoiceApprovalStep]:
        """Row-locks the currently actionable (PENDING) step for the
        duration of the current transaction, so two concurrent
        approve/reject calls on the same level can't both act on it."""
        return (
            self.db.query(InvoiceApprovalStep)
            .filter(
                InvoiceApprovalStep.invoice_approval_id == invoice_approval_id,
                InvoiceApprovalStep.status == "PENDING",
            )
            .with_for_update()
            .first()
        )

    # ---- invoice_approval_step_approver ------------------------------------

    def create_step_approver(self, approver: InvoiceApprovalStepApprover) -> InvoiceApprovalStepApprover:
        self.db.add(approver)
        self.db.flush()
        return approver

    def get_approvers_for_step(self, approval_step_id: int) -> List[InvoiceApprovalStepApprover]:
        return (
            self.db.query(InvoiceApprovalStepApprover)
            .filter(InvoiceApprovalStepApprover.approval_step_id == approval_step_id)
            .all()
        )

    def get_step_approver(
        self, approval_step_id: int, user_uuid
    ) -> Optional[InvoiceApprovalStepApprover]:
        return (
            self.db.query(InvoiceApprovalStepApprover)
            .filter(
                InvoiceApprovalStepApprover.approval_step_id == approval_step_id,
                InvoiceApprovalStepApprover.user_uuid == user_uuid,
            )
            .first()
        )

    # ---- shared -------------------------------------------------------------

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
