# Backend/tests/test_vendor_onboarding.py
"""Tests for the PR Officer -> Vendor Intaker onboarding handoff.

Fake-DAO style (see test_purchase_category_department.py): no DB, no network.
VendorIntakeService is monkeypatched at the vendor_onboarding_service module
level, because the point of these tests is the handoff/status orchestration -
Vendor Intake and Pre-Screen have their own suite (test_vendor_intake.py) and
are deliberately NOT re-tested here.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest

import Backend.Business_Layer.services.vendor_onboarding_service as vos
from Backend.Business_Layer.services.vendor_onboarding_service import VendorOnboardingService

ONBOARDING_STATUS_CODES = [
    "CREATED", "ASSIGNED", "IN_PROGRESS", "PRE_SCREEN_PENDING",
    "NEED_INFORMATION", "PASSED", "FAILED", "COMPLETED", "CANCELLED",
]


class FakeDB:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


def _status(code, status_id):
    return SimpleNamespace(status_code=code, status_id=status_id, module_name="VENDOR_ONBOARDING")


def _pr(pr_id=1, status="APPROVED", department_id=1, purchase_category_id=10):
    return SimpleNamespace(
        id=pr_id,
        status=SimpleNamespace(status_code=status),
        department_id=department_id,
        purchase_category_id=purchase_category_id,
    )


def _engagement(pre_screen="PASS"):
    return SimpleNamespace(
        pre_screen_status=pre_screen, nda_final_required=False, nda_recommended=False
    )


class FakeOnboardingDAO:
    def __init__(self, pr=None, vendors=None, engagement=None):
        self._pr = pr
        self._vendors = vendors if vendors is not None else []
        self._engagement = engagement
        self.requests: Dict[int, object] = {}
        self.audit_logs: List[object] = []
        # Deliberately arbitrary, non-sequential ids: nothing in the service
        # may depend on a particular status_master id.
        self.statuses = {
            code: _status(code, 500 + index * 7)
            for index, code in enumerate(ONBOARDING_STATUS_CODES)
        }
        self._next_id = 1
        # Vendor-side lookups used when completion activates the vendor.
        self.vendor_statuses = {
            "PENDING": _status("PENDING", 900),
            "ACTIVE": _status("ACTIVE", 901),
        }
        self.vendors_by_id: Dict[int, object] = {}

    def register_vendor(self, vendor_id, status_code="PENDING"):
        vendor = SimpleNamespace(
            vendor_id=vendor_id,
            status_id=self.vendor_statuses[status_code].status_id,
        )
        self.vendors_by_id[vendor_id] = vendor
        return vendor

    # masters / lookups
    def get_pr_by_id(self, pr_id):
        return self._pr

    def get_eligible_vendors(self, department_id, purchase_category_id):
        return self._vendors

    def get_engagement(self, vendor_id, department_id, purchase_category_id):
        return self._engagement

    def get_status_by_module_code(self, module_name, status_code):
        assert module_name == "VENDOR_ONBOARDING"
        return self.statuses.get(status_code)

    def get_vendor_by_id(self, vendor_id):
        return self.vendors_by_id.get(vendor_id)

    def get_status_by_id(self, status_id):
        for status in list(self.statuses.values()) + list(self.vendor_statuses.values()):
            if status.status_id == status_id:
                return status
        return None

    # requests
    def create_request(self, request):
        request.id = self._next_id
        self._next_id += 1
        self.requests[request.id] = request
        return request

    def get_request_by_id(self, request_id):
        return self.requests.get(request_id)

    def get_open_request(self, pr_id, department_id, purchase_category_id):
        for request in self.requests.values():
            if (
                request.pr_id == pr_id
                and request.department_id == department_id
                and request.purchase_category_id == purchase_category_id
                and request.closed_at is None
            ):
                return request
        return None

    def get_open_requests_for_pr(self, pr_id):
        return [r for r in self.requests.values() if r.pr_id == pr_id and r.closed_at is None]

    def get_all_requests(self, pr_id=None, status_id=None, assigned_to=None,
                         vendor_id=None, skip=0, limit=100):
        rows = list(self.requests.values())
        if pr_id is not None:
            rows = [r for r in rows if r.pr_id == pr_id]
        if assigned_to is not None:
            rows = [r for r in rows if r.assigned_to == assigned_to]
        return rows

    def create_audit_log(self, audit_log):
        self.audit_logs.append(audit_log)
        return audit_log


class FakeIntakeService:
    """Stands in for the real VendorIntakeService. Records the payload it was
    handed so the tests can assert PR context is passed through untouched."""

    calls: List[object] = []
    pre_screen_result = "PASS"
    pre_screen_reason = None

    def __init__(self, db):
        self.db = db

    def create_intake(self, payload, user_id):
        FakeIntakeService.calls.append(payload)
        return SimpleNamespace(
            engagement=SimpleNamespace(vendor_category_mapping_id=77),
            vendor=SimpleNamespace(vendor_id=900),
            vendor_created=True,
            gst_status="Active",
        )

    def run_pre_screen(self, engagement_id, user_id):
        return SimpleNamespace(
            engagement=SimpleNamespace(vendor_category_mapping_id=engagement_id),
            result=FakeIntakeService.pre_screen_result,
            reason=FakeIntakeService.pre_screen_reason,
            checks=[],
            nda_recommended=False,
        )


class FakeVendorService:
    """Stands in for the real VendorService(db) that completion calls to
    activate the vendor. Records the activation and mirrors the real
    service's single-commit behaviour, so the atomicity ordering in
    ``complete`` is exercised rather than bypassed."""

    activations: List[tuple] = []

    def __init__(self, db):
        self.db = db

    def change_status(self, vendor_id, is_active, user_id):
        FakeVendorService.activations.append((vendor_id, is_active, user_id))
        self.db.commit()
        return SimpleNamespace(vendor_id=vendor_id)


@pytest.fixture
def env(monkeypatch):
    FakeIntakeService.calls = []
    FakeIntakeService.pre_screen_result = "PASS"
    FakeIntakeService.pre_screen_reason = None
    FakeVendorService.activations = []
    monkeypatch.setattr(vos, "VendorIntakeService", FakeIntakeService)
    monkeypatch.setattr(vos, "VendorService", FakeVendorService)

    service = VendorOnboardingService(db=FakeDB())
    dao = FakeOnboardingDAO(pr=_pr(), engagement=_engagement())
    # The vendor intake fake always produces vendor 900; it starts PENDING,
    # exactly as VendorService.create_vendor leaves a newly created vendor.
    dao.register_vendor(900, status_code="PENDING")
    service.onboarding_dao = dao

    return SimpleNamespace(service=service, dao=dao, vendor_service=FakeVendorService)


def _create_payload(**overrides):
    defaults = dict(
        pr_id=1,
        business_requirement="Laptops for the new dev team",
        purpose_of_onboarding="Only supplier with 5-day lead time",
        requested_vendor_name="Acme Supplies",
        requested_vendor_email="sales@acme.example",
        assigned_to=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _start_payload(**overrides):
    defaults = dict(
        gst_registered=False, gstin=None, vendor_name="Acme Supplies", country_id=10,
        address_line1="1 Industrial Road", address_line2=None, city="Pune",
        state=None, postal_code=None, payment_term_id=None, currency_id=None,
        pan_number=None, phone_number=None, email=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Vendor availability
# ---------------------------------------------------------------------------


def test_vendor_available_when_eligible_vendor_exists(env):
    env.dao._vendors = [SimpleNamespace(vendor_id=1, vendor_name="Acme")]

    result = env.service.check_vendor_availability(1, "officer-1")

    assert result.available is True
    assert result.department_id == 1
    assert result.purchase_category_id == 10
    assert len(result.vendors) == 1


def test_vendor_not_available_when_no_eligible_vendor(env):
    result = env.service.check_vendor_availability(1, "officer-1")

    assert result.available is False
    assert result.vendors == []


def test_vendor_availability_is_audited_on_the_pr_timeline(env):
    env.service.check_vendor_availability(1, "officer-1")

    audit = env.dao.audit_logs[-1]
    assert audit.table_name == "purchase_requisition"
    assert audit.action == "VENDOR_AVAILABILITY_CHECKED"
    assert audit.record_id == 1


def test_vendor_availability_uses_pr_department_and_category(env):
    captured = {}
    original = env.dao.get_eligible_vendors

    def _capture(department_id, purchase_category_id):
        captured["args"] = (department_id, purchase_category_id)
        return original(department_id, purchase_category_id)

    env.dao.get_eligible_vendors = _capture
    env.dao._pr = _pr(department_id=4, purchase_category_id=42)

    env.service.check_vendor_availability(1, "officer-1")

    assert captured["args"] == (4, 42)


def test_vendor_availability_for_missing_pr_raises(env):
    env.dao._pr = None

    with pytest.raises(ValueError, match="not found"):
        env.service.check_vendor_availability(999, "officer-1")


# ---------------------------------------------------------------------------
# Creating the onboarding request
# ---------------------------------------------------------------------------


def test_create_request_preserves_pr_context(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    assert request.pr_id == 1
    assert request.department_id == 1
    assert request.purchase_category_id == 10
    assert request.business_requirement == "Laptops for the new dev team"
    assert request.purpose_of_onboarding == "Only supplier with 5-day lead time"
    assert request.requested_vendor_name == "Acme Supplies"
    assert request.status.status_code == "CREATED"


def test_create_request_with_assignee_starts_assigned(env):
    request = env.service.create_request(_create_payload(assigned_to="intaker-9"), "officer-1")

    assert request.assigned_to == "intaker-9"
    assert request.status.status_code == "ASSIGNED"


def test_create_request_requires_approved_pr(env):
    env.dao._pr = _pr(status="PENDING_APPROVAL")

    with pytest.raises(ValueError, match="approved purchase requisition"):
        env.service.create_request(_create_payload(), "officer-1")


def test_duplicate_open_request_is_rejected(env):
    env.service.create_request(_create_payload(), "officer-1")

    with pytest.raises(ValueError, match="already exists"):
        env.service.create_request(_create_payload(), "officer-1")


def test_new_request_allowed_after_previous_one_closed(env):
    first = env.service.create_request(_create_payload(), "officer-1")
    first.closed_at = "2026-09-17"

    second = env.service.create_request(_create_payload(), "officer-1")

    assert second.id != first.id


def test_create_request_is_audited(env):
    env.service.create_request(_create_payload(), "officer-1")

    actions = [(a.table_name, a.action) for a in env.dao.audit_logs]
    assert ("vendor_onboarding_request", "CREATED") in actions
    assert ("purchase_requisition", "VENDOR_ONBOARDING_REQUESTED") in actions


# ---------------------------------------------------------------------------
# Assignment and status transitions
# ---------------------------------------------------------------------------


def test_assign_moves_created_to_assigned(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    assigned = env.service.assign(request.id, "intaker-9", "officer-1")

    assert assigned.assigned_to == "intaker-9"
    assert assigned.status.status_code == "ASSIGNED"


def test_assign_requires_a_non_blank_assignee(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    with pytest.raises(ValueError, match="assigned_to is required"):
        env.service.assign(request.id, "   ", "officer-1")


def test_invalid_transition_is_rejected(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    with pytest.raises(ValueError, match="cannot move from CREATED to COMPLETED"):
        env.service.update_status(request.id, "COMPLETED", "officer-1")


def test_cancel_sets_closed_at(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    cancelled = env.service.update_status(request.id, "CANCELLED", "officer-1", reason="duplicate")

    assert cancelled.status.status_code == "CANCELLED"
    assert cancelled.closed_at is not None


def test_unknown_status_code_is_rejected(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    with pytest.raises(ValueError, match="cannot move from"):
        env.service.update_status(request.id, "NOT_A_REAL_STATUS", "officer-1")


def test_missing_status_master_row_raises_rather_than_guessing(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    del env.dao.statuses["ASSIGNED"]

    with pytest.raises(ValueError, match="is not configured for module"):
        env.service.update_status(request.id, "ASSIGNED", "officer-1")


# ---------------------------------------------------------------------------
# Existing Vendor Intake + Pre-Screen reuse
# ---------------------------------------------------------------------------


def test_start_delegates_to_vendor_intake_with_pr_context(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    updated, intake_result = env.service.start(request.id, _start_payload(), "intaker-9")

    payload = FakeIntakeService.calls[0]
    assert payload.department_id == 1
    assert payload.category_id == 10
    assert payload.business_requirement == "Laptops for the new dev team"
    assert payload.purpose_of_onboarding == "Only supplier with 5-day lead time"
    assert updated.vendor_id == 900
    assert updated.engagement_id == 77
    assert updated.status.status_code == "PRE_SCREEN_PENDING"
    assert intake_result.vendor_created is True


def test_start_falls_back_to_requested_vendor_name_and_email(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    env.service.start(request.id, _start_payload(vendor_name=None, email=None), "intaker-9")

    payload = FakeIntakeService.calls[0]
    assert payload.vendor_name == "Acme Supplies"
    assert payload.email == "sales@acme.example"


def test_start_twice_is_rejected(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    env.service.start(request.id, _start_payload(), "intaker-9")

    with pytest.raises(ValueError, match="already been completed"):
        env.service.start(request.id, _start_payload(), "intaker-9")


def test_pre_screen_pass_moves_request_to_passed(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    env.service.start(request.id, _start_payload(), "intaker-9")

    updated, outcome = env.service.run_pre_screen(request.id, "intaker-9")

    assert outcome.result == "PASS"
    assert updated.status.status_code == "PASSED"


def test_pre_screen_need_information_pauses_onboarding(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    env.service.start(request.id, _start_payload(), "intaker-9")
    FakeIntakeService.pre_screen_result = "NEED_INFORMATION"

    updated, _ = env.service.run_pre_screen(request.id, "intaker-9")

    assert updated.status.status_code == "NEED_INFORMATION"
    assert updated.closed_at is None


def test_pre_screen_fail_stops_onboarding(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    env.service.start(request.id, _start_payload(), "intaker-9")
    FakeIntakeService.pre_screen_result = "FAIL"

    updated, _ = env.service.run_pre_screen(request.id, "intaker-9")

    assert updated.status.status_code == "FAILED"
    assert updated.closed_at is not None


def test_pre_screen_before_intake_is_rejected(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    with pytest.raises(ValueError, match="intake must be completed"):
        env.service.run_pre_screen(request.id, "intaker-9")


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def test_complete_after_passed_pre_screen(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    env.service.start(request.id, _start_payload(), "intaker-9")
    env.service.run_pre_screen(request.id, "intaker-9")

    completed = env.service.complete(request.id, "intaker-9")

    assert completed.status.status_code == "COMPLETED"
    assert completed.closed_at is not None


def test_complete_is_blocked_when_pre_screen_did_not_pass(env):
    request = env.service.create_request(_create_payload(), "officer-1")
    env.service.start(request.id, _start_payload(), "intaker-9")
    FakeIntakeService.pre_screen_result = "NEED_INFORMATION"
    env.service.run_pre_screen(request.id, "intaker-9")
    env.dao._engagement = _engagement(pre_screen="NEED_INFORMATION")

    with pytest.raises(ValueError, match="Pre-Screen has passed"):
        env.service.complete(request.id, "intaker-9")


def test_complete_before_intake_is_rejected(env):
    request = env.service.create_request(_create_payload(), "officer-1")

    with pytest.raises(ValueError, match="intake must be completed"):
        env.service.complete(request.id, "intaker-9")


# ---------------------------------------------------------------------------
# Migration / route wiring guards
# ---------------------------------------------------------------------------


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "Data_Access_Layer"
    / "migration_vendor_onboarding.sql"
)


def test_migration_seeds_every_onboarding_status_used_by_the_service():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    for code in ONBOARDING_STATUS_CODES:
        assert re.search(rf"'VENDOR_ONBOARDING',\s*'{code}'", sql), f"{code} not seeded"

    assert "ON CONFLICT (module_name, status_code) DO NOTHING" in sql


def _executable_sql() -> str:
    """Migration text with comment lines stripped, so assertions about the SQL
    itself are not fooled by prose in the header comments."""
    lines = MIGRATION_PATH.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("--"))


def test_migration_does_not_delete_data_or_hardcode_status_ids():
    sql = _executable_sql()

    assert "DELETE FROM" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    # Statuses are inserted by (module_name, status_code) only - the migration
    # never writes or depends on a specific status_id value.
    assert "status_id" not in sql


def test_migration_enforces_one_open_request_per_pr_department_category():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_onboarding_request_open" in sql
    assert "(pr_id, department_id, purchase_category_id)" in sql
    assert "WHERE closed_at IS NULL" in sql


def test_service_transitions_cover_every_seeded_status():
    assert set(vos.ONBOARDING_TRANSITIONS) == set(ONBOARDING_STATUS_CODES)


def test_onboarding_routes_declare_literal_paths_before_dynamic_ones():
    from Backend.API_Layer.routes.vendor_onboarding_route import router

    paths = [r.path for r in router.routes]
    dynamic_index = paths.index("/{request_id}")

    assert all(not p.startswith("/{") for p in paths[:dynamic_index])


def test_rfq_eligibility_route_is_not_shadowed_by_rfq_id():
    from starlette.routing import Match

    from Backend.API_Layer.routes.rfq_route import router

    scope = {
        "type": "http", "method": "GET", "path": "/eligibility",
        "path_params": {}, "headers": [], "query_string": b"", "root_path": "",
    }
    matched = [r for r in router.routes if r.matches(scope)[0] == Match.FULL]

    assert matched, "no route matched /eligibility"
    assert matched[0].name == "get_rfq_eligibility"


# ---------------------------------------------------------------------------
# Admin: Internal Request (= Purchase Requisition) -> Vendor Onboarding
#
# "Internal Request" is this product's name for ap.purchase_requisition - it
# carries the requester, department, lines, required_by, estimated_total,
# status and the vendor requirement. The onboarding request already stores it
# as pr_id, so the traceability chain is
#     purchase_requisition -> vendor_onboarding_request -> vendor
# ---------------------------------------------------------------------------


def _completed(env):
    request = env.service.create_request(_create_payload(), "admin-1")
    env.service.start(request.id, _start_payload(), "admin-1")
    env.service.run_pre_screen(request.id, "admin-1")
    return env.service.complete(request.id, "admin-1")


def test_onboarding_keeps_the_internal_request_reference_end_to_end(env):
    request = env.service.create_request(_create_payload(), "admin-1")
    assert request.pr_id == 1

    env.service.start(request.id, _start_payload(), "admin-1")
    env.service.run_pre_screen(request.id, "admin-1")
    completed = env.service.complete(request.id, "admin-1")

    # purchase_requisition -> vendor_onboarding_request -> vendor
    assert completed.pr_id == 1
    assert completed.vendor_id == 900
    assert completed.engagement_id == 77
    assert completed.status.status_code == "COMPLETED"


def test_completion_activates_the_vendor_through_the_existing_vendor_service(env):
    _completed(env)

    assert env.vendor_service.activations == [(900, True, "admin-1")]


def test_completion_records_the_activation_in_the_audit_trail(env):
    _completed(env)

    completed_rows = [a for a in env.dao.audit_logs if a.action == "COMPLETED"]
    assert len(completed_rows) == 1
    assert completed_rows[0].new_values["vendor_id"] == 900
    assert completed_rows[0].new_values["vendor_activated"] is True


def test_an_already_active_vendor_is_not_re_activated(env):
    """Intake may reuse an existing, already-active vendor - completing then
    must not churn a misleading STATUS_CHANGE audit row."""

    env.dao.register_vendor(900, status_code="ACTIVE")

    completed = _completed(env)

    assert completed.status.status_code == "COMPLETED"
    assert env.vendor_service.activations == []
    completed_rows = [a for a in env.dao.audit_logs if a.action == "COMPLETED"]
    assert completed_rows[0].new_values["vendor_activated"] is False


def test_completion_is_atomic_when_vendor_activation_fails(env, monkeypatch):
    """Vendor activation and the onboarding status change must succeed or
    fail together. The activation call is what commits, so a failure there
    leaves nothing committed."""

    commits = []
    monkeypatch.setattr(type(env.service.db), "commit", lambda self: commits.append(1))

    def _boom(self, vendor_id, is_active, user_id):
        raise ValueError("ACTIVE status is not configured for the VENDOR module")

    monkeypatch.setattr(vos.VendorService, "change_status", _boom)

    request = env.service.create_request(_create_payload(), "admin-1")
    env.service.start(request.id, _start_payload(), "admin-1")
    env.service.run_pre_screen(request.id, "admin-1")
    commits.clear()

    with pytest.raises(ValueError, match="not configured"):
        env.service.complete(request.id, "admin-1")

    # Nothing was committed by complete() - the route's rollback discards the
    # pending COMPLETED transition along with it.
    assert commits == []


def test_completion_cannot_run_twice_so_no_duplicate_vendor_is_created(env):
    request = env.service.create_request(_create_payload(), "admin-1")
    env.service.start(request.id, _start_payload(), "admin-1")
    env.service.run_pre_screen(request.id, "admin-1")
    env.service.complete(request.id, "admin-1")

    with pytest.raises(ValueError, match="cannot move from COMPLETED"):
        env.service.complete(request.id, "admin-1")

    assert env.vendor_service.activations == [(900, True, "admin-1")]
    assert len(FakeIntakeService.calls) == 1


def test_intake_cannot_run_twice_for_one_onboarding_request(env):
    """Guards duplicate vendor creation at the other end of the flow."""

    request = env.service.create_request(_create_payload(), "admin-1")
    env.service.start(request.id, _start_payload(), "admin-1")

    with pytest.raises(ValueError, match="already been completed"):
        env.service.start(request.id, _start_payload(), "admin-1")

    assert len(FakeIntakeService.calls) == 1


def test_duplicate_active_onboarding_for_the_same_internal_request_is_prevented(env):
    env.service.create_request(_create_payload(), "admin-1")

    with pytest.raises(ValueError, match="An open vendor onboarding request already exists"):
        env.service.create_request(_create_payload(), "admin-1")


def test_completion_requires_a_passed_pre_screen(env):
    """The existing gates stay: a request still sitting at PRE_SCREEN_PENDING
    cannot be completed, so no vendor is created or activated."""

    request = env.service.create_request(_create_payload(), "admin-1")
    env.service.start(request.id, _start_payload(), "admin-1")

    with pytest.raises(ValueError, match="cannot move from PRE_SCREEN_PENDING to COMPLETED"):
        env.service.complete(request.id, "admin-1")

    assert env.vendor_service.activations == []


def test_completion_is_blocked_when_pre_screen_did_not_pass(env):
    """Even once the status graph would allow it, the engagement's recorded
    Pre-Screen verdict is re-checked before the vendor is activated."""

    request = env.service.create_request(_create_payload(), "admin-1")
    env.service.start(request.id, _start_payload(), "admin-1")
    env.service.run_pre_screen(request.id, "admin-1")
    env.dao._engagement.pre_screen_status = "NEED_INFORMATION"

    with pytest.raises(ValueError, match="Pre-Screen has passed"):
        env.service.complete(request.id, "admin-1")

    assert env.vendor_service.activations == []


def test_admin_flow_reuses_the_existing_vendor_services(env):
    """No duplicated vendor/address/tax/engagement logic - onboarding
    orchestrates the existing services."""

    import inspect

    source = inspect.getsource(vos)

    assert "VendorIntakeService(self.db).create_intake" in source
    assert "VendorIntakeService(self.db).run_pre_screen" in source
    assert "VendorService(self.db).change_status" in source
    # Nothing here constructs vendor-side rows itself.
    for duplicated in ("VendorAddress(", "VendorTax(", "VendorBank("):
        assert duplicated not in source, f"onboarding service builds {duplicated} itself"


def test_the_documented_admin_endpoints_all_exist():
    """The project's own route names, per its existing conventions."""

    from Backend.API_Layer.routes import procurement_route, vendor_onboarding_route

    pr_paths = {(tuple(sorted(r.methods)), r.path) for r in procurement_route.router.routes}
    onboarding_paths = {
        (tuple(sorted(r.methods)), r.path) for r in vendor_onboarding_route.router.routes
    }

    # Internal Requests (= purchase requisitions)
    assert (("GET",), "/purchase-requisitions") in pr_paths
    assert (("GET",), "/purchase-requisitions/{pr_id}") in pr_paths

    # Vendor onboarding, started from an internal request and completed
    assert (("POST",), "") in onboarding_paths
    assert (("GET",), "") in onboarding_paths
    assert (("GET",), "/{request_id}") in onboarding_paths
    assert (("PATCH",), "/{request_id}/status") in onboarding_paths
    assert (("POST",), "/{request_id}/start") in onboarding_paths
    assert (("POST",), "/{request_id}/complete") in onboarding_paths


def test_every_onboarding_route_is_permission_gated():
    """Authorization is unchanged: the existing ONBOARDING_* permission
    bundles remain the gate, and no route is left open."""

    from Backend.API_Layer.routes import vendor_onboarding_route

    for route in vendor_onboarding_route.router.routes:
        assert route.dependencies, f"{route.path} has no permission dependency"

    for bundle in (
        vendor_onboarding_route.ONBOARDING_VIEW,
        vendor_onboarding_route.ONBOARDING_CREATE,
        vendor_onboarding_route.ONBOARDING_PROCESS,
    ):
        assert bundle, "permission bundle is empty"
