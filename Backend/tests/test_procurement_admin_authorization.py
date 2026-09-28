# Backend/tests/test_procurement_admin_authorization.py
"""Authorization tests for the Procurement admin APIs (individual + bulk PR
delete).

Follows test_procurement_authorization.py: a minimal FastAPI app with a fake
auth/db middleware and PrBulkCleanupService stubbed, so only the
permission_based_access wiring is verified here (the cleanup itself is
covered by test_pr_bulk_cleanup.py).
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import procurement_admin_route, procurement_route
from Backend.Business_Layer.services.pr_bulk_cleanup_service import CleanupResult

from Backend.tests.test_procurement_authorization import (
    PR_APPROVER_PERMISSIONS,
    PR_CREATOR_PERMISSIONS,
    PROCUREMENT_OFFICER_PERMISSIONS,
)

# The Admin role's everyday permissions, WITHOUT the purge permission.
ADMIN_WITHOUT_PURGE_PERMISSIONS = sorted(
    set(PR_CREATOR_PERMISSIONS) | set(PR_APPROVER_PERMISSIONS) | set(PROCUREMENT_OFFICER_PERMISSIONS)
    | {"APPROVAL_POLICY_MANAGE", "PR_REJECT", "SEND_RFQ"}
)
ADMIN_WITH_PURGE_PERMISSIONS = ADMIN_WITHOUT_PURGE_PERMISSIONS + ["PR_ADMIN_PURGE"]

# (label, method, path, json body) for every admin endpoint.
ENDPOINTS = [
    ("bulk_ids", "DELETE", "/purchase-requisitions", {"pr_ids": [1, 2]}),
    ("bulk_all", "DELETE", "/purchase-requisitions", {"delete_all": True}),
    ("individual", "DELETE", "/purchase-requisitions/1", None),
]
ENDPOINT_IDS = [e[0] for e in ENDPOINTS]


class _FakeService:
    calls = 0

    def __init__(self, db):
        pass

    def _result(self, n):
        _FakeService.calls += 1
        return CleanupResult(deleted_counts={"purchase_requisition": n})

    def delete_all_purchase_requisitions(self):
        return self._result(0)

    def delete_purchase_requisitions(self, pr_ids):
        return self._result(len(pr_ids))

    def delete_purchase_requisition(self, pr_id):
        return self._result(1)


@pytest.fixture(autouse=True)
def _stub_service(monkeypatch):
    _FakeService.calls = 0
    monkeypatch.setattr(procurement_admin_route, "PrBulkCleanupService", _FakeService)


def _client(user):
    class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if user is not None:
                request.state.user = user
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_FakeAuthAndDBMiddleware)
    app.include_router(procurement_admin_route.router)
    return TestClient(app)


def _call(user, endpoint):
    _, method, path, body = endpoint
    return _client(user).request(method, path, json=body)


def _user(permissions):
    return {"user_id": "u-1", "permissions": permissions}


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=ENDPOINT_IDS)
def test_unauthenticated_is_401(endpoint):
    response = _call(None, endpoint)
    assert response.status_code == 401
    assert _FakeService.calls == 0


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=ENDPOINT_IDS)
@pytest.mark.parametrize(
    "permissions",
    [
        ADMIN_WITHOUT_PURGE_PERMISSIONS,
        PR_CREATOR_PERMISSIONS,
        PR_APPROVER_PERMISSIONS,
        PROCUREMENT_OFFICER_PERMISSIONS,
        ["PR_DELETE"],
        ["Super_Admin"],
        [],
    ],
    ids=["admin_without_purge", "pr_creator", "pr_approver", "procurement_officer", "pr_delete",
         "super_admin_is_not_a_permission", "none"],
)
def test_without_pr_admin_purge_is_forbidden(permissions, endpoint):
    response = _call(_user(permissions), endpoint)
    assert response.status_code == 403
    assert _FakeService.calls == 0


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=ENDPOINT_IDS)
def test_permissions_claim_missing_is_forbidden(endpoint):
    response = _call({"user_id": "u-1"}, endpoint)
    assert response.status_code == 403
    assert _FakeService.calls == 0


def test_forbidden_is_decided_before_the_body_is_validated():
    response = _client(_user(PR_CREATOR_PERMISSIONS)).request("DELETE", "/purchase-requisitions", json={})
    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=ENDPOINT_IDS)
@pytest.mark.parametrize(
    "permissions",
    [ADMIN_WITH_PURGE_PERMISSIONS, ["PR_ADMIN_PURGE"], ["pr_admin_purge"], " PR_ADMIN_PURGE "],
    ids=["admin_with_purge", "exact", "lowercase", "bare_string_whitespace"],
)
def test_pr_admin_purge_is_allowed(permissions, endpoint):
    response = _call(_user(permissions), endpoint)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert _FakeService.calls == 1


def test_only_permission_based_access_is_used_no_role_logic():
    source = inspect.getsource(procurement_admin_route)
    assert procurement_admin_route._PR_ADMIN_PURGE_PERMISSIONS == ["PR_ADMIN_PURGE"]
    assert "role_based_access" not in source
    assert "Super_Admin" not in source
    for route in procurement_admin_route.router.routes:
        assert len(route.dependencies) == 1, route.path


def test_not_exposed_on_the_everyday_procurement_router():
    everyday = {(route.path, method) for route in procurement_route.router.routes for method in route.methods}
    assert ("/purchase-requisitions", "DELETE") not in everyday
    assert not any("admin" in path for path, _ in everyday)
