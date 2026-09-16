# Backend/tests/test_invoice_approval_workflow.py
"""Tests for the policy-driven, multi-level invoice approval engine
(ApprovalPolicyService.match_policy, ApproverResolverService.resolve,
InvoiceApprovalService.send_for_approval/approve/reject).

Follows the project's existing test style (see test_pr_approval_workflow.py):
fake DAOs stand in for the real SQLAlchemy DAOs, no real DB connection.
Replaces test_invoice_approval_service.py, which tested the old
single-level approve_invoice() method that no longer exists.

Row-locking (with_for_update) is exercised against a real DB, not here -
these are unit tests of the business logic, not a concurrency test.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Dict, List

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService
from Backend.Business_Layer.services.approver_resolver_service import ApproverResolverService
from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService
from Backend.Data_Access_Layer.models.invoice import Invoice

APPROVER_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
APPROVER_B = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
AP_EXEC = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
FIN_EXEC = uuid.UUID("00000000-0000-0000-0000-0000000000e2")


class FakeStatus:
    def __init__(self, status_id, module_name, status_code):
        self.status_id = status_id
        self.module_name = module_name
        self.status_code = status_code


class StatusRegistry:
    def __init__(self):
        self._by_code = {}
        self._by_id = {}
        self._next_id = 1

    def add(self, module_name, status_code):
        status = FakeStatus(self._next_id, module_name, status_code)
        self._by_code[(module_name, status_code)] = status
        self._by_id[status.status_id] = status
        self._next_id += 1
        return status

    def get_by_module_code(self, module_name, status_code):
        return self._by_code.get((module_name, status_code))

    def get_by_id(self, status_id):
        return self._by_id.get(status_id)

    def attach(self, obj):
        if obj is not None and getattr(obj, "status_id", None) is not None:
            set_committed_value(obj, "status", self.get_by_id(obj.status_id))
        return obj


class FakeDB:
    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeInvoiceDAO:
    def __init__(self, registry, invoices):
        self.registry = registry
        self.invoices = invoices

    def get_invoice_by_id_locked(self, invoice_id):
        return self.registry.attach(self.invoices.get(invoice_id))

    def get_invoice_by_id(self, invoice_id):
        return self.registry.attach(self.invoices.get(invoice_id))

    def get_status_by_code(self, status_code):
        return self.registry.get_by_module_code("INVOICE", status_code)

    def get_all_statuses(self):
        return [s for s in self.registry._by_id.values() if s.module_name == "INVOICE"]


class FakeMasterDAO:
    def __init__(self, departments, categories):
        self.departments = departments
        self.categories = categories

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)

    def get_purchase_category_by_id(self, purchase_category_id):
        return self.categories.get(purchase_category_id)


class FakeApprovalPolicyDAO:
    def __init__(self):
        self.policies: Dict[int, object] = {}
        self.levels: Dict[int, List[object]] = {}
        self.instances_used: set = set()
        self._next_policy_id = 1
        self._next_level_id = 1

    def create_policy(self, policy):
        policy.id = self._next_policy_id
        self._next_policy_id += 1
        self.policies[policy.id] = policy
        self.levels[policy.id] = []
        return policy

    def create_level(self, level):
        level.id = self._next_level_id
        self._next_level_id += 1
        self.levels.setdefault(level.approval_policy_id, []).append(level)
        return level

    def get_policy_by_id(self, policy_id):
        return self.policies.get(policy_id)

    def get_policy_by_name(self, name):
        return next((p for p in self.policies.values() if p.name == name), None)

    def get_all_policies(self, department_id=None, purchase_category_id=None, is_active=None):
        result = list(self.policies.values())
        if department_id is not None:
            result = [p for p in result if p.department_id == department_id]
        if purchase_category_id is not None:
            result = [p for p in result if p.purchase_category_id == purchase_category_id]
        if is_active is not None:
            result = [p for p in result if p.is_active == is_active]
        return result

    def get_active_policies_for(self, department_id, purchase_category_id):
        return [
            p for p in self.policies.values()
            if p.department_id == department_id
            and p.purchase_category_id == purchase_category_id
            and p.is_active
        ]

    def get_active_default_policies(self):
        return [p for p in self.policies.values() if p.is_default and p.is_active]

    def delete_levels_for_policy(self, policy_id):
        self.levels[policy_id] = []

    def get_levels_for_policy(self, policy_id):
        return list(self.levels.get(policy_id, []))

    def delete_policy(self, policy):
        self.policies.pop(policy.id, None)
        self.levels.pop(policy.id, None)

    def policy_has_approval_instances(self, policy_id):
        return policy_id in self.instances_used


class FakeInvoiceApprovalDAO:
    def __init__(self):
        self.instances: Dict[int, object] = {}
        self.steps: Dict[int, object] = {}
        self.audit_logs: list = []
        self._next_instance_id = 1
        self._next_step_id = 1
        self._next_approver_id = 1

    def create_invoice_approval(self, approval):
        approval.invoice_approval_id = self._next_instance_id
        self._next_instance_id += 1
        approval.steps = []
        self.instances[approval.invoice_approval_id] = approval
        return approval

    def get_invoice_approval_by_id(self, invoice_approval_id):
        return self.instances.get(invoice_approval_id)

    def get_active_invoice_approval_for_invoice(self, invoice_id):
        candidates = [
            a for a in self.instances.values()
            if a.invoice_id == invoice_id and a.status in ("PENDING", "IN_PROGRESS")
        ]
        return candidates[-1] if candidates else None

    def get_latest_invoice_approval_for_invoice(self, invoice_id):
        candidates = [a for a in self.instances.values() if a.invoice_id == invoice_id]
        return candidates[-1] if candidates else None

    def create_step(self, step):
        step.id = self._next_step_id
        self._next_step_id += 1
        step.approvers = []
        self.steps[step.id] = step
        self.instances[step.invoice_approval_id].steps.append(step)
        return step

    def get_active_step_locked(self, invoice_approval_id):
        for s in sorted(
            (s for s in self.steps.values() if s.invoice_approval_id == invoice_approval_id),
            key=lambda s: s.level_number,
        ):
            if s.status == "PENDING":
                return s
        return None

    def create_step_approver(self, approver):
        approver.id = self._next_approver_id
        self._next_approver_id += 1
        self.steps[approver.approval_step_id].approvers.append(approver)
        return approver

    def get_approvers_for_step(self, approval_step_id):
        return list(self.steps[approval_step_id].approvers)

    def get_step_approver(self, approval_step_id, user_uuid):
        return next(
            (a for a in self.get_approvers_for_step(approval_step_id) if a.user_uuid == user_uuid), None
        )

    def create_audit_log(self, audit_log):
        audit_log.audit_log_id = len(self.audit_logs) + 1
        self.audit_logs.append(audit_log)
        return audit_log


class FakeApproverDirectoryDAO:
    def __init__(self):
        self.users: Dict[uuid.UUID, dict] = {}
        self.user_id_map: Dict[int, uuid.UUID] = {}

    def add_user(self, user_id, user_uuid, roles, active=True):
        self.users[user_uuid] = {"active": active, "roles": set(roles)}
        self.user_id_map[int(user_id)] = user_uuid

    def get_user_uuid_by_user_id(self, user_id):
        try:
            return self.user_id_map.get(int(user_id))
        except (TypeError, ValueError):
            return None

    def get_active_users_by_role(self, role_code):
        return [u for u, info in self.users.items() if info["active"] and role_code in info["roles"]]

    def is_user_active(self, user_uuid):
        info = self.users.get(user_uuid)
        return info is not None and info["active"]

    def has_active_role(self, user_uuid, role_code):
        info = self.users.get(user_uuid)
        return info is not None and info["active"] and role_code in info["roles"]


class FakeDepartmentApproverDAO:
    """AP-owned department-approver mapping - independent of any UMS
    role, see approval.py's DepartmentApprover docstring."""

    def __init__(self):
        self.mappings: Dict[int, set] = {}  # department_id -> {user_uuid}

    def add(self, department_id, user_uuid):
        self.mappings.setdefault(department_id, set()).add(user_uuid)

    def get_active_user_uuids_for_department(self, department_id):
        return list(self.mappings.get(department_id, set()))

    def get_by_department_and_user(self, department_id, user_uuid):
        if user_uuid in self.mappings.get(department_id, set()):
            return SimpleNamespace(is_active=True)
        return None


