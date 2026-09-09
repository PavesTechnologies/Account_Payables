# Backend/tests/test_purchase_category_department.py
"""Tests for the real Department -> PurchaseCategory ownership relationship
(purchase_category.department_id) and its enforcement in PR create/update.

Follows the project's existing fake-DAO test style (see
test_pr_approval_workflow.py / test_rfq_workflow.py): no real DB connection.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from Backend.Business_Layer.services.master_service import MasterService
from Backend.Business_Layer.services.procurement_service import ProcurementService


# ---------------------------------------------------------------------------
# Master (Department / PurchaseCategory CRUD) fakes
# ---------------------------------------------------------------------------


class FakeMasterDB:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeMasterDAO:
    def __init__(self, departments: dict):
        self.departments = departments
        self.categories: Dict[int, object] = {}
        self._next_id = 1

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)

    def get_all_purchase_categories(self, department_id=None):
        rows = list(self.categories.values())
        if department_id is not None:
            rows = [c for c in rows if c.department_id == department_id]
        return sorted(rows, key=lambda c: c.name)

    def get_purchase_category_by_id(self, purchase_category_id):
        return self.categories.get(purchase_category_id)

    def get_purchase_category_by_code_or_name(self, code, name):
        for c in self.categories.values():
            if c.code == code or c.name == name:
                return c
        return None

    def create_purchase_category(self, purchase_category):
        purchase_category.id = self._next_id
        self._next_id += 1
        self.categories[purchase_category.id] = purchase_category
        return purchase_category


@pytest.fixture
def master_env():
    departments = {
        1: SimpleNamespace(id=1, code="IT", is_active=True),
        2: SimpleNamespace(id=2, code="HR", is_active=False),  # inactive on purpose
    }
    service = MasterService(db=FakeMasterDB())
    dao = FakeMasterDAO(departments)
    service.master_dao = dao
    return SimpleNamespace(service=service, dao=dao, departments=departments)


def test_create_category_with_valid_department_succeeds(master_env):
    payload = SimpleNamespace(code="it_hardware", name="IT Hardware", department_id=1, is_active=True)
    category = master_env.service.create_purchase_category(payload)
    assert category.department_id == 1
    assert category.code == "IT_HARDWARE"


def test_create_category_with_nonexistent_department_is_rejected(master_env):
    payload = SimpleNamespace(code="x", name="X", department_id=999, is_active=True)
    with pytest.raises(ValueError, match="Department not found"):
        master_env.service.create_purchase_category(payload)


def test_create_category_with_inactive_department_is_rejected(master_env):
    payload = SimpleNamespace(code="hr_recruitment", name="HR Recruitment", department_id=2, is_active=True)
    with pytest.raises(ValueError, match="not active"):
        master_env.service.create_purchase_category(payload)


def test_categories_can_be_filtered_by_department(master_env):
    master_env.service.create_purchase_category(
        SimpleNamespace(code="it_hardware", name="IT Hardware", department_id=1, is_active=True)
    )
    master_env.service.create_purchase_category(
        SimpleNamespace(code="it_software", name="IT Software", department_id=1, is_active=True)
    )
    master_env.departments[2] = SimpleNamespace(id=2, code="HR", is_active=True)
    master_env.service.create_purchase_category(
        SimpleNamespace(code="hr_recruitment", name="HR Recruitment", department_id=2, is_active=True)
    )

    all_categories = master_env.service.get_all_purchase_categories()
    assert len(all_categories) == 3

    it_only = master_env.service.get_all_purchase_categories(department_id=1)
    assert {c.code for c in it_only} == {"IT_HARDWARE", "IT_SOFTWARE"}

    hr_only = master_env.service.get_all_purchase_categories(department_id=2)
    assert {c.code for c in hr_only} == {"HR_RECRUITMENT"}


def test_update_category_reassignment_validates_new_department(master_env):
    category = master_env.service.create_purchase_category(
        SimpleNamespace(code="it_hardware", name="IT Hardware", department_id=1, is_active=True)
    )
    with pytest.raises(ValueError, match="Department not found"):
        master_env.service.update_purchase_category(
            category.id, SimpleNamespace(code="IT_HARDWARE", name="IT Hardware", department_id=999, is_active=True)
        )


# ---------------------------------------------------------------------------
# PR department/category match enforcement
# ---------------------------------------------------------------------------


class FakeStatus:
    def __init__(self, status_id, module_name, status_code):
        self.status_id = status_id
        self.module_name = module_name
        self.status_code = status_code


class StatusRegistry:
    def __init__(self):
        self._by_code: Dict[Tuple[str, str], FakeStatus] = {}
        self._by_id: Dict[int, FakeStatus] = {}
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
            status = self.get_by_id(obj.status_id)
            if hasattr(obj, "_sa_instance_state"):
                set_committed_value(obj, "status", status)
            else:
                obj.status = status
        return obj


class FakeDB:
    def __init__(self, registry):
        self.registry = registry

    def commit(self):
        pass

    def refresh(self, obj):
        self.registry.attach(obj)

    def rollback(self):
        pass


class FakeProcurementDAO:
    def __init__(self, registry, departments, categories):
        self.registry = registry
        self.departments = departments
        self.categories = categories
        self.prs: Dict[int, object] = {}
        self.lines: Dict[int, object] = {}
        self._next_pr_id = 1
        self._next_line_id = 1

    def create_purchase_requisition(self, pr):
        pr.id = self._next_pr_id
        self._next_pr_id += 1
        self.prs[pr.id] = pr
        return self.registry.attach(pr)

    def get_purchase_requisition_by_id(self, pr_id):
        return self.registry.attach(self.prs.get(pr_id))

    def get_lines_by_pr_id(self, pr_id):
        return [l for l in self.lines.values() if l.pr_id == pr_id]

    def create_purchase_requisition_line(self, line):
        line.id = self._next_line_id
        self._next_line_id += 1
        self.lines[line.id] = line
        return line

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)

    def create_audit_log(self, audit_log):
        return audit_log


class FakeMasterDAOForPR:
    def __init__(self, departments, categories):
        self.departments = departments
        self.categories = categories

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)

    def get_purchase_category_by_id(self, purchase_category_id):
        return self.categories.get(purchase_category_id)

    def get_uom_by_code(self, code):
        return None


@pytest.fixture
def pr_env():
    registry = StatusRegistry()
    registry.add("PURCHASE_REQUISITION", "DRAFT")

    departments = {
        1: SimpleNamespace(id=1, is_active=True),  # IT
        2: SimpleNamespace(id=2, is_active=True),  # HR
    }
    categories = {
        100: SimpleNamespace(id=100, is_active=True, department_id=1),  # IT_HARDWARE, belongs to IT
        200: SimpleNamespace(id=200, is_active=True, department_id=2),  # HR_RECRUITMENT, belongs to HR
    }

    service = ProcurementService(db=FakeDB(registry))
    service.procurement_dao = FakeProcurementDAO(registry, departments, categories)
    service.master_dao = FakeMasterDAOForPR(departments, categories)

    return SimpleNamespace(service=service, departments=departments, categories=categories)


def _create_payload(department_id, purchase_category_id):
    return SimpleNamespace(
        department_id=department_id, purchase_category_id=purchase_category_id,
        priority="NORMAL", required_by=None, delivery_location=None, justification=None, lines=[],
    )


def test_pr_create_with_matching_department_category_succeeds(pr_env):
    pr = pr_env.service.create_purchase_requisition(_create_payload(1, 100), user_id="buyer1")
    assert pr.department_id == 1
    assert pr.purchase_category_id == 100


def test_pr_create_with_mismatched_department_category_is_rejected(pr_env):
    with pytest.raises(ValueError, match="does not belong to the selected department"):
        pr_env.service.create_purchase_requisition(_create_payload(1, 200), user_id="buyer1")


def test_pr_update_also_rejects_mismatched_department_category(pr_env):
    pr = pr_env.service.create_purchase_requisition(_create_payload(1, 100), user_id="buyer1")

    update = SimpleNamespace(
        department_id=None, purchase_category_id=200, priority=None,
        required_by=None, delivery_location=None, justification=None,
    )
    with pytest.raises(ValueError, match="does not belong to the selected department"):
        pr_env.service.update_purchase_requisition(pr.id, update)
