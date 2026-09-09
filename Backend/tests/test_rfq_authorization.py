# Backend/tests/test_rfq_authorization.py
"""Authorization tests for the RFQ APIs.

Follows the project's existing route-test convention (see
test_procurement_authorization.py / test_new_routes.py): a minimal FastAPI
app with a fake auth/db middleware, and RFQService monkeypatched so these
tests only verify the permission_based_access dependency wiring - not
business logic (that's covered by test_rfq_workflow.py).

Prior to this change, rfq_route.py had no authorization at all - every
endpoint was reachable by any authenticated user regardless of role. A first
authorization pass then gated it with brand-new, unprecedented permission
strings (RFQ_VIEW/RFQ_CREATE/RFQ_CLOSE) that were never part of the officer's
actual granted permission set (see PROCUREMENT_OFFICER_PERMISSIONS in
test_procurement_authorization.py, which predates any RFQ work and is the
canonical reference for what this role already has) - so real PR Officer
users got 403 on every RFQ endpoint. This file's permission list now matches
that canonical set exactly (view/create/close reuse the officer's existing
QUOTATION_VIEW/QUOTATION_CREATE/QUOTATION_UPDATE grants; only INVITE_VENDOR
and SEND_RFQ - explicitly promised as new capabilities - are net-new).
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import rfq_route
from Backend.tests.test_procurement_authorization import (
    PROCUREMENT_OFFICER_PERMISSIONS as PROCUREMENT_OFFICER_QUOTATION_PERMISSIONS,
)

# The officer's real, already-granted permission set (imported from the
# canonical reference) plus the two genuinely new capabilities this RFQ
# feature was built for.
PROCUREMENT_OFFICER_PERMISSIONS = PROCUREMENT_OFFICER_QUOTATION_PERMISSIONS + [
    "INVITE_VENDOR",
    "SEND_RFQ",
]

# Everything the officer already had *before* RFQ work, deliberately without
# INVITE_VENDOR/SEND_RFQ - proves those two remain distinct, required grants
# rather than being silently implied by QUOTATION_* access.
PROCUREMENT_OFFICER_WITHOUT_RFQ_ACTIONS = list(PROCUREMENT_OFFICER_QUOTATION_PERMISSIONS)

PR_CREATOR_PERMISSIONS = ["PR_VIEW", "PR_CREATE", "PR_EDIT", "PR_SUBMIT"]


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
    app.include_router(rfq_route.router)
    return TestClient(app)


def _user(permissions):
    return {"user_id": "test-user", "permissions": permissions}


def _fake_rfq():
    return SimpleNamespace(
        id=1,
        rfq_number="RFQ-000001",
        pr_id=1,
        status_id=1,
        created_by="test-user",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        due_date=None,
        sent_at=None,
        closed_by=None,
        closed_at=None,
        rfq_vendor=[],
    )


def _stub_service(monkeypatch, method_name, return_value=None):
    from Backend.Business_Layer.services import rfq_service

    def _stub(self, *args, **kwargs):
        return return_value if return_value is not None else _fake_rfq()

    monkeypatch.setattr(rfq_service.RFQService, method_name, _stub)


def _stub_send_rfq(monkeypatch):
    from Backend.Business_Layer.services import rfq_service

    def _stub(self, *args, **kwargs):
        return _fake_rfq(), []

    monkeypatch.setattr(rfq_service.RFQService, "send_rfq", _stub)


# ---------------------------------------------------------------------------
# 401 / 403
# ---------------------------------------------------------------------------


def test_no_authenticated_user_returns_401():
    client = _make_client(None)
    response = client.get("/")
    assert response.status_code == 401


def test_missing_permission_returns_403(monkeypatch):
    _stub_service(monkeypatch, "list_rfqs", return_value=[])
    client = _make_client(_user(["PR_VIEW"]))
    response = client.get("/")
    assert response.status_code == 403


def test_permissions_missing_from_jwt_returns_403():
    client = _make_client({"user_id": "test-user"})
    response = client.get("/")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Procurement Officer: full access to the RFQ endpoint matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def officer_client():
    return _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))


def test_officer_can_create_rfq(monkeypatch, officer_client):
    _stub_service(monkeypatch, "create_rfq")
    response = officer_client.post("/", json={"pr_id": 1})
    assert response.status_code == 200


def test_officer_can_list_rfqs(monkeypatch, officer_client):
    _stub_service(monkeypatch, "list_rfqs", return_value=[])
    response = officer_client.get("/")
    assert response.status_code == 200


def test_officer_can_get_rfq_by_id(monkeypatch, officer_client):
    _stub_service(monkeypatch, "get_rfq")
    response = officer_client.get("/1")
    assert response.status_code == 200


def test_officer_can_invite_vendors(monkeypatch, officer_client):
    _stub_service(monkeypatch, "invite_vendors")
    response = officer_client.post("/1/vendors", json={"vendor_ids": [1, 2]})
    assert response.status_code == 200


def test_officer_can_list_rfq_vendors(monkeypatch, officer_client):
    _stub_service(monkeypatch, "list_vendors", return_value=[])
    response = officer_client.get("/1/vendors")
    assert response.status_code == 200


def test_officer_can_send_rfq(monkeypatch, officer_client):
    _stub_send_rfq(monkeypatch)
    response = officer_client.post("/1/send")
    assert response.status_code == 200


def test_officer_can_close_rfq(monkeypatch, officer_client):
    _stub_service(monkeypatch, "close_rfq")
    response = officer_client.post("/1/close")
    assert response.status_code == 200


def test_officer_can_view_quotations_for_rfq(monkeypatch, officer_client):
    _stub_service(monkeypatch, "list_quotations", return_value=[])
    response = officer_client.get("/1/quotations")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Officer's pre-existing (pre-RFQ-feature) permissions alone are not enough
# for the two genuinely new capabilities - this is the exact 403 regression
# that motivated this fix, locked in so it can't silently reappear.
# ---------------------------------------------------------------------------


@pytest.fixture
def officer_without_rfq_actions_client():
    return _make_client(_user(PROCUREMENT_OFFICER_WITHOUT_RFQ_ACTIONS))


def test_officer_can_view_and_create_rfq_without_new_grants(monkeypatch, officer_without_rfq_actions_client):
    """QUOTATION_VIEW/QUOTATION_CREATE/QUOTATION_UPDATE - already granted to
    every procurement officer - are sufficient for view/create/close, so no
    UMS/JWT change is required for those three actions."""
    _stub_service(monkeypatch, "list_rfqs", return_value=[])
    assert officer_without_rfq_actions_client.get("/").status_code == 200

    _stub_service(monkeypatch, "create_rfq")
    assert officer_without_rfq_actions_client.post("/", json={"pr_id": 1}).status_code == 200

    _stub_service(monkeypatch, "close_rfq")
    assert officer_without_rfq_actions_client.post("/1/close").status_code == 200


def test_officer_without_invite_vendor_grant_is_rejected(officer_without_rfq_actions_client):
    response = officer_without_rfq_actions_client.post("/1/vendors", json={"vendor_ids": [1]})
    assert response.status_code == 403


def test_officer_without_send_rfq_grant_is_rejected(officer_without_rfq_actions_client):
    response = officer_without_rfq_actions_client.post("/1/send")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Invite Vendor: isolated, minimal proof of the canonical permission name.
# The endpoint is gated by exactly permission_based_access(["INVITE_VENDOR"])
# (Backend/API_Layer/routes/rfq_route.py) - no accidental dependency on
# RFQ_VIEW/RFQ_CREATE/RFQ_CLOSE/QUOTATION_CREATE or any other permission.
# ---------------------------------------------------------------------------


def test_invite_vendor_allowed_with_only_invite_vendor_permission(monkeypatch):
    """A JWT carrying nothing but INVITE_VENDOR must be sufficient on its
    own - proves the check isn't silently ANDed with some other permission."""
    _stub_service(monkeypatch, "invite_vendors")
    client = _make_client(_user(["INVITE_VENDOR"]))
    response = client.post("/1/vendors", json={"vendor_ids": [1]})
    assert response.status_code == 200


