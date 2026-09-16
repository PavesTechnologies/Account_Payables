# Backend/Business_Layer/services/invoice_approval_service.py
"""Runtime engine for the policy-driven, multi-level invoice approval
workflow: send_for_approval creates a one-time snapshot of whichever
ApprovalPolicy matches the invoice (see ApprovalPolicyService.match_policy
and ApproverResolverService.resolve); approve/reject then walk that
snapshot level by level, never re-consulting the policy again (spec
section 14 - a later policy edit must never affect an already-running
approval).

Follows the same shape as ProcurementService's PR approval flow
(Backend/Business_Layer/services/procurement_service.py): plain
ValueError for every business-rule violation, no internal
try/except/rollback (the route layer owns that, exactly like
procurement_route.py), an AuditLog row per meaningful transition.
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from Backend.Data_Access_Layer.dao.approval_policy_dao import ApprovalPolicyDAO
from Backend.Data_Access_Layer.dao.invoice_approval_dao import InvoiceApprovalDAO
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.models.approval import (
    InvoiceApproval,
    InvoiceApprovalStep,
    InvoiceApprovalStepApprover,
)
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService
from Backend.Business_Layer.services.approver_resolver_service import ApproverResolverService

STATUS_CODE_PENDING_APPROVAL = "PENDING_APPROVAL"
STATUS_CODE_APPROVED = "APPROVED"
STATUS_CODE_REJECTED = "REJECTED"


class InvoiceApprovalService:
    def __init__(self, db):
        self.db = db
        self.invoice_dao = InvoiceDAO(db)
        self.approval_dao = InvoiceApprovalDAO(db)
        self.policy_dao = ApprovalPolicyDAO(db)
        self.policy_service = ApprovalPolicyService(db)
        self.resolver = ApproverResolverService(db)

    # =========================================================
    # Send for approval
    # =========================================================

    def send_for_approval(self, invoice_id: int, user_id) -> InvoiceApproval:
        invoice = self.invoice_dao.get_invoice_by_id_locked(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")

        current_code = invoice.status.status_code if invoice.status else None
        if current_code != STATUS_CODE_PENDING_APPROVAL:
            raise ValueError(
                f"Invoice {invoice_id} cannot be sent for approval while in status {current_code}"
            )

        if self.approval_dao.get_active_invoice_approval_for_invoice(invoice_id) is not None:
            raise ValueError(f"Invoice {invoice_id} already has an approval in progress")

        if invoice.department_id is None or invoice.purchase_category_id is None:
            raise ValueError(
                "Invoice is missing department/purchase category - required before it can be "
                "sent for approval"
            )

        policy = self.policy_service.match_policy(
            invoice.department_id, invoice.purchase_category_id, invoice.net_amount
        )
        levels = sorted(
            (level for level in self.policy_dao.get_levels_for_policy(policy.id) if level.is_active),
            key=lambda level: level.level_number,
        )
        if not levels:
            raise ValueError(f"Approval policy '{policy.name}' has no active levels configured")

        # Resolve every level's approvers up front - if any level can't be
        # resolved, abort with no side effects at all rather than creating
        # a partially initialized workflow (spec section 28).
        resolved_levels = []
        for level in levels:
            approver_uuids = self.resolver.resolve(
                level.approver_type,
                role_code=level.role_code,
                user_uuid=level.user_uuid,
                department_id=invoice.department_id,
            )
            if not approver_uuids:
                descriptor = level.role_code or level.approver_type
                raise ValueError(f"No active approver found for level {level.level_number} ({descriptor})")
            resolved_levels.append((level, approver_uuids))

        instance = InvoiceApproval(
            invoice_id=invoice.invoice_id,
            approval_policy_id=policy.id,
            status="IN_PROGRESS",
        )
        self.approval_dao.create_invoice_approval(instance)
        self.db.flush()

        now = datetime.datetime.now(datetime.timezone.utc)
        for index, (level, approver_uuids) in enumerate(resolved_levels):
            is_first = index == 0
            step = InvoiceApprovalStep(
                invoice_approval_id=instance.invoice_approval_id,
                level_number=level.level_number,
                approver_type=level.approver_type,
                approval_rule=level.approval_rule,
                role_code=level.role_code,
                department_id=invoice.department_id if level.approver_type == "DEPARTMENT_APPROVER" else None,
                status="PENDING" if is_first else "WAITING",
                started_at=now if is_first else None,
            )
            self.approval_dao.create_step(step)
            self.db.flush()

            for approver_uuid in approver_uuids:
                self.approval_dao.create_step_approver(
                    InvoiceApprovalStepApprover(
                        approval_step_id=step.id,
                        user_uuid=approver_uuid,
                        status="PENDING" if is_first else "WAITING",
                    )
                )

        self._record_audit(
            invoice.invoice_id, "INVOICE_SENT_FOR_APPROVAL", user_id,
            {"invoice_approval_id": instance.invoice_approval_id, "approval_policy_id": policy.id},
        )

        self.db.commit()
        return self.approval_dao.get_invoice_approval_by_id(instance.invoice_approval_id)

    # =========================================================
    # Approve / Reject
    # =========================================================

    def approve(self, invoice_id: int, user_id, comments: Optional[str]) -> InvoiceApproval:
        instance = self._require_active_instance(invoice_id)
        step = self.approval_dao.get_active_step_locked(instance.invoice_approval_id)
        if step is None:
            raise ValueError("There is no active approval step for this invoice")

        step_approver = self._require_assigned_approver(step, user_id)

        now = datetime.datetime.now(datetime.timezone.utc)
        step_approver.status = "APPROVED"
        step_approver.decided_at = now
        step_approver.comments = comments

        self._record_audit(
            instance.invoice_id, "INVOICE_APPROVAL_STEP_DECISION", user_id,
            {
                "invoice_approval_id": instance.invoice_approval_id,
                "level_number": step.level_number,
                "decision": "APPROVED",
                "comments": comments,
            },
        )

        if self._is_step_complete(step):
            self._advance_or_complete(instance, step, user_id)

        self.db.commit()
        return self.approval_dao.get_invoice_approval_by_id(instance.invoice_approval_id)

    def reject(self, invoice_id: int, user_id, comments: str) -> InvoiceApproval:
        if not comments or not comments.strip():
            raise ValueError("A comment is required to reject an invoice")
        comments = comments.strip()

        instance = self._require_active_instance(invoice_id)
        step = self.approval_dao.get_active_step_locked(instance.invoice_approval_id)
        if step is None:
            raise ValueError("There is no active approval step for this invoice")

        step_approver = self._require_assigned_approver(step, user_id)

        now = datetime.datetime.now(datetime.timezone.utc)
        step_approver.status = "REJECTED"
        step_approver.decided_at = now
        step_approver.comments = comments

        for other in self.approval_dao.get_approvers_for_step(step.id):
            if other.id != step_approver.id and other.status == "PENDING":
                other.status = "SKIPPED"

        step.status = "REJECTED"
        step.completed_at = now

        instance.status = "REJECTED"
        instance.completed_at = now

        rejected_status = self._require_invoice_status(STATUS_CODE_REJECTED)
        invoice = self.invoice_dao.get_invoice_by_id_locked(instance.invoice_id)
        invoice.status_id = rejected_status.status_id
        invoice.updated_by = str(user_id)

        self._record_audit(
            instance.invoice_id, "INVOICE_REJECTED", user_id,
            {
                "invoice_approval_id": instance.invoice_approval_id,
                "level_number": step.level_number,
                "comments": comments,
            },
        )

        self.db.commit()
        return self.approval_dao.get_invoice_approval_by_id(instance.invoice_approval_id)

    # =========================================================
    # Read
    # =========================================================

    def get_approval_detail(self, invoice_id: int) -> InvoiceApproval:
        instance = self.approval_dao.get_latest_invoice_approval_for_invoice(invoice_id)
        if instance is None:
            raise ValueError(f"Invoice {invoice_id} has no approval history")
        return instance

    def get_steps(self, invoice_id: int) -> List[InvoiceApprovalStep]:
        return self.get_approval_detail(invoice_id).steps

    def get_all_statuses(self):
        return self.invoice_dao.get_all_statuses()

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_active_instance(self, invoice_id: int) -> InvoiceApproval:
        instance = self.approval_dao.get_active_invoice_approval_for_invoice(invoice_id)
        if instance is None:
            raise ValueError(f"Invoice {invoice_id} has no approval in progress")
        return instance

    def _require_assigned_approver(self, step: InvoiceApprovalStep, user_id) -> InvoiceApprovalStepApprover:
        user_uuid = self.resolver.resolve_user_uuid(user_id)
        if user_uuid is None:
            raise ValueError("Could not resolve the current user's identity for approval purposes")

        step_approver = self.approval_dao.get_step_approver(step.id, user_uuid)
        if step_approver is None:
            raise ValueError("You are not an assigned approver for the current approval step")
        if step_approver.status != "PENDING":
            raise ValueError(f"Your decision on this step has already been recorded ({step_approver.status})")
        if not self.resolver.is_eligible_now(user_uuid, step.approver_type, step.role_code, step.department_id):
            raise ValueError("You are no longer an active/eligible approver for this step")
        return step_approver

    def _is_step_complete(self, step: InvoiceApprovalStep) -> bool:
        approvers = self.approval_dao.get_approvers_for_step(step.id)
        if step.approval_rule == "ANY_ONE":
            if any(a.status == "APPROVED" for a in approvers):
                for a in approvers:
                    if a.status == "PENDING":
                        a.status = "SKIPPED"
                return True
            return False
        # ALL
        return all(a.status == "APPROVED" for a in approvers)

    def _advance_or_complete(self, instance: InvoiceApproval, current_step: InvoiceApprovalStep, user_id) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        current_step.status = "APPROVED"
        current_step.completed_at = now

        remaining = [s for s in instance.steps if s.level_number > current_step.level_number]
        next_step = min(remaining, key=lambda s: s.level_number) if remaining else None

        if next_step is not None:
            next_step.status = "PENDING"
            next_step.started_at = now
            for approver in self.approval_dao.get_approvers_for_step(next_step.id):
                approver.status = "PENDING"
            return

        instance.status = "APPROVED"
        instance.completed_at = now

        approved_status = self._require_invoice_status(STATUS_CODE_APPROVED)
        invoice = self.invoice_dao.get_invoice_by_id_locked(instance.invoice_id)
        invoice.status_id = approved_status.status_id
        invoice.updated_by = str(user_id)

        self._record_audit(
            instance.invoice_id, "INVOICE_APPROVED", user_id,
            {"invoice_approval_id": instance.invoice_approval_id},
        )

    def _require_invoice_status(self, status_code: str):
        status = self.invoice_dao.get_status_by_code(status_code)
        if status is None:
            raise ValueError(f"Status '{status_code}' is not configured for the INVOICE module")
        return status

    def _record_audit(self, invoice_id: int, action: str, user_id, values: dict) -> None:
        self.approval_dao.create_audit_log(
            AuditLog(
                table_name="invoice",
                record_id=invoice_id,
                action=action,
                changed_by=str(user_id) if user_id is not None else None,
                new_values={k: v for k, v in values.items() if v is not None} or None,
            )
        )
