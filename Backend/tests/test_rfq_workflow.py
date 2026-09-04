# Backend/tests/test_rfq_workflow.py
"""Tests for the RFQ -> Quotation -> Vendor Selection -> PO workflow.

Follows the project's existing test style (see test_vendor_buyer_validation.py):
fake DAOs stand in for the real SQLAlchemy DAOs, no real DB connection. The
fakes here are shared between ProcurementService and RFQService the same way
the real DB session is shared between them in production, so this doubles as
an end-to-end smoke test of the whole workflow described in the task.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from Backend.Business_Layer.services.procurement_service import ProcurementService
from Backend.Business_Layer.services.rfq_service import RFQService
from Backend.Business_Layer.utils.email_service import EmailSendResult

# The real service methods construct real SQLAlchemy model instances
# (PurchaseRequisition, Quotation, RFQ, RFQVendor) directly - they are never
# faked here, only the DAOs are. Those instances are transient (never added
# to a session), so `.status_id` set via the constructor does NOT make the
# `.status` relationship resolve on its own the way a committed/refreshed
# row would in production. `set_committed_value` is SQLAlchemy's supported
# way to populate a relationship on such an instance without a DB round
# trip, and - unlike a plain `obj.status = ...` assignment - without firing
# the `back_populates` collection-sync machinery those relationships carry.


class FakeStatus:
    def __init__(self, status_id: int, module_name: str, status_code: str):
        self.status_id = status_id
        self.module_name = module_name
        self.status_code = status_code


class StatusRegistry:
    """Resolves (module_name, status_code) <-> status_id like status_master."""

    def __init__(self):
        self._by_code: Dict[Tuple[str, str], FakeStatus] = {}
        self._by_id: Dict[int, FakeStatus] = {}
        self._next_id = 1

    def add(self, module_name: str, status_code: str) -> FakeStatus:
        status = FakeStatus(self._next_id, module_name, status_code)
        self._by_code[(module_name, status_code)] = status
        self._by_id[status.status_id] = status
        self._next_id += 1
        return status

    def get_by_module_code(self, module_name: str, status_code: str) -> Optional[FakeStatus]:
        return self._by_code.get((module_name, status_code))

    def get_by_id(self, status_id: int) -> Optional[FakeStatus]:
        return self._by_id.get(status_id)

    def attach(self, obj):
        """Resolve `obj.status` from `obj.status_id`, bypassing relationship
        events - mirrors what a real `session.refresh()`/query would show."""
        if obj is not None and getattr(obj, "status_id", None) is not None:
            set_committed_value(obj, "status", self.get_by_id(obj.status_id))
        return obj


class FakeVendor:
    def __init__(self, vendor_id, status: FakeStatus, email=None, vendor_name=None):
        self.vendor_id = vendor_id
        self.status = status
        self.email = email if email is not None else f"vendor{vendor_id}@example.com"
        self.vendor_name = vendor_name if vendor_name is not None else f"Vendor {vendor_id}"


# ---------------------------------------------------------------------------
# Fake DAOs (shared stores across ProcurementService and RFQService, the
# same way both services share one real DB session in production)
# ---------------------------------------------------------------------------


class FakeDB:
    def __init__(self, registry: StatusRegistry):
        self.registry = registry

    def commit(self):
        pass

    def refresh(self, obj):
        self.registry.attach(obj)

    def rollback(self):
        pass


class FakeProcurementDAO:
    def __init__(self, registry: StatusRegistry, vendors: Dict[int, FakeVendor],
                 departments: dict, categories: dict):
        self.registry = registry
        self.vendors = vendors
        self.departments = departments
        self.categories = categories
        self.prs: Dict[int, object] = {}
        self.lines: Dict[int, object] = {}
        self.quotations: Dict[int, object] = {}
        self.audit_logs: list = []
        self._next_pr_id = 1
        self._next_line_id = 1
        self._next_quotation_id = 1

    def create_audit_log(self, audit_log):
        audit_log.audit_log_id = len(self.audit_logs) + 1
        self.audit_logs.append(audit_log)
        return audit_log

    def create_purchase_requisition(self, pr):
        pr.id = self._next_pr_id
        self._next_pr_id += 1
        self.prs[pr.id] = pr
        return self.registry.attach(pr)

    def get_purchase_requisition_by_id(self, pr_id):
        return self.registry.attach(self.prs.get(pr_id))

    def get_lines_by_pr_id(self, pr_id):
        return [l for l in self.lines.values() if l.pr_id == pr_id]

    def create_purchase_requisition_line(self, line):
        line.id = self._next_line_id
        self._next_line_id += 1
        self.lines[line.id] = line
        return line

    def get_line_by_id(self, line_id):
        return self.lines.get(line_id)

    def delete_purchase_requisition_line(self, line):
        self.lines.pop(line.id, None)

    def create_quotation(self, quotation):
        quotation.id = self._next_quotation_id
        self._next_quotation_id += 1
        self.quotations[quotation.id] = quotation
        return self.registry.attach(quotation)

    def get_quotation_by_id(self, quotation_id):
        return self.registry.attach(self.quotations.get(quotation_id))

    def get_quotations_by_pr_id(self, pr_id):
        return [self.registry.attach(q) for q in self.quotations.values() if q.pr_id == pr_id]

    def get_quotations_by_rfq_id(self, rfq_id):
        return [self.registry.attach(q) for q in self.quotations.values() if q.rfq_id == rfq_id]

    def delete_quotation(self, quotation):
        self.quotations.pop(quotation.id, None)

    def get_allowed_category_ids_for_department(self, department_id):
        return set()

    def get_vendor_by_id(self, vendor_id):
        return self.vendors.get(vendor_id)

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)


class FakeRFQDAO:
    def __init__(self, registry: StatusRegistry, vendors: Dict[int, FakeVendor]):
        self.registry = registry
        self.vendors = vendors
        self.rfqs: Dict[int, object] = {}
        self.rfq_vendors: list = []
        self._next_rfq_id = 1
        self._next_rfqv_id = 1

    def create_rfq(self, rfq):
        rfq.id = self._next_rfq_id
        self._next_rfq_id += 1
        self.rfqs[rfq.id] = rfq
        return self.registry.attach(rfq)

    def get_rfq_by_id(self, rfq_id):
        return self.registry.attach(self.rfqs.get(rfq_id))

    def get_all_rfqs(self, pr_id=None, status_id=None, skip=0, limit=100):
        rows = list(self.rfqs.values())
        if pr_id is not None:
            rows = [r for r in rows if r.pr_id == pr_id]
        if status_id is not None:
            rows = [r for r in rows if r.status_id == status_id]
        return [self.registry.attach(r) for r in rows]

    def create_rfq_vendor(self, rfq_vendor):
        rfq_vendor.id = self._next_rfqv_id
        self._next_rfqv_id += 1
        self.rfq_vendors.append(rfq_vendor)
        return rfq_vendor

    def get_rfq_vendors(self, rfq_id):
        return [rv for rv in self.rfq_vendors if rv.rfq_id == rfq_id]

    def is_vendor_invited(self, rfq_id, vendor_id):
        return any(rv.rfq_id == rfq_id and rv.vendor_id == vendor_id for rv in self.rfq_vendors)

    def get_vendor_by_id(self, vendor_id):
        return self.vendors.get(vendor_id)

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)


class FakeMasterDAO:
    def __init__(self, departments: dict, categories: dict):
        self.departments = departments
        self.categories = categories

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)

    def get_purchase_category_by_id(self, purchase_category_id):
        return self.categories.get(purchase_category_id)


class FakePurchaseOrderDAO:
    def __init__(self, registry: StatusRegistry):
        self.registry = registry
        self.purchase_orders = {}
        self.lines = []
        self._next_po_id = 1

    def create_purchase_order(self, po):
        po.po_id = self._next_po_id
        self._next_po_id += 1
        self.purchase_orders[po.po_id] = po
        return po

    def create_purchase_order_line(self, line):
        self.lines.append(line)
        return line

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)


# ---------------------------------------------------------------------------
# Fixture: a fully wired workflow with 3 vendors, a department/category, and
# both services sharing the same fake persistence layer.
# ---------------------------------------------------------------------------


class Workflow:
    def __init__(self):
        self.registry = StatusRegistry()
        for code in ("DRAFT", "PENDING_APPROVAL", "APPROVED", "VENDOR_SELECTION", "PO_GENERATED", "REJECTED", "CANCELLED"):
            self.registry.add("PURCHASE_REQUISITION", code)
        for code in ("RECEIVED", "SELECTED", "REJECTED"):
            self.registry.add("QUOTATION", code)
        for code in ("DRAFT", "SENT", "RESPONSE_RECEIVED", "CLOSED"):
            self.registry.add("RFQ", code)
        self.registry.add("PO", "OPEN")
        active = self.registry.add("VENDOR", "ACTIVE")

        self.vendors = {
            1: FakeVendor(1, active),  # ABC Technologies
            2: FakeVendor(2, active),  # XYZ Computers
            3: FakeVendor(3, active),  # PQR Systems
        }
        self.departments = {10: SimpleNamespace(id=10, is_active=True)}
        self.categories = {20: SimpleNamespace(id=20, is_active=True)}

        self.procurement_dao = FakeProcurementDAO(self.registry, self.vendors, self.departments, self.categories)
        self.rfq_dao = FakeRFQDAO(self.registry, self.vendors)
        self.master_dao = FakeMasterDAO(self.departments, self.categories)
        self.po_dao = FakePurchaseOrderDAO(self.registry)

        self.procurement_service = ProcurementService(db=FakeDB(self.registry))
        self.procurement_service.procurement_dao = self.procurement_dao
        self.procurement_service.master_dao = self.master_dao
        self.procurement_service.po_dao = self.po_dao
        self.procurement_service.rfq_dao = self.rfq_dao

        self.rfq_service = RFQService(db=FakeDB(self.registry))
        self.rfq_service.procurement_dao = self.procurement_dao
        self.rfq_service.rfq_dao = self.rfq_dao

    def create_approved_pr(self) -> FakePR:
        payload = SimpleNamespace(
            department_id=10,
            purchase_category_id=20,
            priority="NORMAL",
            required_by=None,
            delivery_location=None,
            justification=None,
            lines=[
                SimpleNamespace(
                    item_name="Business Laptop",
                    description=None,
                    quantity=5,
                    uom="EA",
                    estimated_unit_price=60000,
                    estimated_amount=300000,
                )
            ],
        )
        pr = self.procurement_service.create_purchase_requisition(payload, user_id="buyer1")
        self.procurement_service.submit_purchase_requisition(pr.id)
        return self.procurement_service.approve_purchase_requisition(pr.id, "manager1", "Approved")


@pytest.fixture
def wf(monkeypatch):
    # These tests exercise RFQ/PR business rules, not real email delivery
    # (see test_rfq_email_sending.py for that) - stub send_email so
    # send_rfq() always succeeds without touching SMTP/network at all.
    import Backend.Business_Layer.services.rfq_service as rfq_service_module

    def _fake_send_email(**kwargs):
        return EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc))

    monkeypatch.setattr(rfq_service_module, "send_email", _fake_send_email)
    return Workflow()


# ---------------------------------------------------------------------------
# End-to-end smoke test (mirrors the task's smoke_test scenario)
# ---------------------------------------------------------------------------


def test_full_rfq_to_po_smoke_test(wf: Workflow):
    pr = wf.create_approved_pr()
    assert pr.status.status_code == "APPROVED"

    rfq = wf.rfq_service.create_rfq(pr.id, due_date=datetime.date(2026, 9, 10), user_id="buyer1")
    assert rfq.status.status_code == "DRAFT"
    assert wf.procurement_dao.get_purchase_requisition_by_id(pr.id).sourcing_type == "RFQ"

    wf.rfq_service.invite_vendors(rfq.id, [1, 2, 3], user_id="buyer1")
    assert {v.vendor_id for v in wf.rfq_service.list_vendors(rfq.id)} == {1, 2, 3}

    wf.rfq_service.send_rfq(rfq.id, user_id="buyer1")
    assert wf.rfq_dao.get_rfq_by_id(rfq.id).status.status_code == "SENT"

    abc_q = wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="s3://q-abc", quotation_number="QT-ABC-001",
        quotation_date=None, valid_until=None, total_amount=300000, user_id="buyer1",
        rfq_id=rfq.id, delivery_days=15, payment_terms="30 days",
    )
    # first quotation flips PR APPROVED -> VENDOR_SELECTION and RFQ SENT -> RESPONSE_RECEIVED
    assert wf.procurement_dao.get_purchase_requisition_by_id(pr.id).status.status_code == "VENDOR_SELECTION"
    assert wf.rfq_dao.get_rfq_by_id(rfq.id).status.status_code == "RESPONSE_RECEIVED"

    wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=2, file_url="s3://q-xyz", quotation_number="QT-XYZ-045",
        quotation_date=None, valid_until=None, total_amount=285000, user_id="buyer1",
        rfq_id=rfq.id, delivery_days=20, payment_terms="30 days",
    )
    pqr_q = wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=3, file_url="s3://q-pqr", quotation_number="QT-PQR-018",
        quotation_date=None, valid_until=None, total_amount=295000, user_id="buyer1",
        rfq_id=rfq.id, delivery_days=10, payment_terms="45 days",
    )

    wf.rfq_service.close_rfq(rfq.id, user_id="buyer1")
    assert wf.rfq_dao.get_rfq_by_id(rfq.id).status.status_code == "CLOSED"

    updated_pr = wf.procurement_service.select_vendor(
        pr.id, pqr_q.id, reason="Faster delivery and better payment terms"
    )
    assert updated_pr.selected_vendor_id == 3
    assert updated_pr.selected_quotation_id == pqr_q.id
    assert updated_pr.selection_reason == "Faster delivery and better payment terms"

    quotations_by_vendor = {q.vendor_id: q.status.status_code for q in wf.procurement_dao.get_quotations_by_pr_id(pr.id)}
    assert quotations_by_vendor == {1: "REJECTED", 2: "REJECTED", 3: "SELECTED"}

    po = wf.procurement_service.generate_purchase_order(pr.id, user_id="buyer1")
    assert po.vendor_id == 3
    assert po.quotation_id == pqr_q.id
    assert wf.procurement_dao.get_purchase_requisition_by_id(pr.id).status.status_code == "PO_GENERATED"


# ---------------------------------------------------------------------------
# Business rule / negative-path tests
# ---------------------------------------------------------------------------


def test_rfq_cannot_be_created_before_pr_is_approved(wf: Workflow):
    payload = SimpleNamespace(
        department_id=10, purchase_category_id=20, priority="NORMAL",
        required_by=None, delivery_location=None, justification=None, lines=[],
    )
    draft_pr = wf.procurement_service.create_purchase_requisition(payload, user_id="buyer1")

    with pytest.raises(ValueError, match="status DRAFT"):
        wf.rfq_service.create_rfq(draft_pr.id, due_date=None, user_id="buyer1")


def test_invite_vendors_rejects_inactive_vendor(wf: Workflow):
    inactive_status = wf.registry.add("VENDOR", "INACTIVE")
    wf.vendors[99] = FakeVendor(99, inactive_status)
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")

    with pytest.raises(ValueError, match="ACTIVE"):
        wf.rfq_service.invite_vendors(rfq.id, [99], user_id="buyer1")


def test_send_rfq_requires_at_least_one_invited_vendor(wf: Workflow):
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")

    with pytest.raises(ValueError, match="at least one invited vendor"):
        wf.rfq_service.send_rfq(rfq.id, user_id="buyer1")


def test_quotation_rejected_for_uninvited_vendor(wf: Workflow):
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")
    wf.rfq_service.invite_vendors(rfq.id, [1], user_id="buyer1")
    wf.rfq_service.send_rfq(rfq.id, user_id="buyer1")

    with pytest.raises(ValueError, match="not invited"):
        wf.procurement_service.create_quotation(
            pr_id=pr.id, vendor_id=2, file_url="s3://x", quotation_number=None,
            quotation_date=None, valid_until=None, total_amount=100, user_id="buyer1",
            rfq_id=rfq.id,
        )


def test_closed_rfq_rejects_new_quotations(wf: Workflow):
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")
    wf.rfq_service.invite_vendors(rfq.id, [1], user_id="buyer1")
    wf.rfq_service.send_rfq(rfq.id, user_id="buyer1")
    wf.rfq_service.close_rfq(rfq.id, user_id="buyer1")

    with pytest.raises(ValueError, match="closed"):
        wf.procurement_service.create_quotation(
            pr_id=pr.id, vendor_id=1, file_url="s3://x", quotation_number=None,
            quotation_date=None, valid_until=None, total_amount=100, user_id="buyer1",
            rfq_id=rfq.id,
        )


def test_select_vendor_requires_rfq_closed_first(wf: Workflow):
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")
    wf.rfq_service.invite_vendors(rfq.id, [1], user_id="buyer1")
    wf.rfq_service.send_rfq(rfq.id, user_id="buyer1")
    quotation = wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="s3://x", quotation_number=None,
        quotation_date=None, valid_until=None, total_amount=100, user_id="buyer1",
        rfq_id=rfq.id,
    )

    with pytest.raises(ValueError, match="RFQ must be closed"):
        wf.procurement_service.select_vendor(pr.id, quotation.id)

    wf.rfq_service.close_rfq(rfq.id, user_id="buyer1")
    updated_pr = wf.procurement_service.select_vendor(pr.id, quotation.id)
    assert updated_pr.selected_quotation_id == quotation.id


def test_quotation_without_rfq_still_works_unchanged(wf: Workflow):
    """Backward compatibility: rfq_id is optional, legacy PR-only quotations
    (no RFQ at all) must keep working exactly as before."""
    pr = wf.create_approved_pr()

    quotation = wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="s3://legacy", quotation_number="Q1",
        quotation_date=None, valid_until=None, total_amount=500, user_id="buyer1",
    )
    assert quotation.rfq_id is None

    updated_pr = wf.procurement_service.select_vendor(pr.id, quotation.id)
    assert updated_pr.selected_quotation_id == quotation.id


def test_record_sourcing_decision_rejects_conflicting_second_call(wf: Workflow):
    pr = wf.create_approved_pr()
    wf.procurement_service.record_sourcing_decision(pr.id, "CATALOG")

    with pytest.raises(ValueError, match="already recorded"):
        wf.procurement_service.record_sourcing_decision(pr.id, "RFQ")


def test_rfq_creation_blocked_after_catalog_decision(wf: Workflow):
    pr = wf.create_approved_pr()
    wf.procurement_service.record_sourcing_decision(pr.id, "CATALOG")

    with pytest.raises(ValueError, match="CATALOG"):
        wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")
