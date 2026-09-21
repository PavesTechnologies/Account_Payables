# Backend/tests/test_nda.py
"""Tests for the NDA module (Stage 2).

Fake-DAO style, no DB and no network. Two things are stubbed for a specific
reason:

* ``s3_utils`` is replaced in ``sys.modules`` because NdaService imports it
  lazily inside its methods (the real module imports boto3 and reads AWS_* at
  module scope, so it cannot be imported in a test environment).
* ``build_nda_pdf`` is monkeypatched because PyMuPDF is a heavy native
  dependency that is not installed everywhere. ``render_template_body`` and
  ``build_nda_object_key`` are the REAL implementations - placeholder
  substitution and key format are what these tests are actually asserting.
"""
from __future__ import annotations

import datetime
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest

import Backend.Business_Layer.services.nda_service as nda_module
from Backend.Business_Layer.services.nda_service import (
    LOOKUP_EXPIRED,
    LOOKUP_INVALID,
    LOOKUP_NOT_FOUND,
    LOOKUP_VALID,
    NdaService,
)
from Backend.Business_Layer.utils.nda_document import (
    SUPPORTED_PLACEHOLDERS,
    build_nda_context,
    build_nda_object_key,
    render_template_body,
)

NDA_STATUS_CODES = [
    "NOT_REQUIRED", "PENDING", "SENT", "SIGNED", "COMPLETED", "REJECTED", "EXPIRED",
]

TODAY = datetime.date.today()


class FakeDB:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


def _status(code, status_id):
    return SimpleNamespace(status_code=code, status_id=status_id, module_name="NDA")


def _template(code="STANDARD_NDA", version="1.0", is_active=True, body=None):
    return SimpleNamespace(
        id=1, code=code, name="Standard NDA", version=version, is_active=is_active,
        body=body or (
            "NDA between {{COMPANY_NAME}} and {{VENDOR_NAME}} ({{VENDOR_CODE}}).\n"
            "PR: {{PR_NUMBER}} | Dept: {{DEPARTMENT}} | Category: {{PURCHASE_CATEGORY}}\n"
            "Requirement: {{BUSINESS_REQUIREMENT}}\nEffective: {{EFFECTIVE_DATE}}"
        ),
    )


def _vendor(vendor_id=100, email="sales@acme.example", code="ACME1234"):
    return SimpleNamespace(
        vendor_id=vendor_id, vendor_name="Acme Supplies", vendor_code=code, email=email
    )


def _pr(pr_id=1, number="PR-000123", department_id=1, purchase_category_id=10):
    return SimpleNamespace(
        id=pr_id, pr_number=number,
        department_id=department_id, purchase_category_id=purchase_category_id,
    )


def _engagement(nda_final=True, requirement="Replace end-of-life laptops"):
    return SimpleNamespace(
        nda_final_required=nda_final,
        nda_recommended=nda_final,
        business_requirement=requirement,
        department=SimpleNamespace(name="IT"),
        purchase_category=SimpleNamespace(name="IT Hardware"),
    )


class FakeNdaDAO:
    def __init__(self, vendor=None, pr=None, engagement=None, template=None, config=None):
        self._vendor = vendor
        self._pr = pr
        self._engagement = engagement
        self._template = template
        self.config: Dict[str, str] = config or {}
        self.ndas: Dict[int, object] = {}
        self.audit_logs: List[object] = []
        # Deliberately arbitrary ids - nothing may depend on a specific one.
        self.statuses = {
            code: _status(code, 800 + index * 11)
            for index, code in enumerate(NDA_STATUS_CODES)
        }
        self._next_id = 1

    def get_status_by_module_code(self, module_name, status_code):
        assert module_name == "NDA"
        return self.statuses.get(status_code)

    def get_status_by_id(self, status_id):
        for status in self.statuses.values():
            if status.status_id == status_id:
                return status
        return None

    def get_config_value(self, config_key):
        return self.config.get(config_key)

    def get_vendor_by_id(self, vendor_id):
        return self._vendor

    def get_pr_by_id(self, pr_id):
        return self._pr

    def get_engagement(self, vendor_id, department_id, purchase_category_id):
        return self._engagement

    def get_active_template_by_code(self, code):
        if self._template is not None and self._template.code == code and self._template.is_active:
            return self._template
        return None

    def get_template_by_code(self, code):
        if self._template is not None and self._template.code == code:
            return self._template
        return None

    def get_template_by_id(self, template_id):
        return self._template

    def get_default_active_template(self):
        if self._template is not None and self._template.is_active:
            return self._template
        return None

    def create_nda(self, nda):
        nda.nda_id = self._next_id
        self._next_id += 1
        self.ndas[nda.nda_id] = nda
        return nda

    def get_nda_by_id(self, nda_id):
        return self.ndas.get(nda_id)

    def get_ndas_by_vendor(self, vendor_id):
        return [n for n in self.ndas.values() if n.vendor_id == vendor_id]

    def get_ndas_in_scope(self, vendor_id, department_id, purchase_category_id):
        return [
            n for n in self.ndas.values()
            if n.vendor_id == vendor_id
            and (n.department_id is None or n.department_id == department_id)
            and (n.purchase_category_id is None or n.purchase_category_id == purchase_category_id)
        ]

    def create_audit_log(self, audit_log):
        self.audit_logs.append(audit_log)
        return audit_log


