# Backend/Business_Layer/services/rfq_service.py
import datetime
import uuid
from dataclasses import dataclass
from typing import List, Optional

from Backend.Business_Layer.utils.email_service import EmailSendResult, send_email
from Backend.Data_Access_Layer.dao.procurement_dao import ProcurementDAO
from Backend.Data_Access_Layer.dao.rfq_dao import RFQDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.purchase import Quotation
from Backend.Data_Access_Layer.models.rfq import RFQ, RFQVendor

RFQ_STATUS_MODULE = "RFQ"
PR_STATUS_MODULE = "PURCHASE_REQUISITION"
RFQ_HISTORY_TABLE = "rfq"

RFQ_TRANSITIONS = {
    "DRAFT": {"SENT"},
    "SENT": {"RESPONSE_RECEIVED", "CLOSED"},
    "RESPONSE_RECEIVED": {"CLOSED"},
    "CLOSED": set(),
}


@dataclass
class RFQVendorSendResult:
    vendor_id: int
    email: Optional[str]
    success: bool
    sent_at: datetime.datetime
    error: Optional[str] = None


class RFQService:
    def __init__(self, db):
        self.db = db
        self.rfq_dao = RFQDAO(db)
        self.procurement_dao = ProcurementDAO(db)

    # =========================================================
    # RFQ
    # =========================================================

    def create_rfq(self, pr_id: int, due_date, user_id: str) -> RFQ:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"APPROVED"}, "used to create an RFQ")

        if pr.sourcing_type is not None and pr.sourcing_type != "RFQ":
            raise ValueError(
                f"Purchase requisition sourcing decision is {pr.sourcing_type}; cannot create an RFQ"
            )

        draft_status = self._require_status(RFQ_STATUS_MODULE, "DRAFT")

        rfq = RFQ(
            rfq_number=f"RFQ-TMP-{uuid.uuid4().hex[:12]}",
            pr_id=pr_id,
            status_id=draft_status.status_id,
            created_by=user_id,
            due_date=due_date,
        )
        self.rfq_dao.create_rfq(rfq)
        rfq.rfq_number = f"RFQ-{rfq.id:06d}"

        pr.sourcing_type = "RFQ"

        self.db.commit()
        self.db.refresh(rfq)
        return rfq

    def get_rfq(self, rfq_id: int) -> RFQ:
        return self._require_rfq(rfq_id)

    def list_rfqs(
        self,
        pr_id: Optional[int] = None,
        status_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RFQ]:

        return self.rfq_dao.get_all_rfqs(pr_id, status_id, skip, limit)

    # =========================================================
    # RFQ Vendor (invitation)
    # =========================================================

    def invite_vendors(self, rfq_id: int, vendor_ids: List[int], user_id: str) -> RFQ:
        rfq = self._require_rfq(rfq_id)
        self._require_rfq_status(rfq, {"DRAFT", "SENT"}, "invited with vendors")

        if not vendor_ids:
            raise ValueError("At least one vendor_id is required to invite vendors")

        for vendor_id in vendor_ids:
            self._require_active_vendor(vendor_id)
            if not self.rfq_dao.is_vendor_invited(rfq_id, vendor_id):
                self.rfq_dao.create_rfq_vendor(
                    RFQVendor(rfq_id=rfq_id, vendor_id=vendor_id, invited_by=user_id)
                )

        self.db.commit()
        self.db.refresh(rfq)
        return rfq

    def list_vendors(self, rfq_id: int) -> List[RFQVendor]:
        self._require_rfq(rfq_id)
        return self.rfq_dao.get_rfq_vendors(rfq_id)

    # =========================================================
    # Send / Close
    # =========================================================

    def send_rfq(self, rfq_id: int, user_id: str) -> tuple[RFQ, List[RFQVendorSendResult]]:
        rfq = self._require_rfq(rfq_id)
        self._require_rfq_status(rfq, {"DRAFT"}, "sent")

        invitations = self.rfq_dao.get_rfq_vendors(rfq_id)
        if not invitations:
            raise ValueError("RFQ must have at least one invited vendor before it can be sent")

        pr = self.procurement_dao.get_purchase_requisition_by_id(rfq.pr_id)
        lines = self.procurement_dao.get_lines_by_pr_id(rfq.pr_id) if pr is not None else []

        results: List[RFQVendorSendResult] = []
        for invitation in invitations:
            vendor = self.rfq_dao.get_vendor_by_id(invitation.vendor_id)
            result = self._send_rfq_email_to_vendor(rfq, pr, lines, vendor, invitation.vendor_id)
            results.append(result)
            self._record_rfq_history(
                rfq_id,
                "EMAIL_SENT" if result.success else "EMAIL_FAILED",
                user_id,
                {"vendor_id": result.vendor_id, "email": result.email, "error": result.error},
            )

        # The send action must be handled (attempted, and at least reach one
        # invited vendor) before the RFQ can be marked SENT - do not claim a
        # successful send, or move the workflow forward, if every vendor
        # email failed.
        if not any(result.success for result in results):
            self.db.commit()
            raise ValueError(
                "RFQ could not be sent: email delivery failed for every invited vendor"
            )

        self._transition_rfq(rfq, "SENT")
        rfq.sent_at = datetime.datetime.now(datetime.timezone.utc)

        self.db.commit()
        self.db.refresh(rfq)
        return rfq, results

    def _send_rfq_email_to_vendor(self, rfq: RFQ, pr, lines, vendor, vendor_id: int) -> RFQVendorSendResult:
        sent_at = datetime.datetime.now(datetime.timezone.utc)

        if vendor is None:
            return RFQVendorSendResult(
                vendor_id=vendor_id, email=None, success=False, sent_at=sent_at,
                error="Invited vendor no longer exists",
            )
        if not vendor.email:
            return RFQVendorSendResult(
                vendor_id=vendor.vendor_id, email=None, success=False, sent_at=sent_at,
                error="Vendor has no email address on file",
            )

        subject, html_body, text_body = self._build_rfq_email_content(rfq, pr, lines, vendor)
        result: EmailSendResult = send_email(
            to_address=vendor.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
        return RFQVendorSendResult(
            vendor_id=vendor.vendor_id,
            email=vendor.email,
            success=result.success,
            sent_at=result.sent_at,
            error=result.error,
        )

    @staticmethod
    def _build_rfq_email_content(rfq: RFQ, pr, lines, vendor) -> tuple[str, str, str]:
        subject = f"Request for Quotation - {rfq.rfq_number}"
        pr_number = pr.pr_number if pr is not None else "N/A"
        due_date = rfq.due_date.isoformat() if rfq.due_date else "Not specified"
        item_lines = [f"- {line.item_name} (Qty: {line.quantity})" for line in lines] or [
            "- See attached/referenced requisition for item details"
        ]
        items_text = "\n".join(item_lines)
        items_html = "".join(
            f"<li>{line.item_name} (Qty: {line.quantity})</li>" for line in lines
        ) or "<li>See referenced requisition for item details</li>"

        text_body = (
            f"Dear {vendor.vendor_name},\n\n"
            f"You are invited to submit a quotation for RFQ {rfq.rfq_number} "
            f"(Purchase Requisition {pr_number}).\n\n"
            f"Response due date: {due_date}\n\n"
            f"Requested items:\n{items_text}\n\n"
            "Please prepare your quotation with pricing, delivery timeline, and "
            "payment terms, and send it to us referencing this RFQ number before "
            "the due date above.\n\n"
            "Regards,\n"
            "Procurement Team"
        )
        html_body = (
            f"<p>Dear {vendor.vendor_name},</p>"
            f"<p>You are invited to submit a quotation for RFQ "
            f"<strong>{rfq.rfq_number}</strong> "
            f"(Purchase Requisition <strong>{pr_number}</strong>).</p>"
            f"<p><strong>Response due date:</strong> {due_date}</p>"
            f"<p><strong>Requested items:</strong></p><ul>{items_html}</ul>"
            "<p>Please prepare your quotation with pricing, delivery timeline, and "
            "payment terms, and send it to us referencing this RFQ number before "
            "the due date above.</p>"
            "<p>Regards,<br/>Procurement Team</p>"
        )
        return subject, html_body, text_body

    def _record_rfq_history(
        self, rfq_id: int, action: str, user_id: str, details: dict
    ) -> None:
        self.procurement_dao.create_audit_log(
            AuditLog(
                table_name=RFQ_HISTORY_TABLE,
                record_id=rfq_id,
                action=action,
                changed_by=user_id,
                new_values=details,
            )
        )

    def close_rfq(self, rfq_id: int, user_id: str) -> RFQ:
        rfq = self._require_rfq(rfq_id)
        self._require_rfq_status(rfq, {"SENT", "RESPONSE_RECEIVED"}, "closed")

        self._transition_rfq(rfq, "CLOSED")
        rfq.closed_by = user_id
        rfq.closed_at = datetime.datetime.now(datetime.timezone.utc)

        self.db.commit()
        self.db.refresh(rfq)
        return rfq

    # =========================================================
    # Quotations for an RFQ
    # =========================================================

    def list_quotations(self, rfq_id: int) -> List[Quotation]:
        self._require_rfq(rfq_id)
        return self.procurement_dao.get_quotations_by_rfq_id(rfq_id)

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_rfq(self, rfq_id: int) -> RFQ:
        rfq = self.rfq_dao.get_rfq_by_id(rfq_id)
        if rfq is None:
            raise ValueError("RFQ not found")
        return rfq

    @staticmethod
    def _require_rfq_status(rfq: RFQ, allowed_codes: set, action_description: str) -> None:
        if rfq.status.status_code not in allowed_codes:
            raise ValueError(
                f"RFQ cannot be {action_description} while in status {rfq.status.status_code}"
            )

    def _transition_rfq(self, rfq: RFQ, target_code: str) -> None:
        current_code = rfq.status.status_code
        allowed = RFQ_TRANSITIONS.get(current_code, set())
        if target_code not in allowed:
            raise ValueError(f"RFQ cannot move from {current_code} to {target_code}")
        target_status = self._require_status(RFQ_STATUS_MODULE, target_code)
        rfq.status_id = target_status.status_id

    def _require_pr(self, pr_id: int):
        pr = self.procurement_dao.get_purchase_requisition_by_id(pr_id)
        if pr is None:
            raise ValueError("Purchase requisition not found")
        return pr

    @staticmethod
    def _require_pr_status(pr, allowed_codes: set, action_description: str) -> None:
        if pr.status.status_code not in allowed_codes:
            raise ValueError(
                f"Purchase requisition cannot be {action_description} while in status {pr.status.status_code}"
            )

    def _require_status(self, module_name: str, status_code: str):
        status = self.rfq_dao.get_status_by_module_code(module_name, status_code)
        if status is None:
            raise ValueError(f"Status '{status_code}' is not configured for module '{module_name}'")
        return status

    def _require_active_vendor(self, vendor_id: int):
        vendor = self.rfq_dao.get_vendor_by_id(vendor_id)
        if vendor is None:
            raise ValueError("Vendor not found for the given vendor_id")
        if vendor.status is None or vendor.status.status_code != "ACTIVE":
            raise ValueError("Vendor must be ACTIVE to be used in procurement")
        return vendor
