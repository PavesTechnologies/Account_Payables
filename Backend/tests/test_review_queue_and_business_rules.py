# Backend/tests/test_review_queue_and_business_rules.py
"""Unit tests for:
- get_review_queue (Path A/Path B, derived — no dedicated queue table)
- PO_MANDATORY wiring (creates a PO_REQUIRED issue instead of blocking)
- AUTO_APPROVAL_LIMIT wiring (_maybe_auto_approve)

DAOs are faked, same convention as the rest of this test suite.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

import pytest

import Backend.Business_Layer.services.invoice_process_service as svc
from Backend.Business_Layer.utils import invoice_status


@dataclass
class _Status:
    status_id: int
    status_code: str


@dataclass
class _Invoice:
    invoice_id: int
    net_amount: Decimal
    status_id: Optional[int] = None
    po_id: Optional[int] = None
    invoice_number: Optional[str] = "INV-1"
    vendor_id: Optional[int] = 1
    inbound_document_id: Optional[int] = None
    created_at: datetime.datetime = field(default_factory=lambda: datetime.datetime(2026, 1, 1))


@dataclass
class _InboundDocument:
    inbound_document_id: int
    vendor_id: Optional[int]
    file_name: str
    extraction_status: str
    extraction_confidence: Optional[Decimal]
    received_at: datetime.datetime


class _FakeInvoiceDAO:
    open_issues: dict = {}
    status_by_code = {
        invoice_status.STATUS_CODE_PENDING_APPROVAL: _Status(8, "PENDING_APPROVAL"),
        "APPROVED": _Status(9, "APPROVED"),
    }
    by_status_code: dict = {}
    created_issues: List = []

    def __init__(self, db):
        self.db = db

    def get_status_by_code(self, code):
        return self.status_by_code.get(code)

    def get_open_invoice_issues(self, invoice_id):
        return self.open_issues.get(invoice_id, [])

    def get_invoices_by_status_code(self, status_code):
        return self.by_status_code.get(status_code, [])

    def create_invoice_issue(self, issue):
        _FakeInvoiceDAO.created_issues.append(issue)
        self.open_issues.setdefault(issue.invoice_id, []).append(issue)
        return issue


class _FakeInboundDocumentDAO:
    awaiting: List = []

    def __init__(self, db):
        self.db = db

    def get_awaiting_vendor_assignment(self):
        return self.awaiting


class _FakeMasterDAO:
    config: dict = {}

    def __init__(self, db):
        self.db = db

    def get_system_config_by_key(self, key):
        value = self.config.get(key)
        return None if value is None else type("Cfg", (), {"config_value": value})()


@pytest.fixture(autouse=True)
def _patch_daos(monkeypatch):
    _FakeInvoiceDAO.open_issues = {}
    _FakeInvoiceDAO.by_status_code = {}
    _FakeInvoiceDAO.created_issues = []
    _FakeInboundDocumentDAO.awaiting = []
    _FakeMasterDAO.config = {}
    monkeypatch.setattr(svc, "InvoiceDAO", _FakeInvoiceDAO)
    monkeypatch.setattr(svc, "InboundDocumentDAO", _FakeInboundDocumentDAO)
    monkeypatch.setattr(svc, "MasterDAO", _FakeMasterDAO)

    def _fake_get_numeric_system_config(db, key, default=None):
        value = _FakeMasterDAO.config.get(key)
        return None if value is None else Decimal(value)

    monkeypatch.setattr(svc, "get_numeric_system_config", _fake_get_numeric_system_config)
    yield


# ---------------------------------------------------------------------------
# get_review_queue
# ---------------------------------------------------------------------------


def test_get_review_queue_merges_both_paths_sorted_by_recency():
    _FakeInvoiceDAO.by_status_code[invoice_status.STATUS_CODE_OCR_REVIEW_PENDING] = [
        _Invoice(invoice_id=1, net_amount=Decimal("100"), created_at=datetime.datetime(2026, 1, 2)),
    ]
    _FakeInboundDocumentDAO.awaiting = [
        _InboundDocument(
            inbound_document_id=10, vendor_id=None, file_name="a.pdf",
            extraction_status="EXTRACTED", extraction_confidence=Decimal("54.1"),
            received_at=datetime.datetime(2026, 1, 3),
        ),
    ]

    items, total_a, total_b = svc.get_review_queue(db=object(), skip=0, limit=50)

    assert total_a == 1
    assert total_b == 1
    assert len(items) == 2
    # Most recent (Path B, 2026-01-03) first
    assert items[0]["path"] == "PATH_B"
    assert items[0]["inbound_document_id"] == 10
    assert items[1]["path"] == "PATH_A"
    assert items[1]["invoice_id"] == 1


def test_get_review_queue_pagination_window():
    _FakeInvoiceDAO.by_status_code[invoice_status.STATUS_CODE_OCR_REVIEW_PENDING] = [
        _Invoice(invoice_id=i, net_amount=Decimal("100"), created_at=datetime.datetime(2026, 1, i))
        for i in range(1, 6)
    ]

    items, total_a, total_b = svc.get_review_queue(db=object(), skip=1, limit=2)

    assert total_a == 5
    assert len(items) == 2
    # Sorted descending by created_at: day5, day4, day3, day2, day1 -> skip 1, take 2 -> day4, day3
    assert items[0]["invoice_id"] == 4
    assert items[1]["invoice_id"] == 3


# ---------------------------------------------------------------------------
# PO_MANDATORY
# ---------------------------------------------------------------------------


def test_maybe_auto_approve_skipped_when_po_required_issue_is_open():
    _FakeMasterDAO.config["AUTO_APPROVAL_LIMIT"] = "5000"
    invoice = _Invoice(invoice_id=1, net_amount=Decimal("100"), status_id=8)  # PENDING_APPROVAL
    invoice_dao = _FakeInvoiceDAO(db=None)
    invoice_dao.open_issues[1] = [object()]  # an unresolved issue exists (e.g. PO_REQUIRED)

    svc._maybe_auto_approve(invoice, invoice_dao, db=object())

    assert invoice.status_id == 8  # unchanged - still PENDING_APPROVAL


# ---------------------------------------------------------------------------
# AUTO_APPROVAL_LIMIT
# ---------------------------------------------------------------------------


def test_maybe_auto_approve_approves_when_within_limit_and_clean():
    _FakeMasterDAO.config["AUTO_APPROVAL_LIMIT"] = "5000"
    invoice = _Invoice(invoice_id=1, net_amount=Decimal("100"), status_id=8)  # PENDING_APPROVAL
    invoice_dao = _FakeInvoiceDAO(db=None)

    svc._maybe_auto_approve(invoice, invoice_dao, db=object())

    assert invoice.status_id == 9  # APPROVED


def test_maybe_auto_approve_does_nothing_when_over_limit():
    _FakeMasterDAO.config["AUTO_APPROVAL_LIMIT"] = "5000"
    invoice = _Invoice(invoice_id=1, net_amount=Decimal("50000"), status_id=8)
    invoice_dao = _FakeInvoiceDAO(db=None)

    svc._maybe_auto_approve(invoice, invoice_dao, db=object())

    assert invoice.status_id == 8  # unchanged


def test_maybe_auto_approve_does_nothing_when_limit_not_configured():
    invoice = _Invoice(invoice_id=1, net_amount=Decimal("100"), status_id=8)
    invoice_dao = _FakeInvoiceDAO(db=None)

    svc._maybe_auto_approve(invoice, invoice_dao, db=object())

    assert invoice.status_id == 8  # unchanged - AUTO_APPROVAL_LIMIT not configured


def test_maybe_auto_approve_ignores_invoices_not_pending_approval():
    _FakeMasterDAO.config["AUTO_APPROVAL_LIMIT"] = "5000"
    invoice = _Invoice(invoice_id=1, net_amount=Decimal("100"), status_id=5)  # some other status
    invoice_dao = _FakeInvoiceDAO(db=None)

    svc._maybe_auto_approve(invoice, invoice_dao, db=object())

    assert invoice.status_id == 5  # untouched
