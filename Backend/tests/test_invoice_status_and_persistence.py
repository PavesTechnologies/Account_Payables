# Backend/tests/test_invoice_status_and_persistence.py
"""Unit tests for status resolution, line persistence, and the
persist_processed_invoice / apply_ocr_review orchestration.

DAOs are faked (not mocked against a real DB) since this project has no
DB test fixtures today — these tests exercise business logic/control
flow, not SQL. `db` is a bare object; DAOs never actually need to run
real SQL because every DAO used here is replaced with an in-memory fake.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import List, Optional

import pytest

import Backend.Business_Layer.services.invoice_process_service as svc
from Backend.API_Layer.interface.invoice_process_interface import (
    ConfidenceResult,
    DocumentResult,
    ExtractedInvoice,
    ExtractedInvoiceLine,
    FinalResponse,
    InvoiceLineReviewRequest,
    InvoiceOCRReviewRequest,
    ValidationResult,
    VendorMatch,
)
from Backend.Business_Layer.utils import invoice_status, line_persistence
from Backend.Business_Layer.utils.exceptions import DuplicateInvoiceError, FieldExtractionError
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument


# ---------------------------------------------------------------------------
# invoice_status
# ---------------------------------------------------------------------------


def _extracted(**overrides) -> ExtractedInvoice:
    base = dict(
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        subtotal=Decimal("1000.00"),
        total=Decimal("1180.00"),
        currency="INR",
    )
    base.update(overrides)
    return ExtractedInvoice(**base)


def test_is_extraction_unusable_flags_missing_invoice_number():
    assert invoice_status.is_extraction_unusable(_extracted(invoice_number=None)) is not None


def test_is_extraction_unusable_flags_missing_invoice_date():
    assert invoice_status.is_extraction_unusable(_extracted(invoice_date=None)) is not None


def test_is_extraction_unusable_flags_no_amount_at_all():
    assert invoice_status.is_extraction_unusable(_extracted(subtotal=None, total=None)) is not None


def test_is_extraction_usable_when_header_fields_present():
    assert invoice_status.is_extraction_unusable(_extracted()) is None


def test_resolve_processing_status_code():
    assert invoice_status.resolve_processing_status_code(True) == invoice_status.STATUS_CODE_OCR_FAILED
    assert invoice_status.resolve_processing_status_code(False) == invoice_status.STATUS_CODE_OCR_REVIEW_PENDING


# ---------------------------------------------------------------------------
# line_persistence
# ---------------------------------------------------------------------------


def test_build_invoice_line_models_derives_unit_price_from_amount_and_quantity():
    lines = [
        ExtractedInvoiceLine(line_number=1, description="Laptop", quantity=Decimal("2"), line_amount=Decimal("1000.00"))
    ]
    models, skipped = line_persistence.build_invoice_line_models(lines)
    assert skipped == 0
    assert len(models) == 1
    assert models[0].unit_price == Decimal("500.0000")


def test_build_invoice_line_models_derives_amount_from_price_and_quantity():
    lines = [
        ExtractedInvoiceLine(line_number=1, description="Laptop", quantity=Decimal("2"), unit_price=Decimal("500.00"))
    ]
    models, skipped = line_persistence.build_invoice_line_models(lines)
    assert skipped == 0
    assert models[0].line_amount == Decimal("1000.00")


def test_build_invoice_line_models_skips_line_missing_description():
    lines = [ExtractedInvoiceLine(line_number=1, description=None, line_amount=Decimal("100.00"))]
    models, skipped = line_persistence.build_invoice_line_models(lines)
    assert models == []
    assert skipped == 1


def test_build_invoice_line_models_skips_line_missing_both_amount_and_price():
    lines = [ExtractedInvoiceLine(line_number=1, description="Freight", quantity=Decimal("1"))]
    models, skipped = line_persistence.build_invoice_line_models(lines)
    assert models == []
    assert skipped == 1


def test_check_line_total_mismatch_within_tolerance_is_none():
    lines = [ExtractedInvoiceLine(line_number=1, description="A", line_amount=Decimal("999.50"))]
    assert line_persistence.check_line_total_mismatch(lines, _extracted(subtotal=Decimal("1000.00"))) is None


def test_check_line_total_mismatch_beyond_tolerance_returns_description():
    lines = [ExtractedInvoiceLine(line_number=1, description="A", line_amount=Decimal("500.00"))]
    reason = line_persistence.check_line_total_mismatch(lines, _extracted(subtotal=Decimal("1000.00")))
    assert reason is not None
    assert "500" in reason or "1000" in reason


# ---------------------------------------------------------------------------
# persist_processed_invoice / apply_ocr_review — fake DAOs, no real DB
# ---------------------------------------------------------------------------


class _FakeDB:
    def __init__(self):
        self.committed = 0
        self.rolled_back = 0

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def refresh(self, obj):
        pass


class _FakeInvoiceDAO:
    instances: List["_FakeInvoiceDAO"] = []

    def __init__(self, db):
        self.db = db
        self.created_invoice = None
        self.created_lines: List = []
        self.created_attachment = None
        self.created_issues: List = []
        self.existing_invoice = None
        self.open_issues: List = []
        _FakeInvoiceDAO.instances.append(self)

    def get_invoice_by_vendor_and_number(self, vendor_id, invoice_number):
        return self.existing_invoice

    def get_status_by_code(self, code):
        return SimpleNamespace(status_id={"OCR_REVIEW_PENDING": 6, "OCR_FAILED": 7, "PENDING_APPROVAL": 8}.get(code, 1))

    def create_invoice(self, invoice):
        invoice.invoice_id = 555
        self.created_invoice = invoice
        return invoice

    def create_invoice_lines(self, lines):
        self.created_lines = lines
        return lines

    def create_invoice_line(self, line):
        self.created_lines.append(line)
        return line

    def create_invoice_attachment(self, attachment):
        self.created_attachment = attachment
        return attachment

    def create_invoice_issue(self, issue):
        self.created_issues.append(issue)
        return issue

    def get_invoice_by_id(self, invoice_id):
        return self.created_invoice

    def get_open_invoice_issues(self, invoice_id):
        return self.open_issues


class _FakeMasterDAO:
    def __init__(self, db):
        self.db = db

    def get_currency_by_code(self, code):
        if code in ("INR", "USD"):
            return SimpleNamespace(currency_id=1 if code == "INR" else 2)
        return None

    def get_payment_term_by_name(self, name):
        return None

    def get_tax_type_by_code(self, country_id, tax_code, effective_from):
        return None

    def get_system_config_by_key(self, key):
        return None


class _FakeInboundDocumentDAO:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, inbound_document_id):
        return _FakeInboundDocumentDAO._store.get(inbound_document_id)

    _store = {}


@pytest.fixture(autouse=True)
def _patch_daos(monkeypatch):
    _FakeInvoiceDAO.instances = []
    monkeypatch.setattr(svc, "InvoiceDAO", _FakeInvoiceDAO)
    monkeypatch.setattr(svc, "MasterDAO", _FakeMasterDAO)
    monkeypatch.setattr(svc, "InboundDocumentDAO", _FakeInboundDocumentDAO)
    monkeypatch.setattr(svc, "get_numeric_system_config", lambda db, key, default=None: default)
    monkeypatch.setattr(svc.notifications, "notify_vendor_not_found", lambda *a, **k: None)
    # Default: automatic vendor onboarding is not eligible, so a vendor-not-matched
    # FinalResponse exercises the existing manual-fallback path unless a test
    # overrides this to simulate a successful (or failing) auto-onboarding.
    monkeypatch.setattr(svc.vendor_auto_onboarding, "auto_create_vendor_from_extraction", lambda *a, **k: None)
    yield


def _inbound_document(**overrides) -> InboundDocument:
    doc = InboundDocument(
        inbound_document_id=1,
        source_type="UPLOAD",
        file_name="invoice.pdf",
        file_path="invoices/2026/01/abc_invoice.pdf",
        extraction_status="PENDING",
    )
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


def _final_response(extracted: ExtractedInvoice, vendor_match: VendorMatch, overall_confidence=95.0) -> FinalResponse:
    return FinalResponse(
        document=DocumentResult(source_filename="invoice.pdf", page_count=1, pages=[]),
        extracted_invoice=extracted,
        validation=ValidationResult(valid=True, errors=[]),
        vendor_match=vendor_match,
        confidence=ConfidenceResult(
            ocr_confidence=95, extraction_confidence=95, validation_confidence=100,
            vendor_confidence=100, overall_confidence=overall_confidence,
        ),
    )


def test_persist_processed_invoice_path_a_happy_path():
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(_extracted(), VendorMatch(matched=True, vendor_id=42, confidence=100.0))

    outcome = svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")

    assert outcome.invoice_id == 555
    assert outcome.invoice_status == invoice_status.STATUS_CODE_OCR_REVIEW_PENDING
    assert inbound_document.extraction_status == "EXTRACTED"
    assert inbound_document.vendor_id == 42
    assert db.committed >= 1


def test_persist_processed_invoice_duplicate_raises_and_links_inbound_document():
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(_extracted(), VendorMatch(matched=True, vendor_id=42, confidence=100.0))

    original_dao_init = svc.InvoiceDAO

    class DuplicateInvoiceDAO(original_dao_init):
        def __init__(self, db):
            super().__init__(db)
            self.existing_invoice = SimpleNamespace(invoice_id=999)

    svc.InvoiceDAO = DuplicateInvoiceDAO
    try:
        with pytest.raises(DuplicateInvoiceError):
            svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")
    finally:
        svc.InvoiceDAO = original_dao_init

    assert inbound_document.invoice_id == 999


def test_persist_processed_invoice_path_b_vendor_not_matched_and_not_auto_onboarded():
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(_extracted(), VendorMatch(matched=False, vendor_id=None, confidence=0.0))

    outcome = svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")

    assert outcome.invoice_id is None
    assert outcome.invoice_status == invoice_status.RESPONSE_STATUS_PENDING_VENDOR_ONBOARDING
    assert inbound_document.vendor_id is None
    assert inbound_document.extraction_status == "EXTRACTED"


def test_persist_processed_invoice_auto_onboards_vendor_and_creates_invoice(monkeypatch):
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(_extracted(), VendorMatch(matched=False, vendor_id=None, confidence=0.0))

    notify_calls = []
    monkeypatch.setattr(svc.vendor_auto_onboarding, "auto_create_vendor_from_extraction", lambda *a, **k: 777)
    monkeypatch.setattr(svc.notifications, "notify_vendor_not_found", lambda *a, **k: notify_calls.append(a))

    outcome = svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")

    assert outcome.invoice_id == 555  # from _FakeInvoiceDAO.create_invoice
    assert outcome.invoice_status == invoice_status.STATUS_CODE_OCR_REVIEW_PENDING
    assert inbound_document.vendor_id == 777
    assert notify_calls == []  # no vendor-not-found notification once auto-onboarding succeeded

    dao_instance = _FakeInvoiceDAO.instances[-1]
    assert dao_instance.created_invoice.vendor_id == 777


def test_persist_processed_invoice_auto_onboarding_failure_rolls_back(monkeypatch):
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(_extracted(), VendorMatch(matched=False, vendor_id=None, confidence=0.0))

    def _raise(*a, **k):
        raise RuntimeError("DB write failed while creating the auto-onboarded vendor")

    monkeypatch.setattr(svc.vendor_auto_onboarding, "auto_create_vendor_from_extraction", _raise)

    with pytest.raises(RuntimeError):
        svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")

    assert db.rolled_back >= 1
    assert db.committed == 0


def test_persist_processed_invoice_unusable_extraction_marks_failed():
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(
        _extracted(invoice_number=None), VendorMatch(matched=True, vendor_id=42, confidence=100.0)
    )

    with pytest.raises(FieldExtractionError):
        svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")

    assert inbound_document.extraction_status == "FAILED"


def test_persist_processed_invoice_low_confidence_creates_issue():
    db = _FakeDB()
    inbound_document = _inbound_document()
    final_response = _final_response(
        _extracted(), VendorMatch(matched=True, vendor_id=42, confidence=100.0), overall_confidence=50.0
    )

    svc.persist_processed_invoice(final_response, inbound_document, db, user_id="user-1")

    dao_instance = _FakeInvoiceDAO.instances[-1]
    issue_types = [issue.issue_type for issue in dao_instance.created_issues]
    assert invoice_status.ISSUE_TYPE_LOW_CONFIDENCE in issue_types


def test_apply_ocr_review_create_branch_requires_vendor_id():
    db = _FakeDB()
    inbound_document = _inbound_document(invoice_id=None)
    _FakeInboundDocumentDAO._store[1] = inbound_document

    review = InvoiceOCRReviewRequest(invoice_number="INV-1")
    with pytest.raises(ValueError):
        svc.apply_ocr_review(1, review, db, user_id="user-1")


def test_apply_ocr_review_create_branch_success():
    db = _FakeDB()
    inbound_document = _inbound_document(invoice_id=None)
    _FakeInboundDocumentDAO._store[2] = inbound_document

    review = InvoiceOCRReviewRequest(
        vendor_id=42,
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        currency_id=1,
        gross_amount=Decimal("1000.00"),
        net_amount=Decimal("1180.00"),
        lines=[InvoiceLineReviewRequest(line_number=1, description="Laptop", line_amount=Decimal("1000.00"))],
    )

    invoice = svc.apply_ocr_review(2, review, db, user_id="user-1")

    assert invoice.invoice_id == 555
    assert invoice.status_id == 8  # PENDING_APPROVAL per _FakeInvoiceDAO
    assert inbound_document.invoice_id == 555
    assert inbound_document.vendor_id == 42


def test_apply_ocr_review_update_branch_resolves_open_issues():
    db = _FakeDB()
    existing_invoice = SimpleNamespace(
        invoice_id=555, invoice_line=[], status_id=6, updated_by=None, vendor_id=42,
    )
    inbound_document = _inbound_document(invoice_id=555)
    _FakeInboundDocumentDAO._store[3] = inbound_document

    class UpdateInvoiceDAO(_FakeInvoiceDAO):
        def __init__(self, db):
            super().__init__(db)
            self.open_issues = [SimpleNamespace(resolved_by=None, resolved_at=None)]

        def get_invoice_by_id(self, invoice_id):
            return existing_invoice

    svc.InvoiceDAO = UpdateInvoiceDAO
    try:
        review = InvoiceOCRReviewRequest(invoice_number="INV-1-CORRECTED")
        invoice = svc.apply_ocr_review(3, review, db, user_id="reviewer-1")
    finally:
        svc.InvoiceDAO = _FakeInvoiceDAO

    assert invoice.invoice_number == "INV-1-CORRECTED"
    assert invoice.status_id == 8
    assert invoice.updated_by == "reviewer-1"


def test_apply_ocr_review_po_mandatory_flags_issue_without_blocking(monkeypatch):
    """PO_MANDATORY=true and no po_id on the invoice: a PO_REQUIRED issue is
    raised (non-blocking — invoice still reaches PENDING_APPROVAL) and that
    open issue then prevents AUTO_APPROVAL_LIMIT from auto-approving it."""
    db = _FakeDB()
    existing_invoice = SimpleNamespace(
        invoice_id=556, invoice_line=[], status_id=6, updated_by=None, vendor_id=42,
        po_id=None, net_amount=Decimal("10.00"),
    )
    inbound_document = _inbound_document(invoice_id=556)
    _FakeInboundDocumentDAO._store[4] = inbound_document

    class POMandatoryMasterDAO(_FakeMasterDAO):
        def get_system_config_by_key(self, key):
            if key == "PO_MANDATORY":
                return SimpleNamespace(config_value="true")
            return None

    class UpdateInvoiceDAO(_FakeInvoiceDAO):
        def __init__(self, db):
            super().__init__(db)
            self.open_issues = []

        def get_invoice_by_id(self, invoice_id):
            return existing_invoice

        def get_open_invoice_issues(self, invoice_id):
            return self.created_issues

    monkeypatch.setattr(svc, "MasterDAO", POMandatoryMasterDAO)
    monkeypatch.setattr(svc, "get_numeric_system_config", lambda db, key, default=None: Decimal("5000"))
    svc.InvoiceDAO = UpdateInvoiceDAO
    try:
        review = InvoiceOCRReviewRequest(invoice_number="INV-1-CORRECTED")
        invoice = svc.apply_ocr_review(4, review, db, user_id="reviewer-1")
    finally:
        svc.InvoiceDAO = _FakeInvoiceDAO

    dao_instance = UpdateInvoiceDAO.instances[-1]
    assert len(dao_instance.created_issues) == 1
    assert dao_instance.created_issues[0].issue_type == "PO_REQUIRED"
    assert dao_instance.created_issues[0].invoice_id == 556
    # Even though net_amount (10.00) is well under the 5000 AUTO_APPROVAL_LIMIT,
    # the open PO_REQUIRED issue must block auto-approval.
    assert invoice.status_id == 8  # PENDING_APPROVAL, not auto-approved
