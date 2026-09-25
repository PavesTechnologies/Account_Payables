# Backend/Business_Layer/services/vendor_onboarding_service.py
"""PR Officer -> Vendor Intaker onboarding handoff.

Orchestration only. Vendor creation/resolution, GST verification, address,
VendorEngagement and Pre-Screen all come from the existing
``VendorIntakeService``; the screening-rule/NDA recommendation comes from the
existing ``VendorScreeningRule`` engine. Nothing in this module re-implements
any of that - it calls into it and records the resulting workflow state.

Import direction is one-way (this service -> VendorIntakeService) so there is
no circular import, and so no orchestration leaks into the route layer.

Workflow status is resolved from ``ap.status_master`` by
(module_name='VENDOR_ONBOARDING', status_code) - never a hardcoded status id -
and every move goes through ``_transition`` against ONBOARDING_TRANSITIONS,
mirroring ``ProcurementService._transition_pr``.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List, Optional

from Backend.API_Layer.interface.vendor_intake_interface import VendorIntakeCreateRequest
from Backend.Business_Layer.services.vendor_intake_service import VendorIntakeService
from Backend.Business_Layer.services.vendor_service import VendorService
from Backend.Business_Layer.utils import pr_workflow_events as events
from Backend.Data_Access_Layer.dao.vendor_onboarding_dao import VendorOnboardingDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.vendor import Vendor
from Backend.Data_Access_Layer.models.vendor_onboarding import VendorOnboardingRequest

ONBOARDING_STATUS_MODULE = "VENDOR_ONBOARDING"
PR_HISTORY_TABLE = "purchase_requisition"
ONBOARDING_HISTORY_TABLE = "vendor_onboarding_request"

PR_APPROVED_STATUS_CODE = "APPROVED"
# Completing onboarding activates the vendor it produced, so the vendor is
# usable by the workflows that require an ACTIVE vendor (RFQ invitation,
# quotation capture). Resolved by module+code like every other status.
VENDOR_ACTIVE_STATUS_CODE = "ACTIVE"

STATUS_CREATED = "CREATED"
STATUS_ASSIGNED = "ASSIGNED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_PRE_SCREEN_PENDING = "PRE_SCREEN_PENDING"
STATUS_NEED_INFORMATION = "NEED_INFORMATION"
STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"
STATUS_COMPLETED = "COMPLETED"
STATUS_CANCELLED = "CANCELLED"

ONBOARDING_TRANSITIONS = {
    STATUS_CREATED: {STATUS_ASSIGNED, STATUS_IN_PROGRESS, STATUS_CANCELLED},
    STATUS_ASSIGNED: {STATUS_IN_PROGRESS, STATUS_CANCELLED},
    STATUS_IN_PROGRESS: {
        STATUS_PRE_SCREEN_PENDING, STATUS_NEED_INFORMATION, STATUS_FAILED, STATUS_CANCELLED,
    },
    STATUS_PRE_SCREEN_PENDING: {
        STATUS_PASSED, STATUS_NEED_INFORMATION, STATUS_FAILED, STATUS_CANCELLED,
    },
    STATUS_NEED_INFORMATION: {
        STATUS_IN_PROGRESS, STATUS_PRE_SCREEN_PENDING, STATUS_CANCELLED,
    },
    STATUS_PASSED: {STATUS_COMPLETED, STATUS_CANCELLED},
    STATUS_FAILED: {STATUS_CANCELLED},
    STATUS_COMPLETED: set(),
    STATUS_CANCELLED: set(),
}

# Reaching one of these frees the PR+department+category slot for a new
# request - it is what the partial unique index keys on via closed_at.
TERMINAL_STATUS_CODES = {STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED}

# Pre-Screen result -> onboarding status
PRE_SCREEN_STATUS_MAP = {
    "PASS": STATUS_PASSED,
    "NEED_INFORMATION": STATUS_NEED_INFORMATION,
    "FAIL": STATUS_FAILED,
}

ACTION_CREATED = "CREATED"
ACTION_ASSIGNED = "ASSIGNED"
ACTION_STATUS_CHANGED = "STATUS_CHANGED"
ACTION_INTAKE_STARTED = "INTAKE_STARTED"
ACTION_PRE_SCREENED = "PRE_SCREENED"
ACTION_COMPLETED = "COMPLETED"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


@dataclass
class VendorAvailabilityResult:
    pr_id: int
    department_id: int
    purchase_category_id: int
    available: bool
    vendors: List[Vendor]


class VendorOnboardingService:
    def __init__(self, db):
        self.db = db
        self.onboarding_dao = VendorOnboardingDAO(db)

    # =========================================================
    # Vendor availability (PR Officer)
    # =========================================================

    def check_vendor_availability(
        self,
        pr_id: int,
        user_id: Optional[str] = None,
    ) -> VendorAvailabilityResult:

        pr = self._require_pr(pr_id)
        vendors = self.onboarding_dao.get_eligible_vendors(
            pr.department_id, pr.purchase_category_id
        )

        result = VendorAvailabilityResult(
            pr_id=pr.id,
            department_id=pr.department_id,
            purchase_category_id=pr.purchase_category_id,
            available=bool(vendors),
            vendors=vendors,
        )

        if user_id is not None:
            self._record_pr_history(
                pr.id,
                events.VENDOR_AVAILABILITY_CHECKED,
                user_id,
                {
                    "department_id": pr.department_id,
                    "purchase_category_id": pr.purchase_category_id,
                    "available": result.available,
                    "eligible_vendor_count": len(vendors),
                },
            )
            self.db.commit()

        return result

    # =========================================================
    # Onboarding request lifecycle
    # =========================================================

    def create_request(self, payload, user_id: str) -> VendorOnboardingRequest:
        pr = self._require_pr(payload.pr_id)

        pr_status_code = pr.status.status_code if pr.status is not None else None
        if pr_status_code != PR_APPROVED_STATUS_CODE:
            raise ValueError(
                "Vendor onboarding can only be requested for an approved purchase requisition"
            )

        # Department/category are taken from the PR itself rather than the
        # request body, so the onboarding context can never drift from the PR
        # it belongs to (and nothing is hardcoded).
        department_id = pr.department_id
        purchase_category_id = pr.purchase_category_id

        existing = self.onboarding_dao.get_open_request(
            pr.id, department_id, purchase_category_id
        )
        if existing is not None:
            raise ValueError(
                "An open vendor onboarding request already exists for this purchase requisition, "
                "department and category"
            )

        # Assigning at creation time starts the request at ASSIGNED rather
        # than CREATED, so the caller never sees a transient CREATED row for a
        # request that already has an owner.
        status = self._require_status(STATUS_ASSIGNED if payload.assigned_to else STATUS_CREATED)

        request = VendorOnboardingRequest(
            pr_id=pr.id,
            department_id=department_id,
            purchase_category_id=purchase_category_id,
            status_id=status.status_id,
            business_requirement=payload.business_requirement,
            purpose_of_onboarding=payload.purpose_of_onboarding,
            requested_vendor_name=payload.requested_vendor_name,
            requested_vendor_email=payload.requested_vendor_email,
            assigned_to=payload.assigned_to,
            created_by=user_id,
            updated_by=user_id,
        )
        request.status = status

        self.onboarding_dao.create_request(request)

        self._record_onboarding_history(
            request.id,
            ACTION_CREATED,
            user_id,
            {
                "pr_id": pr.id,
                "department_id": department_id,
                "purchase_category_id": purchase_category_id,
                "requested_vendor_name": request.requested_vendor_name,
                "assigned_to": request.assigned_to,
            },
        )
        self._record_pr_history(
            pr.id,
            events.VENDOR_ONBOARDING_REQUESTED,
            user_id,
            {"onboarding_request_id": request.id, "requested_vendor_name": request.requested_vendor_name},
        )

        self.db.commit()
        self.db.refresh(request)
        return request

    def get_request(self, request_id: int) -> VendorOnboardingRequest:
        return self._require_request(request_id)

    def list_requests(
        self,
        pr_id: Optional[int] = None,
        status_id: Optional[int] = None,
        assigned_to: Optional[str] = None,
        vendor_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[VendorOnboardingRequest]:

        return self.onboarding_dao.get_all_requests(
            pr_id=pr_id, status_id=status_id, assigned_to=assigned_to,
            vendor_id=vendor_id, skip=skip, limit=limit,
        )

    def assign(self, request_id: int, assigned_to: str, user_id: str) -> VendorOnboardingRequest:
        if not assigned_to or not assigned_to.strip():
            raise ValueError("assigned_to is required")

        request = self._require_request(request_id)
        request.assigned_to = assigned_to.strip()

        if self._status_code(request) == STATUS_CREATED:
            self._transition(request, STATUS_ASSIGNED)

        request.updated_by = user_id
        self._record_onboarding_history(
            request.id, ACTION_ASSIGNED, user_id, {"assigned_to": request.assigned_to}
        )

        self.db.commit()
        self.db.refresh(request)
        return request

    def update_status(
        self,
        request_id: int,
        status_code: str,
        user_id: str,
        reason: Optional[str] = None,
    ) -> VendorOnboardingRequest:

        request = self._require_request(request_id)
        previous = self._status_code(request)
        self._transition(request, status_code)
        request.updated_by = user_id

        self._record_onboarding_history(
            request.id,
            ACTION_STATUS_CHANGED,
            user_id,
            {"from": previous, "to": status_code, "reason": reason},
        )

        self.db.commit()
        self.db.refresh(request)
        return request

    # =========================================================
    # Existing Vendor Intake + Pre-Screen (reused, never re-implemented)
    # =========================================================

    def start(self, request_id: int, payload, user_id: str):
        """Run the EXISTING Vendor Intake for this onboarding request and link
        the resulting vendor/engagement back to it. Department, category and
        business requirement are injected from the onboarding request so the
        PR context is preserved end to end."""

        request = self._require_request(request_id)
        if request.vendor_id is not None:
            raise ValueError("Vendor intake has already been completed for this onboarding request")

        intake_payload = VendorIntakeCreateRequest(
            department_id=request.department_id,
            category_id=request.purchase_category_id,
            business_requirement=request.business_requirement,
            purpose_of_onboarding=request.purpose_of_onboarding,
            gst_registered=payload.gst_registered,
            gstin=payload.gstin,
            vendor_name=payload.vendor_name or request.requested_vendor_name,
            country_id=payload.country_id,
            address_line1=payload.address_line1,
            address_line2=payload.address_line2,
            city=payload.city,
            state=payload.state,
            postal_code=payload.postal_code,
            payment_term_id=payload.payment_term_id,
            currency_id=payload.currency_id,
            pan_number=payload.pan_number,
            phone_number=payload.phone_number,
            email=payload.email or request.requested_vendor_email,
        )

        if self._status_code(request) in {STATUS_CREATED, STATUS_ASSIGNED}:
            self._transition(request, STATUS_IN_PROGRESS)

        intake_result = VendorIntakeService(self.db).create_intake(intake_payload, user_id)

        request.vendor_id = intake_result.vendor.vendor_id
        request.engagement_id = intake_result.engagement.vendor_category_mapping_id
        request.updated_by = user_id
        self._transition(request, STATUS_PRE_SCREEN_PENDING)

        self._record_onboarding_history(
            request.id,
            ACTION_INTAKE_STARTED,
            user_id,
            {
                "vendor_id": request.vendor_id,
                "engagement_id": request.engagement_id,
                "vendor_created": intake_result.vendor_created,
                "gst_status": intake_result.gst_status,
            },
        )

        self.db.commit()
        self.db.refresh(request)
        return request, intake_result

    def run_pre_screen(self, request_id: int, user_id: str):
        """Delegate to the EXISTING Pre-Screen and map its verdict onto the
        onboarding request. Pre-Screen rules are not duplicated here."""

        request = self._require_request(request_id)
        if request.engagement_id is None:
            raise ValueError("Vendor intake must be completed before Pre-Screen can run")

        outcome = VendorIntakeService(self.db).run_pre_screen(request.engagement_id, user_id)

        target_status = PRE_SCREEN_STATUS_MAP.get(outcome.result)
        if target_status is None:
            raise ValueError(f"Unexpected Pre-Screen result '{outcome.result}'")

        if self._status_code(request) != target_status:
            self._transition(request, target_status)
        request.updated_by = user_id

        self._record_onboarding_history(
            request.id,
            ACTION_PRE_SCREENED,
            user_id,
            {
                "engagement_id": request.engagement_id,
                "result": outcome.result,
                "reason": outcome.reason,
                "nda_recommended": outcome.nda_recommended,
            },
        )

        self.db.commit()
        self.db.refresh(request)
        return request, outcome

    def complete(self, request_id: int, user_id: str) -> VendorOnboardingRequest:
        request = self._require_request(request_id)

        if request.engagement_id is None:
            raise ValueError("Vendor intake must be completed before onboarding can be completed")

        engagement = self.onboarding_dao.get_engagement(
            request.vendor_id, request.department_id, request.purchase_category_id
        )
        if engagement is None or engagement.pre_screen_status != "PASS":
            raise ValueError("Onboarding cannot be completed until Pre-Screen has passed")

        self._transition(request, STATUS_COMPLETED)
        request.updated_by = user_id

        # Activate the vendor through the EXISTING vendor service rather than
        # writing status_id here - it owns status resolution (by module+code,
        # never a hardcoded id) and the STATUS_CHANGE audit row.
        #
        # Ordering is deliberate and is what makes completion atomic: the
        # transition above and the audit row below are still pending in this
        # session, and change_status() commits the SAME session, so the
        # onboarding status change and the vendor activation land in one
        # commit. If it raises - vendor missing, or VENDOR/ACTIVE not
        # configured - nothing is committed and the route rolls the whole
        # thing back, leaving the request un-completed.
        activated = False
        if request.vendor_id is not None and not self._vendor_is_active(request.vendor_id):
            activated = True

        self._record_onboarding_history(
            request.id,
            ACTION_COMPLETED,
            user_id,
            {
                "vendor_id": request.vendor_id,
                "engagement_id": request.engagement_id,
                "vendor_activated": activated,
            },
        )

        if activated:
            VendorService(self.db).change_status(request.vendor_id, True, user_id)
        else:
            self.db.commit()

        self.db.refresh(request)
        return request

    def _vendor_is_active(self, vendor_id: int) -> bool:
        """Whether the vendor already sits in VENDOR/ACTIVE - a vendor that
        intake reused may well be active already, and re-activating it would
        add a misleading STATUS_CHANGE audit row."""

        vendor = self.onboarding_dao.get_vendor_by_id(vendor_id)
        if vendor is None or vendor.status_id is None:
            return False

        status = self.onboarding_dao.get_status_by_id(vendor.status_id)
        return status is not None and status.status_code == VENDOR_ACTIVE_STATUS_CODE

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_pr(self, pr_id: int):
        pr = self.onboarding_dao.get_pr_by_id(pr_id)
        if pr is None:
            raise ValueError("Purchase requisition not found")
        return pr

    def _require_request(self, request_id: int) -> VendorOnboardingRequest:
        request = self.onboarding_dao.get_request_by_id(request_id)
        if request is None:
            raise ValueError("Vendor onboarding request not found")
        return request

    def _require_status(self, status_code: str):
        status = self.onboarding_dao.get_status_by_module_code(
            ONBOARDING_STATUS_MODULE, status_code
        )
        if status is None:
            raise ValueError(
                f"Status '{status_code}' is not configured for module '{ONBOARDING_STATUS_MODULE}'"
            )
        return status

    @staticmethod
    def _status_code(request: VendorOnboardingRequest) -> Optional[str]:
        return request.status.status_code if request.status is not None else None

    def _transition(self, request: VendorOnboardingRequest, target_code: str) -> None:
        current_code = self._status_code(request)
        allowed = ONBOARDING_TRANSITIONS.get(current_code, set())
        if target_code not in allowed:
            raise ValueError(
                f"Vendor onboarding request cannot move from {current_code} to {target_code}"
            )

        target_status = self._require_status(target_code)
        request.status_id = target_status.status_id
        request.status = target_status

        request.closed_at = _utcnow() if target_code in TERMINAL_STATUS_CODES else None

    def _record_onboarding_history(
        self,
        request_id: int,
        action: str,
        user_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:

        values = {key: value for key, value in (metadata or {}).items() if value is not None}
        self.onboarding_dao.create_audit_log(
            AuditLog(
                table_name=ONBOARDING_HISTORY_TABLE,
                record_id=request_id,
                action=action,
                changed_by=user_id,
                new_values=values or None,
            )
        )

    def _record_pr_history(
        self,
        pr_id: int,
        event: str,
        user_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:

        values = {key: value for key, value in (metadata or {}).items() if value is not None}
        self.onboarding_dao.create_audit_log(
            AuditLog(
                table_name=PR_HISTORY_TABLE,
                record_id=pr_id,
                action=event,
                changed_by=user_id,
                new_values=values or None,
            )
        )