@pytest.fixture
def fake_s3(monkeypatch):
    """Replaces the lazily-imported s3_utils module."""
    module = types.ModuleType("Backend.API_Layer.utils.s3_utils")
    calls = SimpleNamespace(uploads=[], presigned=[], fetched=[])

    def upload_to_s3(filename, content, content_type=None, prefix="invoices/", key=None):
        calls.uploads.append(
            {"filename": filename, "content": content, "content_type": content_type,
             "prefix": prefix, "key": key}
        )
        return {"status": "success", "filename": filename,
                "filepath": key or f"{prefix}2026/09/abc_{filename}"}

    def generate_presigned_url(key, expires_in=300):
        calls.presigned.append((key, expires_in))
        return f"https://private-bucket.s3.amazonaws.com/{key}?X-Amz-Expires={expires_in}"

    def get_object_bytes(key):
        calls.fetched.append(key)
        return b"%PDF-1.4 stored-bytes"

    module.upload_to_s3 = upload_to_s3
    module.generate_presigned_url = generate_presigned_url
    module.get_object_bytes = get_object_bytes
    module.DEFAULT_PRESIGNED_URL_TTL_SECONDS = 300

    monkeypatch.setitem(sys.modules, "Backend.API_Layer.utils.s3_utils", module)
    return calls


@pytest.fixture
def fake_pdf(monkeypatch):
    captured = SimpleNamespace(title=None, body=None)

    def _build(title, body):
        captured.title = title
        captured.body = body
        return b"%PDF-1.4 generated"

    monkeypatch.setattr(nda_module, "build_nda_pdf", _build)
    return captured


@pytest.fixture
def emails(monkeypatch):
    sent = []

    def _send(to_address, subject, html_body=None, text_body=None, attachments=None, smtp_config=None):
        sent.append(SimpleNamespace(
            to_address=to_address, subject=subject, html_body=html_body,
            text_body=text_body, attachments=attachments or [],
        ))
        return SimpleNamespace(
            success=True, sent_at=datetime.datetime.now(datetime.timezone.utc), error=None
        )

    monkeypatch.setattr(nda_module, "send_email", _send)
    return sent


@pytest.fixture
def env(monkeypatch):
    dao = FakeNdaDAO(
        vendor=_vendor(), pr=_pr(), engagement=_engagement(), template=_template()
    )
    service = NdaService(db=FakeDB())
    service.nda_dao = dao
    monkeypatch.setattr(nda_module.NdaService, "_company_name", staticmethod(lambda: "Paves Technologies"))
    return SimpleNamespace(service=service, dao=dao)


def _actions(dao):
    return [a.action for a in dao.audit_logs]


# ---------------------------------------------------------------------------
# Template rendering (real implementation)
# ---------------------------------------------------------------------------


def test_all_supported_placeholders_are_substituted():
    context = build_nda_context(
        vendor_name="Acme", vendor_code="ACME1", pr_number="PR-1",
        department_name="IT", purchase_category_name="Hardware",
        business_requirement="Laptops", company_name="Paves",
        effective_date=datetime.date(2026, 9, 18),
    )
    body = " ".join("{{%s}}" % name for name in SUPPORTED_PLACEHOLDERS)

    rendered = render_template_body(body, context)

    assert "{{" not in rendered
    assert "Acme" in rendered and "PR-1" in rendered and "2026-09-18" in rendered


