# Backend/tests/test_rfq_email_sending.py
"""Tests for actual RFQ email dispatch (Business_Layer/utils/email_service.py
and RFQService.send_rfq).

Two layers are tested separately:
  - email_service.send_email: pure SMTP-transport unit tests, smtplib is
    replaced with a fake so no real network/credentials are involved.
  - RFQService.send_rfq: business-flow tests (per-vendor results, partial
    failure, missing email, RFQ status), with send_email itself monkeypatched
    so these don't depend on SMTP configuration either.

A real Gmail SMTP integration test is included at the bottom, gated behind
SMTP_* env vars actually being configured - see its docstring.
"""
from __future__ import annotations

import datetime
import os
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import pytest
from sqlalchemy.orm.attributes import set_committed_value

import Backend.Business_Layer.services.rfq_service as rfq_service_module
from Backend.Business_Layer.services.rfq_service import RFQService
from Backend.Business_Layer.utils import email_service
from Backend.Business_Layer.utils.email_service import EmailSendResult, send_email


# ---------------------------------------------------------------------------
# email_service.send_email - pure transport unit tests
# ---------------------------------------------------------------------------


class _FakeSMTP:
    """Stands in for smtplib.SMTP as a context manager. `behavior` controls
    which step (if any) raises, to simulate different SMTP failure modes."""

    instances = []

    def __init__(self, host, port, timeout=30, behavior="ok"):
        self.host = host
        self.port = port
        self.behavior = behavior
        self.calls = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))
        if self.behavior == "auth_fail":
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    def send_message(self, message):
        self.calls.append(("send_message", message["To"], message["Subject"]))
        if self.behavior == "send_fail":
            raise ConnectionResetError("connection lost")


SMTP_CONFIG = {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "sender@example.com",
    "password": "app-password-123",
    "from_address": "sender@example.com",
}


@pytest.fixture(autouse=True)
def _reset_fake_smtp_instances():
    _FakeSMTP.instances = []
    yield
    _FakeSMTP.instances = []


def test_email_service_success(monkeypatch):
    monkeypatch.setattr(
        email_service.smtplib, "SMTP",
        lambda host, port, timeout=30: _FakeSMTP(host, port, timeout, behavior="ok"),
    )

    result = send_email(
        to_address="vendor@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        text_body="Hi",
        smtp_config=SMTP_CONFIG,
    )

    assert isinstance(result, EmailSendResult)
    assert result.success is True
    assert result.error is None
    assert len(_FakeSMTP.instances) == 1
    sent = _FakeSMTP.instances[0].calls
    assert ("login", "sender@example.com", "app-password-123") in sent
    assert ("send_message", "vendor@example.com", "Hello") in sent


def test_email_service_smtp_auth_failure_returns_failure_result_not_raise(monkeypatch):
    monkeypatch.setattr(
        email_service.smtplib, "SMTP",
        lambda host, port, timeout=30: _FakeSMTP(host, port, timeout, behavior="auth_fail"),
    )

    result = send_email(
        to_address="vendor@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        smtp_config=SMTP_CONFIG,
    )

    assert result.success is False
    assert result.error is not None
    assert "app-password-123" not in result.error  # never leak the credential


def test_email_service_send_failure_returns_failure_result(monkeypatch):
    monkeypatch.setattr(
        email_service.smtplib, "SMTP",
        lambda host, port, timeout=30: _FakeSMTP(host, port, timeout, behavior="send_fail"),
    )

    result = send_email(
        to_address="vendor@example.com",
        subject="Hello",
        text_body="Hi",
        smtp_config=SMTP_CONFIG,
    )

    assert result.success is False
    assert "connection lost" in result.error


def test_email_service_missing_smtp_config_is_a_clean_failure(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "RFQ_FROM_EMAIL"):
        monkeypatch.delenv(key, raising=False)

    result = send_email(to_address="vendor@example.com", subject="Hello", text_body="Hi")

    assert result.success is False
    assert "not configured" in result.error


def test_email_service_missing_recipient_is_a_clean_failure():
    result = send_email(to_address="", subject="Hello", text_body="Hi", smtp_config=SMTP_CONFIG)
    assert result.success is False
    assert "recipient" in result.error.lower()


# ---------------------------------------------------------------------------
# RFQService.send_rfq - business flow tests (email_service mocked)
# ---------------------------------------------------------------------------


class FakeStatus:
    def __init__(self, status_id, module_name, status_code):
        self.status_id = status_id
        self.module_name = module_name
        self.status_code = status_code


