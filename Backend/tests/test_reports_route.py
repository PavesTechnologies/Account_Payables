"""Route-level tests for reports_route.py and GET /dashboard/finance: backend-enforced permissions,
error mapping and export headers. The reporting service is monkeypatched."""
import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import dashboard_route, reports_route

REPORT = {"key": "payments_made", "title": "Payments made", "generated_at": datetime.datetime(2026, 10, 9, 10, 0),
          "period": {"type": "range", "as_of": datetime.date(2026, 10, 9), "from_date": datetime.date(2026, 7, 1),
                     "to_date": datetime.date(2026, 10, 9)},
          "columns": [{"key": "invoice_number", "label": "Invoice", "type": "text"},
                      {"key": "amount", "label": "Amount", "type": "money"}],
          "rows": [{"invoice_number": "INV-1", "amount": 10, "currency_code": "INR"}],
          "totals": [{"currency_code": "INR", "rows": 1, "amount": 10}], "notes": []}


class _FakeService:
    def __init__(self, db):
        pass

    def available_reports(self, user):
        return [{"key": "payments_made", "title": "Payments made", "period": "range"}]

    def run_report(self, key, user, *args):
        if key == "secret":
            raise PermissionError("You do not have permission to run this report")
        if key == "missing":
            raise ValueError("Unknown report 'missing'")
        return dict(REPORT)

    def can_export(self, user, key):
        return "AP_MANAGEMENT_REPORTS_VIEW" not in user["permissions"] or "AP_MANAGEMENT_REPORTS_EXPORT" in user["permissions"]

    def finance_dashboard(self, user):
        return {"action_cards": [], "as_of": datetime.date(2026, 10, 9)}


def _client(permissions):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u", "permissions": permissions}
            request.state.db = SimpleNamespace()
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(reports_route.router, prefix="/reports")
    app.include_router(dashboard_route.router, prefix="/dashboard")
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(reports_route, "APReportingService", _FakeService)
    monkeypatch.setattr(dashboard_route, "APReportingService", _FakeService)


def test_json_and_errors():
    client = _client(["PAYMENT_VIEW"])
    assert client.get("/reports").json()[0]["key"] == "payments_made"
    assert client.get("/reports/payments_made").json()["rows"][0]["invoice_number"] == "INV-1"
    assert client.get("/reports/secret").status_code == 403
    assert client.get("/reports/missing").status_code == 404
    assert client.get("/reports/payments_made?format=csv").status_code == 422


@pytest.mark.parametrize("fmt, media", [
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), ("pdf", "application/pdf")])
def test_exports(fmt, media):
    response = _client(["PAYMENT_VIEW"]).get(f"/reports/payments_made?format={fmt}")
    assert response.status_code == 200
    assert response.headers["content-type"] == media
    assert f'payments_made_' in response.headers["content-disposition"] and f".{fmt}" in response.headers["content-disposition"]
    assert len(response.content) > 1000


def test_finance_dashboard_requires_payment_permission():
    assert _client(["INVOICE_VIEW"]).get("/dashboard/finance").status_code == 403
    assert _client(["PAYMENT_PROCESS"]).get("/dashboard/finance").status_code == 200


def test_management_viewer_needs_export_grant_to_download():
    viewer = _client(["AP_MANAGEMENT_REPORTS_VIEW"])
    assert viewer.get("/reports/payments_made").status_code == 200
    assert viewer.get("/reports/payments_made?format=xlsx").status_code == 403
    exporter = _client(["AP_MANAGEMENT_REPORTS_VIEW", "AP_MANAGEMENT_REPORTS_EXPORT"])
    assert exporter.get("/reports/payments_made?format=pdf").status_code == 200
