"""Route-level tests for payment_terms_route.py: permission gating (backend-enforced, not just
hidden buttons) and error-to-HTTP mapping. Services are monkeypatched - business rules are
covered by test_payment_term_compliance.py / test_vendor_agreement_service.py."""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import payment_terms_route as route


def _client(permissions, roles=()):
    class _FakeAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-1", "permissions": permissions, "roles": list(roles)}
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_FakeAuth)
    app.include_router(route.invoice_router, prefix="/invoice")
    app.include_router(route.terms_router, prefix="/payment-terms")
    app.include_router(route.agreement_router, prefix="/vendor-agreements")
    return TestClient(app)


_SUMMARY = {"invoice_id": 1, "evaluated": True, "validation_status": "VERIFIED_OVERRIDE", "is_overdue": False,
            "is_exception": False, "blocks_ready_for_payment": False, "msme_statutory": False}


class _FakeCompliance:
    verify_calls = []

    def __init__(self, db):
        pass

    def get_summary(self, invoice_id):
        if invoice_id == 404:
            raise ValueError("Invoice 404 not found")
        return dict(_SUMMARY, invoice_id=invoice_id)

    def verify(self, invoice_id, days, basis, remarks, user_id):
        if days == 999:
            raise ValueError("applied_term_days must be between 0 and 365")
        type(self).verify_calls.append((invoice_id, days, basis, remarks, user_id))

    def evaluate_invoice_id(self, invoice_id, user_id):
        pass

    def list_exceptions(self, *args):
        return {"items": [], "total": 0, "page": 1, "page_size": 20}


class _FakeAgreements:
    def __init__(self, db):
        pass

    def verify(self, agreement_id, remarks, user_id):
        raise PermissionError("The agreement must be verified by a different user from the one who uploaded it")

    def list_for_vendor(self, vendor_id):
        return []


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _FakeCompliance.verify_calls = []
    monkeypatch.setattr(route, "PaymentTermComplianceService", _FakeCompliance)
    monkeypatch.setattr(route, "VendorAgreementService", _FakeAgreements)


def test_view_requires_a_finance_or_invoice_permission():
    assert _client([]).get("/invoice/1/payment-terms").status_code == 403
    response = _client(["INVOICE_VIEW"]).get("/invoice/1/payment-terms")
    assert response.status_code == 200 and response.json()["validation_status"] == "VERIFIED_OVERRIDE"


def test_not_found_maps_to_404():
    assert _client(["PAYMENT_VIEW"]).get("/invoice/404/payment-terms").status_code == 404


def test_verify_requires_dedicated_permission_even_for_payment_processors():
    body = {"applied_term_days": 30, "due_basis": "INVOICE_DATE", "remarks": "Confirmed with vendor"}
    assert _client(["PAYMENT_PROCESS", "PAYMENT_VIEW"]).post("/invoice/1/payment-terms/verify", json=body).status_code == 403
    assert _client(["INVOICE_PAYMENT_TERM_VERIFY"]).post("/invoice/1/payment-terms/verify", json=body).status_code == 200
    assert _FakeCompliance.verify_calls == [(1, 30, "INVOICE_DATE", "Confirmed with vendor", "u-1")]


def test_verify_validation():
    client = _client(["INVOICE_PAYMENT_TERM_VERIFY"])
    assert client.post("/invoice/1/payment-terms/verify", json={"remarks": "no"}).status_code == 422
    assert client.post("/invoice/1/payment-terms/verify",
                       json={"applied_term_days": 400, "remarks": "Confirmed"}).status_code == 422


def test_exceptions_and_metadata():
    client = _client(["PAYMENT_VIEW"])
    assert client.get("/payment-terms/exceptions?status=MISMATCH").json()["total"] == 0
    meta = client.get("/payment-terms/metadata").json()
    assert "REVIEW_REQUIRED" in meta["exception_statuses"] and "AGREEMENT_EXPIRED" in meta["reasons"]


def test_agreement_view_by_role_or_permission():
    assert _client([]).get("/vendor-agreements/vendor/5").status_code == 403
    assert _client([], roles=["Vendor_Intake"]).get("/vendor-agreements/vendor/5").status_code == 200
    assert _client(["PAYMENT_VIEW"]).get("/vendor-agreements/vendor/5").status_code == 200


def test_agreement_verify_needs_permission_and_four_eyes_maps_to_403():
    assert _client([], roles=["Admin"]).post("/vendor-agreements/1/verify", json={}).status_code == 403
    response = _client(["VENDOR_AGREEMENT_VERIFY"]).post("/vendor-agreements/1/verify", json={})
    assert response.status_code == 403 and "different user" in response.json()["detail"]