class StatusRegistry:
    def __init__(self):
        self._by_code: Dict[Tuple[str, str], FakeStatus] = {}
        self._by_id: Dict[int, FakeStatus] = {}
        self._next_id = 1

    def add(self, module_name, status_code):
        status = FakeStatus(self._next_id, module_name, status_code)
        self._by_code[(module_name, status_code)] = status
        self._by_id[status.status_id] = status
        self._next_id += 1
        return status

    def get_by_module_code(self, module_name, status_code):
        return self._by_code.get((module_name, status_code))

    def get_by_id(self, status_id):
        return self._by_id.get(status_id)

    def attach(self, obj):
        """Resolve `obj.status` from `obj.status_id`. Uses `set_committed_value`
        for real (transient) ORM instances, same as test_rfq_workflow.py, but
        falls back to a plain attribute set for the plain SimpleNamespace
        fixtures this file builds by hand (they have no ORM instance state
        for set_committed_value to attach to)."""
        if obj is not None and getattr(obj, "status_id", None) is not None:
            status = self.get_by_id(obj.status_id)
            if hasattr(obj, "_sa_instance_state"):
                set_committed_value(obj, "status", status)
            else:
                obj.status = status
        return obj


class FakeVendor:
    def __init__(self, vendor_id, status, email=None, vendor_name=None):
        self.vendor_id = vendor_id
        self.status = status
        self.email = email
        self.vendor_name = vendor_name or f"Vendor {vendor_id}"


class FakeDB:
    def __init__(self, registry):
        self.registry = registry

    def commit(self):
        pass

    def refresh(self, obj):
        self.registry.attach(obj)

    def rollback(self):
        pass


class FakeProcurementDAO:
    def __init__(self, registry, pr):
        self.registry = registry
        self.pr = pr
        self.lines = []
        self.audit_logs = []

    def get_purchase_requisition_by_id(self, pr_id):
        return self.registry.attach(self.pr) if self.pr.id == pr_id else None

    def get_lines_by_pr_id(self, pr_id):
        return self.lines

    def create_audit_log(self, audit_log):
        audit_log.audit_log_id = len(self.audit_logs) + 1
        self.audit_logs.append(audit_log)
        return audit_log


class FakeRFQDAO:
    def __init__(self, registry, vendors):
        self.registry = registry
        self.vendors = vendors
        self.rfqs = {}
        self.rfq_vendors = []

    def get_rfq_by_id(self, rfq_id):
        return self.registry.attach(self.rfqs.get(rfq_id))

    def get_rfq_vendors(self, rfq_id):
        return [rv for rv in self.rfq_vendors if rv.rfq_id == rfq_id]

    def get_vendor_by_id(self, vendor_id):
        return self.vendors.get(vendor_id)

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)


@pytest.fixture
def rfq_env():
    registry = StatusRegistry()
    for code in ("DRAFT", "SENT", "RESPONSE_RECEIVED", "CLOSED"):
        registry.add("RFQ", code)
    active = registry.add("VENDOR", "ACTIVE")

    pr = SimpleNamespace(id=1, pr_number="PR-000001")

    vendors = {
        1: FakeVendor(1, active, email="abc@example.com", vendor_name="ABC Technologies"),
        2: FakeVendor(2, active, email="xyz@example.com", vendor_name="XYZ Computers"),
        3: FakeVendor(3, active, email=None, vendor_name="No Email Co"),  # no email on file
    }

    rfq = SimpleNamespace(
        id=10, rfq_number="RFQ-000010", pr_id=1, status_id=registry.get_by_module_code("RFQ", "DRAFT").status_id,
        due_date=datetime.date(2026, 9, 10), created_by="buyer1",
    )
    registry.attach(rfq)

    procurement_dao = FakeProcurementDAO(registry, pr)
    rfq_dao = FakeRFQDAO(registry, vendors)
    rfq_dao.rfqs[rfq.id] = rfq

    service = RFQService(db=FakeDB(registry))
    service.procurement_dao = procurement_dao
    service.rfq_dao = rfq_dao

    return SimpleNamespace(
        service=service, registry=registry, pr=pr, rfq=rfq, vendors=vendors,
        procurement_dao=procurement_dao, rfq_dao=rfq_dao,
    )


def _invite(env, vendor_id):
    env.rfq_dao.rfq_vendors.append(
        SimpleNamespace(id=len(env.rfq_dao.rfq_vendors) + 1, rfq_id=env.rfq.id, vendor_id=vendor_id, invited_by="buyer1")
    )


