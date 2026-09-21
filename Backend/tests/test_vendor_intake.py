# Backend/tests/test_vendor_intake.py
"""Unit tests for Vendor Intake -> Save -> Pre-Screen.

Follows the project's existing fake-DAO test style (see
test_purchase_category_department.py / test_vendor_auto_onboarding.py):
no real DB connection, no real GST network call. VendorIntakeService's own
DAOs (vendor_dao / intake_dao) are swapped for fakes after construction
(same trick as test_purchase_category_department.py's `service.master_dao
= dao`); the internal `VendorService(self.db)` / `call_gst_search` calls
are monkeypatched at the vendor_intake_service module level.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import pytest

import Backend.Business_Layer.services.vendor_intake_service as vis
from Backend.Business_Layer.utils.vendor_auto_onboarding import GSTVerificationResult
from Backend.Business_Layer.services.vendor_intake_service import VendorIntakeService
from Backend.API_Layer.interface.vendor_intake_interface import (
    NdaDecisionRequest,
    VendorIntakeCreateRequest,
    VendorScreeningRuleRequest,
)

VALID_GSTIN = "07AAJCA9880A1ZL"


def _gst_response(status_cd="1", sts="Active", trade_name="ACME INDIA PRIVATE LIMITED",
                   legal_name="ACME INDIA PRIVATE LIMITED LGL", gstin=VALID_GSTIN):
    addr = {
        "bnm": "", "loc": "NEHRU PLACE", "st": "International Trade Tower",
        "bno": "Block E", "dst": "South Delhi", "pncd": "110019",
        "stcd": "Delhi", "flno": "14th Floor",
    }
    return {
        "data": {
            "data": {
                "gstin": gstin, "sts": sts, "tradeNam": trade_name, "lgnm": legal_name,
                "pradr": {"addr": addr},
            },
            "status_cd": status_cd,
        }
    }


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDB:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeVendorService:
    """Stands in for the real VendorService(db) instantiated inside
    VendorIntakeService - avoids needing a real DB session for vendor
    creation, mirroring test_vendor_auto_onboarding.py's _FakeVendorService.

    Registers every vendor it "creates" into the shared FakeVendorDAO (set
    by the `env` fixture before each test) so that a subsequent lookup by
    name/GSTIN/id - exactly as the real VendorService and VendorDAO would
    see each other's writes through the same DB session - finds it.
    """

    created_requests = []
    vendor_dao = None

    def __init__(self, db):
        self.db = db

    def create_vendor(self, request, user_id):
        FakeVendorService.created_requests.append((request, user_id))
        vendor_id = FakeVendorService.vendor_dao.next_vendor_id()
        vendor = SimpleNamespace(vendor_id=vendor_id, vendor_name=request.vendor_name, status_id=1)
        FakeVendorService.vendor_dao.register_vendor(vendor, gstin=request.gstin)
        return vendor

    def create_address(self, vendor_id, request, user_id):
        """Mirrors the real VendorService.create_address the manual intake
        path now delegates to (POST /apm/vendor/{id}/addresses' implementation)."""
        address = SimpleNamespace(
            vendor_id=vendor_id,
            address_type=request.address_type,
            address_line1=request.address_line1,
            address_line2=request.address_line2,
            city=request.city,
            state=request.state,
            postal_code=request.postal_code,
            country_id=request.country_id,
            is_primary=request.is_primary,
        )
        FakeVendorService.vendor_dao.create_vendor_address(address)
        return address


class FakeVendorDAO:
    def __init__(self):
        self.vendors_by_id: Dict[int, object] = {}
        self.vendors_by_gstin: Dict[str, object] = {}
        self.vendors_by_name: Dict[str, object] = {}
        self.addresses: Dict[int, list] = {}
        self.statuses: Dict[int, object] = {}
        self.created_addresses = []
        self.created_taxes = []
        self.audit_logs = []
        self._next_address_id = 500
        self._next_vendor_id = 1000

    def next_vendor_id(self) -> int:
        vendor_id = self._next_vendor_id
        self._next_vendor_id += 1
        return vendor_id

    def register_vendor(self, vendor, gstin: Optional[str] = None) -> None:
        self.vendors_by_id[vendor.vendor_id] = vendor
        self.vendors_by_name[vendor.vendor_name.strip().lower()] = vendor
        if gstin:
            self.vendors_by_gstin[gstin] = vendor

    def get_vendor_by_gstin(self, gstin, exclude_vendor_id=None):
        return self.vendors_by_gstin.get(gstin)

    def get_vendor_by_name(self, vendor_name):
        return self.vendors_by_name.get(vendor_name.strip().lower())

    def vendor_exists(self, vendor_id):
        return vendor_id in self.vendors_by_id

    def get_vendor_by_id(self, vendor_id):
        return self.vendors_by_id.get(vendor_id)

    def get_status_by_id(self, status_id):
        return self.statuses.get(status_id)

    def get_addresses_by_vendor(self, vendor_id):
        return self.addresses.get(vendor_id, [])

    def create_vendor_address(self, address):
        address.vendor_address_id = self._next_address_id
        self._next_address_id += 1
        self.created_addresses.append(address)
        self.addresses.setdefault(address.vendor_id, []).append(address)
        return address

    def create_vendor_tax(self, tax):
        self.created_taxes.append(tax)
        return tax

    def create_audit_log(self, audit_log):
        self.audit_logs.append(audit_log)
        return audit_log


class FakeVendorIntakeDAO:
    def __init__(self, departments: dict, categories: dict):
        self.departments = departments
        self.categories = categories
        self.engagements: Dict[Tuple[int, int, int], object] = {}
        self.engagements_by_id: Dict[int, object] = {}
        self.rules: Dict[int, object] = {}
        self._next_engagement_id = 1
        self._next_rule_id = 1

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)

    def get_purchase_category_by_id(self, category_id):
        return self.categories.get(category_id)

    def get_engagement(self, vendor_id, department_id, purchase_category_id):
        return self.engagements.get((vendor_id, department_id, purchase_category_id))

    def get_engagement_by_id(self, engagement_id):
        return self.engagements_by_id.get(engagement_id)

    def get_other_engagement(self, engagement_id, vendor_id, department_id, purchase_category_id):
        existing = self.engagements.get((vendor_id, department_id, purchase_category_id))
        if existing is not None and existing.vendor_category_mapping_id != engagement_id:
            return existing
        return None

    def get_engagements_by_vendor(self, vendor_id):
        return [e for e in self.engagements_by_id.values() if e.vendor_id == vendor_id]

    def create_engagement(self, engagement):
        engagement.vendor_category_mapping_id = self._next_engagement_id
        self._next_engagement_id += 1
        key = (engagement.vendor_id, engagement.department_id, engagement.purchase_category_id)
        self.engagements[key] = engagement
        self.engagements_by_id[engagement.vendor_category_mapping_id] = engagement
        return engagement

    def create_screening_rule(self, rule):
        rule.id = self._next_rule_id
        self._next_rule_id += 1
        self.rules[rule.id] = rule
        return rule

    def get_screening_rule_by_id(self, rule_id):
        return self.rules.get(rule_id)

    def get_screening_rule_by_name(self, name):
        for r in self.rules.values():
            if r.name == name:
                return r
        return None

    def get_all_screening_rules(self):
        return list(self.rules.values())

    def get_active_screening_rules_for_scope(self, department_id, purchase_category_id):
        return [
            r for r in self.rules.values()
            if r.is_active
            and (r.department_id is None or r.department_id == department_id)
            and (r.purchase_category_id is None or r.purchase_category_id == purchase_category_id)
        ]


