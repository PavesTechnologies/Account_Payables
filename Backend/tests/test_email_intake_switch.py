"""Email intake on/off switch: OFF by default, audited, permission-gated, and honoured by the runner.
Also the READ_MAIL_ACCESS gate on the /intake mailbox-check routes. No DB / mailbox."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import email_intake_route, intake_route
from Backend.Business_Layer.services import email_intake_settings_service as settings_mod
from Backend.Business_Layer.services import invoice_email_intake_service as intake
from Backend.Data_Access_Layer.models.audit import AuditLog


class _Db:
    def __init__(self):
        self.rows, self.audit, self.commits = {}, [], 0

    def add(self, obj):
        if isinstance(obj, AuditLog):
            self.audit.append(obj)
        else:
            self.rows[obj.config_key] = obj

    def commit(self):
        self.commits += 1

    def close(self):
        pass

    def rollback(self):
        pass


class _MasterDAO:
    def __init__(self, db):
        self.db = db

    def get_system_config_by_key(self, key):
        return self.db.rows.get(key)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(settings_mod, "MasterDAO", _MasterDAO)


def test_off_by_default_and_toggle_is_audited():
    db = _Db()
    service = settings_mod.EmailIntakeSettingsService(db)
    assert service.is_enabled() is False
    status = service.set_enabled(True, "u-7")
    assert status["enabled"] is True and status["updated_by"] == "u-7"
    assert db.audit[-1].action == "EMAIL_INTAKE_ENABLED" and db.audit[-1].changed_by == "u-7"
    service.set_enabled(True, "u-7")  # no change -> no extra audit row
    assert len(db.audit) == 1
    service.set_enabled(False, "u-8")
    assert service.is_enabled() is False and db.audit[-1].action == "EMAIL_INTAKE_DISABLED"


def test_last_run_fits_the_config_column():
    db = _Db()
    service = settings_mod.EmailIntakeSettingsService(db)
    service.record_run({"status": "error", "error": "x" * 400})
    value = db.rows["EMAIL_INTAKE_LAST_RUN"].config_value
    assert len(value) <= 255 and '"status":"error"' in value
    assert service.status()["last_run"]["status"] == "error"


# ======================================================================
# Runner honours the switch
# ======================================================================
@pytest.fixture
def runner(monkeypatch):
    db = _Db()
    calls = []

    async def fake_run_once(execute):
        calls.append(execute)
        return intake.RunReport(examined=3, imported=[{"subject": "Invoice"}])

    monkeypatch.setattr(intake, "SessionLocal", lambda: db)
    monkeypatch.setattr(intake, "try_lock", lambda d: True)
    monkeypatch.setattr(intake, "unlock", lambda d: None)
    monkeypatch.setattr(intake, "run_once", fake_run_once)
    return SimpleNamespace(db=db, calls=calls)


def test_execute_does_nothing_while_switched_off(runner):
    report = asyncio.run(intake.run_locked(True))
    assert report.disabled is True and runner.calls == []
    assert "EMAIL_INTAKE_LAST_RUN" not in runner.db.rows


def test_dry_run_ignores_the_switch_and_writes_nothing(runner):
    report = asyncio.run(intake.run_locked(False))
    assert report.disabled is False and runner.calls == [False]
    assert "EMAIL_INTAKE_LAST_RUN" not in runner.db.rows


def test_execute_runs_when_on_and_records_the_run(runner):
    settings_mod.EmailIntakeSettingsService(runner.db).set_enabled(True, "u-1")
    asyncio.run(intake.run_locked(True))
    assert runner.calls == [True]
    assert '"imported":1' in runner.db.rows["EMAIL_INTAKE_LAST_RUN"].config_value


def test_another_run_holding_the_lock_skips(runner, monkeypatch):
    monkeypatch.setattr(intake, "try_lock", lambda d: False)
    assert asyncio.run(intake.run_locked(True)) is None and runner.calls == []


# ======================================================================
# Routes
# ======================================================================
def _client(permissions, db):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-9", "permissions": permissions}
            request.state.db = db
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(email_intake_route.router, prefix="/email-intake")
    app.include_router(intake_route.router, prefix="/intake")
    return TestClient(app)


def test_status_and_toggle_permissions():
    db = _Db()
    viewer = _client(["INVOICE_BULK_UPLOAD"], db)
    body = viewer.get("/email-intake/status").json()
    assert body["enabled"] is False and body["can_manage"] is False
    assert viewer.put("/email-intake/status", json={"enabled": True}).status_code == 403
    assert _client(["INVOICE_VIEW"], db).get("/email-intake/status").status_code == 403

    manager = _client(["EMAIL_INTAKE_MANAGE"], db)
    res = manager.put("/email-intake/status", json={"enabled": True})
    assert res.status_code == 200 and res.json()["enabled"] is True and res.json()["can_manage"] is True
    assert db.audit[-1].changed_by == "u-9"


def test_mailbox_check_routes_need_read_mail_access(monkeypatch):
    monkeypatch.setattr(intake_route, "get_graph_token", intake_route.get_graph_token)
    client = _client(["INVOICE_BULK_UPLOAD"], _Db())
    assert client.get("/intake/graph-token").status_code == 403
    assert client.get("/intake/mails").status_code == 403
    assert client.post("/intake/send-mail", params={"to_mail": "a@b.c", "subject": "s", "content": "c"}).status_code == 403
