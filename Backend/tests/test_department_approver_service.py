# Backend/tests/test_department_approver_service.py
"""Tests for DepartmentApproverService - the AP-owned admin mapping of
"which users can approve for department X" (see
Data_Access_Layer/models/approval.py's DepartmentApprover docstring for
why this is deliberately not a UMS role).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Dict, List

import pytest

from Backend.Business_Layer.services.department_approver_service import DepartmentApproverService

USER_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000a2")


class FakeDB:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeMasterDAO:
    def __init__(self, departments):
        self.departments = departments

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)


class FakeApproverDirectoryDAO:
    def __init__(self, active_users):
        self.active_users = active_users

    def is_user_active(self, user_uuid):
        return user_uuid in self.active_users


class FakeDepartmentApproverDAO:
    def __init__(self):
        self.mappings: Dict[int, object] = {}
        self._next_id = 1

    def create(self, mapping):
        mapping.id = self._next_id
        self._next_id += 1
        self.mappings[mapping.id] = mapping
        return mapping

    def get_by_id(self, mapping_id):
        return self.mappings.get(mapping_id)

    def get_by_department_and_user(self, department_id, user_uuid):
        return next(
            (m for m in self.mappings.values() if m.department_id == department_id and m.user_uuid == user_uuid),
            None,
        )

    def list_for_department(self, department_id, is_active=None) -> List:
        result = [m for m in self.mappings.values() if m.department_id == department_id]
        if is_active is not None:
            result = [m for m in result if m.is_active == is_active]
        return result

    def delete(self, mapping):
        self.mappings.pop(mapping.id, None)


class Setup:
    def __init__(self):
        self.departments = {
            10: SimpleNamespace(id=10, is_active=True),
            11: SimpleNamespace(id=11, is_active=False),
        }
        self.dao = FakeDepartmentApproverDAO()
        self.master_dao = FakeMasterDAO(self.departments)
        self.directory_dao = FakeApproverDirectoryDAO(active_users={USER_A, USER_B})
        self.service = DepartmentApproverService(FakeDB())
        self.service.dao = self.dao
        self.service.master_dao = self.master_dao
        self.service.directory_dao = self.directory_dao


@pytest.fixture
def setup():
    return Setup()


def test_add_department_approver(setup: Setup):
    mapping = setup.service.add(10, USER_A, created_by="admin1")
    assert mapping.department_id == 10
    assert mapping.user_uuid == USER_A
    assert mapping.is_active is True


def test_add_to_unknown_department_raises(setup: Setup):
    with pytest.raises(ValueError, match="Department not found"):
        setup.service.add(999, USER_A, created_by="admin1")


def test_add_to_inactive_department_raises(setup: Setup):
    with pytest.raises(ValueError, match="Department is not active"):
        setup.service.add(11, USER_A, created_by="admin1")


def test_add_inactive_user_raises(setup: Setup):
    inactive_user = uuid.uuid4()
    with pytest.raises(ValueError, match="active user in the approver directory"):
        setup.service.add(10, inactive_user, created_by="admin1")


def test_adding_the_same_active_mapping_twice_raises(setup: Setup):
    setup.service.add(10, USER_A, created_by="admin1")
    with pytest.raises(ValueError, match="already a department approver"):
        setup.service.add(10, USER_A, created_by="admin1")


def test_re_adding_a_deactivated_mapping_reactivates_it(setup: Setup):
    mapping = setup.service.add(10, USER_A, created_by="admin1")
    setup.dao.mappings[mapping.id].is_active = False

    reactivated = setup.service.add(10, USER_A, created_by="admin2")
    assert reactivated.id == mapping.id
    assert reactivated.is_active is True


def test_remove_department_approver(setup: Setup):
    mapping = setup.service.add(10, USER_A, created_by="admin1")
    setup.service.remove(mapping.id)
    assert setup.dao.get_by_id(mapping.id) is None


def test_remove_nonexistent_mapping_raises(setup: Setup):
    with pytest.raises(ValueError, match="not found"):
        setup.service.remove(999)


def test_list_for_department_filters_by_active(setup: Setup):
    m1 = setup.service.add(10, USER_A, created_by="admin1")
    m2 = setup.service.add(10, USER_B, created_by="admin1")
    setup.dao.mappings[m2.id].is_active = False

    all_mappings = setup.service.list_for_department(10)
    assert {m.id for m in all_mappings} == {m1.id, m2.id}

    active_only = setup.service.list_for_department(10, is_active=True)
    assert {m.id for m in active_only} == {m1.id}


def test_list_for_unknown_department_raises(setup: Setup):
    with pytest.raises(ValueError, match="Department not found"):
        setup.service.list_for_department(999)
