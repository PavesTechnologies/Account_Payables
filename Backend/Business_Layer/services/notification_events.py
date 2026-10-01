# Backend/Business_Layer/services/notification_events.py
"""AP business event -> action notification mapping.

One method per real state transition. Each is called from the business
service at the point the transition has been applied, BEFORE that service's
own commit (see NotificationDispatcher for why). Every method is wrapped by
``_best_effort`` - building a notification can never raise into, or change
the outcome of, the workflow that triggered it.

Recipient rules (Role -> Responsibility -> Action):
  * concrete owner/assignee first (rfq.created_by, onboarding assigned_to,
    invoice approval step approver user_uuid, payment.created_by, ...)
  * the UMS role (catalog fallback) only when there is no concrete owner
  * the actor is always excluded
  * PR workflow: submission/resubmission -> PR_Approver role (approval is
    permission-based, so no concrete approver exists); return for
    clarification -> the PR's own requester (pr.created_by) only.
"""
from __future__ import annotations

import functools
import hashlib
import logging
from typing import Iterable, List, Optional

from Backend.Business_Layer.services.notification_service import (
    NotificationDispatcher,
    independent_dispatcher,
)
from Backend.Business_Layer.utils import notification_types as nt

logger = logging.getLogger(__name__)

PR_SOURCING_STATUS_CODES = {"APPROVED", "VENDOR_SELECTION"}

_PR_TYPES = (
    nt.PR_APPROVAL_REQUIRED, nt.PR_RETURNED,
    nt.PR_APPROVED_SOURCING, nt.PO_GENERATION_REQUIRED, nt.PROCUREMENT_BLOCKED,
)
_RFQ_TYPES = (
    nt.VENDOR_SELECTION_REQUIRED, nt.RFQ_DEADLINE_REACHED,
    nt.RFQ_VENDOR_EMAIL_FAILURE, nt.PROCUREMENT_BLOCKED,
)
_QUOTATION_TYPES = (nt.QUOTATION_RECEIVED, nt.QUOTATION_VALIDITY_ENDING)
_ONBOARDING_INTAKE_TYPES = (
    nt.VENDOR_ONBOARDING_REQUESTED, nt.VENDOR_ONBOARDING_ASSIGNED,
    nt.VENDOR_INFORMATION_REQUIRED, nt.VENDOR_PRESCREEN_REQUIRED,
)
_NDA_TYPES = (
    nt.NDA_REQUIRED, nt.NDA_PENDING, nt.NDA_SIGNED_REVIEW_PENDING, nt.NDA_EXPIRED_RFQ_BLOCKED,
)
_INVOICE_REVIEW_TYPES = (nt.INVOICE_REVIEW_REQUIRED, nt.INVOICE_VALIDATION_EXCEPTION, nt.INVOICE_RETURNED)
_INVOICE_PAYMENT_TYPES = (
    nt.PAYMENT_READY, nt.INVOICE_DUE, nt.INVOICE_OVERDUE, nt.INVOICE_PAYMENT_ACTION_REQUIRED,
)
_APPROVAL_STEP_TYPES = (nt.INVOICE_APPROVAL_REQUIRED, nt.INVOICE_APPROVAL_AGEING)
_PAYMENT_TYPES = (nt.PAYMENT_DUE, nt.PAYMENT_FAILED, nt.PAYMENT_EXCEPTION, nt.FINANCE_ESCALATION)
# Vendor Management outcomes sent to the procurement owner (PO Officer side).
_ONBOARDING_OUTCOME_TYPES = (nt.VENDOR_ONBOARDING_COMPLETED, nt.VENDOR_ONBOARDING_FAILED)


