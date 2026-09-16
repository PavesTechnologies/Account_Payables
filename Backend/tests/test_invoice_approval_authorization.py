# Backend/tests/test_invoice_approval_authorization.py
"""Authorization tests for the invoice approval APIs
(send-for-approval/approve/reject/status). Follows the project's
existing route-test convention (see test_procurement_authorization.py):
a minimal FastAPI app with a fake auth/db middleware,
InvoiceApprovalService monkeypatched so these tests only verify the
permission_based_access dependency wiring - not business logic (that's
covered by test_invoice_approval_workflow.py).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import invoice_approval_route


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
    app.include_router(invoice_approval_route.router)
    return TestClient(app)


def _user(permissions):
    return {"user_id": "5100010", "permissions": permissions}


def _fake_invoice_approval():
    return SimpleNamespace(
        invoice_approval_id=1, invoice_id=1, approval_policy_id=1, status="IN_PROGRESS",
        created_at="2026-01-01T00:00:00", completed_at=None, steps=[],
    )


def _stub_service(monkeypatch, method_name, return_value=None):
    from Backend.Business_Layer.services import invoice_approval_service

    def _stub(self, *args, **kwargs):
        return return_value if return_value is not None else _fake_invoice_approval()

    monkeypatch.setattr(invoice_approval_service.InvoiceApprovalService, method_name, _stub)


# ---------------------------------------------------------------------------
# 401 / 403
# ---------------------------------------------------------------------------

def test_no_authenticated_user_returns_401_on_approve():
    client = _make_client(None)
    response = client.post("/1/approve", json={})
    assert response.status_code == 401


def test_missing_permission_returns_403_on_approve():
    client = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    response = client.post("/1/approve", json={})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Each action gated on its own permission
# ---------------------------------------------------------------------------

def test_send_for_approval_requires_its_own_permission(monkeypatch):
    _stub_service(monkeypatch, "send_for_approval")
    denied = _make_client(_user(["INVOICE_APPROVE"]))
    assert denied.post("/1/send-for-approval").status_code == 403

    allowed = _make_client(_user(["INVOICE_SEND_FOR_APPROVAL"]))
    assert allowed.post("/1/send-for-approval").status_code == 200


def test_approve_requires_its_own_permission(monkeypatch):
    _stub_service(monkeypatch, "approve")
    denied = _make_client(_user(["INVOICE_REJECT"]))
    assert denied.post("/1/approve", json={"comments": "ok"}).status_code == 403

    allowed = _make_client(_user(["INVOICE_APPROVE"]))
    assert allowed.post("/1/approve", json={"comments": "ok"}).status_code == 200


def test_reject_requires_its_own_permission(monkeypatch):
    _stub_service(monkeypatch, "reject")
    denied = _make_client(_user(["INVOICE_APPROVE"]))
    assert denied.post("/1/reject", json={"comments": "no"}).status_code == 403

    allowed = _make_client(_user(["INVOICE_REJECT"]))
    assert allowed.post("/1/reject", json={"comments": "no"}).status_code == 200


def test_reject_without_comment_is_a_validation_error(monkeypatch):
    _stub_service(monkeypatch, "reject")
    client = _make_client(_user(["INVOICE_REJECT"]))
    response = client.post("/1/reject", json={})
    assert response.status_code == 422  # comments is a required field on the request body


def test_view_endpoints_accept_any_of_view_approve_or_reject(monkeypatch):
    _stub_service(monkeypatch, "get_approval_detail")
    for perm in ("INVOICE_APPROVAL_VIEW", "INVOICE_APPROVE", "INVOICE_REJECT"):
        client = _make_client(_user([perm]))
        assert client.get("/1/approval").status_code == 200

    denied = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    assert denied.get("/1/approval").status_code == 403


def test_get_all_statuses_has_no_permission_gate(monkeypatch):
    """Pre-existing, unchanged behavior - not part of this feature's scope."""
    from Backend.Business_Layer.services import invoice_approval_service

    monkeypatch.setattr(invoice_approval_service.InvoiceApprovalService, "get_all_statuses", lambda self: [])
    client = _make_client(_user([]))
    assert client.get("/get-all-statuses").status_code == 200


# ---------------------------------------------------------------------------
# Service-level ValueError -> HTTP status mapping
# ---------------------------------------------------------------------------

def test_not_found_message_maps_to_404(monkeypatch):
    from Backend.Business_Layer.services import invoice_approval_service

    def _raise_not_found(self, *args, **kwargs):
        raise ValueError("Invoice 999 not found")

    monkeypatch.setattr(invoice_approval_service.InvoiceApprovalService, "approve", _raise_not_found)
    client = _make_client(_user(["INVOICE_APPROVE"]))
    response = client.post("/999/approve", json={})
    assert response.status_code == 404


def test_business_rule_violation_maps_to_422(monkeypatch):
    from Backend.Business_Layer.services import invoice_approval_service

    def _raise_business_error(self, *args, **kwargs):
        raise ValueError("You are not an assigned approver for the current approval step")

    monkeypatch.setattr(invoice_approval_service.InvoiceApprovalService, "approve", _raise_business_error)
    client = _make_client(_user(["INVOICE_APPROVE"]))
    response = client.post("/1/approve", json={})
    assert response.status_code == 422