def test_unknown_placeholder_is_left_visible_rather_than_blanked():
    rendered = render_template_body("{{VENDOR_NAME}} {{NOT_A_FIELD}}", {"VENDOR_NAME": "Acme"})

    assert rendered == "Acme {{NOT_A_FIELD}}"


def test_empty_template_body_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        render_template_body("", {})


def test_object_key_matches_the_required_format():
    key = build_nda_object_key("PR-000123", "ACME1234", "1.0", year=2026)

    assert key == "ap/nda/generated/2026/PR-000123/ACME1234/NDA-PR-000123-ACME1234-v1.0.pdf"


def test_signed_documents_use_a_separate_prefix():
    key = build_nda_object_key("PR-1", "V1", "2.0", signed=True, year=2026)

    assert key.startswith("ap/nda/signed/")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def test_generate_populates_vendor_pr_department_category_and_requirement(env, fake_s3, fake_pdf):
    env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    body = fake_pdf.body
    assert "Acme Supplies" in body
    assert "ACME1234" in body
    assert "PR-000123" in body
    assert "IT" in body
    assert "IT Hardware" in body
    assert "Replace end-of-life laptops" in body
    assert "Paves Technologies" in body
    assert "{{" not in body


def test_generate_uploads_pdf_to_private_s3_with_the_expected_key(env, fake_s3, fake_pdf):
    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    upload = fake_s3.uploads[0]
    assert upload["content"] == b"%PDF-1.4 generated"
    assert upload["content_type"] == "application/pdf"
    assert upload["key"].startswith("ap/nda/generated/")
    assert upload["key"].endswith("NDA-PR-000123-ACME1234-v1.0.pdf")
    assert result.nda.document_key == upload["key"]


def test_generate_persists_template_version_and_metadata(env, fake_s3, fake_pdf):
    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    nda = result.nda
    assert nda.template_version == "1.0"
    assert nda.template_id == 1
    assert nda.nda_required is True
    assert nda.status.status_code == "PENDING"
    assert nda.recipient_email == "sales@acme.example"
    assert nda.pr_id == 1
    assert nda.department_id == 1
    assert nda.purchase_category_id == 10


def test_generate_audits_requirement_generation_and_upload(env, fake_s3, fake_pdf):
    env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    actions = _actions(env.dao)
    assert "NDA_REQUIREMENT_DECIDED" in actions
    assert "NDA_GENERATED" in actions
    assert "NDA_UPLOADED" in actions


def test_not_required_engagement_produces_a_not_required_nda_without_pdf(env, fake_s3, fake_pdf):
    env.dao._engagement = _engagement(nda_final=False)

    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.required is False
    assert result.nda.status.status_code == "NOT_REQUIRED"
    assert result.nda.document_key is None
    assert fake_s3.uploads == []


def test_missing_vendor_is_rejected(env, fake_s3, fake_pdf):
    env.dao._vendor = None

    with pytest.raises(ValueError, match="Vendor not found"):
        env.service.generate_nda(vendor_id=999, user_id="officer-1", pr_id=1)


def test_inactive_template_is_rejected(env, fake_s3, fake_pdf):
    env.dao._template = _template(is_active=False)

    with pytest.raises(ValueError, match="not active"):
        env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)


def test_no_template_configured_is_rejected(env, fake_s3, fake_pdf):
    env.dao._template = None

    with pytest.raises(ValueError, match="No active NDA template"):
        env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)


# ---------------------------------------------------------------------------
# Existing NDA check / reuse
# ---------------------------------------------------------------------------


def _completed_nda(env, valid_until=None, department_id=1, purchase_category_id=10):
    nda = SimpleNamespace(
        nda_id=env.dao._next_id, vendor_id=100, pr_id=1,
        department_id=department_id, purchase_category_id=purchase_category_id,
        nda_required=True, nda_status_id=env.dao.statuses["COMPLETED"].status_id,
        status=env.dao.statuses["COMPLETED"], template_id=1, template_version="1.0",
        document_key="ap/nda/generated/2026/PR-000123/ACME1234/NDA-x-v1.0.pdf",
        signed_document_key=None, recipient_email="sales@acme.example",
        valid_from=TODAY - datetime.timedelta(days=10),
        valid_until=valid_until if valid_until is not None else TODAY + datetime.timedelta(days=365),
        sent_at=None, signed_at=None, completed_at=None, updated_by=None,
    )
    env.dao.ndas[nda.nda_id] = nda
    env.dao._next_id += 1
    return nda