def _level(number, approver_type, approval_rule="ANY_ONE", role_code=None, user_uuid=None, is_active=True):
    return SimpleNamespace(
        level_number=number, approver_type=approver_type, approval_rule=approval_rule,
        role_code=role_code, user_uuid=user_uuid, is_active=is_active,
    )


class Workflow:
    def __init__(self):
        self.registry = StatusRegistry()
        for code in ("PENDING_APPROVAL", "APPROVED", "REJECTED"):
            self.registry.add("INVOICE", code)

        self.departments = {10: SimpleNamespace(id=10, is_active=True)}
        self.categories = {20: SimpleNamespace(id=20, is_active=True, department_id=10)}
        self.invoices: Dict[int, object] = {}

        self.invoice_dao = FakeInvoiceDAO(self.registry, self.invoices)
        self.approval_dao = FakeInvoiceApprovalDAO()
        self.policy_dao = FakeApprovalPolicyDAO()
        self.master_dao = FakeMasterDAO(self.departments, self.categories)
        self.directory_dao = FakeApproverDirectoryDAO()
        self.department_approver_dao = FakeDepartmentApproverDAO()

        db = FakeDB()

        self.policy_service = ApprovalPolicyService(db)
        self.policy_service.dao = self.policy_dao
        self.policy_service.master_dao = self.master_dao

        self.resolver = ApproverResolverService(db)
        self.resolver.dao = self.directory_dao
        self.resolver.department_approver_dao = self.department_approver_dao

        self.service = InvoiceApprovalService(db)
        self.service.invoice_dao = self.invoice_dao
        self.service.approval_dao = self.approval_dao
        self.service.policy_dao = self.policy_dao
        self.service.master_dao = self.master_dao
        self.service.policy_service = self.policy_service
        self.service.resolver = self.resolver

        self._next_invoice_id = 1

        # 5100001 is AP_EXECUTIVE, 5100002 is FINANCE_EXECUTIVE - mirrors
        # the real ums_user_cache/approver_directory shape seen in prod.
        self.directory_dao.add_user(5100001, AP_EXEC, roles=["AP_EXECUTIVE"])
        self.directory_dao.add_user(5100002, FIN_EXEC, roles=["FINANCE_EXECUTIVE"])
        # Department approver: an AP-owned mapping (department_id 10 ->
        # user_uuid), not a UMS role - the account still has to be active
        # in approver_directory, but carries no special role for this.
        self.directory_dao.add_user(5100010, APPROVER_A, roles=[])
        self.directory_dao.add_user(5100011, APPROVER_B, roles=[])
        self.department_approver_dao.add(10, APPROVER_A)
        self.department_approver_dao.add(10, APPROVER_B)

    def add_invoice(self, *, net_amount, department_id=10, purchase_category_id=20, status_code="PENDING_APPROVAL"):
        # A real mapped Invoice() instance, not a SimpleNamespace -
        # set_committed_value (used by StatusRegistry.attach) needs a real
        # ORM instance's _sa_instance_state, exactly like
        # test_pr_approval_workflow.py's FakeProcurementDAO builds real
        # PurchaseRequisition() instances rather than plain namespaces.
        invoice_id = self._next_invoice_id
        self._next_invoice_id += 1
        status = self.registry.get_by_module_code("INVOICE", status_code)
        invoice = Invoice(
            invoice_id=invoice_id, department_id=department_id, purchase_category_id=purchase_category_id,
            net_amount=Decimal(net_amount), status_id=status.status_id, updated_by=None,
        )
        self.registry.attach(invoice)
        self.invoices[invoice_id] = invoice
        return invoice

    def invoice_after(self, invoice_id):
        return self.invoice_dao.get_invoice_by_id_locked(invoice_id)

    def create_policy(self, *, name="Default Policy", department_id=10, purchase_category_id=20,
                       min_amount=None, max_amount=None, levels, is_active=True):
        data = SimpleNamespace(
            name=name, department_id=department_id, purchase_category_id=purchase_category_id,
            description=None, min_amount=min_amount, max_amount=max_amount, is_active=is_active, levels=levels,
        )
        return self.policy_service.create_policy(data)


