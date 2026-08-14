# Backend/Business_Layer/services/invoice_approval_service.py
"""Single-level invoice approval (approve/reject) on top of the existing
InvoiceApproval table.

Per product decision (2026-08-13): no approval_level column, no new
approval table — any authenticated user with the approve/reject action
available to them can decide. Multiple InvoiceApproval rows per
invoice_id are allowed by design (no unique constraint), so a full
append-only decision history falls out for free.
"""
from __future__ import annotations

import datetime
from typing import List

from Backend.Data_Access_Layer.dao.invoice_approval_dao import InvoiceApprovalDAO
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.models.approval import InvoiceApproval
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice

INVOICE_STATUS_MODULE = "INVOICE"
STATUS_CODE_PENDING_APPROVAL = "PENDING_APPROVAL"
STATUS_CODE_APPROVED = "APPROVED"
STATUS_CODE_REJECTED = "REJECTED"

DECISION_APPROVED = "APPROVED"
DECISION_REJECTED = "REJECTED"


class InvoiceApprovalService:
    def __init__(self, db):
        self.db = db
        self.invoice_dao = InvoiceDAO(db)
        self.approval_dao = InvoiceApprovalDAO(db)

    def _require_pending_invoice(self, invoice_id: int) -> Invoice:
        invoice = self.invoice_dao.get_invoice_by_id_locked(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")

        current_code = invoice.status.status_code if invoice.status else None
        if current_code != STATUS_CODE_PENDING_APPROVAL:
            raise ValueError(
                f"Invoice {invoice_id} is not pending approval (current status: {current_code})"
            )
        return invoice

    def approve_invoice(self, invoice_id: int, approver_name: str, comments: str | None) -> InvoiceApproval:
        try:
            invoice = self._require_pending_invoice(invoice_id)

            approved_status = self.approval_dao.get_status_by_module_code(
                INVOICE_STATUS_MODULE, STATUS_CODE_APPROVED
            )
            if approved_status is None:
                raise ValueError(f"Status '{STATUS_CODE_APPROVED}' is not configured for the INVOICE module")

            approval = InvoiceApproval(
                invoice_id=invoice.invoice_id,
                approver_name=approver_name,
                decision=DECISION_APPROVED,
                comments=comments,
                decided_at=datetime.datetime.utcnow(),
            )
            self.approval_dao.create_approval(approval)

            invoice.status_id = approved_status.status_id
            invoice.updated_by = approver_name

            self.approval_dao.create_audit_log(
                AuditLog(
                    table_name="invoice",
                    record_id=invoice.invoice_id,
                    action="APPROVE",
                    changed_by=approver_name,
                    new_values={"status_code": STATUS_CODE_APPROVED, "comments": comments},
                )
            )

            self.db.commit()
            self.db.refresh(approval)
            return approval
        except Exception:
            self.db.rollback()
            raise

    def reject_invoice(self, invoice_id: int, approver_name: str, comments: str) -> InvoiceApproval:
        try:
            invoice = self._require_pending_invoice(invoice_id)

            rejected_status = self.approval_dao.get_status_by_module_code(
                INVOICE_STATUS_MODULE, STATUS_CODE_REJECTED
            )
            if rejected_status is None:
                raise ValueError(f"Status '{STATUS_CODE_REJECTED}' is not configured for the INVOICE module")

            approval = InvoiceApproval(
                invoice_id=invoice.invoice_id,
                approver_name=approver_name,
                decision=DECISION_REJECTED,
                comments=comments,
                decided_at=datetime.datetime.utcnow(),
            )
            self.approval_dao.create_approval(approval)

            invoice.status_id = rejected_status.status_id
            invoice.updated_by = approver_name

            self.approval_dao.create_audit_log(
                AuditLog(
                    table_name="invoice",
                    record_id=invoice.invoice_id,
                    action="REJECT",
                    changed_by=approver_name,
                    new_values={"status_code": STATUS_CODE_REJECTED, "comments": comments},
                )
            )

            self.db.commit()
            self.db.refresh(approval)
            return approval
        except Exception:
            self.db.rollback()
            raise

    def get_approval_history(self, invoice_id: int) -> List[InvoiceApproval]:
        invoice = self.invoice_dao.get_invoice_by_id(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        return self.approval_dao.get_approvals_by_invoice_id(invoice_id)