def test_valid_completed_nda_is_reused_and_no_new_pdf_is_made(env, fake_s3, fake_pdf):
    existing = _completed_nda(env)

    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.reused is True
    assert result.nda.nda_id == existing.nda_id
    assert fake_s3.uploads == []
    assert "NDA_REUSED" in _actions(env.dao)


def test_no_existing_nda_generates_a_new_one(env, fake_s3, fake_pdf):
    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.reused is False
    assert len(fake_s3.uploads) == 1


def test_expired_nda_is_not_reused(env, fake_s3, fake_pdf):
    _completed_nda(env, valid_until=TODAY - datetime.timedelta(days=1))

    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.reused is False
    assert len(fake_s3.uploads) == 1


def test_incomplete_nda_is_not_reused(env, fake_s3, fake_pdf):
    nda = _completed_nda(env)
    nda.status = env.dao.statuses["SENT"]

    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.reused is False


def test_nda_scoped_to_another_department_is_not_reused(env, fake_s3, fake_pdf):
    _completed_nda(env, department_id=99, purchase_category_id=99)

    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.reused is False


def test_company_wide_nda_with_null_scope_is_reusable(env, fake_s3, fake_pdf):
    _completed_nda(env, department_id=None, purchase_category_id=None)

    result = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    assert result.reused is True


def test_check_existing_reports_each_outcome(env):
    assert env.service.check_existing_nda(100, 1, 10).outcome == LOOKUP_NOT_FOUND

    nda = _completed_nda(env)
    assert env.service.check_existing_nda(100, 1, 10).outcome == LOOKUP_VALID

    nda.valid_until = TODAY - datetime.timedelta(days=1)
    assert env.service.check_existing_nda(100, 1, 10).outcome == LOOKUP_EXPIRED

    nda.valid_until = TODAY + datetime.timedelta(days=1)
    nda.status = env.dao.statuses["REJECTED"]
    assert env.service.check_existing_nda(100, 1, 10).outcome == LOOKUP_INVALID


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def test_successful_send_marks_nda_sent_and_attaches_the_stored_pdf(env, fake_s3, fake_pdf, emails):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    nda, result = env.service.send_nda(generated.nda.nda_id, "officer-1")

    assert result.success is True
    assert nda.status.status_code == "SENT"
    assert nda.sent_at is not None

    message = emails[0]
    assert message.to_address == "sales@acme.example"
    assert len(message.attachments) == 1
    assert message.attachments[0].content_type == "application/pdf"
    # The exact archived object is attached, not a re-generated one.
    assert message.attachments[0].content == b"%PDF-1.4 stored-bytes"
    assert fake_s3.fetched == [nda.document_key]

    actions = _actions(env.dao)
    assert "NDA_SEND_ATTEMPTED" in actions and "NDA_SENT" in actions


def test_failed_send_does_not_mark_nda_sent(env, fake_s3, fake_pdf, monkeypatch):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    monkeypatch.setattr(
        nda_module, "send_email",
        lambda **kwargs: SimpleNamespace(
            success=False, sent_at=datetime.datetime.now(datetime.timezone.utc),
            error="SMTP unavailable",
        ),
    )

    nda, result = env.service.send_nda(generated.nda.nda_id, "officer-1")

    assert result.success is False
    assert nda.status.status_code == "PENDING"
    assert nda.sent_at is None

    actions = _actions(env.dao)
    assert "NDA_SEND_FAILED" in actions
    assert "NDA_SENT" not in actions


def test_send_requires_a_generated_document(env, fake_s3, fake_pdf, emails):
    env.dao._engagement = _engagement(nda_final=False)
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="not required"):
        env.service.send_nda(generated.nda.nda_id, "officer-1")


