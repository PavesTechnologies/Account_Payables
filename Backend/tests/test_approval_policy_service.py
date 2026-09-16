# Backend/tests/test_approval_policy_service.py
"""CRUD/validation tests for ApprovalPolicyService not already covered by
the end-to-end scenarios in test_invoice_approval_workflow.py (matching
and overlap-at-creation are covered there).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, List

import pytest

from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService


class FakeDB:
    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


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


def _level(number, approver_type="ROLE", approval_rule="ANY_ONE", role_code="AP_EXECUTIVE", user_uuid=None):
    return SimpleNamespace(
        level_number=number, approver_type=approver_type, approval_rule=approval_rule,
        role_code=role_code, user_uuid=user_uuid, is_active=True,
    )


class Setup:
    def __init__(self):
        self.departments = {
            10: SimpleNamespace(id=10, is_active=True),
            11: SimpleNamespace(id=11, is_active=False),  # inactive department
        }
        self.categories = {
            20: SimpleNamespace(id=20, is_active=True, department_id=10),
            21: SimpleNamespace(id=21, is_active=True, department_id=11),  # belongs to a different dept
        }
        self.dao = FakeApprovalPolicyDAO()
        self.master_dao = FakeMasterDAO(self.departments, self.categories)
        self.service = ApprovalPolicyService(FakeDB())
        self.service.dao = self.dao
        self.service.master_dao = self.master_dao

    def create(self, name="Policy A", department_id=10, purchase_category_id=20, **kwargs):
        data = SimpleNamespace(
            name=name, department_id=department_id, purchase_category_id=purchase_category_id,
            description=None, min_amount=kwargs.get("min_amount"), max_amount=kwargs.get("max_amount"),
            is_active=kwargs.get("is_active", True), levels=kwargs.get("levels", [_level(1)]),
            is_default=kwargs.get("is_default", False),
        )
        return self.service.create_policy(data)

    def create_default(self, name="Default Policy", **kwargs):
        data = SimpleNamespace(
            name=name, department_id=None, purchase_category_id=None,
            description=None, min_amount=None, max_amount=None,
            is_active=kwargs.get("is_active", True),
            levels=kwargs.get("levels", [_level(1, role_code="Super_Admin")]),
            is_default=True,
        )
        return self.service.create_policy(data)


@pytest.fixture
def setup():
    return Setup()


def test_create_policy_with_unknown_department_is_rejected(setup: Setup):
    with pytest.raises(ValueError, match="Department not found"):
        setup.create(department_id=999)


def test_create_policy_with_inactive_department_is_rejected(setup: Setup):
    with pytest.raises(ValueError, match="Department is not active"):
        setup.create(department_id=11, purchase_category_id=21)


def test_create_policy_with_category_from_wrong_department_is_rejected(setup: Setup):
    with pytest.raises(ValueError, match="does not belong to the selected department"):
        setup.create(department_id=10, purchase_category_id=21)


def test_duplicate_policy_name_is_rejected(setup: Setup):
    setup.create(name="Engineering High Value")
    with pytest.raises(ValueError, match="already exists"):
        setup.create(name="Engineering High Value", min_amount=99999)


def test_invalid_approver_type_is_rejected(setup: Setup):
    with pytest.raises(ValueError, match="approver_type must be one of"):
        setup.create(levels=[_level(1, approver_type="MANAGER")])


def test_role_level_requires_role_code(setup: Setup):
    with pytest.raises(ValueError, match="role_code is required"):
        setup.create(levels=[_level(1, approver_type="ROLE", role_code=None)])


def test_user_level_requires_user_uuid(setup: Setup):
    with pytest.raises(ValueError, match="user_uuid is required"):
        setup.create(levels=[_level(1, approver_type="USER", role_code=None, user_uuid=None)])


def test_duplicate_level_numbers_are_rejected(setup: Setup):
    with pytest.raises(ValueError, match="Duplicate level_number"):
        setup.create(levels=[_level(1), _level(1)])


def test_update_policy_replaces_levels(setup: Setup):
    policy = setup.create(levels=[_level(1, role_code="AP_EXECUTIVE")])
    update = SimpleNamespace(
        name=None, department_id=None, purchase_category_id=None, description=None,
        min_amount=None, max_amount=None,
        levels=[_level(1, role_code="AP_EXECUTIVE"), _level(2, role_code="FINANCE_EXECUTIVE")],
    )
    updated = setup.service.update_policy(policy.id, update)
    assert len(setup.dao.get_levels_for_policy(updated.id)) == 2


def test_update_nonexistent_policy_raises(setup: Setup):
    update = SimpleNamespace(
        name=None, department_id=None, purchase_category_id=None, description=None,
        min_amount=None, max_amount=None, levels=None,
    )
    with pytest.raises(ValueError, match="Approval policy not found"):
        setup.service.update_policy(999, update)


def test_deactivate_then_reactivate_revalidates_overlap(setup: Setup):
    policy_a = setup.create(name="A", min_amount=0, max_amount=50000)
    setup.service.set_policy_status(policy_a.id, False)
    # now safe to create an overlapping policy since A is inactive
    setup.create(name="B", min_amount=0, max_amount=50000)

    # reactivating A should now be rejected - it would overlap with B
    with pytest.raises(ValueError, match="overlaps"):
        setup.service.set_policy_status(policy_a.id, True)


def test_delete_unused_policy_succeeds(setup: Setup):
    policy = setup.create()
    setup.service.delete_policy(policy.id)
    assert setup.dao.get_policy_by_id(policy.id) is None


def test_delete_policy_with_approval_history_is_blocked(setup: Setup):
    policy = setup.create()
    setup.dao.instances_used.add(policy.id)
    with pytest.raises(ValueError, match="deactivate it instead"):
        setup.service.delete_policy(policy.id)


def test_list_policies_filters_by_active(setup: Setup):
    setup.create(name="Active One", min_amount=0, max_amount=50000, is_active=True)
    inactive = setup.create(name="Inactive One", min_amount=50000.01, max_amount=None, is_active=True)
    setup.service.set_policy_status(inactive.id, False)

    active_only = setup.service.list_policies(is_active=True)
    assert {p.name for p in active_only} == {"Active One"}


# ---------------------------------------------------------------------------
# Default (catch-all fallback) policy
# ---------------------------------------------------------------------------

def test_create_default_policy_succeeds_with_no_scoping(setup: Setup):
    policy = setup.create_default()
    assert policy.is_default is True
    assert policy.department_id is None
    assert policy.purchase_category_id is None
    assert policy.min_amount is None
    assert policy.max_amount is None


def test_default_policy_with_department_is_rejected(setup: Setup):
    with pytest.raises(ValueError, match="cannot have a department"):
        setup.service.create_policy(SimpleNamespace(
            name="Bad Default", department_id=10, purchase_category_id=None,
            description=None, min_amount=None, max_amount=None,
            is_active=True, levels=[_level(1, role_code="Super_Admin")], is_default=True,
        ))


def test_default_policy_with_amount_range_is_rejected(setup: Setup):
    with pytest.raises(ValueError, match="cannot have a department"):
        setup.service.create_policy(SimpleNamespace(
            name="Bad Default", department_id=None, purchase_category_id=None,
            description=None, min_amount=0, max_amount=1000,
            is_active=True, levels=[_level(1, role_code="Super_Admin")], is_default=True,
        ))


def test_second_active_default_policy_is_rejected(setup: Setup):
    setup.create_default(name="Default A")
    with pytest.raises(ValueError, match="default policy already exists"):
        setup.create_default(name="Default B")


def test_inactive_default_policy_does_not_block_a_new_active_one(setup: Setup):
    first = setup.create_default(name="Default A")
    setup.service.set_policy_status(first.id, False)
    second = setup.create_default(name="Default B")
    assert second.is_default is True


def test_reactivating_a_default_policy_checks_uniqueness_too(setup: Setup):
    first = setup.create_default(name="Default A")
    setup.service.set_policy_status(first.id, False)
    setup.create_default(name="Default B")  # now the one active default

    with pytest.raises(ValueError, match="default policy already exists"):
        setup.service.set_policy_status(first.id, True)


def test_default_policy_cannot_gain_scoping_via_update(setup: Setup):
    policy = setup.create_default()
    update = SimpleNamespace(
        name=None, department_id=10, purchase_category_id=None,
        description=None, min_amount=None, max_amount=None, levels=None,
    )
    with pytest.raises(ValueError, match="cannot have a department"):
        setup.service.update_policy(policy.id, update)


def test_match_policy_falls_back_to_default_when_nothing_scoped_matches(setup: Setup):
    default_policy = setup.create_default()
    matched = setup.service.match_policy(department_id=10, purchase_category_id=20, amount=999999)
    assert matched.id == default_policy.id


def test_match_policy_prefers_a_scoped_policy_over_the_default(setup: Setup):
    setup.create_default()
    scoped = setup.create(name="Scoped Policy")
    matched = setup.service.match_policy(department_id=10, purchase_category_id=20, amount=1000)
    assert matched.id == scoped.id


def test_match_policy_still_raises_when_no_default_and_nothing_scoped_matches(setup: Setup):
    with pytest.raises(ValueError, match="No applicable approval policy"):
        setup.service.match_policy(department_id=10, purchase_category_id=20, amount=1000)