@pytest.fixture
def wf():
    return Workflow()


# ---------------------------------------------------------------------------
# Policy matching
# ---------------------------------------------------------------------------

def test_no_matching_policy_raises(wf: Workflow):
    invoice = wf.add_invoice(net_amount=1000)
    with pytest.raises(ValueError, match="No applicable approval policy"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)


def test_amount_outside_range_does_not_match(wf: Workflow):
    wf.create_policy(min_amount=50000, max_amount=None, levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    with pytest.raises(ValueError, match="No applicable approval policy"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)


def test_overlapping_active_policy_is_rejected_at_creation(wf: Workflow):
    wf.create_policy(name="A", min_amount=0, max_amount=50000, levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    with pytest.raises(ValueError, match="overlaps"):
        wf.create_policy(
            name="B", min_amount=40000, max_amount=100000, levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")]
        )


def test_non_overlapping_ranges_are_both_allowed(wf: Workflow):
    wf.create_policy(name="A", min_amount=0, max_amount=50000, levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    policy_b = wf.create_policy(
        name="B", min_amount=50000.01, max_amount=None, levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")]
    )
    assert policy_b.id is not None


def test_min_amount_greater_than_max_amount_is_rejected(wf: Workflow):
    with pytest.raises(ValueError, match="min_amount cannot be greater than max_amount"):
        wf.create_policy(min_amount=100, max_amount=50, levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])


def test_policy_requires_at_least_one_level(wf: Workflow):
    with pytest.raises(ValueError, match="at least one level"):
        wf.create_policy(levels=[])


# ---------------------------------------------------------------------------
# Approver resolution
# ---------------------------------------------------------------------------

def test_department_approver_resolves_configured_mapping(wf: Workflow):
    resolved = wf.resolver.resolve("DEPARTMENT_APPROVER", department_id=10)
    assert set(resolved) == {APPROVER_A, APPROVER_B}


def test_department_approver_excludes_configured_but_inactive_account(wf: Workflow):
    """The mapping row exists, but the account itself went inactive since
    (e.g. CDC picked up a UMS deactivation) - must not resolve."""
    wf.directory_dao.users[APPROVER_A]["active"] = False
    resolved = wf.resolver.resolve("DEPARTMENT_APPROVER", department_id=10)
    assert resolved == [APPROVER_B]


def test_role_resolves_active_users_with_that_role(wf: Workflow):
    resolved = wf.resolver.resolve("ROLE", role_code="AP_EXECUTIVE")
    assert resolved == [AP_EXEC]


def test_inactive_user_excluded_from_role_resolution(wf: Workflow):
    wf.directory_dao.add_user(5100099, uuid.uuid4(), roles=["AP_EXECUTIVE"], active=False)
    resolved = wf.resolver.resolve("ROLE", role_code="AP_EXECUTIVE")
    assert resolved == [AP_EXEC]  # the inactive one is excluded


def test_user_type_requires_active_account(wf: Workflow):
    inactive_uuid = uuid.uuid4()
    wf.directory_dao.add_user(5100098, inactive_uuid, roles=[], active=False)
    assert wf.resolver.resolve("USER", user_uuid=inactive_uuid) == []
    assert wf.resolver.resolve("USER", user_uuid=AP_EXEC) == [AP_EXEC]  # AP_EXEC has no roles req'd for USER type


def test_no_approver_found_for_role_send_for_approval_aborts_entirely(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="NO_SUCH_ROLE")])
    invoice = wf.add_invoice(net_amount=1000)

    with pytest.raises(ValueError, match="No active approver found"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)

    # no partially-initialized instance left behind
    assert wf.approval_dao.get_latest_invoice_approval_for_invoice(invoice.invoice_id) is None