def test_send_requires_a_recipient_email(env, fake_s3, fake_pdf, emails):
    env.dao._vendor = _vendor(email=None)
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="no email address"):
        env.service.send_nda(generated.nda.nda_id, "officer-1")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_full_lifecycle_pending_sent_signed_completed(env, fake_s3, fake_pdf, emails):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)
    nda_id = generated.nda.nda_id

    env.service.send_nda(nda_id, "officer-1")
    signed = env.service.update_status(nda_id, "SIGNED", "officer-1")
    assert signed.status.status_code == "SIGNED"
    assert signed.signed_at is not None

    completed = env.service.update_status(
        nda_id, "COMPLETED", "officer-1", signed_document_key="ap/nda/signed/2026/x.pdf"
    )
    assert completed.status.status_code == "COMPLETED"
    assert completed.completed_at is not None
    assert completed.signed_document_key == "ap/nda/signed/2026/x.pdf"
    # Validity runs from completion, using the configured window.
    assert completed.valid_from == TODAY
    assert completed.valid_until > TODAY


def test_completion_validity_window_uses_configuration(env, fake_s3, fake_pdf, emails):
    env.dao.config["NDA_VALIDITY_MONTHS"] = "12"
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)
    env.service.send_nda(generated.nda.nda_id, "officer-1")

    completed = env.service.update_status(generated.nda.nda_id, "COMPLETED", "officer-1")

    assert completed.valid_until.year == TODAY.year + 1


def test_invalid_transition_is_rejected(env, fake_s3, fake_pdf):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="cannot move from PENDING to SIGNED"):
        env.service.update_status(generated.nda.nda_id, "SIGNED", "officer-1")


def test_unknown_status_is_rejected(env, fake_s3, fake_pdf):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="cannot move from"):
        env.service.update_status(generated.nda.nda_id, "NOT_A_STATUS", "officer-1")


def test_missing_status_master_row_raises_rather_than_guessing(env, fake_s3, fake_pdf):
    del env.dao.statuses["PENDING"]

    with pytest.raises(ValueError, match="is not configured for module 'NDA'"):
        env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)


def test_rejected_nda_is_terminal(env, fake_s3, fake_pdf, emails):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)
    env.service.update_status(generated.nda.nda_id, "REJECTED", "officer-1")

    with pytest.raises(ValueError, match="cannot move from REJECTED"):
        env.service.update_status(generated.nda.nda_id, "COMPLETED", "officer-1")


# ---------------------------------------------------------------------------
# Manual signed-document upload
# ---------------------------------------------------------------------------


SIGNED_PDF = b"%PDF-1.4 signed-by-vendor"


def _sent_nda(env, emails):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)
    env.service.send_nda(generated.nda.nda_id, "officer-1")
    return generated.nda.nda_id


def test_upload_signed_document_stores_key_and_sets_signed(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)

    nda = env.service.upload_signed_document(
        nda_id, "signed-nda.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )

    assert nda.status.status_code == "SIGNED"
    assert nda.signed_at is not None
    assert nda.signed_document_key.startswith("ap/nda/signed/")
    assert nda.signed_document_key.endswith("NDA-PR-000123-ACME1234-v1.0.pdf")

    upload = fake_s3.uploads[-1]
    assert upload["content"] == SIGNED_PDF
    assert upload["key"] == nda.signed_document_key
    # Only the key is persisted - never the bytes, never a URL.
    assert "http" not in (nda.signed_document_key or "")


def test_upload_signed_document_keeps_generated_document_key(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)
    generated_key = env.dao.ndas[nda_id].document_key

    nda = env.service.upload_signed_document(
        nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )

    assert nda.document_key == generated_key
    assert nda.signed_document_key != generated_key


def test_upload_signed_document_is_audited(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)

    env.service.upload_signed_document(
        nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )

    actions = _actions(env.dao)
    assert "NDA_SIGNED_DOCUMENT_UPLOADED" in actions
    assert "NDA_SIGNED" in actions


def test_upload_signed_document_for_missing_nda_is_rejected(env, fake_s3, fake_pdf):
    with pytest.raises(ValueError, match="NDA not found"):
        env.service.upload_signed_document(
            999, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
        )


def test_upload_signed_document_rejects_empty_content(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)

    with pytest.raises(ValueError, match="empty"):
        env.service.upload_signed_document(
            nda_id, "signed.pdf", b"", "application/pdf", "reviewer-1"
        )


def test_upload_before_nda_is_sent_is_rejected(env, fake_s3, fake_pdf):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="has not been sent"):
        env.service.upload_signed_document(
            generated.nda.nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
        )


