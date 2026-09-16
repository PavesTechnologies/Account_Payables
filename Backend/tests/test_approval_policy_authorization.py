# Backend/tests/test_approval_policy_authorization.py
"""Authorization tests for the Approval Policy admin APIs.

Follows the project's existing route-test convention (see
test_procurement_authorization.py): a minimal FastAPI app with a fake
auth/db middleware, ApprovalPolicyService/ApproverDirectoryDAO
monkeypatched so these tests only verify the permission_based_access
dependency wiring - not business logic (that's covered by
test_approval_policy_service.py).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import approval_policy_route


def _make_middleware(user):
    class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if user is not None:
                request.state.user = user
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    return _FakeAuthAndDBMiddleware


def _make_client(user):
    app = FastAPI()
    app.add_middleware(_make_middleware(user))
    app.include_router(approval_policy_route.router)
    return TestClient(app)


def _user(permissions):
    return {"user_id": "test-user", "permissions": permissions}


def _fake_policy():
    return SimpleNamespace(
        id=1, name="Policy A", is_default=False, department_id=1, purchase_category_id=1, is_active=True,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        description=None, min_amount=None, max_amount=None, levels=[],
    )


def _stub_service(monkeypatch, method_name, return_value=None):
    from Backend.Business_Layer.services import approval_policy_service

    def _stub(self, *args, **kwargs):
        return return_value if return_value is not None else _fake_policy()

    monkeypatch.setattr(approval_policy_service.ApprovalPolicyService, method_name, _stub)


def _stub_directory(monkeypatch, method_name, return_value):
    from Backend.Data_Access_Layer.dao import approver_directory_dao

    monkeypatch.setattr(
        approver_directory_dao.ApproverDirectoryDAO, method_name, lambda self, *a, **kw: return_value
    )


def _fake_department_approver():
    return SimpleNamespace(
        id=1, department_id=1, user_uuid="00000000-0000-0000-0000-0000000000a1",
        is_active=True, created_at="2026-01-01T00:00:00", created_by="admin1",
    )


def _stub_department_approver_service(monkeypatch, method_name, return_value=None):
    from Backend.Business_Layer.services import department_approver_service

    def _stub(self, *args, **kwargs):
        return return_value if return_value is not None else _fake_department_approver()

    monkeypatch.setattr(department_approver_service.DepartmentApproverService, method_name, _stub)


# ---------------------------------------------------------------------------
# 401 / 403 / normalization
# ---------------------------------------------------------------------------

def test_no_authenticated_user_returns_401():
    client = _make_client(None)
    response = client.get("/approval-policies")
    assert response.status_code == 401


def test_missing_permission_returns_403():
    client = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    response = client.get("/approval-policies")
    assert response.status_code == 403


def test_correct_permission_is_allowed(monkeypatch):
    _stub_service(monkeypatch, "list_policies", return_value=[])
    client = _make_client(_user(["APPROVAL_POLICY_MANAGE"]))
    response = client.get("/approval-policies")
    assert response.status_code == 200


def test_case_insensitive_permission_is_allowed(monkeypatch):
    _stub_service(monkeypatch, "list_policies", return_value=[])
    client = _make_client(_user(["approval_policy_manage"]))
    response = client.get("/approval-policies")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Endpoint matrix - all gated on APPROVAL_POLICY_MANAGE
# ---------------------------------------------------------------------------

@pytest.fixture
def manager_client():
    return _make_client(_user(["APPROVAL_POLICY_MANAGE"]))


def test_manager_can_list_policies(monkeypatch, manager_client):
    _stub_service(monkeypatch, "list_policies", return_value=[])
    assert manager_client.get("/approval-policies").status_code == 200


def test_manager_can_get_policy(monkeypatch, manager_client):
    _stub_service(monkeypatch, "get_policy")
    assert manager_client.get("/approval-policies/1").status_code == 200


def test_manager_can_create_policy(monkeypatch, manager_client):
    _stub_service(monkeypatch, "create_policy")
    response = manager_client.post(
        "/approval-policies",
        json={
            "name": "Policy A", "department_id": 1, "purchase_category_id": 1,
            "levels": [{"level_number": 1, "approver_type": "ROLE", "role_code": "AP_EXECUTIVE"}],
        },
    )
    assert response.status_code == 200


def test_manager_can_update_policy(monkeypatch, manager_client):
    _stub_service(monkeypatch, "update_policy")
    assert manager_client.put("/approval-policies/1", json={}).status_code == 200


def test_manager_can_change_policy_status(monkeypatch, manager_client):
    _stub_service(monkeypatch, "set_policy_status")
    response = manager_client.patch("/approval-policies/1/status", json={"is_active": False})
    assert response.status_code == 200


def test_manager_can_delete_policy(monkeypatch, manager_client):
    _stub_service(monkeypatch, "delete_policy", return_value=None)
    assert manager_client.delete("/approval-policies/1").status_code == 200


def test_manager_can_list_approver_roles(monkeypatch, manager_client):
    _stub_directory(monkeypatch, "list_distinct_role_codes", [])
    assert manager_client.get("/approval/roles").status_code == 200


def test_manager_can_list_approvers(monkeypatch, manager_client):
    _stub_directory(monkeypatch, "list_active_directory", [])
    assert manager_client.get("/approval/approvers").status_code == 200


def test_non_manager_cannot_create_policy():
    client = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    response = client.post(
        "/approval-policies",
        json={"name": "X", "department_id": 1, "purchase_category_id": 1, "levels": []},
    )
    assert response.status_code == 403


def test_non_manager_cannot_delete_policy():
    client = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    assert client.delete("/approval-policies/1").status_code == 403


# ---------------------------------------------------------------------------
# Department approvers (AP-owned mapping, not a UMS role)
# ---------------------------------------------------------------------------

def test_manager_can_list_department_approvers(monkeypatch, manager_client):
    _stub_department_approver_service(monkeypatch, "list_for_department", return_value=[])
    assert manager_client.get("/approval/department-approvers?department_id=1").status_code == 200


def test_manager_can_add_department_approver(monkeypatch, manager_client):
    _stub_department_approver_service(monkeypatch, "add")
    response = manager_client.post(
        "/approval/department-approvers",
        json={"department_id": 1, "user_uuid": "00000000-0000-0000-0000-0000000000a1"},
    )
    assert response.status_code == 200


def test_manager_can_remove_department_approver(monkeypatch, manager_client):
    _stub_department_approver_service(monkeypatch, "remove", return_value=None)
    assert manager_client.delete("/approval/department-approvers/1").status_code == 200


def test_non_manager_cannot_add_department_approver():
    client = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    response = client.post(
        "/approval/department-approvers",
        json={"department_id": 1, "user_uuid": "00000000-0000-0000-0000-0000000000a1"},
    )
    assert response.status_code == 403
