# Backend/tests/test_payment_service.py
"""Unit tests for payment creation, allocation limits, and the
SCHEDULED -> SENT -> CLEARED / FAILED status lifecycle.

DAOs are faked, same convention as the rest of this test suite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

import pytest

import Backend.Business_Layer.services.payment_service as svc
from Backend.API_Layer.interface.payment_interface import (
    PaymentAllocationRequest,
    PaymentCreateRequest,
)


@dataclass
class _Status:
    status_id: int
    status_code: str


@dataclass
class _Invoice:
    invoice_id: int
    vendor_id: int
    net_amount: Decimal
    amount_paid: Decimal
    status: Optional[_Status]
    status_id: Optional[int] = None
    updated_by: Optional[str] = None


@dataclass
class _PaymentInvoice:
    payment_invoice_id: int
    invoice_id: int
    allocated_amount: Decimal


@dataclass
class _Payment:
    payment_id: int
    vendor_id: int
    status: Optional[_Status]
    status_id: Optional[int] = None
    payment_date: Optional[object] = None
    reference_number: Optional[str] = None
    updated_by: Optional[str] = None
    payment_invoice: List[_PaymentInvoice] = field(default_factory=list)


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


class _FakeVendorDAO:
    vendors: set = set()

    def __init__(self, db):
        self.db = db

    def vendor_exists(self, vendor_id):
        return vendor_id in self.vendors


class _FakeInvoiceDAO:
    store: dict = {}

    def __init__(self, db):
        self.db = db

    def get_invoice_by_id_locked(self, invoice_id):
        return self.store.get(invoice_id)

    def get_status_by_code(self, code):
        return {
            "PAID": _Status(status_id=12, status_code="PAID"),
            "PARTIALLY_PAID": _Status(status_id=11, status_code="PARTIALLY_PAID"),
        }.get(code)


class _FakePaymentDAO:
    statuses = {
        ("PAYMENT", "SCHEDULED"): _Status(20, "SCHEDULED"),
        ("PAYMENT", "SENT"): _Status(21, "SENT"),
        ("PAYMENT", "CLEARED"): _Status(22, "CLEARED"),
        ("PAYMENT", "FAILED"): _Status(23, "FAILED"),
    }
    pending_committed: dict = {}
    payments: dict = {}
    audits: List = []
    next_payment_id = 100
    next_allocation_id = 1000

    def __init__(self, db):
        self.db = db

    def get_status_by_module_code(self, module_name, status_code):
        return self.statuses.get((module_name, status_code))

    def create_payment(self, payment):
        payment.payment_id = _FakePaymentDAO.next_payment_id
        _FakePaymentDAO.next_payment_id += 1
        payment.payment_invoice = []
        _FakePaymentDAO.payments[payment.payment_id] = payment
        return payment

    def create_payment_invoice(self, allocation):
        allocation.payment_invoice_id = _FakePaymentDAO.next_allocation_id
        _FakePaymentDAO.next_allocation_id += 1
        payment = _FakePaymentDAO.payments[allocation.payment_id]
        payment.payment_invoice.append(allocation)
        return allocation

    def get_pending_committed_amount_for_invoice(self, invoice_id):
        return self.pending_committed.get(invoice_id, Decimal("0"))

    def get_payment_by_id(self, payment_id):
        return self.payments.get(payment_id)

    def create_audit_log(self, audit_log):
        _FakePaymentDAO.audits.append(audit_log)
        return audit_log


@pytest.fixture(autouse=True)
def _patch_daos(monkeypatch):
    _FakeVendorDAO.vendors = {1}
    _FakeInvoiceDAO.store = {}
    _FakePaymentDAO.pending_committed = {}
    _FakePaymentDAO.payments = {}
    _FakePaymentDAO.audits = []
    _FakePaymentDAO.next_payment_id = 100
    _FakePaymentDAO.next_allocation_id = 1000
    monkeypatch.setattr(svc, "VendorDAO", _FakeVendorDAO)
    monkeypatch.setattr(svc, "InvoiceDAO", _FakeInvoiceDAO)
    monkeypatch.setattr(svc, "PaymentDAO", _FakePaymentDAO)
    yield


def _payable_invoice(invoice_id=1, vendor_id=1, net=Decimal("1000.00"), paid=Decimal("0")):
    return _Invoice(
        invoice_id=invoice_id, vendor_id=vendor_id, net_amount=net, amount_paid=paid,
        status=_Status(status_id=9, status_code="APPROVED"),
    )


def test_create_payment_vendor_not_found_rolls_back():
    db = _FakeDB()
    request = PaymentCreateRequest(
        vendor_id=999, scheduled_date="2026-08-20", currency_id=1, payment_method="NEFT",
        allocations=[PaymentAllocationRequest(invoice_id=1, allocated_amount=Decimal("100"))],
    )
    with pytest.raises(ValueError, match="not found"):
        svc.PaymentService(db).create_payment(request, "user-1")
    assert db.rolled_back == 1


def test_create_payment_invoice_wrong_vendor_raises():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _payable_invoice(vendor_id=2)
    request = PaymentCreateRequest(
        vendor_id=1, scheduled_date="2026-08-20", currency_id=1, payment_method="NEFT",
        allocations=[PaymentAllocationRequest(invoice_id=1, allocated_amount=Decimal("100"))],
    )
    with pytest.raises(ValueError, match="does not belong to vendor"):
        svc.PaymentService(db).create_payment(request, "user-1")


def test_create_payment_invoice_not_payable_status_raises():
    db = _FakeDB()
    invoice = _payable_invoice()
    invoice.status = _Status(status_id=8, status_code="PENDING_APPROVAL")
    _FakeInvoiceDAO.store[1] = invoice
    request = PaymentCreateRequest(
        vendor_id=1, scheduled_date="2026-08-20", currency_id=1, payment_method="NEFT",
        allocations=[PaymentAllocationRequest(invoice_id=1, allocated_amount=Decimal("100"))],
    )
    with pytest.raises(ValueError, match="not payable"):
        svc.PaymentService(db).create_payment(request, "user-1")


def test_create_payment_allocation_exceeds_remaining_raises():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _payable_invoice(net=Decimal("1000.00"), paid=Decimal("0"))
    request = PaymentCreateRequest(
        vendor_id=1, scheduled_date="2026-08-20", currency_id=1, payment_method="NEFT",
        allocations=[PaymentAllocationRequest(invoice_id=1, allocated_amount=Decimal("1500.00"))],
    )
    with pytest.raises(ValueError, match="exceeds the remaining payable amount"):
        svc.PaymentService(db).create_payment(request, "user-1")


def test_create_payment_allocation_excludes_already_pending_committed_amount():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _payable_invoice(net=Decimal("1000.00"), paid=Decimal("0"))
    _FakePaymentDAO.pending_committed[1] = Decimal("600.00")  # another SCHEDULED payment already reserved this

    request = PaymentCreateRequest(
        vendor_id=1, scheduled_date="2026-08-20", currency_id=1, payment_method="NEFT",
        allocations=[PaymentAllocationRequest(invoice_id=1, allocated_amount=Decimal("500.00"))],
    )
    with pytest.raises(ValueError, match="exceeds the remaining payable amount"):
        svc.PaymentService(db).create_payment(request, "user-1")


def test_create_payment_success_multiple_invoices():
    db = _FakeDB()
    _FakeInvoiceDAO.store[1] = _payable_invoice(invoice_id=1, net=Decimal("1000.00"))
    _FakeInvoiceDAO.store[2] = _payable_invoice(invoice_id=2, net=Decimal("500.00"))

    request = PaymentCreateRequest(
        vendor_id=1, scheduled_date="2026-08-20", currency_id=1, payment_method="NEFT",
        allocations=[
            PaymentAllocationRequest(invoice_id=1, allocated_amount=Decimal("1000.00")),
            PaymentAllocationRequest(invoice_id=2, allocated_amount=Decimal("500.00")),
        ],
    )

    payment = svc.PaymentService(db).create_payment(request, "user-1")

    assert payment.total_amount == Decimal("1500.00")
    assert payment.status_id == 20  # SCHEDULED
    assert len(payment.payment_invoice) == 2
    assert db.committed == 1
    assert len(_FakePaymentDAO.audits) == 1


def test_update_status_invalid_transition_raises():
    db = _FakeDB()
    payment = _Payment(payment_id=1, vendor_id=1, status=_Status(22, "CLEARED"))
    _FakePaymentDAO.payments[1] = payment

    with pytest.raises(ValueError, match="Cannot transition"):
        svc.PaymentService(db).update_status(1, "SENT", None, None, "user-1")


def test_update_status_scheduled_to_sent_does_not_touch_invoice():
    db = _FakeDB()
    payment = _Payment(payment_id=1, vendor_id=1, status=_Status(20, "SCHEDULED"))
    _FakePaymentDAO.payments[1] = payment

    updated = svc.PaymentService(db).update_status(1, "SENT", None, "REF123", "user-1")

    assert updated.status_id == 21
    assert updated.reference_number == "REF123"
    assert db.committed == 1


def test_update_status_cleared_applies_amount_paid_and_marks_partially_paid():
    db = _FakeDB()
    invoice = _payable_invoice(invoice_id=1, net=Decimal("1000.00"), paid=Decimal("0"))
    _FakeInvoiceDAO.store[1] = invoice
    payment = _Payment(
        payment_id=1, vendor_id=1, status=_Status(21, "SENT"),
        payment_invoice=[_PaymentInvoice(1, 1, Decimal("400.00"))],
    )
    _FakePaymentDAO.payments[1] = payment

    updated = svc.PaymentService(db).update_status(1, "CLEARED", None, None, "user-1")

    assert updated.status_id == 22
    assert invoice.amount_paid == Decimal("400.00")
    assert invoice.status_id == 11  # PARTIALLY_PAID
    assert updated.payment_date is not None


def test_update_status_cleared_marks_paid_when_fully_covered():
    db = _FakeDB()
    invoice = _payable_invoice(invoice_id=1, net=Decimal("1000.00"), paid=Decimal("0"))
    _FakeInvoiceDAO.store[1] = invoice
    payment = _Payment(
        payment_id=1, vendor_id=1, status=_Status(21, "SENT"),
        payment_invoice=[_PaymentInvoice(1, 1, Decimal("1000.00"))],
    )
    _FakePaymentDAO.payments[1] = payment

    svc.PaymentService(db).update_status(1, "CLEARED", None, None, "user-1")

    assert invoice.amount_paid == Decimal("1000.00")
    assert invoice.status_id == 12  # PAID


def test_update_status_failed_does_not_touch_invoice():
    db = _FakeDB()
    invoice = _payable_invoice(invoice_id=1, net=Decimal("1000.00"), paid=Decimal("0"))
    _FakeInvoiceDAO.store[1] = invoice
    payment = _Payment(
        payment_id=1, vendor_id=1, status=_Status(20, "SCHEDULED"),
        payment_invoice=[_PaymentInvoice(1, 1, Decimal("1000.00"))],
    )
    _FakePaymentDAO.payments[1] = payment

    svc.PaymentService(db).update_status(1, "FAILED", None, None, "user-1")

    assert invoice.amount_paid == Decimal("0")
    assert invoice.status_id is None


def test_get_payment_not_found_raises():
    db = _FakeDB()
    with pytest.raises(ValueError, match="not found"):
        svc.PaymentService(db).get_payment(999)