def test_upload_for_not_required_nda_is_rejected(env, fake_s3, fake_pdf):
    env.dao._engagement = _engagement(nda_final=False)
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="not required"):
        env.service.upload_signed_document(
            generated.nda.nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
        )


def test_upload_after_completion_is_rejected(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)
    env.service.upload_signed_document(
        nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )
    env.service.update_status(nda_id, "COMPLETED", "reviewer-1")

    with pytest.raises(ValueError, match="already completed"):
        env.service.upload_signed_document(
            nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
        )


def test_rejected_nda_accepts_a_corrected_resubmission(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)
    env.service.upload_signed_document(
        nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )
    env.service.update_status(nda_id, "REJECTED", "reviewer-1", reason="Wrong signatory")

    nda = env.service.upload_signed_document(
        nda_id, "corrected.pdf", b"%PDF-1.4 corrected", "application/pdf", "reviewer-1"
    )

    assert nda.status.status_code == "SIGNED"


def test_reupload_while_already_signed_replaces_the_document(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)
    env.service.upload_signed_document(
        nda_id, "first.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )

    nda = env.service.upload_signed_document(
        nda_id, "second.pdf", b"%PDF-1.4 second", "application/pdf", "reviewer-1"
    )

    assert nda.status.status_code == "SIGNED"
    assert fake_s3.uploads[-1]["content"] == b"%PDF-1.4 second"


def test_s3_failure_leaves_nda_unsigned(env, fake_s3, fake_pdf, emails, monkeypatch):
    nda_id = _sent_nda(env, emails)

    import sys as _sys
    module = _sys.modules["Backend.API_Layer.utils.s3_utils"]

    def _boom(**kwargs):
        raise RuntimeError("S3 upload failed.")

    monkeypatch.setattr(module, "upload_to_s3", _boom)

    with pytest.raises(RuntimeError, match="S3 upload failed"):
        env.service.upload_signed_document(
            nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
        )

    nda = env.dao.ndas[nda_id]
    assert nda.status.status_code == "SENT"
    assert nda.signed_document_key is None
    assert "NDA_SIGNED_DOCUMENT_UPLOADED" not in _actions(env.dao)


def test_signed_upload_alone_does_not_make_the_vendor_rfq_eligible(env, fake_s3, fake_pdf, emails):
    """SIGNED means 'received, pending internal review' - COMPLETED is still
    required before RFQ eligibility opens up."""
    nda_id = _sent_nda(env, emails)

    nda = env.service.upload_signed_document(
        nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )

    lookup = env.service.check_existing_nda(100, 1, 10)
    assert nda.status.status_code == "SIGNED"
    assert lookup.outcome != LOOKUP_VALID

    env.service.update_status(nda_id, "COMPLETED", "reviewer-1")
    assert env.service.check_existing_nda(100, 1, 10).outcome == LOOKUP_VALID


# ---------------------------------------------------------------------------
# PDF-only upload validation (real validator)
# ---------------------------------------------------------------------------


def _upload(filename, content_type):
    return SimpleNamespace(filename=filename, content_type=content_type)


def test_pdf_validator_accepts_a_pdf():
    from Backend.API_Layer.utils.file_validation import validate_pdf_upload

    validate_pdf_upload(_upload("signed.pdf", "application/pdf"), SIGNED_PDF)


@pytest.mark.parametrize(
    "filename,content_type",
    [("scan.png", "image/png"), ("scan.jpg", "image/jpeg"), ("doc.docx", None)],
)
def test_pdf_validator_rejects_non_pdf(filename, content_type):
    from Backend.API_Layer.utils.file_validation import validate_pdf_upload
    from Backend.Business_Layer.utils.exceptions import UnsupportedFileType

    with pytest.raises(UnsupportedFileType):
        validate_pdf_upload(_upload(filename, content_type), SIGNED_PDF)


def test_pdf_validator_rejects_empty_and_oversized_files():
    from Backend.API_Layer.utils.file_validation import (
        MAX_UPLOAD_SIZE_BYTES,
        validate_pdf_upload,
    )
    from Backend.Business_Layer.utils.exceptions import InvalidUploadFile

    with pytest.raises(InvalidUploadFile, match="empty"):
        validate_pdf_upload(_upload("signed.pdf", "application/pdf"), b"")

    with pytest.raises(InvalidUploadFile, match="maximum allowed size"):
        validate_pdf_upload(
            _upload("signed.pdf", "application/pdf"), b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
        )


def test_existing_image_uploads_still_allowed_by_the_original_validator():
    """The shared validator must keep accepting the invoice/quotation formats."""
    from Backend.API_Layer.utils.file_validation import validate_upload_file

    for filename, content_type in [
        ("invoice.pdf", "application/pdf"),
        ("scan.png", "image/png"),
        ("scan.jpeg", "image/jpeg"),
        ("scan.tiff", "image/tiff"),
    ]:
        validate_upload_file(_upload(filename, content_type), b"bytes")


def test_signed_upload_route_is_registered_and_gated():
    from Backend.API_Layer.routes import nda_route

    paths = {(tuple(sorted(r.methods)), r.path) for r in nda_route.router.routes}
    assert (("POST",), "/{nda_id}/signed-document") in paths

    bundle = nda_route.NDA_UPLOAD_SIGNED
    assert any(p.startswith("NDA_") for p in bundle)
    assert "INVITE_VENDOR" in bundle or "SEND_RFQ" in bundle
    for invented in ("RFQ_VIEW", "RFQ_CREATE", "RFQ_CLOSE"):
        assert invented not in bundle


# ---------------------------------------------------------------------------
# Secure document access
# ---------------------------------------------------------------------------


def test_document_access_returns_a_short_lived_presigned_url(env, fake_s3, fake_pdf):
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    url, ttl = env.service.get_document_url(generated.nda.nda_id, "officer-1")

    assert url.startswith("https://")
    assert "X-Amz-Expires" in url
    assert ttl == 300
    assert fake_s3.presigned[0][0] == generated.nda.document_key
    assert "NDA_DOCUMENT_ACCESSED" in _actions(env.dao)


def test_signed_document_is_retrievable_via_presigned_url(env, fake_s3, fake_pdf, emails):
    nda_id = _sent_nda(env, emails)
    nda = env.service.upload_signed_document(
        nda_id, "signed.pdf", SIGNED_PDF, "application/pdf", "reviewer-1"
    )

    url, ttl = env.service.get_document_url(nda_id, "reviewer-1", signed=True)

    assert fake_s3.presigned[-1][0] == nda.signed_document_key
    assert url.startswith("https://")
    assert ttl == 300


def test_document_access_without_a_document_is_rejected(env, fake_s3, fake_pdf):
    env.dao._engagement = _engagement(nda_final=False)
    generated = env.service.generate_nda(vendor_id=100, user_id="officer-1", pr_id=1)

    with pytest.raises(ValueError, match="document not found"):
        env.service.get_document_url(generated.nda.nda_id, "officer-1")


# ---------------------------------------------------------------------------
# S3 utility: the NDA additions must not change existing invoice behaviour.
#
# These exercise the REAL s3_utils (only the boto3 client call is stubbed), so
# they need boto3 importable. They skip where it is absent rather than
# silently passing - see the report for which environments run them.
# ---------------------------------------------------------------------------


def _real_s3_utils(monkeypatch):
    pytest.importorskip("boto3", reason="boto3 required to import s3_utils")
    for key, value in {
        "AWS_ACCESS_KEY_ID": "test-key",
        "AWS_SECRET_ACCESS_KEY": "test-secret",
        "AWS_REGION": "ap-south-1",
        "AWS_BUCKET_NAME": "test-bucket",
    }.items():
        monkeypatch.setenv(key, value)

    from Backend.API_Layer.utils import s3_utils

    captured = {}
    monkeypatch.setattr(s3_utils.s3_client, "put_object", lambda **kw: captured.update(kw))
    return s3_utils, captured


def test_existing_invoice_upload_key_layout_is_unchanged(monkeypatch):
    s3_utils, captured = _real_s3_utils(monkeypatch)

    result = s3_utils.upload_to_s3("invoice.pdf", b"data", "application/pdf")

    assert result["filepath"].startswith("invoices/")
    assert result["filepath"].endswith("_invoice.pdf")
    assert captured["Key"] == result["filepath"]
    assert captured["ContentType"] == "application/pdf"


def test_explicit_key_is_used_verbatim_for_nda_uploads(monkeypatch):
    s3_utils, captured = _real_s3_utils(monkeypatch)
    key = "ap/nda/generated/2026/PR-1/V1/NDA-PR-1-V1-v1.0.pdf"

    result = s3_utils.upload_to_s3("NDA.pdf", b"data", "application/pdf", key=key)

    assert result["filepath"] == key
    assert captured["Key"] == key


def test_custom_prefix_replaces_only_the_leading_segment(monkeypatch):
    s3_utils, _ = _real_s3_utils(monkeypatch)

    result = s3_utils.upload_to_s3("x.pdf", b"data", prefix="ap/nda/generated/")

    assert result["filepath"].startswith("ap/nda/generated/")
    assert "invoices/" not in result["filepath"]


def test_presigned_url_ttl_is_clamped(monkeypatch):
    s3_utils, _ = _real_s3_utils(monkeypatch)
    captured = {}
    monkeypatch.setattr(
        s3_utils.s3_client, "generate_presigned_url",
        lambda op, Params, ExpiresIn: captured.update(
            {"op": op, "params": Params, "ttl": ExpiresIn}
        ) or "https://signed",
    )

    s3_utils.generate_presigned_url("some/key", expires_in=99999)

    assert captured["ttl"] == s3_utils.MAX_PRESIGNED_URL_TTL_SECONDS
    assert captured["params"]["Key"] == "some/key"


def test_presigned_url_requires_a_key(monkeypatch):
    s3_utils, _ = _real_s3_utils(monkeypatch)

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        s3_utils.generate_presigned_url("")


# ---------------------------------------------------------------------------
# Migration guards
# ---------------------------------------------------------------------------


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "Data_Access_Layer" / "migration_nda.sql"
)


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _executable_sql() -> str:
    return "\n".join(
        line for line in _migration_sql().splitlines() if not line.strip().startswith("--")
    )


