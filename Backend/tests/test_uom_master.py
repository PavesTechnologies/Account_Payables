# Backend/tests/test_uom_master.py
"""Tests for the UOM master (Data_Access_Layer/models/master.py:UnitOfMeasure)
and its GET /apm/master/uoms endpoint.

Follows the project's existing route-test convention (see
test_procurement_authorization.py): a minimal FastAPI app with a fake
db middleware, MasterService monkeypatched at the route level.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import master_route
from Backend.Business_Layer.services.master_service import MasterService


class FakeUOM:
    def __init__(self, id, code, name, category, allows_decimal, is_active=True):
        self.id = id
        self.code = code
        self.name = name
        self.category = category
        self.allows_decimal = allows_decimal
        self.is_active = is_active


class FakeMasterDAO:
    def __init__(self, uoms):
        self._uoms = uoms

    def get_all_uoms(self, active_only=True):
        if active_only:
            return [u for u in self._uoms if u.is_active]
        return list(self._uoms)


def test_master_service_get_all_uoms_defaults_to_active_only():
    uoms = [
        FakeUOM(1, "EA", "Each", "COUNT", False, is_active=True),
        FakeUOM(2, "OLD", "Deprecated Unit", "COUNT", False, is_active=False),
    ]
    service = MasterService(db=None)
    service.master_dao = FakeMasterDAO(uoms)

    active = service.get_all_uoms()
    assert [u.code for u in active] == ["EA"]

    everything = service.get_all_uoms(active_only=False)
    assert {u.code for u in everything} == {"EA", "OLD"}


def _make_client():
    class _FakeDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_FakeDBMiddleware)
    app.include_router(master_route.router)
    return TestClient(app)


def test_get_uoms_route_returns_active_uoms(monkeypatch):
    uoms = [
        FakeUOM(1, "EA", "Each", "COUNT", False),
        FakeUOM(9, "KG", "Kilogram", "WEIGHT", True),
    ]

    def _stub(self, active_only=True):
        return uoms

    monkeypatch.setattr(MasterService, "get_all_uoms", _stub)

    client = _make_client()
    response = client.get("/uoms")
    assert response.status_code == 200
    body = response.json()
    assert {row["code"] for row in body} == {"EA", "KG"}
    assert all("allows_decimal" in row and "is_active" in row for row in body)