def test_multiple_invited_vendors_each_receive_a_separate_email(rfq_env, monkeypatch):
    _invite(rfq_env, 1)
    _invite(rfq_env, 2)

    sent_to = []

    def fake_send_email(to_address, subject, html_body=None, text_body=None, attachments=None, smtp_config=None):
        sent_to.append(to_address)
        return EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc))

    monkeypatch.setattr(rfq_service_module, "send_email", fake_send_email)

    rfq, results = rfq_env.service.send_rfq(rfq_env.rfq.id, user_id="buyer1")

    # one email per vendor, never combined/CC'd into a single call
    assert sent_to == ["abc@example.com", "xyz@example.com"]
    assert len(results) == 2
    assert all(r.success for r in results)
    assert rfq.status.status_code == "SENT"


def test_missing_vendor_email_is_recorded_as_a_failure_not_a_crash(rfq_env, monkeypatch):
    _invite(rfq_env, 1)
    _invite(rfq_env, 3)  # vendor 3 has no email on file

    monkeypatch.setattr(
        rfq_service_module, "send_email",
        lambda **kwargs: EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc)),
    )

    rfq, results = rfq_env.service.send_rfq(rfq_env.rfq.id, user_id="buyer1")

    by_vendor = {r.vendor_id: r for r in results}
    assert by_vendor[1].success is True
    assert by_vendor[3].success is False
    assert "no email" in by_vendor[3].error.lower()
    # at least one vendor was reachable, so the RFQ still moves to SENT
    assert rfq.status.status_code == "SENT"


def test_partial_vendor_send_failure_is_handled_correctly(rfq_env, monkeypatch):
    _invite(rfq_env, 1)
    _invite(rfq_env, 2)

    def fake_send_email(to_address, **kwargs):
        if to_address == "xyz@example.com":
            return EmailSendResult(
                success=False, sent_at=datetime.datetime.now(datetime.timezone.utc), error="SMTP timeout"
            )
        return EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc))

    monkeypatch.setattr(rfq_service_module, "send_email", fake_send_email)

    rfq, results = rfq_env.service.send_rfq(rfq_env.rfq.id, user_id="buyer1")

    by_vendor = {r.vendor_id: r for r in results}
    assert by_vendor[1].success is True  # vendor A's success is unaffected by vendor B's failure
    assert by_vendor[2].success is False
    assert by_vendor[2].error == "SMTP timeout"
    assert rfq.status.status_code == "SENT"

    # both outcomes were recorded to the audit trail
    actions = [log.action for log in rfq_env.procurement_dao.audit_logs if log.record_id == rfq_env.rfq.id]
    assert actions.count("EMAIL_SENT") == 1
    assert actions.count("EMAIL_FAILED") == 1


def test_rfq_stays_draft_when_every_vendor_email_fails(rfq_env, monkeypatch):
    _invite(rfq_env, 1)
    _invite(rfq_env, 2)

    monkeypatch.setattr(
        rfq_service_module, "send_email",
        lambda **kwargs: EmailSendResult(
            success=False, sent_at=datetime.datetime.now(datetime.timezone.utc), error="SMTP down"
        ),
    )

    with pytest.raises(ValueError, match="every invited vendor"):
        rfq_env.service.send_rfq(rfq_env.rfq.id, user_id="buyer1")

    # status must NOT have been advanced to SENT - the send was never
    # actually handled for anyone
    assert rfq_env.rfq.status.status_code == "DRAFT"


def test_send_rfq_still_requires_at_least_one_invited_vendor(rfq_env, monkeypatch):
    monkeypatch.setattr(
        rfq_service_module, "send_email",
        lambda **kwargs: EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc)),
    )

    with pytest.raises(ValueError, match="at least one invited vendor"):
        rfq_env.service.send_rfq(rfq_env.rfq.id, user_id="buyer1")


# ---------------------------------------------------------------------------
# Real Gmail SMTP integration test (opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not all(os.getenv(k) for k in ("SMTP_USERNAME", "SMTP_PASSWORD", "RFQ_FROM_EMAIL")),
    reason="Requires real SMTP_USERNAME/SMTP_PASSWORD/RFQ_FROM_EMAIL (a Gmail App "
           "Password) configured in the environment - skipped by default so the "
           "regular test suite never depends on network access or real credentials.",
)
def test_live_gmail_smtp_send_is_received():
    """Sends one real email via the configured Gmail account to itself.

    Not run in CI/by default. To run for real: put SMTP_USERNAME,
    SMTP_PASSWORD (a Gmail App Password, not the account password) and
    RFQ_FROM_EMAIL in Backend/.env, then run:
        pytest Backend/tests/test_rfq_email_sending.py -k live_gmail -q
    and check the SMTP_USERNAME mailbox for the message.
    """
    result = send_email(
        to_address=os.environ["SMTP_USERNAME"],
        subject="RFQ email service - live SMTP test",
        html_body="<p>This is a live integration test of the RFQ email service.</p>",
        text_body="This is a live integration test of the RFQ email service.",
    )
    assert result.success, result.error