def test_migration_seeds_every_nda_status_used_by_the_service():
    sql = _migration_sql()

    for code in NDA_STATUS_CODES:
        assert re.search(rf"'NDA',\s*'{code}'", sql), f"{code} not seeded"


def test_migration_status_seed_is_idempotent():
    assert "ON CONFLICT (module_name, status_code) DO NOTHING" in _migration_sql()


def test_migration_is_idempotent_for_config_and_template():
    sql = _migration_sql()

    assert "ON CONFLICT (config_key) DO NOTHING" in sql
    assert "ON CONFLICT (code) DO NOTHING" in sql


def test_migration_preserves_existing_data():
    sql = _executable_sql().upper()

    assert "DELETE FROM" not in sql
    assert "DROP TABLE" not in sql
    assert "TRUNCATE" not in sql
    assert "UPDATE AP." not in sql


def test_migration_never_writes_a_hardcoded_status_id():
    assert "status_id" not in _executable_sql()


def test_service_transitions_cover_every_seeded_status():
    assert set(nda_module.NDA_TRANSITIONS) == set(NDA_STATUS_CODES)


def test_model_references_status_master_status_id_not_id():
    from Backend.Data_Access_Layer.models.nda import VendorNda

    foreign_keys = {
        f"{fk.column.table.fullname}.{fk.column.name}"
        for fk in VendorNda.__table__.foreign_keys
    }

    assert "ap.status_master.status_id" in foreign_keys
    assert "ap.status_master.id" not in foreign_keys
    # No free-text status column - status lives only behind the FK.
    assert "nda_document_status" not in VendorNda.__table__.columns


def test_nda_routes_declare_literal_paths_before_dynamic_ones():
    from Backend.API_Layer.routes.nda_route import router

    paths = [r.path for r in router.routes]
    dynamic_index = paths.index("/{nda_id}")

    assert all(not p.startswith("/{") for p in paths[:dynamic_index])


def test_nda_permissions_fall_back_to_existing_grants():
    from Backend.API_Layer.routes import nda_route

    for bundle in (nda_route.NDA_VIEW, nda_route.NDA_GENERATE, nda_route.NDA_SEND):
        # A new NDA_* string plus an existing officer grant, so users whose
        # UMS roles predate this feature are not locked out.
        assert any(p.startswith("NDA_") for p in bundle)
        assert "INVITE_VENDOR" in bundle or "SEND_RFQ" in bundle
        for invented in ("RFQ_VIEW", "RFQ_CREATE", "RFQ_CLOSE"):
            assert invented not in bundle