def _engagement(vendor_id, department_id, category_id, **overrides):
    defaults = dict(
        vendor_category_mapping_id=None,
        vendor_id=vendor_id,
        department_id=department_id,
        purchase_category_id=category_id,
        purpose_of_onboarding=None,
        pre_screen_status="PENDING",
        pre_screen_result_reason=None,
        pre_screen_checked_at=None,
        nda_recommended=None,
        nda_override=None,
        nda_override_reason=None,
        nda_final_required=None,
        nda_decided_by=None,
        nda_decided_at=None,
        updated_by=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _rule(rule_id, name, department_id=None, purchase_category_id=None, requires_nda=False,
          is_default=False, is_active=True):
    return SimpleNamespace(
        id=rule_id, name=name, department_id=department_id, purchase_category_id=purchase_category_id,
        requires_nda=requires_nda, is_default=is_default, is_active=is_active, description=None,
    )


@pytest.fixture
def env(monkeypatch):
    departments = {
        1: SimpleNamespace(id=1, code="IT", is_active=True),
        2: SimpleNamespace(id=2, code="HR", is_active=False),
        3: SimpleNamespace(id=3, code="FIN", is_active=True),
    }
    categories = {
        10: SimpleNamespace(id=10, code="IT_HW", is_active=True, department_id=1),
        11: SimpleNamespace(id=11, code="IT_SW", is_active=True, department_id=1),
        12: SimpleNamespace(id=12, code="IT_OLD", is_active=False, department_id=1),
        13: SimpleNamespace(id=13, code="HR_REC", is_active=True, department_id=2),
        14: SimpleNamespace(id=14, code="FIN_AUDIT", is_active=True, department_id=3),
    }

    service = VendorIntakeService(db=FakeDB())
    vendor_dao = FakeVendorDAO()
    intake_dao = FakeVendorIntakeDAO(departments, categories)
    service.vendor_dao = vendor_dao
    service.intake_dao = intake_dao

    FakeVendorService.created_requests = []
    FakeVendorService.vendor_dao = vendor_dao
    monkeypatch.setattr(vis, "VendorService", FakeVendorService)

    return SimpleNamespace(service=service, vendor_dao=vendor_dao, intake_dao=intake_dao,
                            departments=departments, categories=categories)


def _manual_payload(**overrides):
    defaults = dict(
        department_id=1, category_id=10,
        business_requirement="Replace end-of-life developer laptops",
        purpose_of_onboarding="New laptops",
        gst_registered=False, gstin=None, vendor_name="Manual Vendor Co", country_id=10,
        address_line1="123 Street", address_line2=None, city="Delhi", state=None, postal_code=None,
        payment_term_id=None, currency_id=None, pan_number=None, phone_number=None, email=None,
    )
    defaults.update(overrides)
    return VendorIntakeCreateRequest(**defaults)


def _gst_payload(**overrides):
    defaults = dict(
        department_id=1, category_id=10,
        business_requirement="Cloud hosting capacity",
        purpose_of_onboarding="New laptops",
        gst_registered=True, gstin=VALID_GSTIN, vendor_name=None, country_id=10,
        payment_term_id=None, currency_id=None, pan_number=None, phone_number=None, email=None,
    )
    defaults.update(overrides)
    return VendorIntakeCreateRequest(**defaults)


# ---------------------------------------------------------------------------
# GST Yes / No
# ---------------------------------------------------------------------------


def test_gst_yes_successful_verification_creates_vendor_and_engagement(env, monkeypatch):
    monkeypatch.setattr(vis, "call_gst_search", lambda gstin: GSTVerificationResult(verified=True, data=_gst_response()))

    result = env.service.create_intake(_gst_payload(), "user-1")

    assert result.vendor_created is True
    assert result.gst_status == "Active"
    assert FakeVendorService.created_requests[0][0].vendor_name == "ACME INDIA PRIVATE LIMITED"
    assert FakeVendorService.created_requests[0][0].gstin == VALID_GSTIN
    assert len(env.vendor_dao.created_addresses) == 1
    assert env.vendor_dao.created_taxes[0].registration_type == "GSTIN"
    assert env.vendor_dao.created_taxes[0].is_verified is True
    assert result.engagement.pre_screen_status == "PENDING"


def test_gst_yes_failed_verification_raises(env, monkeypatch):
    monkeypatch.setattr(
        vis, "call_gst_search",
        lambda gstin: GSTVerificationResult(verified=False, error_message="service unavailable"),
    )

    with pytest.raises(ValueError, match="GST verification failed"):
        env.service.create_intake(_gst_payload(), "user-1")

    assert env.vendor_dao.created_addresses == []


def test_gst_yes_inactive_status_raises(env, monkeypatch):
    monkeypatch.setattr(
        vis, "call_gst_search",
        lambda gstin: GSTVerificationResult(verified=True, data=_gst_response(sts="Cancelled")),
    )

    with pytest.raises(ValueError, match="not Active"):
        env.service.create_intake(_gst_payload(), "user-1")


def test_gst_yes_without_gstin_is_rejected(env):
    with pytest.raises(ValueError, match="gstin is required"):
        env.service.create_intake(_gst_payload(gstin=None), "user-1")


def test_gst_no_manual_flow_creates_vendor(env):
    result = env.service.create_intake(_manual_payload(), "user-1")

    assert result.vendor_created is True
    assert FakeVendorService.created_requests[0][0].vendor_name == "Manual Vendor Co"
    assert FakeVendorService.created_requests[0][0].gstin is None
    assert len(env.vendor_dao.created_addresses) == 1


def test_gst_no_with_gstin_supplied_is_rejected(env):
    with pytest.raises(ValueError, match="must not be provided"):
        env.service.create_intake(_manual_payload(gstin=VALID_GSTIN), "user-1")


# ---------------------------------------------------------------------------
# Department / Category validation
# ---------------------------------------------------------------------------


def test_inactive_department_is_rejected(env):
    with pytest.raises(ValueError, match="not active"):
        env.service.create_intake(_manual_payload(department_id=2, category_id=13), "user-1")


def test_inactive_category_is_rejected(env):
    with pytest.raises(ValueError, match="not active"):
        env.service.create_intake(_manual_payload(category_id=12), "user-1")


def test_category_belonging_to_different_department_is_rejected(env):
    with pytest.raises(ValueError, match="does not belong"):
        env.service.create_intake(_manual_payload(department_id=1, category_id=13), "user-1")


# ---------------------------------------------------------------------------
# Duplicate vs. new engagement / vendor reuse
# ---------------------------------------------------------------------------


def test_same_vendor_same_department_and_category_is_duplicate(env):
    env.service.create_intake(_manual_payload(vendor_name="Repeat Co"), "user-1")

    with pytest.raises(ValueError, match="already exists"):
        env.service.create_intake(_manual_payload(vendor_name="Repeat Co"), "user-1")


def test_same_vendor_different_category_reuses_vendor_new_engagement(env):
    first = env.service.create_intake(_manual_payload(vendor_name="Multi Co", category_id=10), "user-1")

    second = env.service.create_intake(_manual_payload(vendor_name="Multi Co", category_id=11), "user-1")

    assert second.vendor_created is False
    assert second.vendor.vendor_id == first.vendor.vendor_id
    assert len(FakeVendorService.created_requests) == 1


# ---------------------------------------------------------------------------
# Pre-Screen
# ---------------------------------------------------------------------------


def test_pre_screen_pass(env):
    result = env.service.create_intake(_manual_payload(vendor_name="Good Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")

    outcome = env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    assert outcome.result == "PASS"
    assert outcome.reason is None
    assert outcome.nda_recommended is False


def test_pre_screen_blocked_vendor_fails(env):
    result = env.service.create_intake(_manual_payload(vendor_name="Blocked Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="BLOCKED")

    outcome = env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    assert outcome.result == "FAIL"
    assert "blocked" in outcome.reason.lower()


def test_pre_screen_missing_address_needs_information(env):
    result = env.service.create_intake(_manual_payload(vendor_name="No Address Co", address_line1=None, city=None), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")

    outcome = env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    assert outcome.result == "NEED_INFORMATION"
    assert "incomplete" in outcome.reason.lower()


def test_pre_screen_missing_engagement_raises(env):
    with pytest.raises(ValueError, match="not found"):
        env.service.run_pre_screen(9999, "user-1")


# ---------------------------------------------------------------------------
# Business Rule Engine (NDA recommendation)
# ---------------------------------------------------------------------------


def test_nda_recommended_for_specific_department_and_category(env):
    env.intake_dao.create_screening_rule(_rule(None, "IT+HW requires NDA", department_id=1, purchase_category_id=10, requires_nda=True))
    result = env.service.create_intake(_manual_payload(vendor_name="NDA Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")

    outcome = env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    assert outcome.nda_recommended is True
    assert outcome.result == "PASS"  # NDA recommendation never blocks Pre-Screen


def test_nda_not_recommended_when_no_rule_matches(env):
    result = env.service.create_intake(_manual_payload(vendor_name="No Rule Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")

    outcome = env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    assert outcome.nda_recommended is False


def test_more_specific_rule_wins_over_department_wide_rule(env):
    env.intake_dao.create_screening_rule(_rule(None, "IT wide - no NDA", department_id=1, requires_nda=False))
    env.intake_dao.create_screening_rule(_rule(None, "IT+HW - NDA", department_id=1, purchase_category_id=10, requires_nda=True))
    result = env.service.create_intake(_manual_payload(vendor_name="Specific Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")

    outcome = env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    assert outcome.nda_recommended is True


# ---------------------------------------------------------------------------
# NDA override
# ---------------------------------------------------------------------------


def test_nda_override_with_reason_succeeds(env):
    result = env.service.create_intake(_manual_payload(vendor_name="Override Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")
    env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    engagement = env.service.set_nda_decision(
        result.engagement.vendor_category_mapping_id, True, "Contains sensitive pricing data", "reviewer-1"
    )

    assert engagement.nda_override is True
    assert engagement.nda_final_required is True
    assert engagement.nda_override_reason == "Contains sensitive pricing data"


def test_nda_override_without_reason_raises(env):
    result = env.service.create_intake(_manual_payload(vendor_name="Override Co 2"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")
    env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    with pytest.raises(ValueError, match="reason is required"):
        env.service.set_nda_decision(result.engagement.vendor_category_mapping_id, False, None, "reviewer-1")


def test_nda_accept_recommendation_without_override(env):
    env.intake_dao.create_screening_rule(_rule(None, "IT+HW requires NDA", department_id=1, purchase_category_id=10, requires_nda=True))
    result = env.service.create_intake(_manual_payload(vendor_name="Accept Co"), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")
    env.service.run_pre_screen(result.engagement.vendor_category_mapping_id, "user-1")

    engagement = env.service.set_nda_decision(result.engagement.vendor_category_mapping_id, None, None, "reviewer-1")

    assert engagement.nda_override is None
    assert engagement.nda_final_required is True


def test_nda_decision_before_pre_screen_is_rejected(env):
    result = env.service.create_intake(_manual_payload(vendor_name="Too Early Co"), "user-1")

    with pytest.raises(ValueError, match="Run Pre-Screen"):
        env.service.set_nda_decision(result.engagement.vendor_category_mapping_id, None, None, "reviewer-1")


# ---------------------------------------------------------------------------
# Onboarding data persistence (business_requirement / purpose / address)
# ---------------------------------------------------------------------------


def test_business_requirement_and_purpose_are_persisted_separately(env):
    result = env.service.create_intake(
        _manual_payload(
            vendor_name="Fields Co",
            business_requirement="Replace end-of-life developer laptops",
            purpose_of_onboarding="Preferred reseller with fastest lead time",
        ),
        "user-1",
    )

    assert result.engagement.business_requirement == "Replace end-of-life developer laptops"
    assert result.engagement.purpose_of_onboarding == "Preferred reseller with fastest lead time"


def test_business_requirement_is_optional(env):
    result = env.service.create_intake(
        _manual_payload(vendor_name="No Req Co", business_requirement=None), "user-1"
    )

    assert result.engagement.business_requirement is None


def test_address_is_persisted_via_existing_address_implementation(env):
    env.service.create_intake(
        _manual_payload(
            vendor_name="Address Co",
            address_line1="42 Industrial Estate",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
        ),
        "user-1",
    )

    address = env.vendor_dao.created_addresses[0]
    assert address.address_line1 == "42 Industrial Estate"
    assert address.city == "Pune"
    assert address.state == "Maharashtra"
    assert address.postal_code == "411001"
    assert address.address_type == "REGISTERED"
    assert address.is_primary is True
    assert address.country_id == 10


def test_gst_address_is_persisted_from_gst_response(env, monkeypatch):
    monkeypatch.setattr(vis, "call_gst_search", lambda gstin: GSTVerificationResult(verified=True, data=_gst_response()))

    env.service.create_intake(_gst_payload(), "user-1")

    address = env.vendor_dao.created_addresses[0]
    assert address.city == "South Delhi"
    assert address.state == "Delhi"
    assert address.postal_code == "110019"


# ---------------------------------------------------------------------------
# Engagement scoping: same vendor across departments/categories
# ---------------------------------------------------------------------------


def test_same_vendor_different_department_reuses_vendor_new_engagement(env):
    first = env.service.create_intake(
        _manual_payload(vendor_name="Cross Dept Co", department_id=1, category_id=10), "user-1"
    )

    second = env.service.create_intake(
        _manual_payload(vendor_name="Cross Dept Co", department_id=3, category_id=14), "user-1"
    )

    assert second.vendor_created is False
    assert second.vendor.vendor_id == first.vendor.vendor_id
    assert second.engagement.department_id == 3
    assert second.engagement.purchase_category_id == 14
    assert len(FakeVendorService.created_requests) == 1


def test_existing_vendor_is_reused_not_duplicated(env):
    first = env.service.create_intake(_manual_payload(vendor_name="Reuse Co", category_id=10), "user-1")
    second = env.service.create_intake(_manual_payload(vendor_name="Reuse Co", category_id=11), "user-1")

    assert first.vendor_created is True
    assert second.vendor_created is False
    assert len(env.vendor_dao.vendors_by_id) == 1


# ---------------------------------------------------------------------------
# Pre-Screen structured output + NDA document status
# ---------------------------------------------------------------------------


def _passing_engagement(env, **overrides):
    result = env.service.create_intake(_manual_payload(**overrides), "user-1")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="ACTIVE")
    return result.engagement.vendor_category_mapping_id


def test_pre_screen_returns_all_three_checks_with_status(env):
    engagement_id = _passing_engagement(env, vendor_name="Checks Co")

    outcome = env.service.run_pre_screen(engagement_id, "user-1")

    names = [c.name for c in outcome.checks]
    assert names == [
        "Duplicate/Existing Engagement Check",
        "Basic Eligibility Check",
        "Category/Business Rule Check",
    ]
    assert all(c.status == "PASS" for c in outcome.checks)
    assert outcome.result == "PASS"


def test_pre_screen_check_status_distinguishes_fail_from_need_information(env):
    blocked_id = _passing_engagement(env, vendor_name="Status Blocked Co")
    env.vendor_dao.statuses[1] = SimpleNamespace(status_code="BLOCKED")
    blocked = env.service.run_pre_screen(blocked_id, "user-1")

    incomplete_id = _passing_engagement(
        env, vendor_name="Status Incomplete Co", category_id=11, address_line1=None, city=None
    )
    incomplete = env.service.run_pre_screen(incomplete_id, "user-1")

    eligibility = lambda o: next(c for c in o.checks if c.name == "Basic Eligibility Check")
    assert eligibility(blocked).status == "FAIL"
    assert eligibility(incomplete).status == "NEED_INFORMATION"
    assert blocked.result == "FAIL"
    assert incomplete.result == "NEED_INFORMATION"


def test_nda_yes_maps_to_pending_document_status(env):
    env.intake_dao.create_screening_rule(
        _rule(None, "IT+HW requires NDA", department_id=1, purchase_category_id=10, requires_nda=True)
    )
    engagement_id = _passing_engagement(env, vendor_name="NDA Yes Co")

    outcome = env.service.run_pre_screen(engagement_id, "user-1")

    assert outcome.nda_recommended is True
    assert vis.nda_document_status(outcome.nda_recommended) == "PENDING"


def test_nda_no_maps_to_not_required_document_status(env):
    engagement_id = _passing_engagement(env, vendor_name="NDA No Co")

    outcome = env.service.run_pre_screen(engagement_id, "user-1")

    assert outcome.nda_recommended is False
    assert vis.nda_document_status(outcome.nda_recommended) == "NOT_REQUIRED"


def test_nda_document_status_is_none_before_pre_screen():
    assert vis.nda_document_status(None) is None


# ---------------------------------------------------------------------------
# Route wiring: literal paths must not be shadowed by /{engagement_id}
# ---------------------------------------------------------------------------


def test_screening_rules_route_is_not_shadowed_by_engagement_route():
    """Regression test for GET /apm/vendor-intake/screening-rules being
    captured by GET /apm/vendor-intake/{engagement_id}."""
    from starlette.routing import Match

    from Backend.API_Layer.routes.vendor_intake_route import router

    scope = {
        "type": "http", "method": "GET", "path": "/screening-rules",
        "path_params": {}, "headers": [], "query_string": b"", "root_path": "",
    }
    matched = [r for r in router.routes if r.matches(scope)[0] == Match.FULL]

    assert matched, "no route matched /screening-rules"
    assert matched[0].name == "get_all_screening_rules"


def test_engagement_route_still_resolves():
    from starlette.routing import Match

    from Backend.API_Layer.routes.vendor_intake_route import router

    scope = {
        "type": "http", "method": "GET", "path": "/123",
        "path_params": {}, "headers": [], "query_string": b"", "root_path": "",
    }
    matched = [r for r in router.routes if r.matches(scope)[0] == Match.FULL]

    assert matched, "no route matched /123"
    assert matched[0].name == "get_engagement"


def test_all_documented_vendor_intake_routes_exist():
    from Backend.API_Layer.routes.vendor_intake_route import router

    declared = {(tuple(sorted(r.methods)), r.path) for r in router.routes}

    assert (("POST",), "") in declared
    assert (("GET",), "/{engagement_id}") in declared
    assert (("GET",), "/vendor/{vendor_id}") in declared
    assert (("POST",), "/{engagement_id}/pre-screen") in declared
    assert (("PATCH",), "/{engagement_id}/nda-decision") in declared
    assert (("POST",), "/screening-rules") in declared
    assert (("GET",), "/screening-rules") in declared
    assert (("PUT",), "/screening-rules/{rule_id}") in declared


# ---------------------------------------------------------------------------
# Database / model schema alignment
#
# Guards the exact failure that hit production: the model gained columns the
# live ap.vendor_category_mapping table never got, so every query blew up with
# psycopg2 UndefinedColumn.
# ---------------------------------------------------------------------------


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "Data_Access_Layer"
    / "migration_vendor_intake_engagement.sql"
)


def _migration_create_table_body() -> str:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS ap.vendor_category_mapping" in sql
    return sql.split("CREATE TABLE IF NOT EXISTS ap.vendor_category_mapping", 1)[1]


def test_migration_defines_every_vendor_engagement_model_column():
    from Backend.Data_Access_Layer.models.vendor import VendorEngagement

    body = _migration_create_table_body()
    missing = [
        column.name
        for column in VendorEngagement.__table__.columns
        if not re.search(rf"^\s+{re.escape(column.name)}\s", body, re.MULTILINE)
    ]

    assert missing == [], f"columns in the model but not in the migration: {missing}"


def test_migration_defines_required_engagement_columns_explicitly():
    body = _migration_create_table_body()

    for column in (
        "department_id",
        "purchase_category_id",
        "business_requirement",
        "purpose_of_onboarding",
        "pre_screen_status",
        "pre_screen_result_reason",
        "pre_screen_checked_at",
        "nda_recommended",
        "nda_override",
        "nda_override_reason",
        "nda_final_required",
        "nda_decided_by",
        "nda_decided_at",
    ):
        assert re.search(rf"^\s+{column}\s", body, re.MULTILINE), f"{column} missing from migration"


def test_migration_defines_required_keys_and_constraints():
    body = _migration_create_table_body()

    assert "REFERENCES ap.department(id)" in body
    assert "REFERENCES ap.purchase_category(id)" in body
    assert "UNIQUE (vendor_id, department_id, purchase_category_id)" in body


def test_migration_preserves_legacy_rows_instead_of_deleting_them():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "RENAME TO vendor_category_mapping_legacy" in sql
    assert "DELETE FROM ap.vendor_category_mapping" not in sql
    assert "DROP TABLE" not in sql


def test_model_matches_engagement_table_keys():
    from Backend.Data_Access_Layer.models.vendor import VendorEngagement

    table = VendorEngagement.__table__
    assert table.name == "vendor_category_mapping"
    assert table.schema == "ap"

    unique_columns = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("department_id", "purchase_category_id", "vendor_id") in unique_columns
