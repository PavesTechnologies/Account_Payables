# Backend/tests/test_approver_resolver_service.py
"""Tests for ApproverResolverService not already covered by the
end-to-end scenarios in test_invoice_approval_workflow.py (basic
DEPARTMENT_APPROVER/ROLE/USER resolution and the inactive-excluded case
are covered there).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Dict

import pytest

from Backend.Business_Layer.services.approver_resolver_service import ApproverResolverService

AP_EXEC = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


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
    def __init__(self):
        self.mappings: Dict[int, dict] = {}  # department_id -> {user_uuid: is_active}

    def add(self, department_id, user_uuid, is_active=True):
        self.mappings.setdefault(department_id, {})[user_uuid] = is_active

    def get_active_user_uuids_for_department(self, department_id):
        return [u for u, active in self.mappings.get(department_id, {}).items() if active]

    def get_by_department_and_user(self, department_id, user_uuid):
        entry = self.mappings.get(department_id, {})
        if user_uuid not in entry:
            return None
        return SimpleNamespace(is_active=entry[user_uuid])


@pytest.fixture
def resolver():
    svc = ApproverResolverService(db=None)
    svc.dao = FakeApproverDirectoryDAO()
    svc.department_approver_dao = FakeDepartmentApproverDAO()
    return svc


def test_resolve_user_uuid_maps_numeric_user_id(resolver):
    resolver.dao.add_user(5100010, AP_EXEC, roles=["AP_EXECUTIVE"])
    assert resolver.resolve_user_uuid(5100010) == AP_EXEC
    assert resolver.resolve_user_uuid("5100010") == AP_EXEC  # JWT claims often arrive as strings


def test_resolve_user_uuid_returns_none_for_unmapped_user(resolver):
    assert resolver.resolve_user_uuid(9999999) is None


def test_resolve_user_uuid_returns_none_for_non_numeric_input(resolver):
    # e.g. a JWT whose 'sub' claim is already a UUID from a different system
    assert resolver.resolve_user_uuid("not-a-number") is None


def test_resolve_unknown_approver_type_raises(resolver):
    with pytest.raises(ValueError, match="Unknown approver_type"):
        resolver.resolve("MANAGER")


def test_resolve_department_approver_without_department_id_raises(resolver):
    with pytest.raises(ValueError, match="department_id is missing"):
        resolver.resolve("DEPARTMENT_APPROVER", department_id=None)


def test_resolve_department_approver_excludes_inactive_mapping_row(resolver):
    """The department_approver row itself was deactivated by an admin
    (not the user's account) - must not resolve."""
    resolver.dao.add_user(5100010, AP_EXEC, roles=[])
    resolver.department_approver_dao.add(10, AP_EXEC, is_active=False)
    assert resolver.resolve("DEPARTMENT_APPROVER", department_id=10) == []


def test_resolve_role_without_role_code_raises(resolver):
    with pytest.raises(ValueError, match="role_code is missing"):
        resolver.resolve("ROLE", role_code=None)


def test_resolve_user_without_user_uuid_raises(resolver):
    with pytest.raises(ValueError, match="user_uuid is missing"):
        resolver.resolve("USER", user_uuid=None)


def test_is_eligible_now_false_when_account_inactive(resolver):
    resolver.dao.add_user(5100010, AP_EXEC, roles=["AP_EXECUTIVE"], active=False)
    assert resolver.is_eligible_now(AP_EXEC, "ROLE", "AP_EXECUTIVE") is False


def test_is_eligible_now_false_when_role_revoked_but_account_active(resolver):
    """Account is still active, but this specific role assignment was
    revoked since the approval step was created - spec section 20."""
    resolver.dao.add_user(5100010, AP_EXEC, roles=[], active=True)  # role removed, account intact
    assert resolver.is_eligible_now(AP_EXEC, "ROLE", "AP_EXECUTIVE") is False


def test_is_eligible_now_false_when_department_approver_mapping_removed(resolver):
    """Account is still active, but the admin removed this specific
    department-approver mapping since the step was created."""
    resolver.dao.add_user(5100010, AP_EXEC, roles=[], active=True)
    assert resolver.is_eligible_now(AP_EXEC, "DEPARTMENT_APPROVER", department_id=10) is False

    resolver.department_approver_dao.add(10, AP_EXEC, is_active=True)
    assert resolver.is_eligible_now(AP_EXEC, "DEPARTMENT_APPROVER", department_id=10) is True


def test_is_eligible_now_true_for_user_type_needs_only_active_account(resolver):
    resolver.dao.add_user(5100010, AP_EXEC, roles=[], active=True)
    assert resolver.is_eligible_now(AP_EXEC, "USER") is True