def test_department_approver_with_no_configured_mapping_aborts_send_for_approval(wf: Workflow):
    """No department_approver rows configured for this department at all
    (admin never set any up) - a clear error, not a silent skip."""
    wf.create_policy(department_id=10, levels=[_level(1, "DEPARTMENT_APPROVER")])
    invoice = wf.add_invoice(net_amount=1000, department_id=10)
    wf.department_approver_dao.mappings[10] = set()  # clear the default mapping from setUp

    with pytest.raises(ValueError, match="No active approver found"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)


# ---------------------------------------------------------------------------
# send_for_approval
# ---------------------------------------------------------------------------

def test_send_for_approval_creates_expected_levels_and_approvers(wf: Workflow):
    wf.create_policy(levels=[
        _level(1, "DEPARTMENT_APPROVER", approval_rule="ANY_ONE"),
        _level(2, "ROLE", role_code="AP_EXECUTIVE", approval_rule="ANY_ONE"),
        _level(3, "ROLE", role_code="FINANCE_EXECUTIVE", approval_rule="ANY_ONE"),
    ])
    invoice = wf.add_invoice(net_amount=75000)

    instance = wf.service.send_for_approval(invoice.invoice_id, 5100010)
    assert instance.status == "IN_PROGRESS"
    assert len(instance.steps) == 3

    level1, level2, level3 = sorted(instance.steps, key=lambda s: s.level_number)
    assert level1.status == "PENDING"
    assert {a.user_uuid for a in level1.approvers} == {APPROVER_A, APPROVER_B}
    assert all(a.status == "PENDING" for a in level1.approvers)

    assert level2.status == "WAITING"
    assert all(a.status == "WAITING" for a in level2.approvers)
    assert level3.status == "WAITING"