def _best_effort(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:
            logger.exception("In-app notification event %s failed (business action unaffected)", method.__name__)
            return None
    return wrapper


def _code(obj) -> Optional[str]:
    status = getattr(obj, "status", None)
    return getattr(status, "status_code", None)


def _now_token() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _history_event_id(history) -> str:
    """Event identity = the audit_log row that recorded the transition, so a
    replay of that one event dedupes while a later repeat of the transition
    (e.g. a second resubmission) is a genuinely new event."""
    audit_log_id = getattr(history, "audit_log_id", None)
    return f"history:{audit_log_id}" if audit_log_id is not None else f"at:{_now_token()}"


class APNotificationEvents:
    def __init__(self, db, dispatcher: Optional[NotificationDispatcher] = None):
        self.db = db
        self.dispatcher = dispatcher or NotificationDispatcher(db)

    # =========================================================
    # Owner lookups
    # =========================================================

    def _rfq_owner(self, pr_id) -> Optional[List[str]]:
        """PR-level procurement owner = creator of the PR's latest RFQ.
        None when no RFQ exists (-> Procurement_Officer role fallback)."""
        if pr_id is None:
            return None
        from Backend.Data_Access_Layer.dao.rfq_dao import RFQDAO

        rfqs = RFQDAO(self.db).get_all_rfqs(pr_id=pr_id, skip=0, limit=1)
        return [rfqs[0].created_by] if rfqs else None

    def _pr(self, pr_id):
        if pr_id is None:
            return None
        from Backend.Data_Access_Layer.dao.procurement_dao import ProcurementDAO

        return ProcurementDAO(self.db).get_purchase_requisition_by_id(pr_id)

    def _onboarding_requests(self, pr_id, vendor_ids=None) -> list:
        """Onboarding requests raised for a PR (optionally only for the given
        vendors) - used to resolve Vendor Management outcome notifications
        once procurement has acted on them."""
        if pr_id is None:
            return []
        from Backend.Data_Access_Layer.dao.vendor_onboarding_dao import VendorOnboardingDAO

        requests = VendorOnboardingDAO(self.db).get_all_requests(pr_id=pr_id, skip=0, limit=1000)
        if vendor_ids is not None:
            wanted = {int(v) for v in vendor_ids}
            requests = [r for r in requests if r.vendor_id is not None and int(r.vendor_id) in wanted]
        return requests

    def _rfqs_for_pr(self, pr_id) -> list:
        from Backend.Data_Access_Layer.dao.rfq_dao import RFQDAO

        return RFQDAO(self.db).get_all_rfqs(pr_id=pr_id, skip=0, limit=1000)

    def _quotations_for_pr(self, pr_id) -> list:
        from Backend.Data_Access_Layer.dao.procurement_dao import ProcurementDAO

        return ProcurementDAO(self.db).get_quotations_by_pr_id(pr_id)

    def _ndas_for_pr(self, pr_id) -> list:
        from Backend.Data_Access_Layer.dao.nda_dao import NdaDAO

        return NdaDAO(self.db).get_ndas_by_pr(pr_id)

    def _ndas_for_vendor(self, vendor_id) -> list:
        from Backend.Data_Access_Layer.dao.nda_dao import NdaDAO

        return NdaDAO(self.db).get_ndas_by_vendor(vendor_id)

    def _approval_sender(self, invoice) -> Optional[str]:
        """The AP Executive who sent the invoice for approval (latest
        INVOICE_SENT_FOR_APPROVAL audit row) - the owner of a returned invoice."""
        from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO

        rows = InvoiceDAO(self.db).get_audit_log_for_record("invoice", invoice.invoice_id)
        senders = [r.changed_by for r in rows if r.action == "INVOICE_SENT_FOR_APPROVAL" and r.changed_by]
        return senders[-1] if senders else None

    # =========================================================
    # Procurement
    # =========================================================

    @staticmethod
    def _pr_priority(pr) -> Optional[str]:
        return nt.CRITICAL if (pr.priority or "").upper() == "URGENT" else None

    @_best_effort
    def pr_submitted(self, pr, actor_user_id, history=None, resubmitted: bool = False):
        """PR entered PENDING_APPROVAL (``history`` = its PR-history audit row)."""
        if resubmitted:
            self.dispatcher.resolve(nt.ENTITY_PURCHASE_REQUISITION, pr.id, [nt.PR_RETURNED])
        what = "was corrected and resubmitted" if resubmitted else "was submitted"
        self.dispatcher.notify(
            nt.PR_APPROVAL_REQUIRED,
            entity_type=nt.ENTITY_PURCHASE_REQUISITION, entity_id=pr.id, entity_display_id=pr.pr_number,
            message=(
                f"{pr.pr_number} {what} for approval (estimated total {pr.estimated_total}). "
                "Review the PR and approve, reject or return it."
            ),
            event_id=_history_event_id(history), actor_user_id=actor_user_id, owners=None,
            priority=self._pr_priority(pr),
            deadline=pr.required_by,
            metadata={"pr_priority": pr.priority, "resubmitted": resubmitted,
                      "department_id": pr.department_id},
        )

    @_best_effort
    def pr_decided(self, pr):
        """Approved / rejected / returned - the approval decision is made."""
        self.dispatcher.resolve(nt.ENTITY_PURCHASE_REQUISITION, pr.id, [nt.PR_APPROVAL_REQUIRED])

    @_best_effort
    def pr_returned(self, pr, reason: str, actor_user_id, history=None):
        self.pr_decided(pr)
        self.dispatcher.notify(
            nt.PR_RETURNED,
            entity_type=nt.ENTITY_PURCHASE_REQUISITION, entity_id=pr.id, entity_display_id=pr.pr_number,
            message=(
                f"{pr.pr_number} was returned for clarification: {reason}. "
                "Update the PR and resubmit it for approval."
            ),
            event_id=_history_event_id(history), actor_user_id=actor_user_id, owners=[pr.created_by],
            deadline=pr.required_by, metadata={"reason": reason},
        )

    @_best_effort
    def pr_approved(self, pr, actor_user_id):
        self.pr_decided(pr)
        priority = nt.CRITICAL if (pr.priority or "").upper() == "URGENT" else None
        self.dispatcher.notify(
            nt.PR_APPROVED_SOURCING,
            entity_type=nt.ENTITY_PURCHASE_REQUISITION, entity_id=pr.id, entity_display_id=pr.pr_number,
            message=(
                f"{pr.pr_number} has been approved and is ready for sourcing. "
                "Start RFQ (or record a catalog sourcing decision) to move it forward."
            ),
            event_id="approved", actor_user_id=actor_user_id, owners=None, priority=priority,
            deadline=pr.required_by, metadata={"pr_priority": pr.priority},
        )

    @_best_effort
    def sourcing_started(self, pr):
        self.dispatcher.resolve(nt.ENTITY_PURCHASE_REQUISITION, pr.id, [nt.PR_APPROVED_SOURCING])

    @_best_effort
    def pr_closed(self, pr):
        """PR cancelled or PO generated - every procurement action raised for
        this PR is done: PR-level items, its RFQs/quotations, NDA blockers on
        its sourcing, and the Vendor Management outcomes raised for it."""
        self.dispatcher.resolve(nt.ENTITY_PURCHASE_REQUISITION, pr.id, _PR_TYPES)
        for request in self._onboarding_requests(pr.id):
            self.dispatcher.resolve(nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, _ONBOARDING_OUTCOME_TYPES)
        for rfq in self._rfqs_for_pr(pr.id):
            self.dispatcher.resolve(nt.ENTITY_RFQ, rfq.id, _RFQ_TYPES)
        for quotation in self._quotations_for_pr(pr.id):
            self.dispatcher.resolve(nt.ENTITY_QUOTATION, quotation.id, _QUOTATION_TYPES)
        # Only the "RFQ blocked" item depends on this PR's sourcing; the NDA
        # itself is vendor-scoped and reusable, so its other items stay.
        for nda in self._ndas_for_pr(pr.id):
            self.dispatcher.resolve(nt.ENTITY_VENDOR_NDA, nda.nda_id, [nt.NDA_EXPIRED_RFQ_BLOCKED])

    @_best_effort
    def quotation_deleted(self, quotation):
        self.dispatcher.resolve(nt.ENTITY_QUOTATION, quotation.id, _QUOTATION_TYPES)

    @_best_effort
    def vendors_invited(self, rfq, vendor_ids: Iterable[int]):
        """An onboarded vendor was invited to the PR's RFQ - the
        "onboarding completed, continue RFQ" action is done."""
        vendor_ids = list(vendor_ids)
        if not vendor_ids:
            return
        for request in self._onboarding_requests(rfq.pr_id, vendor_ids):
            self.dispatcher.resolve(
                nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, [nt.VENDOR_ONBOARDING_COMPLETED]
            )

    @_best_effort
    def quotation_received(self, quotation, pr, rfq, actor_user_id):
        display = quotation.quotation_number or f"Quotation #{quotation.id}"
        source = f" for {rfq.rfq_number}" if rfq is not None else ""
        self.dispatcher.notify(
            nt.QUOTATION_RECEIVED,
            entity_type=nt.ENTITY_QUOTATION, entity_id=quotation.id, entity_display_id=display,
            message=(
                f"A vendor quotation ({display}) was received{source} on {pr.pr_number}. "
                "Review the quotation so vendor selection can proceed."
            ),
            event_id="received", actor_user_id=actor_user_id,
            owners=[rfq.created_by] if rfq is not None else self._rfq_owner(pr.id),
            deadline=quotation.valid_until,
            metadata={"pr_id": pr.id, "pr_number": pr.pr_number, "rfq_id": getattr(rfq, "id", None),
                      "vendor_id": quotation.vendor_id},
        )

    @_best_effort
    def rfq_send_failures(self, rfq, pr, failed_count: int, total: int, all_failed: bool, actor_user_id):
        if not all_failed:
            # At least one vendor received the RFQ - a previous "nothing could
            # be sent" blocker on this RFQ is no longer actionable.
            self.dispatcher.resolve(nt.ENTITY_RFQ, rfq.id, [nt.PROCUREMENT_BLOCKED])
        if failed_count <= 0:
            return
        pr_number = getattr(pr, "pr_number", None)
        if all_failed:
            code = nt.PROCUREMENT_BLOCKED
            message = (
                f"{rfq.rfq_number} could not be sent: email delivery failed for all {total} selected vendor(s). "
                "The RFQ remains in DRAFT and sourcing is blocked until vendor contact details are fixed and the RFQ is re-sent."
            )
        else:
            code = nt.RFQ_VENDOR_EMAIL_FAILURE
            message = (
                f"{rfq.rfq_number} was sent, but email delivery failed for {failed_count} of {total} vendor(s). "
                "Those vendors have not received the RFQ - review the vendor communication failure."
            )
        self.dispatcher.notify(
            code,
            entity_type=nt.ENTITY_RFQ, entity_id=rfq.id, entity_display_id=rfq.rfq_number,
            message=message, event_id=f"send:{_now_token()}", actor_user_id=actor_user_id,
            owners=[rfq.created_by], deadline=rfq.due_date,
            metadata={"pr_id": rfq.pr_id, "pr_number": pr_number, "failed_count": failed_count, "total": total},
        )

    @_best_effort
    def rfq_closed(self, rfq, quotations_loader, actor_user_id):
        self.dispatcher.resolve(
            nt.ENTITY_RFQ, rfq.id,
            [nt.RFQ_DEADLINE_REACHED, nt.PROCUREMENT_BLOCKED, nt.RFQ_VENDOR_EMAIL_FAILURE],
        )
        received_quotation_count = sum(1 for q in quotations_loader() if _code(q) == "RECEIVED")
        if received_quotation_count <= 0:
            return
        self.dispatcher.notify(
            nt.VENDOR_SELECTION_REQUIRED,
            entity_type=nt.ENTITY_RFQ, entity_id=rfq.id, entity_display_id=rfq.rfq_number,
            message=(
                f"{rfq.rfq_number} is closed with {received_quotation_count} quotation(s) received. "
                "Review the quotations and select a vendor."
            ),
            event_id="closed", actor_user_id=actor_user_id, owners=[rfq.created_by],
            metadata={"pr_id": rfq.pr_id, "quotation_count": received_quotation_count},
        )

    @_best_effort
    def vendor_selected(self, pr, quotation, quotation_ids: Iterable[int], actor_user_id, rfq=None):
        if quotation.rfq_id is not None:
            self.dispatcher.resolve(nt.ENTITY_RFQ, quotation.rfq_id, _RFQ_TYPES)
        for quotation_id in quotation_ids:
            self.dispatcher.resolve(nt.ENTITY_QUOTATION, quotation_id, _QUOTATION_TYPES)

        owners = [rfq.created_by] if rfq is not None else self._rfq_owner(pr.id)
        self.dispatcher.notify(
            nt.PO_GENERATION_REQUIRED,
            entity_type=nt.ENTITY_PURCHASE_REQUISITION, entity_id=pr.id, entity_display_id=pr.pr_number,
            message=(
                f"A vendor has been selected for {pr.pr_number} and the purchase order has not been generated yet. "
                "Generate the PO."
            ),
            event_id=f"selected:{quotation.id}", actor_user_id=actor_user_id, owners=owners,
            deadline=pr.required_by,
            metadata={"quotation_id": quotation.id, "vendor_id": quotation.vendor_id},
        )

    # =========================================================
    # NDA
    # =========================================================

    def _nda_owners(self, nda) -> Optional[List[str]]:
        return self._rfq_owner(nda.pr_id) or ([nda.created_by] if nda.created_by else None)

    @staticmethod
    def _nda_display(nda) -> str:
        return f"NDA-{nda.nda_id:06d}"

    def _resolve_expired_blockers(self, vendor_id, keep_nda_id=None):
        """A new NDA process started, or a valid NDA exists, for this vendor:
        an earlier "NDA expired - RFQ blocked" item is no longer the blocker."""
        for other in self._ndas_for_vendor(vendor_id):
            if other.nda_id != keep_nda_id:
                self.dispatcher.resolve(nt.ENTITY_VENDOR_NDA, other.nda_id, [nt.NDA_EXPIRED_RFQ_BLOCKED])

    @_best_effort
    def nda_required(self, nda, actor_user_id):
        self._resolve_expired_blockers(nda.vendor_id, keep_nda_id=nda.nda_id)
        display = self._nda_display(nda)
        self.dispatcher.notify(
            nt.NDA_REQUIRED,
            entity_type=nt.ENTITY_VENDOR_NDA, entity_id=nda.nda_id, entity_display_id=display,
            message=(
                f"An NDA ({display}) is required for vendor #{nda.vendor_id} before the RFQ can proceed. "
                "Complete the NDA process: review, send and obtain the signed NDA."
            ),
            event_id="generated", actor_user_id=actor_user_id, owners=self._nda_owners(nda),
            metadata={"vendor_id": nda.vendor_id, "pr_id": nda.pr_id},
        )

    @_best_effort
    def nda_send_failed(self, nda, error: Optional[str], actor_user_id):
        display = self._nda_display(nda)
        self.dispatcher.notify(
            nt.NDA_PENDING,
            entity_type=nt.ENTITY_VENDOR_NDA, entity_id=nda.nda_id, entity_display_id=display,
            message=(
                f"{display} could not be emailed to the vendor and is still pending. "
                "RFQ eligibility stays blocked until the NDA is sent and completed - review the NDA."
            ),
            event_id=f"send-failed:{_now_token()}", actor_user_id=actor_user_id, owners=self._nda_owners(nda),
            metadata={"vendor_id": nda.vendor_id, "pr_id": nda.pr_id, "error": error},
        )

    @_best_effort
    def nda_sent(self, nda):
        """Delivered after an earlier failed attempt - the delivery problem is handled."""
        self.dispatcher.resolve(nt.ENTITY_VENDOR_NDA, nda.nda_id, [nt.NDA_PENDING])

    @_best_effort
    def nda_reused(self, nda):
        """An existing valid NDA was reused for the vendor - no NDA blocks the RFQ."""
        self._resolve_expired_blockers(nda.vendor_id, keep_nda_id=nda.nda_id)

    @_best_effort
    def nda_signed(self, nda, actor_user_id):
        display = self._nda_display(nda)
        self.dispatcher.notify(
            nt.NDA_SIGNED_REVIEW_PENDING,
            entity_type=nt.ENTITY_VENDOR_NDA, entity_id=nda.nda_id, entity_display_id=display,
            message=(
                f"The vendor-signed {display} has been received and is pending internal review. "
                "RFQ eligibility stays blocked until it is reviewed and marked COMPLETED."
            ),
            event_id=f"signed:{nda.signed_at.isoformat() if nda.signed_at else _now_token()}",
            actor_user_id=actor_user_id, owners=self._nda_owners(nda),
            metadata={"vendor_id": nda.vendor_id, "pr_id": nda.pr_id},
        )
        self.dispatcher.resolve(nt.ENTITY_VENDOR_NDA, nda.nda_id, [nt.NDA_REQUIRED, nt.NDA_PENDING])

    @_best_effort
    def nda_review_done(self, nda):
        """Signed NDA reviewed and rejected - the review item is done; the
        NDA itself still needs a corrected signed copy."""
        self.dispatcher.resolve(nt.ENTITY_VENDOR_NDA, nda.nda_id, [nt.NDA_SIGNED_REVIEW_PENDING])

    @_best_effort
    def nda_completed(self, nda):
        self.dispatcher.resolve(nt.ENTITY_VENDOR_NDA, nda.nda_id, _NDA_TYPES)
        self._resolve_expired_blockers(nda.vendor_id, keep_nda_id=nda.nda_id)

    @_best_effort
    def nda_expired(self, nda, actor_user_id):
        self.dispatcher.resolve(
            nt.ENTITY_VENDOR_NDA, nda.nda_id,
            [nt.NDA_REQUIRED, nt.NDA_PENDING, nt.NDA_SIGNED_REVIEW_PENDING],
        )
        pr = self._pr(nda.pr_id)
        if pr is None or _code(pr) not in PR_SOURCING_STATUS_CODES:
            return  # no live sourcing to block
        display = self._nda_display(nda)
        self.dispatcher.notify(
            nt.NDA_EXPIRED_RFQ_BLOCKED,
            entity_type=nt.ENTITY_VENDOR_NDA, entity_id=nda.nda_id, entity_display_id=display,
            message=(
                f"{display} for vendor #{nda.vendor_id} has expired, so the RFQ on {pr.pr_number} cannot proceed "
                "with this vendor. Resolve the NDA (generate and complete a new one) to continue the RFQ."
            ),
            event_id="expired", actor_user_id=actor_user_id, owners=self._rfq_owner(nda.pr_id),
            metadata={"vendor_id": nda.vendor_id, "pr_id": nda.pr_id, "pr_number": pr.pr_number},
        )

    # =========================================================
    # Vendor onboarding
    # =========================================================

    @staticmethod
    def _onboarding_display(request) -> str:
        return f"VOR-{request.id:06d}"

    def _onboarding_label(self, request) -> str:
        name = request.requested_vendor_name
        return f" for vendor '{name}'" if name else ""

    @_best_effort
    def onboarding_created(self, request, actor_user_id):
        # A new request for the same PR is how a failed onboarding is handled.
        for previous in self._onboarding_requests(request.pr_id):
            if previous.id != request.id:
                self.dispatcher.resolve(
                    nt.ENTITY_VENDOR_ONBOARDING_REQUEST, previous.id, [nt.VENDOR_ONBOARDING_FAILED]
                )
        if request.assigned_to:
            self.onboarding_assigned(request, actor_user_id)
            return
        display = self._onboarding_display(request)
        self.dispatcher.notify(
            nt.VENDOR_ONBOARDING_REQUESTED,
            entity_type=nt.ENTITY_VENDOR_ONBOARDING_REQUEST, entity_id=request.id, entity_display_id=display,
            message=(
                f"A new vendor onboarding request ({display}){self._onboarding_label(request)} was raised for "
                f"PR #{request.pr_id} and has no assignee yet. Start vendor onboarding."
            ),
            event_id="created", actor_user_id=actor_user_id, owners=None,
            metadata={"pr_id": request.pr_id},
        )

    @_best_effort
    def onboarding_assigned(self, request, actor_user_id, previous_assignee=None):
        if previous_assignee is not None and str(previous_assignee) == str(request.assigned_to):
            return  # re-assigned to the same person: nothing changed for anyone
        self.dispatcher.resolve(
            nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, [nt.VENDOR_ONBOARDING_REQUESTED]
        )
        if previous_assignee:
            # The work moved to someone else - the previous intaker's items are not theirs any more.
            self.dispatcher.resolve(
                nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, _ONBOARDING_INTAKE_TYPES,
                recipient_ref=previous_assignee,
            )
        display = self._onboarding_display(request)
        self.dispatcher.notify(
            nt.VENDOR_ONBOARDING_ASSIGNED,
            entity_type=nt.ENTITY_VENDOR_ONBOARDING_REQUEST, entity_id=request.id, entity_display_id=display,
            message=(
                f"Vendor onboarding request {display}{self._onboarding_label(request)} has been assigned to you. "
                "Process the assigned onboarding request."
            ),
            event_id=f"assigned:{request.assigned_to}:{_now_token()}", actor_user_id=actor_user_id,
            owners=[request.assigned_to], fallback_role=None,
            metadata={"pr_id": request.pr_id},
        )

    @_best_effort
    def onboarding_status_changed(self, request, status_code: str, actor_user_id, reason: Optional[str] = None):
        display = self._onboarding_display(request)
        label = self._onboarding_label(request)
        intaker = [request.assigned_to] if request.assigned_to else None
        common = dict(
            entity_type=nt.ENTITY_VENDOR_ONBOARDING_REQUEST, entity_id=request.id, entity_display_id=display,
            actor_user_id=actor_user_id, metadata={"pr_id": request.pr_id, "reason": reason},
        )

        entity = (nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id)
        if status_code in ("IN_PROGRESS", "PRE_SCREEN_PENDING", "PASSED"):
            # The missing information was supplied and the request moved on.
            self.dispatcher.resolve(*entity, [nt.VENDOR_INFORMATION_REQUIRED])
        if status_code in ("PASSED", "NEED_INFORMATION"):
            # Pre-screen has run - that item is done (FAILED/COMPLETED resolve everything below).
            self.dispatcher.resolve(*entity, [nt.VENDOR_PRESCREEN_REQUIRED])

        if status_code == "NEED_INFORMATION":
            self.dispatcher.notify(
                nt.VENDOR_INFORMATION_REQUIRED,
                message=(
                    f"Onboarding request {display}{label} needs additional vendor information"
                    f"{': ' + reason if reason else ''}. Request/collect the missing information."
                ),
                event_id=f"need-info:{_now_token()}", owners=intaker, **common,
            )
        elif status_code == "PRE_SCREEN_PENDING":
            self.dispatcher.notify(
                nt.VENDOR_PRESCREEN_REQUIRED,
                message=f"Vendor intake for {display}{label} is done and pre-screening is pending. Complete pre-screening.",
                event_id=f"pre-screen:{_now_token()}", owners=intaker, **common,
            )
        elif status_code == "FAILED":
            self.dispatcher.resolve(nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, _ONBOARDING_INTAKE_TYPES)
            message = (
                f"Vendor onboarding {display}{label} for PR #{request.pr_id} has failed"
                f"{': ' + reason if reason else ''}. Review the vendor onboarding issue."
            )
            self.dispatcher.notify(
                nt.VENDOR_ONBOARDING_FAILED, message=message, event_id="failed",
                owners=[request.created_by], **common,
            )
            self.dispatcher.notify(
                nt.VENDOR_ONBOARDING_FAILED, message=message, event_id="failed",
                owners=intaker, fallback_role=None, **common,
            )
        elif status_code == "COMPLETED":
            self.dispatcher.resolve(nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, _ONBOARDING_INTAKE_TYPES)
            self.dispatcher.notify(
                nt.VENDOR_ONBOARDING_COMPLETED,
                message=(
                    f"Vendor onboarding {display}{label} for PR #{request.pr_id} is complete and the vendor is active. "
                    "Continue procurement / RFQ."
                ),
                event_id="completed", owners=[request.created_by], **common,
            )
            # The intaker's work is done - "completed, no further action" is
            # not actionable for them, so nothing is sent to the intaker.
        elif status_code == "CANCELLED":
            self.dispatcher.resolve(nt.ENTITY_VENDOR_ONBOARDING_REQUEST, request.id, _ONBOARDING_INTAKE_TYPES)

    # =========================================================
    # Invoice
    # =========================================================

    @_best_effort
    def invoice_review_required(self, invoice, actor_user_id):
        self.dispatcher.notify(
            nt.INVOICE_REVIEW_REQUIRED,
            entity_type=nt.ENTITY_INVOICE, entity_id=invoice.invoice_id, entity_display_id=invoice.invoice_number,
            message=(
                f"Invoice {invoice.invoice_number} was captured and is waiting for OCR/extraction review. "
                "Review the invoice before it can be sent for approval."
            ),
            event_id="review-pending", actor_user_id=actor_user_id,
            owners=[invoice.created_by] if invoice.created_by else None,
            deadline=invoice.due_date, metadata={"vendor_id": invoice.vendor_id},
        )

    @_best_effort
    def invoice_validation_exception(self, invoice, issue_type: str, description: str, actor_user_id, issue_id=None):
        self.dispatcher.notify(
            nt.INVOICE_VALIDATION_EXCEPTION,
            entity_type=nt.ENTITY_INVOICE, entity_id=invoice.invoice_id, entity_display_id=invoice.invoice_number,
            message=f"Invoice {invoice.invoice_number} has a validation exception: {description}. Resolve the invoice exception.",
            # Per issue row: a review resolves the previous exception, and a
            # re-raised issue on a later review is a new exception to act on.
            event_id=f"issue:{issue_type}:{issue_id if issue_id is not None else _now_token()}",
            actor_user_id=actor_user_id,
            owners=[invoice.created_by] if invoice.created_by else None,
            deadline=invoice.due_date, metadata={"issue_type": issue_type},
        )

    @_best_effort
    def invoice_reviewed(self, invoice):
        self.dispatcher.resolve(nt.ENTITY_INVOICE, invoice.invoice_id, _INVOICE_REVIEW_TYPES)

    @_best_effort
    def approval_step_pending(self, invoice, step, approver_uuids, actor_user_id):
        """Only the step's runtime-assigned approvers - never a role broadcast.
        ``invoice`` may be a zero-arg loader so the lookup stays best-effort."""
        if callable(invoice):
            invoice = invoice()
        if invoice is None or step is None:
            return
        # An approval step exists, so the approval workflow configuration is
        # no longer blocking this invoice.
        self.dispatcher.resolve(nt.ENTITY_INVOICE, invoice.invoice_id, [nt.WORKFLOW_CONFIGURATION_BLOCKED])
        self.dispatcher.notify(
            nt.INVOICE_APPROVAL_REQUIRED,
            entity_type=nt.ENTITY_INVOICE_APPROVAL_STEP, entity_id=step.id,
            entity_display_id=invoice.invoice_number,
            message=(
                f"Invoice {invoice.invoice_number} (net {invoice.net_amount}) is awaiting your decision at "
                f"approval level {step.level_number}. Approve or reject the invoice."
            ),
            event_id="pending", actor_user_id=actor_user_id, owners=list(approver_uuids), fallback_role=None,
            deep_link=nt.deep_link_for(nt.ENTITY_INVOICE, invoice.invoice_id), deadline=invoice.due_date,
            metadata={"invoice_id": invoice.invoice_id, "level_number": step.level_number,
                      "approval_rule": step.approval_rule},
        )

    @_best_effort
    def approval_decided(self, step, decider_uuid, step_closed: bool):
        if step_closed:
            self.dispatcher.resolve(nt.ENTITY_INVOICE_APPROVAL_STEP, step.id, _APPROVAL_STEP_TYPES)
        else:
            self.dispatcher.resolve(
                nt.ENTITY_INVOICE_APPROVAL_STEP, step.id, _APPROVAL_STEP_TYPES, recipient_ref=decider_uuid
            )

    @_best_effort
    def invoice_returned(self, invoice, comments: str, actor_user_id):
        sender = self._approval_sender(invoice) or invoice.created_by
        self.dispatcher.notify(
            nt.INVOICE_RETURNED,
            entity_type=nt.ENTITY_INVOICE, entity_id=invoice.invoice_id, entity_display_id=invoice.invoice_number,
            message=(
                f"Invoice {invoice.invoice_number} was returned by the approver for correction: {comments}. "
                "Review and correct the invoice, then resubmit it for approval."
            ),
            event_id=f"returned:{_now_token()}", actor_user_id=actor_user_id,
            owners=[sender] if sender else None, deadline=invoice.due_date,
            metadata={"comments": comments},
        )

    @_best_effort
    def invoice_approved(self, invoice, actor_user_id):
        import datetime

        overdue = invoice.due_date is not None and invoice.due_date < datetime.date.today()
        self.dispatcher.notify(
            nt.PAYMENT_READY,
            entity_type=nt.ENTITY_INVOICE, entity_id=invoice.invoice_id, entity_display_id=invoice.invoice_number,
            message=(
                f"Invoice {invoice.invoice_number} (net {invoice.net_amount}) is fully approved and ready for "
                f"payment processing{' and is already past its due date' if overdue else ''}. "
                "Mark it ready for payment and schedule the payment."
            ),
            event_id="approved", actor_user_id=actor_user_id, owners=None,
            priority=nt.CRITICAL if overdue else None, deadline=invoice.due_date,
            metadata={"vendor_id": invoice.vendor_id},
        )

    @_best_effort
    def invoice_paid(self, invoice):
        self.dispatcher.resolve(nt.ENTITY_INVOICE, invoice.invoice_id, _INVOICE_PAYMENT_TYPES)

    @_best_effort
    def workflow_configuration_blocked(self, invoice, error: str, actor_user_id):
        """Called on a FAILED send_for_approval whose cause is configuration
        (no matching policy / no levels / no eligible approver). The request
        is rolled back, so this goes through an independent transaction."""
        digest = hashlib.sha1(error.encode("utf-8")).hexdigest()[:16]
        with independent_dispatcher(self.db) as dispatcher:
            if dispatcher is None:
                return
            dispatcher.notify(
                nt.WORKFLOW_CONFIGURATION_BLOCKED,
                entity_type=nt.ENTITY_INVOICE, entity_id=invoice.invoice_id,
                entity_display_id=invoice.invoice_number,
                message=(
                    f"Invoice {invoice.invoice_number} cannot be sent for approval because of the approval "
                    f"workflow configuration: {error}. Review the approval policy / approver configuration."
                ),
                event_id=f"blocked:{digest}", actor_user_id=actor_user_id, owners=None,
                metadata={"error": error, "department_id": invoice.department_id,
                          "purchase_category_id": invoice.purchase_category_id},
            )

    # =========================================================
    # Payment
    # =========================================================

    @_best_effort
    def payment_failed(self, payment, actor_user_id):
        display = f"PAY-{payment.payment_id:06d}"
        common = dict(
            entity_type=nt.ENTITY_PAYMENT, entity_id=payment.payment_id, entity_display_id=display,
            event_id="failed", actor_user_id=actor_user_id,
            metadata={"vendor_id": payment.vendor_id, "total_amount": payment.total_amount,
                      "invoice_ids": [a.invoice_id for a in (payment.payment_invoice or [])]},
        )
        self.dispatcher.notify(
            nt.PAYMENT_FAILED,
            message=(
                f"Payment {display} of {payment.total_amount} to vendor #{payment.vendor_id} has failed. "
                "The vendor has not been paid - review and resolve the payment failure."
            ),
            owners=[payment.created_by] if payment.created_by else None, **common,
        )
        self.dispatcher.notify(
            nt.FINANCE_ESCALATION,
            message=(
                f"Payment {display} of {payment.total_amount} to vendor #{payment.vendor_id} failed and is "
                "escalated for finance management attention. Review the escalated payment issue."
            ),
            owners=None, **common,
        )

    @_best_effort
    def payment_scheduled(self, payment, invoice_ids: Iterable[int]):
        """A payment was scheduled for these invoices: "ready for payment" is
        processed, and an earlier FAILED payment on the same invoices has been
        handled by re-paying."""
        invoice_ids = list(invoice_ids)
        for invoice_id in invoice_ids:
            self.dispatcher.resolve(nt.ENTITY_INVOICE, invoice_id, [nt.PAYMENT_READY])
        from Backend.Data_Access_Layer.dao.payment_dao import PaymentDAO

        for failed_payment_id in PaymentDAO(self.db).get_failed_payment_ids_for_invoices(invoice_ids):
            if failed_payment_id != payment.payment_id:
                self.dispatcher.resolve(nt.ENTITY_PAYMENT, failed_payment_id, _PAYMENT_TYPES)

    @_best_effort
    def payment_cleared(self, payment):
        self.dispatcher.resolve(nt.ENTITY_PAYMENT, payment.payment_id, _PAYMENT_TYPES)

    # =========================================================
    # System configuration
    # =========================================================

    @_best_effort
    def identity_sync_failed(self, failure):
        """A UMS/EOS identity CDC event exhausted its retries: user/role data
        in AP may be stale (approver and notification routing depend on it),
        so an Admin must resolve it. Only called once retries are EXHAUSTED -
        transient, still-retrying failures are background noise."""
        display = f"CDC-{failure.id:06d}"
        self.dispatcher.notify(
            nt.SYSTEM_CONFIGURATION_EXCEPTION,
            entity_type=nt.ENTITY_CDC_FAILURE, entity_id=failure.id, entity_display_id=display,
            message=(
                f"Identity sync for {failure.entity_type}"
                f"{' ' + failure.entity_key if failure.entity_key else ''} failed after "
                f"{failure.retry_count} retries: {(failure.error_message or 'unknown error')[:300]}. "
                "AP user/role data may be out of date - resolve the sync failure."
            ),
            event_id="retries-exhausted", actor_user_id=None, owners=None,
            metadata={"entity_type": failure.entity_type, "entity_key": failure.entity_key,
                      "kafka_topic": failure.kafka_topic, "failure_type": failure.failure_type},
        )
