# Backend/Business_Layer/services/vendor_intake_service.py
"""Vendor Intake -> Save -> Pre-Screen -> existing Vendor Management flow.

Vendor creation itself is delegated to VendorService.create_vendor (same
validators, duplicate checks, vendor_code generation and audit trail as the
existing POST /apm/vendor endpoint - that endpoint is left completely
unchanged). GST-response parsing is delegated to
Business_Layer.utils.vendor_auto_onboarding, the only other place that
already talks to the GST verification service - nothing here re-implements
that parsing.

Transaction note: create_vendor() commits on its own (it is also a public,
independently-callable API today), so a brand-new intake that fails while
creating the *engagement* row leaves an already-committed Vendor with no
engagement yet. That is not a corrupt state - a Vendor Master with no
engagement is simply "not yet engaged for that department/category" - and
retrying the same intake call reuses that vendor (via name/GSTIN lookup)
and only needs to create the engagement. Everything from vendor resolution
through engagement creation that does NOT go through create_vendor uses
plain DAO add()+flush() and a single commit at the end of create_intake,
matching the rest of this codebase's pattern.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from Backend.API_Layer.interface.vendor_intake_interface import (
    PreScreenCheckResult,
    VendorIntakeCreateRequest,
    VendorScreeningRuleRequest,
)
from Backend.API_Layer.interface.vendor_interface import (
    VendorAddressCreateRequest,
    VendorCreateRequest,
)
from Backend.Business_Layer.services.vendor_service import VendorService
from Backend.Business_Layer.utils.extraction.normalizers import pan_from_gstin
from Backend.Business_Layer.utils.vendor_auto_onboarding import (
    build_vendor_address_from_gst,
    call_gst_search,
    extract_vendor_data_from_gst_response,
    normalize_and_validate_gstin,
)
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.Data_Access_Layer.dao.vendor_intake_dao import VendorIntakeDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorEngagement, VendorTax
from Backend.Data_Access_Layer.models.vendor_screening_rule import VendorScreeningRule

GST_ACTIVE_STATUS = "active"
VENDOR_TAX_REGISTRATION_TYPE = "GSTIN"
BLOCKED_VENDOR_STATUS_CODES = {"BLOCKED", "INACTIVE", "REJECTED"}

PRE_SCREEN_PASS = "PASS"
PRE_SCREEN_NEED_INFORMATION = "NEED_INFORMATION"
PRE_SCREEN_FAIL = "FAIL"

NDA_DOCUMENT_STATUS_PENDING = "PENDING"
NDA_DOCUMENT_STATUS_NOT_REQUIRED = "NOT_REQUIRED"

DUPLICATE_CHECK_NAME = "Duplicate/Existing Engagement Check"
ELIGIBILITY_CHECK_NAME = "Basic Eligibility Check"
BUSINESS_RULE_CHECK_NAME = "Category/Business Rule Check"


def nda_document_status(nda_required: Optional[bool]) -> Optional[str]:
    """Derived NDA document status - PENDING when an NDA is required,
    NOT_REQUIRED when it is not, None while no recommendation/decision exists
    yet. Deliberately not a stored column: NDA document generation, storage
    and delivery are out of scope, so there is no document to track a real
    status for - this is purely what the reviewer screen renders."""
    if nda_required is None:
        return None
    return NDA_DOCUMENT_STATUS_PENDING if nda_required else NDA_DOCUMENT_STATUS_NOT_REQUIRED


def _utcnow() -> datetime.datetime:
    """Naive UTC now, matching pre_screen_checked_at/nda_decided_at's plain
    (non-timezone-aware) DateTime columns - datetime.utcnow() is deprecated,
    this is the direct non-deprecated equivalent."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


@dataclass
class IntakeResult:
    engagement: VendorEngagement
    vendor: Vendor
    vendor_created: bool
    gst_status: Optional[str] = None


@dataclass
class PreScreenOutcome:
    engagement: VendorEngagement
    result: str
    reason: Optional[str]
    checks: List[PreScreenCheckResult] = field(default_factory=list)
    nda_recommended: bool = False