def test_missing_department_or_category_on_invoice_blocks_send_for_approval(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    invoice.department_id = None

    with pytest.raises(ValueError, match="missing department/purchase category"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)


def test_invoice_not_pending_approval_cannot_be_sent(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000, status_code="APPROVED")

    with pytest.raises(ValueError, match="cannot be sent for approval"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)


def test_cannot_send_for_approval_twice(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    with pytest.raises(ValueError, match="already has an approval in progress"):
        wf.service.send_for_approval(invoice.invoice_id, 5100010)


# ---------------------------------------------------------------------------
# approve / reject - single level
# ---------------------------------------------------------------------------

def test_single_level_any_one_approval_completes_invoice(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    instance = wf.service.approve(invoice.invoice_id, 5100001, "looks fine")
    assert instance.status == "APPROVED"
    assert instance.steps[0].status == "APPROVED"

    assert wf.invoice_after(invoice.invoice_id).status.status_code == "APPROVED"


def test_unauthorized_user_cannot_approve(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    with pytest.raises(ValueError, match="not an assigned approver"):
        wf.service.approve(invoice.invoice_id, 5100002, "not my call")  # FIN_EXEC, not AP_EXEC


def test_inactive_approver_cannot_approve(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    wf.directory_dao.users[AP_EXEC]["active"] = False
    with pytest.raises(ValueError, match="no longer an active/eligible approver"):
        wf.service.approve(invoice.invoice_id, 5100001, None)


def test_double_decision_on_same_step_is_rejected(wf: Workflow):
    wf.create_policy(levels=[
        _level(1, "DEPARTMENT_APPROVER", approval_rule="ALL"),
    ])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    wf.service.approve(invoice.invoice_id, 5100010, "ok")
    with pytest.raises(ValueError, match="already been recorded"):
        wf.service.approve(invoice.invoice_id, 5100010, "again")


# ---------------------------------------------------------------------------
# ANY_ONE vs ALL quorum
# ---------------------------------------------------------------------------

def test_any_one_completes_on_first_approval_and_skips_the_rest(wf: Workflow):
    wf.create_policy(levels=[_level(1, "DEPARTMENT_APPROVER", approval_rule="ANY_ONE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    instance = wf.service.approve(invoice.invoice_id, 5100010, "A approves")
    step = instance.steps[0]
    statuses = {a.user_uuid: a.status for a in step.approvers}
    assert statuses[APPROVER_A] == "APPROVED"
    assert statuses[APPROVER_B] == "SKIPPED"
    assert step.status == "APPROVED"


def test_all_requires_every_approver(wf: Workflow):
    wf.create_policy(levels=[_level(1, "DEPARTMENT_APPROVER", approval_rule="ALL")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    instance = wf.service.approve(invoice.invoice_id, 5100010, "A approves")
    assert instance.status == "IN_PROGRESS"  # still waiting on B
    assert instance.steps[0].status == "PENDING"

    instance = wf.service.approve(invoice.invoice_id, 5100011, "B approves")
    assert instance.status == "APPROVED"
    assert instance.steps[0].status == "APPROVED"


# ---------------------------------------------------------------------------
# Sequential levels
# ---------------------------------------------------------------------------

def test_sequential_levels_advance_one_at_a_time(wf: Workflow):
    wf.create_policy(levels=[
        _level(1, "DEPARTMENT_APPROVER"),
        _level(2, "ROLE", role_code="AP_EXECUTIVE"),
        _level(3, "ROLE", role_code="FINANCE_EXECUTIVE"),
    ])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    instance = wf.service.approve(invoice.invoice_id, 5100010, None)
    level1, level2, level3 = sorted(instance.steps, key=lambda s: s.level_number)
    assert level1.status == "APPROVED"
    assert level2.status == "PENDING"
    assert level3.status == "WAITING"
    assert wf.invoice_after(invoice.invoice_id).status.status_code == "PENDING_APPROVAL"

    instance = wf.service.approve(invoice.invoice_id, 5100001, None)
    level1, level2, level3 = sorted(instance.steps, key=lambda s: s.level_number)
    assert level2.status == "APPROVED"
    assert level3.status == "PENDING"
    assert wf.invoice_after(invoice.invoice_id).status.status_code == "PENDING_APPROVAL"

    instance = wf.service.approve(invoice.invoice_id, 5100002, None)
    assert instance.status == "APPROVED"
    assert wf.invoice_after(invoice.invoice_id).status.status_code == "APPROVED"


def test_approver_at_a_later_level_cannot_jump_ahead(wf: Workflow):
    wf.create_policy(levels=[
        _level(1, "DEPARTMENT_APPROVER"),
        _level(2, "ROLE", role_code="AP_EXECUTIVE"),
    ])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    with pytest.raises(ValueError, match="not an assigned approver"):
        wf.service.approve(invoice.invoice_id, 5100001, None)  # level 2's approver, level 1 still active


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------

def test_reject_requires_a_comment(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    with pytest.raises(ValueError, match="comment is required"):
        wf.service.reject(invoice.invoice_id, 5100001, "   ")


def test_reject_terminates_instance_and_skips_co_approvers(wf: Workflow):
    wf.create_policy(levels=[
        _level(1, "DEPARTMENT_APPROVER", approval_rule="ALL"),
        _level(2, "ROLE", role_code="AP_EXECUTIVE"),
    ])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)

    instance = wf.service.reject(invoice.invoice_id, 5100010, "missing PO reference")
    assert instance.status == "REJECTED"

    level1, level2 = sorted(instance.steps, key=lambda s: s.level_number)
    assert level1.status == "REJECTED"
    statuses = {a.user_uuid: a.status for a in level1.approvers}
    assert statuses[APPROVER_A] == "REJECTED"
    assert statuses[APPROVER_B] == "SKIPPED"
    assert level2.status == "WAITING"  # never activated

    assert wf.invoice_after(invoice.invoice_id).status.status_code == "REJECTED"


def test_cannot_decide_on_a_rejected_invoice(wf: Workflow):
    wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    wf.service.send_for_approval(invoice.invoice_id, 5100010)
    wf.service.reject(invoice.invoice_id, 5100001, "no")

    with pytest.raises(ValueError, match="no approval in progress"):
        wf.service.approve(invoice.invoice_id, 5100001, "changed my mind")


# ---------------------------------------------------------------------------
# Policy snapshot immutability (spec section 14)
# ---------------------------------------------------------------------------

def test_policy_edit_after_send_for_approval_does_not_affect_running_instance(wf: Workflow):
    policy = wf.create_policy(levels=[_level(1, "ROLE", role_code="AP_EXECUTIVE")])
    invoice = wf.add_invoice(net_amount=1000)
    instance = wf.service.send_for_approval(invoice.invoice_id, 5100010)
    original_step_count = len(instance.steps)

    # policy edited after the fact - add a second level
    update = SimpleNamespace(
        name=None, department_id=None, purchase_category_id=None, description=None,
        min_amount=None, max_amount=None,
        levels=[
            _level(1, "ROLE", role_code="AP_EXECUTIVE"),
            _level(2, "ROLE", role_code="FINANCE_EXECUTIVE"),
        ],
    )
    wf.policy_service.update_policy(policy.id, update)

    # the already-running instance is untouched
    instance_after = wf.approval_dao.get_invoice_approval_by_id(instance.invoice_approval_id)
    assert len(instance_after.steps) == original_step_count

    # approving it completes at the original single level, ignoring the new level 2
    completed = wf.service.approve(invoice.invoice_id, 5100001, None)
    assert completed.status == "APPROVED"
