# Backend/Business_Layer/services/rfq_eligibility_service.py
"""Backend-enforced RFQ eligibility gate.

The frontend may show this result, but it is never the authority: RFQService
calls ``check()`` inside both ``invite_vendors`` and ``send_rfq`` so a direct
API call cannot bypass Pre-Screen or a mandatory NDA. Gating only ``send_rfq``
would leave a hole - ``ProcurementService.create_quotation`` admits any
*invited* vendor, so invite -> quotation -> select_vendor -> PO would skip the
gate entirely.

Every rule here is read from existing state (PR status, vendor status,
VendorEngagement Pre-Screen result, the engagement's NDA decision). No
Pre-Screen or screening-rule logic is re-implemented - that lives in
VendorIntakeService/VendorScreeningRule and is only consumed here.

All checks fail closed: anything missing or unreadable blocks the RFQ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import Backend.Business_Layer.services.nda_service as nda_service_module
from Backend.Business_Layer.services.nda_service import NdaService
from Backend.Data_Access_Layer.dao.vendor_onboarding_dao import VendorOnboardingDAO

PR_ELIGIBLE_STATUS_CODES = {"APPROVED", "VENDOR_SELECTION"}
VENDOR_ACTIVE_STATUS_CODE = "ACTIVE"
PRE_SCREEN_PASS = "PASS"

# An onboarding request in any other state means onboarding is still in
# flight, so the vendor is not yet cleared for RFQ.
ONBOARDING_SETTLED_STATUS_CODES = {"COMPLETED", "CANCELLED"}

CHECK_PR = "PR"
CHECK_VENDOR = "VENDOR"
CHECK_ONBOARDING = "ONBOARDING"
CHECK_PRE_SCREEN = "PRE_SCREEN"
CHECK_NDA = "NDA"

STATUS_PASS = "PASS"
STATUS_NOT_REQUIRED = "NOT_REQUIRED"


@dataclass
class EligibilityCheck:
    check: str
    status: str
    passed: bool
    message: Optional[str] = None


@dataclass
class EligibilityResult:
    eligible: bool
    vendor_id: int
    pr_id: int
    checks: List[EligibilityCheck] = field(default_factory=list)
    failed_checks: List[EligibilityCheck] = field(default_factory=list)
    reason: Optional[str] = None


class RFQEligibilityService:
    def __init__(self, db):
        self.db = db
        self.onboarding_dao = VendorOnboardingDAO(db)
        self.nda_service = NdaService(db)

    def check(self, pr_id: int, vendor_id: int) -> EligibilityResult:
        checks: List[EligibilityCheck] = []

        pr = self.onboarding_dao.get_pr_by_id(pr_id)
        if pr is None:
            return self._result(
                pr_id, vendor_id, checks,
                [EligibilityCheck(CHECK_PR, "NOT_FOUND", False, "Purchase requisition not found.")],
            )

        pr_status_code = pr.status.status_code if pr.status is not None else None
        pr_ok = pr_status_code in PR_ELIGIBLE_STATUS_CODES
        checks.append(
            EligibilityCheck(
                CHECK_PR,
                pr_status_code or "UNKNOWN",
                pr_ok,
                None if pr_ok else "Purchase requisition is not approved.",
            )
        )

        vendor = self.onboarding_dao.get_vendor_by_id(vendor_id)
        if vendor is None:
            checks.append(EligibilityCheck(CHECK_VENDOR, "NOT_FOUND", False, "Vendor not found."))
            return self._result(pr_id, vendor_id, checks)

        vendor_status_code = vendor.status.status_code if vendor.status is not None else None
        vendor_ok = vendor_status_code == VENDOR_ACTIVE_STATUS_CODE
        checks.append(
            EligibilityCheck(
                CHECK_VENDOR,
                vendor_status_code or "UNKNOWN",
                vendor_ok,
                None if vendor_ok else "Vendor is not active.",
            )
        )

        checks.append(self._check_onboarding(pr))
        engagement = self.onboarding_dao.get_engagement(
            vendor_id, pr.department_id, pr.purchase_category_id
        )
        checks.append(self._check_pre_screen(engagement))
        checks.append(self._check_nda(engagement, vendor_id, pr))

        return self._result(pr_id, vendor_id, checks)

    def check_many(self, pr_id: int, vendor_ids: List[int]) -> List[EligibilityResult]:
        return [self.check(pr_id, vendor_id) for vendor_id in vendor_ids]

    def require_eligible(self, pr_id: int, vendor_id: int) -> EligibilityResult:
        """Raises ValueError when the vendor may not take part in this PR's RFQ.
        Used by RFQService so the gate cannot be bypassed via the API."""

        result = self.check(pr_id, vendor_id)
        if not result.eligible:
            raise ValueError(result.reason)
        return result

    # =========================================================
    # Individual checks
    # =========================================================

    def _check_onboarding(self, pr) -> EligibilityCheck:
        open_requests = self.onboarding_dao.get_open_requests_for_pr(pr.id)
        unsettled = [
            request for request in open_requests
            if request.status is None
            or request.status.status_code not in ONBOARDING_SETTLED_STATUS_CODES
        ]

        if not unsettled:
            return EligibilityCheck(CHECK_ONBOARDING, STATUS_PASS, True)

        status_code = unsettled[0].status.status_code if unsettled[0].status else "UNKNOWN"
        return EligibilityCheck(
            CHECK_ONBOARDING,
            status_code,
            False,
            "Vendor onboarding for this purchase requisition is not complete.",
        )

    @staticmethod
    def _check_pre_screen(engagement) -> EligibilityCheck:
        if engagement is None:
            return EligibilityCheck(
                CHECK_PRE_SCREEN,
                "NOT_FOUND",
                False,
                "Vendor has no engagement for this department and category.",
            )

        status = engagement.pre_screen_status
        passed = status == PRE_SCREEN_PASS
        return EligibilityCheck(
            CHECK_PRE_SCREEN,
            status or "UNKNOWN",
            passed,
            None if passed else "Vendor Pre-Screen has not passed.",
        )

    def _check_nda(self, engagement, vendor_id: int, pr) -> EligibilityCheck:
        """The NDA requirement comes from the engagement's recorded decision
        (``nda_final_required``, falling back to the screening-rule
        recommendation). When an NDA IS required, the actual ap.vendor_nda
        lifecycle decides: only a COMPLETED, in-validity, in-scope NDA clears
        the gate. Every other state - PENDING, SENT, REJECTED, EXPIRED, or no
        NDA at all - blocks. SIGNED is configurable and blocks by default."""

        if engagement is None:
            return EligibilityCheck(
                CHECK_NDA, "UNKNOWN", False, "Vendor NDA requirement could not be determined."
            )

        required = engagement.nda_final_required
        if required is None:
            required = engagement.nda_recommended

        if not required:
            return EligibilityCheck(CHECK_NDA, STATUS_NOT_REQUIRED, True)

        lookup = self.nda_service.check_existing_nda(
            vendor_id, pr.department_id, pr.purchase_category_id
        )

        if lookup.outcome == nda_service_module.LOOKUP_VALID:
            return EligibilityCheck(CHECK_NDA, nda_service_module.STATUS_COMPLETED, True)

        if lookup.outcome == nda_service_module.LOOKUP_NOT_FOUND:
            return EligibilityCheck(
                CHECK_NDA, nda_service_module.STATUS_PENDING, False,
                "Mandatory NDA is not completed.",
            )

        current_status = (
            lookup.nda.status.status_code
            if lookup.nda is not None and lookup.nda.status is not None
            else "UNKNOWN"
        )

        if (
            current_status == nda_service_module.STATUS_SIGNED
            and self._signed_is_final()
        ):
            return EligibilityCheck(CHECK_NDA, current_status, True)

        return EligibilityCheck(
            CHECK_NDA, current_status, False,
            lookup.reason or "Mandatory NDA is not completed.",
        )

    def _signed_is_final(self) -> bool:
        """Whether NDA.SIGNED is accepted as the final state instead of
        requiring COMPLETED. Read from system_configuration, defaulting to
        False so the stricter rule applies unless a deployment opts in."""

        raw = self.nda_service.nda_dao.get_config_value(
            nda_service_module.CONFIG_SIGNED_IS_FINAL
        )
        return str(raw or "").strip().upper() in {"TRUE", "1", "YES"}

    # =========================================================
    # Result assembly
    # =========================================================

    @staticmethod
    def _result(
        pr_id: int,
        vendor_id: int,
        checks: List[EligibilityCheck],
        extra_failures: Optional[List[EligibilityCheck]] = None,
    ) -> EligibilityResult:

        all_checks = list(checks) + list(extra_failures or [])
        failed = [check for check in all_checks if not check.passed]

        return EligibilityResult(
            eligible=not failed,
            vendor_id=vendor_id,
            pr_id=pr_id,
            checks=all_checks,
            failed_checks=failed,
            reason="; ".join(
                check.message or f"{check.check} check failed" for check in failed
            ) or None,
        )