def test_invite_vendor_denied_without_invite_vendor_permission():
    """Every other real procurement permission except INVITE_VENDOR itself
    must still be denied - proves no other permission silently substitutes
    for it (e.g. QUOTATION_CREATE, RFQ_VIEW/RFQ_CREATE/RFQ_CLOSE)."""
    other_permissions = [
        p for p in (PROCUREMENT_OFFICER_QUOTATION_PERMISSIONS + ["SEND_RFQ", "RFQ_VIEW", "RFQ_CREATE", "RFQ_CLOSE"])
        if p != "INVITE_VENDOR"
    ]
    client = _make_client(_user(other_permissions))
    response = client.post("/1/vendors", json={"vendor_ids": [1]})
    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have permission to access this resource"


# ---------------------------------------------------------------------------
# PR Creator: no RFQ permissions -> everything rejected
# ---------------------------------------------------------------------------


@pytest.fixture
def pr_creator_client():
    return _make_client(_user(PR_CREATOR_PERMISSIONS))


def test_pr_creator_cannot_create_rfq(pr_creator_client):
    response = pr_creator_client.post("/", json={"pr_id": 1})
    assert response.status_code == 403


def test_pr_creator_cannot_invite_vendors(pr_creator_client):
    response = pr_creator_client.post("/1/vendors", json={"vendor_ids": [1]})
    assert response.status_code == 403


def test_pr_creator_cannot_send_rfq(pr_creator_client):
    response = pr_creator_client.post("/1/send")
    assert response.status_code == 403


def test_pr_creator_cannot_close_rfq(pr_creator_client):
    response = pr_creator_client.post("/1/close")
    assert response.status_code == 403


def test_pr_creator_cannot_view_rfqs(pr_creator_client):
    response = pr_creator_client.get("/")
    assert response.status_code == 403
