# Backend/tests/test_tds_config_route_authorization.py
"""Authorization + error-mapping tests for /apm/tds/config/* (rules, payment
natures, deductors, import). Same convention as test_tds_route_authorization.py:
minimal app with fake auth/db middleware, services monkeypatched - these only
verify permission wiring (403/401) and HTTP status mapping, not business
logic (see test_tds_config_service_db.py)."""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import tds_config_route
from Backend.Business_Layer.services import tds_config_import_service, tds_config_service


def _client(user):
    class _FakeAuthAndDB(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if user is not None:
                request.state.user = user
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_FakeAuthAndDB)
    app.include_router(tds_config_route.router, prefix="/tds/config")
    return TestClient(app)


def _user(*permissions):
    return {"user_id": "5100031", "permissions": list(permissions)}


_NOW = datetime.datetime(2026, 9, 30)
_MASTER = SimpleNamespace(id=1, code="X", name="X", description=None, is_active=True, created_at=_NOW, updated_at=_NOW)
_RULE = {
    "id": 1, "code": "TDS_194C", "rule_name": "n", "effective_from": datetime.date(2026, 4, 1),
    "is_active": True, "status": "ACTIVE", "conditions": [], "rates": [],
}
_REPORT = {
    "valid": True, "imported": False, "total_rows": 1, "valid_rows": 1, "error_rows": 0,
    "new_rows": 1, "updated_rows": 0, "unchanged_rows": 0, "errors": [], "rows": [],
}
_RULE_BODY = {"code": "TDS_194C", "old_section": "194C", "payment_nature_code": "CONTRACTOR", "rate": "1", "effective_from": "2026-04-01"}
_MASTER_BODY = {"code": "X", "name": "X"}
_STATUS_BODY = {"is_active": False}
_FILE = {"file": ("rules.csv", b"Code\n", "text/csv")}


@pytest.fixture(autouse=True)
def _stub_services(monkeypatch):
    svc = tds_config_service.TdsConfigService
    for name in ("list_rules",):
        monkeypatch.setattr(svc, name, lambda self, *a, **k: [_RULE])
    for name in ("get_rule", "create_rule", "update_rule", "set_rule_status"):
        monkeypatch.setattr(svc, name, lambda self, *a, **k: _RULE)
    for name in ("list_payment_natures", "list_deductors"):
        monkeypatch.setattr(svc, name, lambda self, *a, **k: [_MASTER])
    for name in (
        "get_payment_nature", "create_payment_nature", "update_payment_nature", "set_payment_nature_status",
        "get_deductor", "create_deductor", "update_deductor", "set_deductor_status",
    ):
        monkeypatch.setattr(svc, name, lambda self, *a, **k: _MASTER)
    for name in ("delete_rule", "delete_payment_nature", "delete_deductor"):
        monkeypatch.setattr(svc, name, lambda self, *a, **k: None)
    imp = tds_config_import_service.TdsConfigImportService
    monkeypatch.setattr(imp, "validate", lambda self, *a, **k: dict(_REPORT))
    monkeypatch.setattr(imp, "import_rules", lambda self, *a, **k: {**_REPORT, "imported": True})


# (method, path, body, file, required-permission)
ENDPOINTS = [
    ("get", "/tds/config/metadata", None, None, "TDS_CONFIG_VIEW"),
    ("get", "/tds/config/rules", None, None, "TDS_CONFIG_VIEW"),
    ("get", "/tds/config/rules/1", None, None, "TDS_CONFIG_VIEW"),
    ("post", "/tds/config/rules", _RULE_BODY, None, "TDS_CONFIG_CREATE"),
    ("put", "/tds/config/rules/1", _RULE_BODY, None, "TDS_CONFIG_EDIT"),
    ("patch", "/tds/config/rules/1/status", _STATUS_BODY, None, "TDS_CONFIG_EDIT"),
    ("delete", "/tds/config/rules/1", None, None, "TDS_CONFIG_DELETE"),
    ("post", "/tds/config/import/validate", None, _FILE, "TDS_CONFIG_IMPORT"),
    ("post", "/tds/config/import", None, _FILE, "TDS_CONFIG_IMPORT"),
    ("get", "/tds/config/payment-natures", None, None, "TDS_CONFIG_VIEW"),
    ("get", "/tds/config/payment-natures/1", None, None, "TDS_CONFIG_VIEW"),
    ("post", "/tds/config/payment-natures", _MASTER_BODY, None, "TDS_CONFIG_CREATE"),
    ("put", "/tds/config/payment-natures/1", _MASTER_BODY, None, "TDS_CONFIG_EDIT"),
    ("patch", "/tds/config/payment-natures/1/status", _STATUS_BODY, None, "TDS_CONFIG_EDIT"),
    ("delete", "/tds/config/payment-natures/1", None, None, "TDS_CONFIG_DELETE"),
    ("get", "/tds/config/deductors", None, None, "TDS_CONFIG_VIEW"),
    ("get", "/tds/config/deductors/1", None, None, "TDS_CONFIG_VIEW"),
    ("post", "/tds/config/deductors", _MASTER_BODY, None, "TDS_CONFIG_CREATE"),
    ("put", "/tds/config/deductors/1", _MASTER_BODY, None, "TDS_CONFIG_EDIT"),
    ("patch", "/tds/config/deductors/1/status", _STATUS_BODY, None, "TDS_CONFIG_EDIT"),
    ("delete", "/tds/config/deductors/1", None, None, "TDS_CONFIG_DELETE"),
]


def _call(client, method, path, body, files):
    kwargs = {}
    if body is not None:
        kwargs["json"] = body
    if files is not None:
        kwargs["files"] = files
    return getattr(client, method)(path, **kwargs) if kwargs else getattr(client, method)(path)


