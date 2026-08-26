# Backend/tests/test_matching_service.py
"""Unit tests for PO/GRN/Invoice matching (2-way and 3-way).

DAOs are faked (no real DB) — same convention as
test_invoice_status_and_persistence.py: plain in-memory stand-ins
monkeypatched into the service module's namespace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

import pytest

import Backend.Business_Layer.services.matching_service as svc
from Backend.API_Layer.interface.matching_interface import (
    LineMatchStatus,
    MatchType,
    OverallMatchStatus,
)


@dataclass
class _InvoiceLine:
    invoice_line_id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    po_line_id: Optional[int] = None


@dataclass
class _Invoice:
    invoice_id: int
    po_id: Optional[int] = None
    invoice_line: List[_InvoiceLine] = field(default_factory=list)


@dataclass
class _POLine:
    po_line_id: int
    quantity: Decimal
    unit_price: Decimal


@dataclass
class _PO:
    po_id: int
    po_number: str
    purchase_order_line: List[_POLine] = field(default_factory=list)


@dataclass
class _GRNLine:
    grn_id: int
    po_line_id: Optional[int]
    received_quantity: Decimal


class _FakeInvoiceDAO:
    store: dict = {}

    def __init__(self, db):
        self.db = db

    def get_invoice_by_id(self, invoice_id):
        return self.store.get(invoice_id)


class _FakePurchaseOrderDAO:
    store: dict = {}

    def __init__(self, db):
        self.db = db

    def get_purchase_order_by_id(self, po_id):
        return self.store.get(po_id)


class _FakeGoodsReceiptDAO:
    lines_by_po: dict = {}

    def __init__(self, db):
        self.db = db

    def get_lines_by_po_id(self, po_id):
        return self.lines_by_po.get(po_id, [])


class _FakeMasterDAO:
    config: dict = {}

    def __init__(self, db):
        self.db = db

    def get_system_config_by_key(self, key):
        value = self.config.get(key)
        return None if value is None else type("Cfg", (), {"config_value": value})()


@pytest.fixture(autouse=True)
def _patch_daos(monkeypatch):
    _FakeInvoiceDAO.store = {}
    _FakePurchaseOrderDAO.store = {}
    _FakeGoodsReceiptDAO.lines_by_po = {}
    _FakeMasterDAO.config = {}
    monkeypatch.setattr(svc, "InvoiceDAO", _FakeInvoiceDAO)
    monkeypatch.setattr(svc, "PurchaseOrderDAO", _FakePurchaseOrderDAO)
    monkeypatch.setattr(svc, "GoodsReceiptDAO", _FakeGoodsReceiptDAO)
    monkeypatch.setattr(svc, "MasterDAO", _FakeMasterDAO)
    yield


def test_invoice_not_found_raises():
    with pytest.raises(ValueError):
        svc.MatchingService(db=object()).match_invoice(999)


def test_non_po_invoice_reports_no_po():
    _FakeInvoiceDAO.store[1] = _Invoice(invoice_id=1, po_id=None)

    result = svc.MatchingService(db=object()).match_invoice(1)

    assert result.overall_status == OverallMatchStatus.NO_PO
    assert result.match_type == MatchType.NONE
    assert result.lines == []


def test_two_way_match_within_tolerance():
    _FakeInvoiceDAO.store[1] = _Invoice(
        invoice_id=1, po_id=10,
        invoice_line=[_InvoiceLine(1, 1, "Laptop", Decimal("5.0000"), Decimal("20000.0000"), po_line_id=100)],
    )
    _FakePurchaseOrderDAO.store[10] = _PO(
        po_id=10, po_number="PO-1",
        purchase_order_line=[_POLine(100, Decimal("5.0000"), Decimal("20000.0000"))],
    )
    _FakeGoodsReceiptDAO.lines_by_po[10] = []  # no GRN -> 2-way

    result = svc.MatchingService(db=object()).match_invoice(1)

    assert result.match_type == MatchType.TWO_WAY
    assert result.overall_status == OverallMatchStatus.MATCHED
    assert result.lines[0].status == LineMatchStatus.MATCHED


def test_three_way_match_detects_quantity_and_price_variance():
    _FakeInvoiceDAO.store[1] = _Invoice(
        invoice_id=1, po_id=10,
        invoice_line=[_InvoiceLine(1, 1, "Laptop", Decimal("7.0000"), Decimal("21000.0000"), po_line_id=100)],
    )
    _FakePurchaseOrderDAO.store[10] = _PO(
        po_id=10, po_number="PO-1",
        purchase_order_line=[_POLine(100, Decimal("5.0000"), Decimal("20000.0000"))],
    )
    _FakeGoodsReceiptDAO.lines_by_po[10] = [_GRNLine(grn_id=50, po_line_id=100, received_quantity=Decimal("5.0000"))]

    result = svc.MatchingService(db=object()).match_invoice(1)

    assert result.match_type == MatchType.THREE_WAY
    assert result.overall_status == OverallMatchStatus.VARIANCE_DETECTED
    line = result.lines[0]
    assert line.status == LineMatchStatus.QUANTITY_AND_PRICE_VARIANCE
    assert line.quantity_variance == Decimal("2.0000")
    assert line.price_variance == Decimal("1000.0000")


def test_grn_mandatory_but_missing_is_flagged():
    _FakeMasterDAO.config["GRN_MANDATORY"] = "true"
    _FakeInvoiceDAO.store[1] = _Invoice(
        invoice_id=1, po_id=10,
        invoice_line=[_InvoiceLine(1, 1, "Laptop", Decimal("5.0000"), Decimal("20000.0000"), po_line_id=100)],
    )
    _FakePurchaseOrderDAO.store[10] = _PO(
        po_id=10, po_number="PO-1",
        purchase_order_line=[_POLine(100, Decimal("5.0000"), Decimal("20000.0000"))],
    )
    _FakeGoodsReceiptDAO.lines_by_po[10] = []

    result = svc.MatchingService(db=object()).match_invoice(1)

    assert result.overall_status == OverallMatchStatus.GRN_REQUIRED_BUT_MISSING
    assert result.grn_mandatory is True


def test_line_not_linked_to_po_line_is_incomplete():
    _FakeInvoiceDAO.store[1] = _Invoice(
        invoice_id=1, po_id=10,
        invoice_line=[_InvoiceLine(1, 1, "Laptop", Decimal("5.0000"), Decimal("20000.0000"), po_line_id=None)],
    )
    _FakePurchaseOrderDAO.store[10] = _PO(
        po_id=10, po_number="PO-1",
        purchase_order_line=[_POLine(100, Decimal("5.0000"), Decimal("20000.0000"))],
    )
    _FakeGoodsReceiptDAO.lines_by_po[10] = []

    result = svc.MatchingService(db=object()).match_invoice(1)

    assert result.overall_status == OverallMatchStatus.INCOMPLETE
    assert result.lines[0].status == LineMatchStatus.NO_PO_LINE_LINKED
