# Backend/tests/test_invoice_details_service.py
"""Unit tests for InvoiceDetailsService, in particular payable_amount -
net_amount minus TDS when applicable, never a mutation of net_amount itself.
Same fake-DAO convention as the rest of this suite (see test_payment_service.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

import Backend.Business_Layer.services.invoice_details_service as svc


@dataclass
class _Invoice:
    invoice_id: int
    invoice_number: str
    vendor_id: Optional[int]
    inbound_document_id: Optional[int]
    invoice_type: str
    invoice_date: date
    due_date: date
    currency_id: Optional[int]
    gross_amount: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    amount_paid: Decimal
    po_id: Optional[int] = None
    payment_term_id: Optional[int] = None
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    status_id: Optional[int] = None


@dataclass
class _Vendor:
    vendor_id: int
    vendor_name: str


@dataclass
class _InvoiceTds:
    invoice_id: int
    tds_applicable: bool
    tds_amount: Optional[Decimal]


class _FakeInvoiceDetailsDAO:
    def __init__(self, db):
        self.db = db

    def get_invoice_details_by_id(self, invoice_id):
        return _STORE.get(invoice_id)

    def get_all_invoice_details(self):
        return list(_STORE.values())

    def get_status_master_by_id(self, status_id):
        return "READY_FOR_PAYMENT" if status_id == 13 else None


class _FakeVendorDAO:
    def __init__(self, db):
        self.db = db

    def get_vendor_by_id(self, vendor_id):
        return _VENDORS.get(vendor_id)


class _FakeInvoiceDAO:
    def __init__(self, db):
        self.db = db


class _FakeTdsDAO:
    def __init__(self, db):
        self.db = db

    def get_invoice_tds_by_invoice_id(self, invoice_id):
        return _TDS.get(invoice_id)

    def get_invoice_tds_by_invoice_ids(self, invoice_ids):
        return {i: _TDS[i] for i in invoice_ids if i in _TDS}


_STORE: Dict[int, _Invoice] = {}
_VENDORS: Dict[int, _Vendor] = {}
_TDS: Dict[int, _InvoiceTds] = {}


def _reset():
    _STORE.clear()
    _VENDORS.clear()
    _TDS.clear()


def _make_service(monkeypatch) -> svc.InvoiceDetailsService:
    monkeypatch.setattr(svc, "InvoiceDetailsDAO", _FakeInvoiceDetailsDAO)
    monkeypatch.setattr(svc, "VendorDAO", _FakeVendorDAO)
    monkeypatch.setattr(svc, "InvoiceDAO", _FakeInvoiceDAO)
    monkeypatch.setattr(svc, "TdsDAO", _FakeTdsDAO)
    return svc.InvoiceDetailsService(db=None)


def _invoice(invoice_id=1, vendor_id=15, net=Decimal("177000.00"), status_id=13):
    return _Invoice(
        invoice_id=invoice_id, invoice_number=f"INV-{invoice_id}", vendor_id=vendor_id,
        inbound_document_id=None, invoice_type="NON_PO", invoice_date=date(2026, 9, 23),
        due_date=date(2026, 10, 23), currency_id=1, gross_amount=net, discount_amount=Decimal("0"),
        tax_amount=Decimal("27000.00"), net_amount=net, amount_paid=Decimal("0"), status_id=status_id,
    )


def test_get_invoice_details_by_id_payable_amount_reduced_by_tds(monkeypatch):
    _reset()
    _STORE[1] = _invoice(net=Decimal("177000.00"))
    _VENDORS[15] = _Vendor(vendor_id=15, vendor_name="AMAZON WEB SERVICES INDIA PRIVATE LIMITED")
    _TDS[1] = _InvoiceTds(invoice_id=1, tds_applicable=True, tds_amount=Decimal("17700.00"))

    result = _make_service(monkeypatch).get_invoice_details_by_id(1)

    assert result.net_amount == Decimal("177000.00")  # untouched - never mutated
    assert result.tds_applicable is True
    assert result.tds_amount == Decimal("17700.00")
    assert result.payable_amount == Decimal("159300.00")


def test_get_invoice_details_by_id_payable_amount_equals_net_when_no_tds_row(monkeypatch):
    _reset()
    _STORE[1] = _invoice(net=Decimal("1000.00"))
    _VENDORS[15] = _Vendor(vendor_id=15, vendor_name="Test Vendor")

    result = _make_service(monkeypatch).get_invoice_details_by_id(1)

    assert result.tds_applicable is None
    assert result.tds_amount is None
    assert result.payable_amount == Decimal("1000.00")


def test_get_invoice_details_by_id_payable_amount_equals_net_when_tds_not_applicable(monkeypatch):
    _reset()
    _STORE[1] = _invoice(net=Decimal("1000.00"))
    _VENDORS[15] = _Vendor(vendor_id=15, vendor_name="Test Vendor")
    _TDS[1] = _InvoiceTds(invoice_id=1, tds_applicable=False, tds_amount=None)

    result = _make_service(monkeypatch).get_invoice_details_by_id(1)

    assert result.tds_applicable is False
    assert result.payable_amount == Decimal("1000.00")


def test_get_all_invoice_details_computes_payable_amount_per_row(monkeypatch):
    _reset()
    _STORE[1] = _invoice(invoice_id=1, net=Decimal("177000.00"))
    _STORE[2] = _invoice(invoice_id=2, net=Decimal("1000.00"))
    _VENDORS[15] = _Vendor(vendor_id=15, vendor_name="AMAZON WEB SERVICES INDIA PRIVATE LIMITED")
    _TDS[1] = _InvoiceTds(invoice_id=1, tds_applicable=True, tds_amount=Decimal("17700.00"))
    # invoice 2 has no TDS row at all

    results = {r.invoice_id: r for r in _make_service(monkeypatch).get_all_invoice_details()}

    assert results[1].payable_amount == Decimal("159300.00")
    assert results[2].payable_amount == Decimal("1000.00")
    assert results[2].tds_applicable is None