class VendorIntakeService:
    def __init__(self, db):
        self.db = db
        self.vendor_dao = VendorDAO(db)
        self.intake_dao = VendorIntakeDAO(db)

    # =========================================================
    # Vendor Intake (Save)
    # =========================================================

    def create_intake(self, payload: VendorIntakeCreateRequest, user_id: str) -> IntakeResult:
        department = self._require_active_department(payload.department_id)
        category = self._require_active_category_in_department(payload.category_id, payload.department_id)

        gst_status: Optional[str] = None

        if payload.gst_registered:
            if not payload.gstin:
                raise ValueError("gstin is required when gst_registered is true")
            vendor, vendor_created, gst_status = self._resolve_vendor_via_gst(payload, user_id)
        else:
            if payload.gstin:
                raise ValueError("gstin must not be provided when gst_registered is false")
            vendor, vendor_created = self._resolve_vendor_manual(payload, user_id)

        if self.intake_dao.get_engagement(vendor.vendor_id, department.id, category.id) is not None:
            raise ValueError(
                "An engagement already exists for this vendor in the selected department and category"
            )

        engagement = VendorEngagement(
            vendor_id=vendor.vendor_id,
            department_id=department.id,
            purchase_category_id=category.id,
            business_requirement=payload.business_requirement,
            purpose_of_onboarding=payload.purpose_of_onboarding,
            pre_screen_status="PENDING",
            created_by=user_id,
            updated_by=user_id,
        )
        self.intake_dao.create_engagement(engagement)

        self.vendor_dao.create_audit_log(
            AuditLog(
                table_name="vendor_category_mapping",
                record_id=engagement.vendor_category_mapping_id,
                action="CREATE",
                changed_by=user_id,
                new_values={
                    "vendor_id": vendor.vendor_id,
                    "department_id": department.id,
                    "purchase_category_id": category.id,
                    "business_requirement": engagement.business_requirement,
                    "purpose_of_onboarding": engagement.purpose_of_onboarding,
                },
            )
        )

        self.db.commit()
        self.db.refresh(engagement)

        return IntakeResult(
            engagement=engagement,
            vendor=vendor,
            vendor_created=vendor_created,
            gst_status=gst_status,
        )

    def _require_active_department(self, department_id: int):
        department = self.intake_dao.get_department_by_id(department_id)
        if department is None:
            raise ValueError("Department not found for the given department_id")
        if not department.is_active:
            raise ValueError("Department is not active")
        return department

    def _require_active_category_in_department(self, category_id: int, department_id: int):
        category = self.intake_dao.get_purchase_category_by_id(category_id)
        if category is None:
            raise ValueError("Purchase category not found for the given category_id")
        if not category.is_active:
            raise ValueError("Purchase category is not active")
        if category.department_id != department_id:
            raise ValueError("Purchase category does not belong to the selected department")
        return category

    def _resolve_vendor_via_gst(self, payload: VendorIntakeCreateRequest, user_id: str):
        gstin = normalize_and_validate_gstin(payload.gstin)
        if gstin is None:
            raise ValueError("gstin is not a validly formatted GSTIN")

        gst_result = call_gst_search(gstin)
        if not gst_result.verified:
            raise ValueError(
                f"GST verification failed for '{gstin}': {gst_result.error_message or 'verification unsuccessful'}"
            )

        gst_details = extract_vendor_data_from_gst_response(gst_result.data)
        if gst_details is None:
            raise ValueError("GST verification response is incomplete or could not be parsed")
        if gst_details["gstin"] != gstin:
            raise ValueError("GST verification response GSTIN does not match the requested GSTIN")
        if gst_details["status"].strip().lower() != GST_ACTIVE_STATUS:
            raise ValueError(f"GST registration status is '{gst_details['status']}', not Active")

        existing_vendor = self.vendor_dao.get_vendor_by_gstin(gstin)
        if existing_vendor is not None:
            return existing_vendor, False, gst_details["status"]

        # PAN is derived from the GSTIN's own structure (positions 3-12), never
        # read out of the GST API response - that response is not assumed to
        # carry a PAN. A PAN typed on the intake form is only a fallback, since
        # the verified GSTIN is the authoritative source.
        try:
            pan_number = pan_from_gstin(gstin)
        except ValueError:
            pan_number = None
        pan_number = pan_number or payload.pan_number

        vendor_service = VendorService(self.db)
        create_request = VendorCreateRequest(
            vendor_name=gst_details["vendor_name"],
            country_id=payload.country_id,
            payment_term_id=payload.payment_term_id,
            currency_id=payload.currency_id,
            pan_number=pan_number,
            phone_number=payload.phone_number,
            email=payload.email,
            gstin=gstin,
        )
        vendor = vendor_service.create_vendor(create_request, user_id)

        address = build_vendor_address_from_gst(
            gst_details, vendor_id=vendor.vendor_id, country_id=payload.country_id
        )
        if address is None:
            raise ValueError("GST address became unavailable while creating the vendor address")
        self.vendor_dao.create_vendor_address(address)

        tax = VendorTax(
            vendor_address_id=address.vendor_address_id,
            registration_type=VENDOR_TAX_REGISTRATION_TYPE,
            registration_number=gstin,
            is_verified=True,
        )
        self.vendor_dao.create_vendor_tax(tax)
        self.db.commit()

        return vendor, True, gst_details["status"]

    def _resolve_vendor_manual(self, payload: VendorIntakeCreateRequest, user_id: str):
        if not payload.vendor_name or not payload.vendor_name.strip():
            raise ValueError("vendor_name is required when gst_registered is false")

        existing_vendor = self.vendor_dao.get_vendor_by_name(payload.vendor_name)
        if existing_vendor is not None:
            return existing_vendor, False

        vendor_service = VendorService(self.db)
        create_request = VendorCreateRequest(
            vendor_name=payload.vendor_name,
            country_id=payload.country_id,
            payment_term_id=payload.payment_term_id,
            currency_id=payload.currency_id,
            pan_number=payload.pan_number,
            phone_number=payload.phone_number,
            email=payload.email,
        )
        vendor = vendor_service.create_vendor(create_request, user_id)

        # Reuses the existing address implementation (the same
        # VendorService.create_address behind POST /apm/vendor/{id}/addresses),
        # so intake gets its field validation, primary-address handling and
        # audit row for free. Still guarded: an intake with no address saves
        # fine and is caught later by Pre-Screen as NEED_INFORMATION.
        if payload.address_line1 and payload.city:
            vendor_service.create_address(
                vendor.vendor_id,
                VendorAddressCreateRequest(
                    address_type="REGISTERED",
                    address_line1=payload.address_line1,
                    address_line2=payload.address_line2,
                    city=payload.city,
                    state=payload.state,
                    postal_code=payload.postal_code,
                    country_id=payload.country_id,
                    is_primary=True,
                ),
                user_id,
            )

        return vendor, True

    # =========================================================
    # Pre-Screen
    # =========================================================

    def run_pre_screen(self, engagement_id: int, user_id: str) -> PreScreenOutcome:
        engagement = self._require_engagement(engagement_id)

        checks: List[PreScreenCheckResult] = []

        duplicate = self.intake_dao.get_other_engagement(
            engagement.vendor_category_mapping_id,
            engagement.vendor_id,
            engagement.department_id,
            engagement.purchase_category_id,
        )
        duplicate_passed = duplicate is None
        duplicate_reason = (
            None
            if duplicate_passed
            else "A duplicate engagement already exists for this vendor, department and category"
        )
        checks.append(
            PreScreenCheckResult(
                name=DUPLICATE_CHECK_NAME,
                passed=duplicate_passed,
                status=PRE_SCREEN_PASS if duplicate_passed else PRE_SCREEN_FAIL,
                reason=duplicate_reason,
            )
        )

        vendor = self.vendor_dao.get_vendor_by_id(engagement.vendor_id)
        if vendor is None:
            raise ValueError("Vendor not found for this engagement")

        blocked = False
        if vendor.status_id is not None:
            status = self.vendor_dao.get_status_by_id(vendor.status_id)
            blocked = status is not None and status.status_code in BLOCKED_VENDOR_STATUS_CODES

        has_address = len(self.vendor_dao.get_addresses_by_vendor(engagement.vendor_id)) > 0

        if blocked:
            eligibility_reason = "Vendor is blocked/inactive and is not eligible for onboarding"
            eligibility_status = PRE_SCREEN_FAIL
        elif not has_address:
            eligibility_reason = "Vendor intake data is incomplete: no registered address on file"
            eligibility_status = PRE_SCREEN_NEED_INFORMATION
        else:
            eligibility_reason = None
            eligibility_status = PRE_SCREEN_PASS
        eligibility_passed = not blocked and has_address
        checks.append(
            PreScreenCheckResult(
                name=ELIGIBILITY_CHECK_NAME,
                passed=eligibility_passed,
                status=eligibility_status,
                reason=eligibility_reason,
            )
        )

        nda_recommended = self._resolve_nda_recommendation(
            engagement.department_id, engagement.purchase_category_id
        )
        checks.append(
            PreScreenCheckResult(
                name=BUSINESS_RULE_CHECK_NAME,
                passed=True,
                status=PRE_SCREEN_PASS,
                reason=f"NDA {'recommended' if nda_recommended else 'not required'} for this department/category",
            )
        )

        if not duplicate_passed:
            result, reason = PRE_SCREEN_FAIL, duplicate_reason
        elif blocked:
            result, reason = PRE_SCREEN_FAIL, eligibility_reason
        elif not has_address:
            result, reason = PRE_SCREEN_NEED_INFORMATION, eligibility_reason
        else:
            result, reason = PRE_SCREEN_PASS, None

        engagement.pre_screen_status = result
        engagement.pre_screen_result_reason = reason
        engagement.pre_screen_checked_at = _utcnow()
        engagement.nda_recommended = nda_recommended
        engagement.updated_by = user_id

        self.db.commit()
        self.db.refresh(engagement)

        return PreScreenOutcome(
            engagement=engagement, result=result, reason=reason, checks=checks, nda_recommended=nda_recommended
        )

    def _resolve_nda_recommendation(self, department_id: int, purchase_category_id: int) -> bool:
        rules = self.intake_dao.get_active_screening_rules_for_scope(department_id, purchase_category_id)
        if not rules:
            return False

        def _specificity(rule: VendorScreeningRule) -> int:
            return int(rule.department_id is not None) + int(rule.purchase_category_id is not None)

        best = max(rules, key=_specificity)
        return bool(best.requires_nda)

    # =========================================================
    # NDA Decision
    # =========================================================

    def set_nda_decision(
        self,
        engagement_id: int,
        override_required: Optional[bool],
        reason: Optional[str],
        user_id: str,
    ) -> VendorEngagement:

        engagement = self._require_engagement(engagement_id)

        if override_required is None:
            if engagement.nda_recommended is None:
                raise ValueError("Run Pre-Screen before accepting the NDA recommendation")
            engagement.nda_override = None
            engagement.nda_override_reason = None
            engagement.nda_final_required = engagement.nda_recommended
        else:
            if not reason or not reason.strip():
                raise ValueError("A reason is required when overriding the NDA recommendation")
            engagement.nda_override = override_required
            engagement.nda_override_reason = reason.strip()
            engagement.nda_final_required = override_required

        engagement.nda_decided_by = user_id
        engagement.nda_decided_at = _utcnow()
        engagement.updated_by = user_id

        self.db.commit()
        self.db.refresh(engagement)

        return engagement

    # =========================================================
    # Vendor Engagement lookups
    # =========================================================

    def get_engagement(self, engagement_id: int) -> VendorEngagement:
        return self._require_engagement(engagement_id)

    def list_engagements_for_vendor(self, vendor_id: int) -> List[VendorEngagement]:
        if not self.vendor_dao.vendor_exists(vendor_id):
            raise ValueError("Vendor not found")
        return self.intake_dao.get_engagements_by_vendor(vendor_id)

    def _require_engagement(self, engagement_id: int) -> VendorEngagement:
        engagement = self.intake_dao.get_engagement_by_id(engagement_id)
        if engagement is None:
            raise ValueError("Vendor engagement not found")
        return engagement

    # =========================================================
    # Vendor Screening Rule (Business Rule Engine admin config)
    # =========================================================

    def create_screening_rule(self, payload: VendorScreeningRuleRequest, user_id: str) -> VendorScreeningRule:
        self._validate_screening_rule_scope(payload)

        if self.intake_dao.get_screening_rule_by_name(payload.name) is not None:
            raise ValueError("A screening rule with this name already exists")

        rule = VendorScreeningRule(
            name=payload.name,
            department_id=payload.department_id,
            purchase_category_id=payload.purchase_category_id,
            requires_nda=payload.requires_nda,
            is_default=payload.is_default,
            is_active=payload.is_active,
            description=payload.description,
            created_by=user_id,
            updated_by=user_id,
        )
        self.intake_dao.create_screening_rule(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def list_screening_rules(self) -> List[VendorScreeningRule]:
        return self.intake_dao.get_all_screening_rules()

    def update_screening_rule(
        self, rule_id: int, payload: VendorScreeningRuleRequest, user_id: str
    ) -> VendorScreeningRule:
        rule = self.intake_dao.get_screening_rule_by_id(rule_id)
        if rule is None:
            raise ValueError("Screening rule not found")

        self._validate_screening_rule_scope(payload)

        existing = self.intake_dao.get_screening_rule_by_name(payload.name)
        if existing is not None and existing.id != rule_id:
            raise ValueError("A screening rule with this name already exists")

        rule.name = payload.name
        rule.department_id = payload.department_id
        rule.purchase_category_id = payload.purchase_category_id
        rule.requires_nda = payload.requires_nda
        rule.is_default = payload.is_default
        rule.is_active = payload.is_active
        rule.description = payload.description
        rule.updated_by = user_id

        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _validate_screening_rule_scope(self, payload: VendorScreeningRuleRequest) -> None:
        if payload.is_default and (payload.department_id is not None or payload.purchase_category_id is not None):
            raise ValueError("A default screening rule must not be scoped to a department or category")

        if payload.department_id is not None:
            if self.intake_dao.get_department_by_id(payload.department_id) is None:
                raise ValueError("Department not found for the given department_id")

        if payload.purchase_category_id is not None:
            category = self.intake_dao.get_purchase_category_by_id(payload.purchase_category_id)
            if category is None:
                raise ValueError("Purchase category not found for the given purchase_category_id")
            if payload.department_id is not None and category.department_id != payload.department_id:
                raise ValueError("Purchase category does not belong to the selected department")
