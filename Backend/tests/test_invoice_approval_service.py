# Backend/tests/test_invoice_approval_service.py
"""Unit tests for single-level invoice approval (approve/reject/history).

DAOs are faked, same convention as the rest of this test suite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pytest

import Backend.Business_Layer.services.invoice_approval_service as svc


@dataclass
class _Status:
    status_id: int
    status_code: str


@dataclass
class _Invoice:
    invoice_id: int
    status: Optional[_Status] = None
    status_id: Optional[int] = None
    updated_by: Optional[str] = None


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
    store: dict = {}

    def __init__(self, db):
        self.db = db

    def get_invoice_by_id_locked(self, invoice_id):
        return self.store.get(invoice_id)

    def get_invoice_by_id(self, invoice_id):
        return self.store.get(invoice_id)


def _default_statuses():
    return {
        ("INVOICE", "APPROVED"): _Status(status_id=9, status_code="APPROVED"),
        ("INVOICE", "REJECTED"): _Status(status_id=10, status_code="REJECTED"),
    }


class _FakeInvoiceApprovalDAO:
    statuses = _default_statuses()
    created: List = []
    audits: List = []
    history: dict = {}

    def __init__(self, db):
        self.db = db

    def create_approval(self, approval):
        approval.invoice_approval_id = len(_FakeInvoiceApprovalDAO.created) + 1
        _FakeInvoiceApprovalDAO.created.append(approval)
        return approval

    def get_status_by_module_code(self, module_name, status_code):
        return self.statuses.get((module_name, status_code))

    def create_audit_log(self, audit_log):
        _FakeInvoiceApprovalDAO.audits.append(audit_log)
        return audit_log

    def get_approvals_by_invoice_id(self, invoice_id):
        return self.history.get(invoice_id, [])


@pytest.fixture(autouse=True)
def _patch_daos(monkeypatch):
    _FakeInvoiceDAO.store = {}
    _FakeInvoiceApprovalDAO.created = []
    _FakeInvoiceApprovalDAO.audits = []
    _FakeInvoiceApprovalDAO.history = {}
    _FakeInvoiceApprovalDAO.statuses = _default_statuses()
    monkeypatch.setattr(svc, "InvoiceDAO", _FakeInvoiceDAO)
    monkeypatch.setattr(svc, "InvoiceApprovalDAO", _FakeInvoiceApprovalDAO)
    yield


def test_approve_invoice_not_found_raises():
    db = _FakeDB()
    with pytest.raises(ValueError, match="not found"):
        svc.InvoiceApprovalService(db).approve_invoice(1, "user-1", None)
    assert db.rolled_back == 1


def test_approve_invoice_not_pending_approval_raises():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1, status=_Status(1, "DRAFT"), status_id=1)

    with pytest.raises(ValueError, match="not pending approval"):
        svc.InvoiceApprovalService(db).approve_invoice(1, "user-1", None)
    assert db.rolled_back == 1


def test_approve_invoice_success():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1, status=_Status(8, "PENDING_APPROVAL"), status_id=8)

    approval = svc.InvoiceApprovalService(db).approve_invoice(1, "user-1", "looks good")

    assert approval.decision == "APPROVED"
    assert approval.approver_name == "user-1"
    assert _FakeInvoiceDAO.store[1].status_id == 9
    assert _FakeInvoiceDAO.store[1].updated_by == "user-1"
    assert db.committed == 1
    assert len(_FakeInvoiceApprovalDAO.audits) == 1
    assert _FakeInvoiceApprovalDAO.audits[0].action == "APPROVE"


def test_reject_invoice_success_records_comments_as_reason():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1, status=_Status(8, "PENDING_APPROVAL"), status_id=8)

    approval = svc.InvoiceApprovalService(db).reject_invoice(1, "user-2", "GST mismatch")

    assert approval.decision == "REJECTED"
    assert approval.comments == "GST mismatch"
    assert _FakeInvoiceDAO.store[1].status_id == 10
    assert db.committed == 1


def test_reject_invoice_not_pending_approval_rolls_back():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1, status=_Status(9, "APPROVED"), status_id=9)

    with pytest.raises(ValueError, match="not pending approval"):
        svc.InvoiceApprovalService(db).reject_invoice(1, "user-2", "too late")
    assert db.rolled_back == 1
    assert db.committed == 0


def test_get_approval_history_returns_all_rows_invoice_not_found_raises():
    db = _FakeDB()
    with pytest.raises(ValueError, match="not found"):
        svc.InvoiceApprovalService(db).get_approval_history(1)


def test_get_approval_history_success():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1)
    _FakeInvoiceApprovalDAO.history[1] = ["row1", "row2"]

    history = svc.InvoiceApprovalService(db).get_approval_history(1)

    assert history == ["row1", "row2"]


def test_approve_invoice_missing_status_config_raises():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1, status=_Status(8, "PENDING_APPROVAL"), status_id=8)
    _FakeInvoiceApprovalDAO.statuses = {}

    with pytest.raises(ValueError, match="not configured"):
        svc.InvoiceApprovalService(db).approve_invoice(1, "user-1", None)