@pytest.mark.parametrize("method, path, body, files, permission", ENDPOINTS)
def test_endpoint_allows_its_permission(method, path, body, files, permission):
    response = _call(_client(_user(permission)), method, path, body, files)
    assert response.status_code in (200, 201), response.text


@pytest.mark.parametrize("method, path, body, files, permission", ENDPOINTS)
def test_system_admin_without_tds_config_permission_is_forbidden(method, path, body, files, permission):
    """System Configuration (Admin) and TDS Configuration (Finance) are
    separate security boundaries."""
    admin = _user("SYSTEM_CONFIG_MANAGE", "APPROVAL_POLICY_MANAGE", "INVOICE_VIEW")
    assert _call(_client(admin), method, path, body, files).status_code == 403


@pytest.mark.parametrize("method, path, body, files, permission", ENDPOINTS)
def test_unauthenticated_is_401(method, path, body, files, permission):
    assert _call(_client(None), method, path, body, files).status_code == 401


@pytest.mark.parametrize("method, path, body, files, permission", [e for e in ENDPOINTS if e[0] != "get"])
def test_view_permission_cannot_write(method, path, body, files, permission):
    assert _call(_client(_user("TDS_CONFIG_VIEW")), method, path, body, files).status_code == 403


def test_write_permissions_imply_read():
    for permission in ("TDS_CONFIG_CREATE", "TDS_CONFIG_EDIT", "TDS_CONFIG_DELETE", "TDS_CONFIG_IMPORT"):
        assert _client(_user(permission)).get("/tds/config/rules").status_code == 200


def test_invoice_tds_users_can_read_payment_natures_only():
    ap_exec = _client(_user("INVOICE_TDS_DETERMINE", "INVOICE_TDS_EDIT"))
    assert ap_exec.get("/tds/config/payment-natures").status_code == 200
    assert ap_exec.get("/tds/config/payment-natures/1").status_code == 200
    assert ap_exec.post("/tds/config/payment-natures", json=_MASTER_BODY).status_code == 403
    assert ap_exec.get("/tds/config/rules").status_code == 403
    assert ap_exec.get("/tds/config/deductors").status_code == 403


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc, status", [
    (tds_config_service.TdsConfigNotFoundError("TDS rule 9 not found"), 404),
    (tds_config_service.TdsConfigConflictError("TDS rule with code 'X' already exists"), 409),
    (ValueError("Rate: Rate must be between 0 and 100"), 422),
])
def test_service_errors_map_to_http_status(monkeypatch, exc, status):
    def _raise(self, *a, **k):
        raise exc
    monkeypatch.setattr(tds_config_service.TdsConfigService, "create_rule", _raise)
    response = _client(_user("TDS_CONFIG_CREATE")).post("/tds/config/rules", json=_RULE_BODY)
    assert response.status_code == status
    assert response.json()["detail"] == str(exc)


def test_import_with_row_errors_is_422_with_full_report(monkeypatch):
    bad = {**_REPORT, "valid": False, "valid_rows": 0, "error_rows": 1,
           "errors": [{"row": 2, "field": "Rate", "message": "Rate must be numeric"}]}
    monkeypatch.setattr(tds_config_import_service.TdsConfigImportService, "import_rules", lambda self, *a, **k: bad)
    response = _client(_user("TDS_CONFIG_IMPORT")).post("/tds/config/import", files=_FILE)
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["field"] == "Rate"


def test_import_file_error_is_422(monkeypatch):
    def _raise(self, *a, **k):
        raise tds_config_import_service.TdsImportFileError("Unsupported file type - upload an .xlsx or .csv file")
    monkeypatch.setattr(tds_config_import_service.TdsConfigImportService, "validate", _raise)
    response = _client(_user("TDS_CONFIG_IMPORT")).post("/tds/config/import/validate", files=_FILE)
    assert response.status_code == 422
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.parametrize("permissions, expected", [
    (["TDS_CONFIG_IMPORT"], False),
    (["TDS_CONFIG_IMPORT", "TDS_CONFIG_CREATE"], True),
    (["tds_config_import", " tds_config_create "], True),  # same normalization as the dependency
])
def test_import_passes_create_permission_flag_to_service(monkeypatch, permissions, expected):
    seen = {}

    def _capture(self, filename, content, user_id, can_create_masters=False):
        seen["flag"] = can_create_masters
        return {**_REPORT, "imported": True}

    monkeypatch.setattr(tds_config_import_service.TdsConfigImportService, "import_rules", _capture)
    assert _client(_user(*permissions)).post("/tds/config/import", files=_FILE).status_code == 200
    assert seen["flag"] is expected


def test_import_permission_error_maps_to_403(monkeypatch):
    def _raise(self, *a, **k):
        raise tds_config_import_service.TdsImportPermissionError("needs TDS_CONFIG_CREATE")
    monkeypatch.setattr(tds_config_import_service.TdsConfigImportService, "import_rules", _raise)
    response = _client(_user("TDS_CONFIG_IMPORT")).post("/tds/config/import", files=_FILE)
    assert response.status_code == 403 and response.json()["detail"] == "needs TDS_CONFIG_CREATE"


def test_validate_never_needs_create_permission():
    assert _client(_user("TDS_CONFIG_IMPORT")).post("/tds/config/import/validate", files=_FILE).status_code == 200


def test_master_dto_exposes_status():
    body = _client(_user("TDS_CONFIG_VIEW")).get("/tds/config/deductors").json()
    assert body[0]["status"] == "ACTIVE"
