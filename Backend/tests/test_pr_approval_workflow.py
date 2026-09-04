# Backend/tests/test_pr_approval_workflow.py
"""Tests for the PR approval workflow's Return-for-Clarification / Resubmit
extension (SUBMITTED -> RETURNED -> SUBMITTED -> APPROVED/REJECTED).

Follows the project's existing test style (see test_vendor_buyer_validation.py
and test_rfq_workflow.py): fake DAOs stand in for the real SQLAlchemy DAOs,
no real DB connection. The service methods construct real ORM model
instances directly, so `set_committed_value` is used to populate their
`.status` relationship without a DB round trip or triggering back_populates
collection-sync side effects on transient objects.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from Backend.Business_Layer.services.procurement_service import ProcurementService
from Backend.Business_Layer.services.rfq_service import RFQService


class FakeStatus:
    def __init__(self, status_id: int, module_name: str, status_code: str):
        self.status_id = status_id
        self.module_name = module_name
        self.status_code = status_code


class StatusRegistry:
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
        if obj is not None and getattr(obj, "status_id", None) is not None:
            set_committed_value(obj, "status", self.get_by_id(obj.status_id))
        return obj


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
    def __init__(self, registry: StatusRegistry, departments: dict, categories: dict):
        self.registry = registry
        self.departments = departments
        self.categories = categories
        self.prs: Dict[int, object] = {}
        self.lines: Dict[int, object] = {}
        self.audit_logs: list = []
        self._next_pr_id = 1
        self._next_line_id = 1

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

    def get_allowed_category_ids_for_department(self, department_id):
        return set()

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)

    def create_audit_log(self, audit_log):
        audit_log.audit_log_id = len(self.audit_logs) + 1
        self.audit_logs.append(audit_log)
        return audit_log


class FakeMasterDAO:
    def __init__(self, departments: dict, categories: dict):
        self.departments = departments
        self.categories = categories

    def get_department_by_id(self, department_id):
        return self.departments.get(department_id)

    def get_purchase_category_by_id(self, purchase_category_id):
        return self.categories.get(purchase_category_id)


class FakeRFQDAO:
    """Minimal stand-in - only what RFQService.create_rfq touches."""

    def __init__(self, registry: StatusRegistry):
        self.registry = registry
        self.rfqs: Dict[int, object] = {}
        self._next_rfq_id = 1

    def create_rfq(self, rfq):
        rfq.id = self._next_rfq_id
        self._next_rfq_id += 1
        self.rfqs[rfq.id] = rfq
        return self.registry.attach(rfq)

    def get_status_by_module_code(self, module_name, status_code):
        return self.registry.get_by_module_code(module_name, status_code)


class Workflow:
    def __init__(self):
        self.registry = StatusRegistry()
        for code in ("DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "RETURNED",
                     "VENDOR_SELECTION", "PO_GENERATED", "CANCELLED"):
            self.registry.add("PURCHASE_REQUISITION", code)
        self.registry.add("RFQ", "DRAFT")

        self.departments = {10: SimpleNamespace(id=10, is_active=True)}
        self.categories = {20: SimpleNamespace(id=20, is_active=True)}

        self.procurement_dao = FakeProcurementDAO(self.registry, self.departments, self.categories)
        self.master_dao = FakeMasterDAO(self.departments, self.categories)
        self.rfq_dao = FakeRFQDAO(self.registry)

        self.procurement_service = ProcurementService(db=FakeDB(self.registry))
        self.procurement_service.procurement_dao = self.procurement_dao
        self.procurement_service.master_dao = self.master_dao
        self.procurement_service.rfq_dao = self.rfq_dao

        self.rfq_service = RFQService(db=FakeDB(self.registry))
        self.rfq_service.procurement_dao = self.procurement_dao
        self.rfq_service.rfq_dao = self.rfq_dao

    def create_submitted_pr(self, requester: str = "requester1"):
        payload = SimpleNamespace(
            department_id=10,
            purchase_category_id=20,
            priority="NORMAL",
            required_by=None,
            delivery_location=None,
            justification=None,
            lines=[
                SimpleNamespace(
                    item_name="Office Chairs",
                    description=None,
                    quantity=10,
                    uom="EA",
                    estimated_unit_price=5000,
                    estimated_amount=50000,
                )
            ],
        )
        pr = self.procurement_service.create_purchase_requisition(payload, user_id=requester)
        return self.procurement_service.submit_purchase_requisition(pr.id)


@pytest.fixture
def wf():
    return Workflow()


# ---------------------------------------------------------------------------
# Existing approve/reject behaviour stays intact
# ---------------------------------------------------------------------------


def test_submitted_pr_can_be_approved(wf: Workflow):
    pr = wf.create_submitted_pr()
    approved = wf.procurement_service.approve_purchase_requisition(pr.id, "approver1", "Looks good")
    assert approved.status.status_code == "APPROVED"
    assert approved.approved_by == "approver1"
    assert approved.approval_comment == "Looks good"


def test_submitted_pr_can_be_rejected(wf: Workflow):
    pr = wf.create_submitted_pr()
    rejected = wf.procurement_service.reject_purchase_requisition(pr.id, "approver1", "Not needed")
    assert rejected.status.status_code == "REJECTED"
    assert rejected.approval_comment == "Not needed"


# ---------------------------------------------------------------------------
# Return for Clarification
# ---------------------------------------------------------------------------


def test_submitted_pr_can_be_returned_with_a_reason(wf: Workflow):
    pr = wf.create_submitted_pr()
    returned = wf.procurement_service.return_for_clarification(
        pr.id, "approver1", "Please attach vendor quote comparison"
    )
    assert returned.status.status_code == "RETURNED"
    assert returned.approved_by == "approver1"
    assert returned.approval_comment == "Please attach vendor quote comparison"


def test_return_without_reason_is_rejected(wf: Workflow):
    pr = wf.create_submitted_pr()

    with pytest.raises(ValueError, match="reason is required"):
        wf.procurement_service.return_for_clarification(pr.id, "approver1", "   ")


def test_returned_pr_cannot_be_returned_again(wf: Workflow):
    pr = wf.create_submitted_pr()
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    with pytest.raises(ValueError, match="status RETURNED"):
        wf.procurement_service.return_for_clarification(pr.id, "approver1", "Again please")


# ---------------------------------------------------------------------------
# Resubmit
# ---------------------------------------------------------------------------


def test_returned_pr_can_be_resubmitted_by_requester(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    resubmitted = wf.procurement_service.resubmit_pr(pr.id, "requester1")
    assert resubmitted.status.status_code == "PENDING_APPROVAL"
    # active return state is cleared
    assert resubmitted.approved_by is None
    assert resubmitted.approved_at is None
    assert resubmitted.approval_comment is None


def test_non_requester_cannot_resubmit(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    with pytest.raises(ValueError, match="requester"):
        wf.procurement_service.resubmit_pr(pr.id, "someone_else")


def test_approved_pr_cannot_be_resubmitted(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.approve_purchase_requisition(pr.id, "approver1", "ok")

    with pytest.raises(ValueError, match="status APPROVED"):
        wf.procurement_service.resubmit_pr(pr.id, "requester1")


def test_rejected_pr_cannot_be_resubmitted(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.reject_purchase_requisition(pr.id, "approver1", "no")

    with pytest.raises(ValueError, match="status REJECTED"):
        wf.procurement_service.resubmit_pr(pr.id, "requester1")


# ---------------------------------------------------------------------------
# Editing a RETURNED PR (header + lines), by the requester only
# ---------------------------------------------------------------------------


def test_requester_can_edit_returned_pr_header(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    update = SimpleNamespace(
        department_id=None, purchase_category_id=None, priority=None,
        required_by=None, delivery_location="Warehouse B", justification=None,
    )
    updated = wf.procurement_service.update_purchase_requisition(pr.id, update, user_id="requester1")

    assert updated.delivery_location == "Warehouse B"
    # saving a RETURNED PR must not change its status or discard the
    # approver's return reason
    assert updated.status.status_code == "RETURNED"
    assert updated.approval_comment == "Need more detail"


def test_non_requester_cannot_edit_returned_pr_header(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    update = SimpleNamespace(
        department_id=None, purchase_category_id=None, priority=None,
        required_by=None, delivery_location="Warehouse B", justification=None,
    )
    with pytest.raises(ValueError, match="requester"):
        wf.procurement_service.update_purchase_requisition(pr.id, update, user_id="someone_else")


def test_requester_can_add_edit_delete_lines_on_returned_pr(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    new_line_data = SimpleNamespace(
        item_name="Extra Chair", description=None, quantity=2, uom="EA",
        estimated_unit_price=5000, estimated_amount=10000,
    )
    line = wf.procurement_service.add_line(pr.id, new_line_data, user_id="requester1")
    assert line.item_name == "Extra Chair"

    edited_line_data = SimpleNamespace(
        item_name="Extra Chair (Ergonomic)", description=None, quantity=3, uom="EA",
        estimated_unit_price=5500, estimated_amount=16500,
    )
    updated_line = wf.procurement_service.update_line(pr.id, line.id, edited_line_data, user_id="requester1")
    assert updated_line.item_name == "Extra Chair (Ergonomic)"

    wf.procurement_service.delete_line(pr.id, line.id, user_id="requester1")
    assert wf.procurement_dao.get_line_by_id(line.id) is None

    pr_after = wf.procurement_dao.get_purchase_requisition_by_id(pr.id)
    assert pr_after.status.status_code == "RETURNED"


def test_non_requester_cannot_add_edit_delete_lines_on_returned_pr(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")
    existing_line = wf.procurement_dao.get_lines_by_pr_id(pr.id)[0]

    new_line_data = SimpleNamespace(
        item_name="Extra Chair", description=None, quantity=2, uom="EA",
        estimated_unit_price=5000, estimated_amount=10000,
    )
    with pytest.raises(ValueError, match="requester"):
        wf.procurement_service.add_line(pr.id, new_line_data, user_id="someone_else")

    with pytest.raises(ValueError, match="requester"):
        wf.procurement_service.update_line(pr.id, existing_line.id, new_line_data, user_id="someone_else")

    with pytest.raises(ValueError, match="requester"):
        wf.procurement_service.delete_line(pr.id, existing_line.id, user_id="someone_else")


def test_draft_editing_is_unaffected_by_requester_check(wf: Workflow):
    """DRAFT behavior must remain unchanged: no requester restriction."""
    payload = SimpleNamespace(
        department_id=10, purchase_category_id=20, priority="NORMAL",
        required_by=None, delivery_location=None, justification=None, lines=[],
    )
    pr = wf.procurement_service.create_purchase_requisition(payload, user_id="requester1")

    update = SimpleNamespace(
        department_id=None, purchase_category_id=None, priority=None,
        required_by=None, delivery_location="Warehouse C", justification=None,
    )
    # edited by a different user than the creator, with no user_id even
    # supplied - still allowed, exactly like before this change
    updated = wf.procurement_service.update_purchase_requisition(pr.id, update)
    assert updated.delivery_location == "Warehouse C"
    assert updated.status.status_code == "DRAFT"


def test_requester_id_type_mismatch_is_normalized(wf: Workflow):
    """Reproduces the PR-000007 bug: created_by stored as string '1', but
    the authenticated user id may arrive as a different type (e.g. int 1)
    depending on the JWT claim - the comparison must not be type-sensitive."""
    pr = wf.create_submitted_pr(requester="1")
    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Need more detail")

    resubmitted = wf.procurement_service.resubmit_pr(pr.id, 1)  # int, not str
    assert resubmitted.status.status_code == "PENDING_APPROVAL"


# ---------------------------------------------------------------------------
# History / audit trail
# ---------------------------------------------------------------------------


def test_approval_history_preserves_return_and_resubmit_sequence(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")

    wf.procurement_service.return_for_clarification(pr.id, "approver1", "Missing justification")
    wf.procurement_service.resubmit_pr(pr.id, "requester1")
    wf.procurement_service.approve_purchase_requisition(pr.id, "approver1", "Now complete")

    history = [log for log in wf.procurement_dao.audit_logs if log.record_id == pr.id]
    actions = [log.action for log in history]
    assert actions == ["RETURNED", "RESUBMITTED", "APPROVED"]

    returned_entry, resubmitted_entry, approved_entry = history
    assert returned_entry.changed_by == "approver1"
    assert returned_entry.new_values["comment"] == "Missing justification"

    # resubmission preserves the original return reason in history even
    # though the PR's own active approval_comment was cleared
    assert resubmitted_entry.changed_by == "requester1"
    assert resubmitted_entry.new_values["comment"] == "Missing justification"

    assert approved_entry.changed_by == "approver1"
    assert approved_entry.new_values["comment"] == "Now complete"


# ---------------------------------------------------------------------------
# Compatibility with the existing RFQ workflow
# ---------------------------------------------------------------------------


def test_approved_pr_remains_compatible_with_existing_rfq_creation(wf: Workflow):
    pr = wf.create_submitted_pr(requester="requester1")
    wf.procurement_service.approve_purchase_requisition(pr.id, "approver1", "ok")

    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="buyer1")
    assert rfq.pr_id == pr.id
    assert rfq.status.status_code == "DRAFT"
