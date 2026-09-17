# Backend/tests/test_new_routes.py
"""Route-level tests for the new PO, GRN, Approval, and Payment routers.

Same convention as test_process_invoice_route.py: a minimal FastAPI app
with a fake auth/db middleware, and the Business_Layer service classes
monkeypatched so these tests only verify routing, request validation,
and exception-to-HTTP-status mapping — not real business logic (that's
covered by the service-level unit tests).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import (
    goods_receipt_route,
    payment_route,
    purchase_order_route,
)


def _make_middleware(permissions):
    class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "test-user", "permissions": permissions}
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    return _FakeAuthAndDBMiddleware


def _make_client(permissions):
    app = FastAPI()
    app.add_middleware(_make_middleware(permissions))
    app.include_router(purchase_order_route.router, prefix="/po")
    app.include_router(goods_receipt_route.router, prefix="/grn")
    app.include_router(payment_route.router, prefix="/payment")
    return TestClient(app)


@pytest.fixture
def client():
    """PO/GRN routes have no permission gate (pre-existing, unrelated to this feature) — an
    empty permissions list is fine for those. Payment routes now do (PAYMENT_VIEW/
    PAYMENT_PROCESS), so the payment tests below use payment_client instead."""
    return _make_client([])


@pytest.fixture
def payment_client():
    return _make_client(["PAYMENT_VIEW", "PAYMENT_PROCESS"])


# ---------------------------------------------------------------------------
# Purchase Order / Goods Receipt (read-only) - 404 mapping
# ---------------------------------------------------------------------------


def test_get_po_not_found_returns_404(client, monkeypatch):
    from Backend.Business_Layer.services import purchase_order_service

    def _raise(self, po_id):
        raise ValueError("Purchase order not found")

    monkeypatch.setattr(purchase_order_service.PurchaseOrderService, "get_purchase_order", _raise)

    response = client.get("/po/999")
    assert response.status_code == 404


def test_get_grn_not_found_returns_404(client, monkeypatch):
    from Backend.Business_Layer.services import goods_receipt_service

    def _raise(self, grn_id):
        raise ValueError("Goods receipt not found")

    monkeypatch.setattr(goods_receipt_service.GoodsReceiptService, "get_goods_receipt", _raise)

    response = client.get("/grn/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Invoice Approval is now covered by test_invoice_approval_workflow.py
# (business logic) and test_invoice_approval_authorization.py (routing/
# permission wiring) - the old single-level approve_invoice/reject_invoice/
# get_approval_history API this section used to test no longer exists,
# replaced by the policy-driven multi-level engine.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


def _payment_payload(**overrides):
    payload = {
        "vendor_id": 1,
        "scheduled_date": "2026-08-20",
        "currency_id": 1,
        "payment_method": "NEFT",
        "allocations": [{"invoice_id": 1, "allocated_amount": "100.00"}],
    }
    payload.update(overrides)
    return payload


def test_create_payment_success(payment_client, monkeypatch):
    from Backend.Business_Layer.services import payment_service

    def _create(self, request, user_id):
        assert user_id == "test-user"
        return SimpleNamespace(payment_id=42)

    monkeypatch.setattr(payment_service.PaymentService, "create_payment", _create)

    response = payment_client.post("/payment", json=_payment_payload())
    assert response.status_code == 200
    assert response.json()["payment_id"] == 42


def test_create_payment_over_allocation_returns_422(payment_client, monkeypatch):
    from Backend.Business_Layer.services import payment_service

    def _raise(self, request, user_id):
        raise ValueError("Allocated amount 1500.00 exceeds the remaining payable amount (1000.00) for invoice 1")

    monkeypatch.setattr(payment_service.PaymentService, "create_payment", _raise)

    response = payment_client.post("/payment", json=_payment_payload())
    assert response.status_code == 422


def test_create_payment_requires_at_least_one_allocation(payment_client):
    response = payment_client.post("/payment", json=_payment_payload(allocations=[]))
    assert response.status_code == 422


def test_update_payment_status_invalid_transition_returns_422(payment_client, monkeypatch):
    from Backend.Business_Layer.services import payment_service

    def _raise(self, payment_id, status_code, payment_date, reference_number, user_id):
        raise ValueError("Cannot transition payment 1 from 'CLEARED' to 'SENT'")

    monkeypatch.setattr(payment_service.PaymentService, "update_status", _raise)

    response = payment_client.patch("/payment/1/status", json={"status_code": "SENT"})
    assert response.status_code == 422


def test_get_payment_not_found_returns_404(payment_client, monkeypatch):
    from Backend.Business_Layer.services import payment_service

    def _raise(self, payment_id):
        raise ValueError("Payment 999 not found")

    monkeypatch.setattr(payment_service.PaymentService, "get_payment", _raise)

    response = payment_client.get("/payment/999")
    assert response.status_code == 404


def test_create_payment_denied_without_permission():
    response = _make_client([]).post("/payment", json=_payment_payload())
    assert response.status_code == 403


def test_get_payment_denied_without_permission():
    response = _make_client([]).get("/payment/999")
    assert response.status_code == 403
