# Backend/tests/test_tds_route_authorization.py
"""Authorization tests for the TDS determination APIs
(determine/get/update/verify). Follows the project's existing route-test
convention exactly (see test_invoice_approval_authorization.py): a minimal
FastAPI app with a fake auth/db middleware, TDSDeterminationService
monkeypatched so these tests only verify the permission_based_access
dependency wiring - not business logic (that's covered by
test_tds_determination_service.py).
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import tds_route


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
    app.include_router(tds_route.router)
    return TestClient(app)


def _user(permissions):
    return {"user_id": "5100010", "permissions": permissions}


def _fake_invoice_tds():
    return SimpleNamespace(
        invoice_id=1,
        tds_applicable=True,
        payment_nature=None,
        tds_rule=None,
        taxable_base=None,
        tds_rate=None,
        tds_amount=None,
        threshold_amount=None,
        prior_period_aggregate=None,
        current_transaction_amount=None,
        aggregate_amount=None,
        pan_status=None,
        entity_type=None,
        gstin_status=None,
        gstin_checked_at=None,
        determination_status="DETERMINED",
        determination_reason="test",
        determined_at=datetime.datetime(2026, 1, 1),
        determined_by="5100007",
        verified_at=None,
        verified_by=None,
        remarks=None,
    )


def _stub_service(monkeypatch, method_name):
    from Backend.Business_Layer.services import tds_determination_service

    def _stub(self, *args, **kwargs):
        return _fake_invoice_tds()

    monkeypatch.setattr(tds_determination_service.TDSDeterminationService, method_name, _stub)


# ---------------------------------------------------------------------------
# 401 / 403
# ---------------------------------------------------------------------------

def test_no_authenticated_user_returns_401_on_determine():
    client = _make_client(None)
    response = client.post("/1/tds/determine", json={})
    assert response.status_code == 401


def test_missing_permission_returns_403_on_determine():
    client = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    response = client.post("/1/tds/determine", json={})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Each action gated on its own permission
# ---------------------------------------------------------------------------

def test_determine_requires_its_own_permission(monkeypatch):
    _stub_service(monkeypatch, "determine")
    denied = _make_client(_user(["INVOICE_TDS_VIEW"]))
    assert denied.post("/1/tds/determine", json={}).status_code == 403

    allowed = _make_client(_user(["INVOICE_TDS_DETERMINE"]))
    assert allowed.post("/1/tds/determine", json={}).status_code == 200


def test_update_requires_its_own_permission(monkeypatch):
    _stub_service(monkeypatch, "update_inputs")
    denied = _make_client(_user(["INVOICE_TDS_DETERMINE"]))
    assert denied.put("/1/tds", json={"payment_nature_code": "RENT"}).status_code == 403

    allowed = _make_client(_user(["INVOICE_TDS_EDIT"]))
    assert allowed.put("/1/tds", json={"payment_nature_code": "RENT"}).status_code == 200


def test_update_without_payment_nature_code_is_a_validation_error(monkeypatch):
    _stub_service(monkeypatch, "update_inputs")
    client = _make_client(_user(["INVOICE_TDS_EDIT"]))
    response = client.put("/1/tds", json={})
    assert response.status_code == 422  # payment_nature_code is a required field on the request body


def test_verify_requires_its_own_permission(monkeypatch):
    _stub_service(monkeypatch, "verify")
    denied = _make_client(_user(["INVOICE_TDS_EDIT"]))
    assert denied.post("/1/tds/verify", json={}).status_code == 403

    allowed = _make_client(_user(["INVOICE_TDS_VERIFY"]))
    assert allowed.post("/1/tds/verify", json={}).status_code == 200


def test_get_accepts_any_of_the_tds_permissions_or_invoice_view(monkeypatch):
    _stub_service(monkeypatch, "get")
    for perm in ("INVOICE_TDS_VIEW", "INVOICE_TDS_DETERMINE", "INVOICE_TDS_EDIT", "INVOICE_TDS_VERIFY", "INVOICE_VIEW"):
        client = _make_client(_user([perm]))
        assert client.get("/1/tds").status_code == 200

    denied = _make_client(_user(["SOME_OTHER_PERMISSION"]))
    assert denied.get("/1/tds").status_code == 403


# ---------------------------------------------------------------------------
# Service-level ValueError -> HTTP status mapping
# ---------------------------------------------------------------------------

def test_not_found_message_maps_to_404(monkeypatch):
    from Backend.Business_Layer.services import tds_determination_service

    def _raise_not_found(self, *args, **kwargs):
        raise ValueError("Invoice 999 not found")

    monkeypatch.setattr(tds_determination_service.TDSDeterminationService, "determine", _raise_not_found)
    client = _make_client(_user(["INVOICE_TDS_DETERMINE"]))
    response = client.post("/999/tds/determine", json={})
    assert response.status_code == 404


def test_business_rule_violation_maps_to_422(monkeypatch):
    from Backend.Business_Layer.services import tds_determination_service

    def _raise_business_error(self, *args, **kwargs):
        raise ValueError("TDS for invoice 1 has already been verified and can no longer be recalculated")

    monkeypatch.setattr(tds_determination_service.TDSDeterminationService, "determine", _raise_business_error)
    client = _make_client(_user(["INVOICE_TDS_DETERMINE"]))
    response = client.post("/1/tds/determine", json={})
    assert response.status_code == 422
