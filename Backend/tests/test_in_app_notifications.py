# Backend/tests/test_in_app_notifications.py
"""Phase 1 IN-APP notification tests (action-based, user-specific).

Style follows the rest of the suite: no real DB. The procurement tests run
the REAL ProcurementService/RFQService through the existing fake-DAO
Workflow harness (test_rfq_workflow.py), with the notification store and the
UMS identity directory replaced by in-memory fakes that mirror the real
semantics (UNIQUE dedupe_key, recipient-scoped reads). SQL-level scoping of
the real NotificationDAO is checked by compiling its statements for Postgres.
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from Backend.Business_Layer.services import notification_events as events_module
from Backend.Business_Layer.services.notification_events import APNotificationEvents
from Backend.Business_Layer.services.notification_service import (
    NotificationDispatcher,
    NotificationIdentityError,
    NotificationService,
    build_dedupe_key,
)
from Backend.Business_Layer.utils import notification_types as nt
from Backend.Business_Layer.utils.email_service import EmailSendResult
from Backend.Data_Access_Layer.dao.notification_dao import NotificationDAO
from Backend.tests.test_rfq_workflow import Workflow

# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------
U_REQUESTER = uuid.UUID("00000000-0000-0000-0000-000000000101")
U_PR_APPROVER = uuid.UUID("00000000-0000-0000-0000-000000000102")
U_PO_1 = uuid.UUID("00000000-0000-0000-0000-000000000103")
U_PO_2 = uuid.UUID("00000000-0000-0000-0000-000000000104")
U_INTAKE_1 = uuid.UUID("00000000-0000-0000-0000-000000000105")
U_INTAKE_2 = uuid.UUID("00000000-0000-0000-0000-000000000106")
U_AP_EXEC = uuid.UUID("00000000-0000-0000-0000-000000000107")
U_INV_APPROVER_A = uuid.UUID("00000000-0000-0000-0000-000000000108")
U_INV_APPROVER_B = uuid.UUID("00000000-0000-0000-0000-000000000109")
U_PAYMENT = uuid.UUID("00000000-0000-0000-0000-000000000110")
U_FIN_MGR = uuid.UUID("00000000-0000-0000-0000-000000000111")
U_ADMIN = uuid.UUID("00000000-0000-0000-0000-000000000112")
U_REQUESTER_2 = uuid.UUID("00000000-0000-0000-0000-000000000113")
U_FIN_EXEC = uuid.UUID("00000000-0000-0000-0000-000000000114")

USER_IDS = {
    "buyer1": U_REQUESTER, "manager1": U_PR_APPROVER, "officer1": U_PO_1, "officer2": U_PO_2,
    "intake1": U_INTAKE_1, "intake2": U_INTAKE_2, "apexec1": U_AP_EXEC,
    "invapprA": U_INV_APPROVER_A, "invapprB": U_INV_APPROVER_B, "payer1": U_PAYMENT,
    "finmgr1": U_FIN_MGR, "admin1": U_ADMIN, "buyer2": U_REQUESTER_2, "finexec1": U_FIN_EXEC,
}
ROLES = {
    "PR_Creator": [U_REQUESTER, U_REQUESTER_2],
    "PR_Approver": [U_PR_APPROVER],
    nt.ROLE_PROCUREMENT_OFFICER: [U_PO_1, U_PO_2],
    nt.ROLE_VENDOR_INTAKE: [U_INTAKE_1, U_INTAKE_2],
    nt.ROLE_AP_EXECUTIVE: [U_AP_EXEC],
    nt.ROLE_PAYMENT_PROCESSOR: [U_PAYMENT],
    nt.ROLE_FINANCE_MANAGER: [U_FIN_MGR],
    nt.ROLE_FINANCE_EXECUTIVE: [U_FIN_EXEC],
    nt.ROLE_ADMIN: [U_ADMIN],
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDirectoryDAO:
    def get_user_uuid_by_user_id(self, user_id):
        return USER_IDS.get(str(user_id))

    def get_active_users_by_role(self, role_code):
        return list(ROLES.get(role_code, []))


class FakeNotificationDAO:
    """Mirrors NotificationDAO semantics: UNIQUE dedupe_key (ON CONFLICT DO
    NOTHING) and every read/update scoped to recipient_user_uuid."""

    def __init__(self):
        self.rows = []
        self._next_id = 1

    def insert_if_absent(self, values):
        if any(r.dedupe_key == values["dedupe_key"] for r in self.rows):
            return None
        row = SimpleNamespace(
            id=self._next_id, is_read=False, read_at=None, resolved_at=None,
            created_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(microseconds=self._next_id),
            **values,
        )
        self._next_id += 1
        self.rows.append(row)
        return row.id

    def resolve_for_entity(self, entity_type, entity_id, notification_types, recipient_user_uuid=None):
        types = set(notification_types)
        count = 0
        for r in self.rows:
            if (r.entity_type == entity_type and r.entity_id == str(entity_id)
                    and r.notification_type in types and r.resolved_at is None
                    and (recipient_user_uuid is None or r.recipient_user_uuid == recipient_user_uuid)):
                r.resolved_at = datetime.datetime.now(datetime.timezone.utc)
                count += 1
        return count

    def _mine(self, recipient):
        return [r for r in self.rows if r.recipient_user_uuid == recipient]

    def list_for_recipient(self, recipient, is_read=None, priority=None, notification_type=None, skip=0, limit=20,
                           notification_types=None):
        rows = self._mine(recipient)
        if notification_types is not None:
            rows = [r for r in rows if r.notification_type in set(notification_types)]
        if is_read is not None:
            rows = [r for r in rows if r.is_read == is_read]
        if priority is not None:
            rows = [r for r in rows if r.priority == priority]
        if notification_type is not None:
            rows = [r for r in rows if r.notification_type == notification_type]
        rows = sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)
        return rows[skip:skip + limit], len(rows)

    def count_unread(self, recipient):
        return sum(1 for r in self._mine(recipient) if not r.is_read)

    def get_for_recipient(self, notification_id, recipient):
        return next((r for r in self._mine(recipient) if r.id == notification_id), None)

    def mark_all_read(self, recipient):
        count = 0
        for r in self._mine(recipient):
            if not r.is_read:
                r.is_read, r.read_at = True, datetime.datetime.now(datetime.timezone.utc)
                count += 1
        return count

    # helpers
    def for_user(self, user_uuid, notification_type=None):
        rows = self._mine(user_uuid)
        return [r for r in rows if notification_type is None or r.notification_type == notification_type]


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.savepoints = 0

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def begin_nested(self):
        session = self

        class _SP:
            def __enter__(self):
                session.savepoints += 1

            def __exit__(self, *exc):
                return False
        return _SP()


@pytest.fixture
def store(monkeypatch):
    store = FakeNotificationDAO()
    directory = FakeDirectoryDAO()
    monkeypatch.setattr(
        events_module, "NotificationDispatcher",
        lambda db: NotificationDispatcher(db, dao=store, directory_dao=directory),
    )
    store.directory = directory
    # Onboarding requests per PR (the real lookup hits VendorOnboardingDAO).
    store.onboarding_requests = []
    monkeypatch.setattr(
        APNotificationEvents, "_onboarding_requests",
        lambda self, pr_id, vendor_ids=None: [
            r for r in store.onboarding_requests
            if r.pr_id == pr_id and (vendor_ids is None or r.vendor_id in set(vendor_ids))
        ],
    )
    # NDAs (the real lookups hit NdaDAO).
    store.ndas = []
    monkeypatch.setattr(
        APNotificationEvents, "_ndas_for_pr", lambda self, pr_id: [n for n in store.ndas if n.pr_id == pr_id]
    )
    monkeypatch.setattr(
        APNotificationEvents, "_ndas_for_vendor",
        lambda self, vendor_id: [n for n in store.ndas if n.vendor_id == vendor_id],
    )
    return store


@pytest.fixture
def wf(monkeypatch, store):
    import Backend.Business_Layer.services.rfq_service as rfq_service_module

    monkeypatch.setattr(
        rfq_service_module, "send_email",
        lambda **kwargs: EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc)),
    )
    workflow = Workflow()

    def _rfq_owner(self, pr_id):
        rfqs = [r for r in workflow.rfq_dao.rfqs.values() if r.pr_id == pr_id]
        return [max(rfqs, key=lambda r: r.id).created_by] if rfqs else None

    monkeypatch.setattr(APNotificationEvents, "_rfq_owner", _rfq_owner)
    monkeypatch.setattr(
        APNotificationEvents, "_rfqs_for_pr",
        lambda self, pr_id: [r for r in workflow.rfq_dao.rfqs.values() if r.pr_id == pr_id],
    )
    monkeypatch.setattr(
        APNotificationEvents, "_quotations_for_pr",
        lambda self, pr_id: [q for q in workflow.procurement_dao.quotations.values() if q.pr_id == pr_id],
    )
    return workflow


def _dispatcher(store, db=None):
    return NotificationDispatcher(db or FakeSession(), dao=store, directory_dao=store.directory)


def _run_rfq_to_vendor_selection(wf):
    """PR raised by buyer1, approved by manager1; officer1 owns the RFQ;
    officer2 records quotations, closes the RFQ and selects the vendor."""
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=datetime.date(2026, 12, 1), user_id="officer1")
    wf.rfq_service.invite_vendors(rfq.id, [1, 2], user_id="officer1")
    wf.rfq_service.send_rfq(rfq.id, [1, 2], user_id="officer1")
    q1 = wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="s3://q1", quotation_number="QT-1", quotation_date=None,
        valid_until=datetime.date(2026, 12, 31), total_amount=Decimal("1000"), user_id="officer2", rfq_id=rfq.id,
    )
    wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=2, file_url="s3://q2", quotation_number="QT-2", quotation_date=None,
        valid_until=None, total_amount=Decimal("1200"), user_id="officer2", rfq_id=rfq.id,
    )
    wf.rfq_service.close_rfq(rfq.id, user_id="officer2")
    wf.procurement_service.select_vendor(pr.id, q1.id, reason="cheapest", user_id="officer2")
    return pr, rfq, q1


# ---------------------------------------------------------------------------
# PR workflow: Requester / Approver
# ---------------------------------------------------------------------------


def _submitted_pr(wf, requester="buyer1", priority="NORMAL"):
    if wf.registry.get_by_module_code("PURCHASE_REQUISITION", "RETURNED") is None:
        wf.registry.add("PURCHASE_REQUISITION", "RETURNED")
    pr = wf.procurement_service.create_purchase_requisition(
        SimpleNamespace(
            department_id=10, purchase_category_id=20, priority=priority, required_by=None,
            delivery_location=None, justification=None,
            lines=[SimpleNamespace(item_name="X", description=None, quantity=Decimal("1"), uom="EA",
                                   estimated_unit_price=10, estimated_amount=10)],
        ),
        user_id=requester,
    )
    return wf.procurement_service.submit_purchase_requisition(pr.id, user_id=requester)


def test_pr_submission_notifies_the_pr_approver_only(wf, store):
    pr = _submitted_pr(wf)

    [n] = store.rows
    assert n.recipient_user_uuid == U_PR_APPROVER
    assert n.notification_type == nt.PR_APPROVAL_REQUIRED
    assert (n.entity_type, n.entity_id) == (nt.ENTITY_PURCHASE_REQUISITION, str(pr.id))
    assert nt.module_for(n.notification_type) == nt.MODULE_PROCUREMENT
    assert n.payload["action_label"] == "Review PR"
    assert "submitted for approval" in n.message
    assert n.resolved_at is None


def test_pr_approval_resolves_approval_item_and_requester_gets_nothing(wf, store):
    pr = _submitted_pr(wf)
    wf.procurement_service.approve_purchase_requisition(pr.id, "manager1", "ok")

    [approval] = store.for_user(U_PR_APPROVER)
    assert approval.resolved_at is not None
    assert store.for_user(U_REQUESTER) == []
    # sourcing work goes to the procurement role, never to PR roles
    sourcing = {n.recipient_user_uuid for n in store.rows if n.notification_type == nt.PR_APPROVED_SOURCING}
    assert sourcing == {U_PO_1, U_PO_2}


def test_pr_return_notifies_the_original_requester_only(wf, store):
    pr_a = _submitted_pr(wf, requester="buyer1")
    pr_b = _submitted_pr(wf, requester="buyer2")
    wf.procurement_service.return_for_clarification(pr_a.id, "manager1", "add a quote reference")

    [returned] = store.for_user(U_REQUESTER, nt.PR_RETURNED)
    assert returned.entity_id == str(pr_a.id)
    assert "add a quote reference" in returned.message
    assert returned.payload["action_label"] == "Update and resubmit"
    assert store.for_user(U_REQUESTER_2, nt.PR_RETURNED) == []  # the other PR's owner
    assert store.for_user(U_PR_APPROVER, nt.PR_RETURNED) == []  # the actor
    # the approval item for PR A is decided; PR B's is still open
    by_pr = {n.entity_id: n for n in store.for_user(U_PR_APPROVER, nt.PR_APPROVAL_REQUIRED)}
    assert by_pr[str(pr_a.id)].resolved_at is not None
    assert by_pr[str(pr_b.id)].resolved_at is None


def test_resubmission_resolves_return_and_raises_a_new_approval_item(wf, store):
    pr = _submitted_pr(wf)
    wf.procurement_service.return_for_clarification(pr.id, "manager1", "clarify")
    wf.procurement_service.resubmit_pr(pr.id, "buyer1")

    [returned] = store.for_user(U_REQUESTER, nt.PR_RETURNED)
    assert returned.resolved_at is not None
    approvals = store.for_user(U_PR_APPROVER, nt.PR_APPROVAL_REQUIRED)
    assert len(approvals) == 2  # first submission + resubmission are distinct events
    assert approvals[0].resolved_at is not None and approvals[1].resolved_at is None
    assert "resubmitted" in approvals[1].message


def test_replaying_the_same_submission_event_does_not_duplicate(wf, store):
    pr = _submitted_pr(wf)
    history = wf.procurement_dao.get_pr_history(pr.id)[-1]
    APNotificationEvents(FakeSession()).pr_submitted(pr, "buyer1", history)
    assert len(store.for_user(U_PR_APPROVER, nt.PR_APPROVAL_REQUIRED)) == 1


def test_pr_rejection_resolves_approval_and_notifies_nobody(wf, store):
    pr = _submitted_pr(wf)
    wf.procurement_service.reject_purchase_requisition(pr.id, "manager1", "no budget")
    assert len(store.rows) == 1 and store.rows[0].resolved_at is not None
    assert store.for_user(U_REQUESTER) == []


def test_every_pr_approver_is_notified_and_a_submitting_approver_is_excluded(wf, store, monkeypatch):
    monkeypatch.setitem(ROLES, "PR_Approver", [U_PR_APPROVER, U_REQUESTER])
    _submitted_pr(wf, requester="buyer1")
    assert {n.recipient_user_uuid for n in store.rows} == {U_PR_APPROVER}


def test_pr_submission_without_any_approver_still_succeeds(wf, store, monkeypatch):
    monkeypatch.setitem(ROLES, "PR_Approver", [])
    pr = _submitted_pr(wf)
    assert pr.status.status_code == "PENDING_APPROVAL"
    assert store.rows == []


def test_urgent_pr_submission_is_critical(wf, store):
    _submitted_pr(wf, priority="URGENT")
    assert store.rows[0].priority == nt.CRITICAL


def test_pr_roles_get_only_their_own_pr_work_across_the_full_workflow(wf, store):
    pr, _, _ = _run_rfq_to_vendor_selection(wf)
    wf.procurement_service.generate_purchase_order(pr.id, user_id="officer1")

    assert store.for_user(U_REQUESTER) == []
    assert [n.notification_type for n in store.for_user(U_PR_APPROVER)] == [nt.PR_APPROVAL_REQUIRED]
    assert all(n.resolved_at is not None for n in store.for_user(U_PR_APPROVER))


def test_cancelling_a_pr_resolves_every_open_procurement_item_for_it(wf, store):
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="officer1")
    wf.rfq_service.invite_vendors(rfq.id, [1], user_id="officer1")
    wf.rfq_service.send_rfq(rfq.id, [1], user_id="officer1")
    wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="s3://q", quotation_number="QT-C", quotation_date=None,
        valid_until=None, total_amount=1, user_id="officer2", rfq_id=rfq.id,
    )
    wf.rfq_service.close_rfq(rfq.id, user_id="officer2")
    store.ndas.append(SimpleNamespace(nda_id=9, vendor_id=1, pr_id=pr.id, created_by="officer1"))
    _dispatcher(store).notify(
        nt.NDA_EXPIRED_RFQ_BLOCKED, entity_type=nt.ENTITY_VENDOR_NDA, entity_id=9, entity_display_id="NDA-9",
        message="m", event_id="expired", owners=["officer1"],
    )
    open_types = {n.notification_type for n in store.for_user(U_PO_1) if n.resolved_at is None}
    assert open_types >= {nt.QUOTATION_RECEIVED, nt.VENDOR_SELECTION_REQUIRED, nt.NDA_EXPIRED_RFQ_BLOCKED}

    wf.procurement_service.cancel_purchase_requisition(pr.id)
    assert [n for n in store.for_user(U_PO_1) if n.resolved_at is None] == []


def test_deleting_a_quotation_resolves_its_review_item(wf, store):
    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="officer1")
    wf.rfq_service.invite_vendors(rfq.id, [1], user_id="officer1")
    wf.rfq_service.send_rfq(rfq.id, [1], user_id="officer1")
    quotation = wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="s3://q", quotation_number="QT-D", quotation_date=None,
        valid_until=None, total_amount=1, user_id="officer2", rfq_id=rfq.id,
    )
    wf.procurement_service.delete_quotation(quotation.id)
    [n] = store.for_user(U_PO_1, nt.QUOTATION_RECEIVED)
    assert n.resolved_at is not None


def test_closing_the_rfq_resolves_its_email_failure_item(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    rfq = SimpleNamespace(id=4, rfq_number="RFQ-4", pr_id=1, created_by="officer1", due_date=None)
    ev.rfq_send_failures(rfq, None, 1, 2, False, "officer2")
    ev.rfq_closed(rfq, lambda: [], "officer2")
    [n] = store.for_user(U_PO_1, nt.RFQ_VENDOR_EMAIL_FAILURE)
    assert n.resolved_at is not None


# ---------------------------------------------------------------------------
# PO Officer
# ---------------------------------------------------------------------------


def test_po_officer_receives_approved_pr_sourcing_notification(wf, store):
    pr = wf.create_approved_pr()

    for officer in (U_PO_1, U_PO_2):
        [n] = store.for_user(officer, nt.PR_APPROVED_SOURCING)
        assert n.entity_type == nt.ENTITY_PURCHASE_REQUISITION
        assert n.entity_id == str(pr.id)
        assert n.priority == nt.HIGH
        assert n.title == f"{pr.pr_number} — Procurement action required"
        assert "approved and is ready for sourcing" in n.message
        assert n.payload["action_label"] == "Start RFQ"
        assert n.payload["entity_display_id"] == pr.pr_number
        assert n.payload["deep_link"] == f"/procurement/purchase-requisitions/{pr.id}"
    # the sourcing broadcast is limited to the Procurement_Officer role
    sourcing = {n.recipient_user_uuid for n in store.rows if n.notification_type == nt.PR_APPROVED_SOURCING}
    assert sourcing == {U_PO_1, U_PO_2}


def test_starting_rfq_resolves_sourcing_notification(wf, store):
    pr = wf.create_approved_pr()
    wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="officer1")
    assert all(n.resolved_at is not None for n in store.for_user(U_PO_2, nt.PR_APPROVED_SOURCING))


def test_po_officer_receives_quotation_notification_as_rfq_owner_only(wf, store):
    pr, rfq, q1 = _run_rfq_to_vendor_selection(wf)

    received = store.for_user(U_PO_1, nt.QUOTATION_RECEIVED)
    assert {n.entity_id for n in received} == {str(q1.id), str(q1.id + 1)}
    assert received[0].payload["metadata"]["rfq_id"] == rfq.id
    # concrete owner exists (rfq.created_by) -> no role broadcast, and the
    # actor who recorded the quotations is excluded
    assert store.for_user(U_PO_2, nt.QUOTATION_RECEIVED) == []


def test_po_officer_receives_vendor_selection_notification(wf, store):
    _, rfq, _ = _run_rfq_to_vendor_selection(wf)
    [n] = store.for_user(U_PO_1, nt.VENDOR_SELECTION_REQUIRED)
    assert n.entity_type == nt.ENTITY_RFQ and n.entity_id == str(rfq.id)
    assert "2 quotation(s) received" in n.message
    assert n.payload["action_label"] == "Select vendor"


def test_po_officer_receives_po_generation_notification(wf, store):
    pr, _, q1 = _run_rfq_to_vendor_selection(wf)
    [n] = store.for_user(U_PO_1, nt.PO_GENERATION_REQUIRED)
    assert n.entity_id == str(pr.id)
    assert n.payload["action_label"] == "Generate PO"
    assert n.payload["metadata"]["quotation_id"] == q1.id


def test_rfq_partial_email_failure_notifies_rfq_owner(wf, store, monkeypatch):
    import Backend.Business_Layer.services.rfq_service as rfq_service_module

    pr = wf.create_approved_pr()
    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="officer1")
    wf.rfq_service.invite_vendors(rfq.id, [1, 2], user_id="officer1")
    monkeypatch.setattr(
        rfq_service_module, "send_email",
        lambda to_address, **kw: EmailSendResult(
            success=to_address == "vendor1@example.com",
            sent_at=datetime.datetime.now(datetime.timezone.utc), error=None if to_address == "vendor1@example.com" else "bounce",
        ),
    )
    wf.rfq_service.send_rfq(rfq.id, [1, 2], user_id="officer2")

    [n] = store.for_user(U_PO_1, nt.RFQ_VENDOR_EMAIL_FAILURE)
    assert "failed for 1 of 2" in n.message


# ---------------------------------------------------------------------------
# Actor exclusion
# ---------------------------------------------------------------------------


def test_actor_does_not_receive_notification_for_own_action(wf, store):
    pr, _, _ = _run_rfq_to_vendor_selection(wf)

    # officer2 performed quotation capture / close / selection -> none of
    # those notifications went to officer2
    for code in (nt.QUOTATION_RECEIVED, nt.VENDOR_SELECTION_REQUIRED, nt.PO_GENERATION_REQUIRED):
        assert store.for_user(U_PO_2, code) == []

    # the concrete owner being the actor never falls back to the role
    store.rows.clear()
    pr2 = wf.create_approved_pr()
    rfq2 = wf.rfq_service.create_rfq(pr2.id, due_date=None, user_id="officer1")
    wf.rfq_service.invite_vendors(rfq2.id, [1], user_id="officer1")
    wf.rfq_service.send_rfq(rfq2.id, [1], user_id="officer1")
    wf.procurement_service.create_quotation(
        pr_id=pr2.id, vendor_id=1, file_url="s3://q", quotation_number="QT-9", quotation_date=None,
        valid_until=None, total_amount=1, user_id="officer1", rfq_id=rfq2.id,
    )
    assert [n for n in store.rows if n.notification_type == nt.QUOTATION_RECEIVED] == []


def test_actor_holding_the_target_role_is_excluded_from_role_broadcast(store):
    pr = SimpleNamespace(id=5, pr_number="PR-000005", priority="NORMAL", required_by=None)
    APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store)).pr_approved(pr, "officer1")
    assert {n.recipient_user_uuid for n in store.rows} == {U_PO_2}


# ---------------------------------------------------------------------------
# Vendor Intake
# ---------------------------------------------------------------------------


def _onboarding_request(**overrides):
    values = dict(id=7, pr_id=3, requested_vendor_name="Acme", assigned_to=None, created_by="officer1")
    values.update(overrides)
    return SimpleNamespace(**values)


def test_vendor_intaker_receives_onboarding_assignment(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    request = _onboarding_request()
    ev.onboarding_created(request, "officer1")
    assert {n.recipient_user_uuid for n in store.rows} == {U_INTAKE_1, U_INTAKE_2}
    assert all(n.notification_type == nt.VENDOR_ONBOARDING_REQUESTED for n in store.rows)

    request.assigned_to = "intake2"
    ev.onboarding_assigned(request, "officer1")

    [assigned] = store.for_user(U_INTAKE_2, nt.VENDOR_ONBOARDING_ASSIGNED)
    assert assigned.payload["action_label"] == "Process onboarding request"
    assert store.for_user(U_INTAKE_1, nt.VENDOR_ONBOARDING_ASSIGNED) == []
    # the unassigned-request broadcast is no longer actionable once picked up
    assert all(n.resolved_at is not None for n in store.rows if n.notification_type == nt.VENDOR_ONBOARDING_REQUESTED)


def test_real_onboarding_service_assign_emits_assignment(store, monkeypatch):
    from Backend.Business_Layer.services.vendor_onboarding_service import VendorOnboardingService

    service = VendorOnboardingService(FakeSession())
    request = _onboarding_request(status=SimpleNamespace(status_code="ASSIGNED"), status_id=1)
    service.onboarding_dao = SimpleNamespace(
        get_request_by_id=lambda request_id: request,
        create_audit_log=lambda log: log,
    )
    service.assign(7, "intake1", "officer1")
    [n] = store.rows
    assert (n.recipient_user_uuid, n.notification_type) == (U_INTAKE_1, nt.VENDOR_ONBOARDING_ASSIGNED)


def test_onboarding_completion_notifies_requesting_po_officer_and_resolves_intake_items(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    request = _onboarding_request(assigned_to="intake1")
    ev.onboarding_status_changed(request, "NEED_INFORMATION", "officer1", "missing PAN")
    [info] = store.for_user(U_INTAKE_1, nt.VENDOR_INFORMATION_REQUIRED)
    assert "missing PAN" in info.message

    ev.onboarding_status_changed(request, "COMPLETED", "intake1")
    [done] = store.for_user(U_PO_1, nt.VENDOR_ONBOARDING_COMPLETED)
    assert done.priority == nt.MEDIUM
    assert info.resolved_at is not None
    assert store.for_user(U_INTAKE_1, nt.VENDOR_ONBOARDING_COMPLETED) == []  # actor


# ---------------------------------------------------------------------------
# Invoice approver / AP Executive / Finance
# ---------------------------------------------------------------------------


def _invoice(**overrides):
    values = dict(invoice_id=42, invoice_number="INV-42", net_amount=Decimal("5000"), vendor_id=9,
                  due_date=datetime.date(2099, 1, 1), created_by="apexec1",
                  department_id=1, purchase_category_id=2)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_invoice_approver_receives_only_their_assigned_approval(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    step = SimpleNamespace(id=11, level_number=1, approval_rule="ANY_ONE")
    ev.approval_step_pending(_invoice(), step, [U_INV_APPROVER_A], "apexec1")

    [n] = store.rows
    assert n.recipient_user_uuid == U_INV_APPROVER_A
    assert n.notification_type == nt.INVOICE_APPROVAL_REQUIRED
    assert n.entity_type == nt.ENTITY_INVOICE_APPROVAL_STEP and n.entity_id == "11"
    assert n.payload["deep_link"] == "/invoices/42"
    assert store.for_user(U_INV_APPROVER_B) == []


def test_invoice_approval_with_no_resolvable_approver_never_broadcasts(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.approval_step_pending(_invoice(), SimpleNamespace(id=12, level_number=1, approval_rule="ALL"), [], "apexec1")
    assert store.rows == []


def test_real_invoice_approval_service_notifies_first_step_approver(store, monkeypatch):
    from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService

    invoice = _invoice(status=SimpleNamespace(status_code="OCR_REVIEWED"), status_id=1, updated_by=None)
    created = {}

    class _ApprovalDAO:
        def get_active_invoice_approval_for_invoice(self, invoice_id):
            return None

        def create_invoice_approval(self, instance):
            instance.invoice_approval_id = 1
            created["instance"] = instance

        def create_step(self, step):
            step.id = 100 + step.level_number

        def create_step_approver(self, approver):
            pass

        def create_audit_log(self, log):
            return log

        def get_invoice_approval_by_id(self, invoice_approval_id):
            return created["instance"]

    service = InvoiceApprovalService(FakeSession())
    session = service.db
    session.flush = lambda: None
    service.invoice_dao = SimpleNamespace(
        get_invoice_by_id_locked=lambda invoice_id: invoice,
        get_status_by_code=lambda code: SimpleNamespace(status_id=8),
    )
    service.approval_dao = _ApprovalDAO()
    service.policy_service = SimpleNamespace(match_policy=lambda *a: SimpleNamespace(id=1, name="P"))
    service.policy_dao = SimpleNamespace(get_levels_for_policy=lambda policy_id: [
        SimpleNamespace(level_number=1, is_active=True, approver_type="USER", approval_rule="ANY_ONE",
                        role_code=None, user_uuid=U_INV_APPROVER_A),
        SimpleNamespace(level_number=2, is_active=True, approver_type="USER", approval_rule="ANY_ONE",
                        role_code=None, user_uuid=U_INV_APPROVER_B),
    ])
    service.resolver = SimpleNamespace(resolve=lambda approver_type, **kw: [kw["user_uuid"]])

    service.send_for_approval(42, "apexec1")

    [n] = store.rows
    assert n.recipient_user_uuid == U_INV_APPROVER_A  # level 2 approver not yet notified
    assert n.entity_id == "101"


def test_invoice_returned_notifies_the_ap_executive_owner(store, monkeypatch):
    monkeypatch.setattr(APNotificationEvents, "_approval_sender", lambda self, invoice: "apexec1")
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.invoice_returned(_invoice(), "wrong GSTIN", "invapprA")
    [n] = store.rows
    assert (n.recipient_user_uuid, n.notification_type) == (U_AP_EXEC, nt.INVOICE_RETURNED)
    assert "wrong GSTIN" in n.message


def test_payment_user_receives_payment_ready_notification(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.invoice_approved(_invoice(), "invapprA")
    [n] = store.rows
    assert (n.recipient_user_uuid, n.notification_type) == (U_PAYMENT, nt.PAYMENT_READY)
    assert n.priority == nt.HIGH
    assert n.payload["action_label"] == "Process payment"


def test_overdue_approved_invoice_is_critical(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.invoice_approved(_invoice(due_date=datetime.date(2000, 1, 1)), "invapprA")
    assert store.rows[0].priority == nt.CRITICAL


def _with_tds(monkeypatch, status, applicable=True):
    tds = None if status is None else SimpleNamespace(determination_status=status, tds_applicable=applicable)
    monkeypatch.setattr(APNotificationEvents, "_invoice_tds", lambda self, invoice_id: tds)


@pytest.mark.parametrize("applicable", [True, False])
def test_approved_invoice_with_unverified_tds_notifies_finance_executive(store, monkeypatch, applicable):
    _with_tds(monkeypatch, "DETERMINED", applicable)
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.tds_verification_required(_invoice(), "invapprA")
    [n] = store.rows
    assert (n.recipient_user_uuid, n.notification_type) == (U_FIN_EXEC, nt.INVOICE_TDS_VERIFICATION_REQUIRED)
    assert (n.entity_type, n.entity_id, n.priority) == (nt.ENTITY_INVOICE, "42", nt.MEDIUM)
    assert n.title == "INV-42 — TDS verification required"
    assert n.message == "Invoice INV-42 has been approved. Verify TDS to make it ready for payment."
    assert n.payload["action_label"] == "Verify TDS"
    assert nt.module_for(n.notification_type) == nt.MODULE_PAYMENTS


@pytest.mark.parametrize("status", ["VERIFIED", None])
def test_no_tds_verification_notification_when_already_verified_or_missing(store, monkeypatch, status):
    _with_tds(monkeypatch, status)
    APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store)).tds_verification_required(_invoice(), "invapprA")
    assert store.rows == []


def test_finance_executive_approving_is_not_notified_about_their_own_approval(store, monkeypatch):
    _with_tds(monkeypatch, "DETERMINED")
    APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store)).tds_verification_required(_invoice(), "finexec1")
    assert store.rows == []


def test_real_tds_verify_resolves_the_verification_notification(store, monkeypatch):
    from Backend.Business_Layer.services.tds_determination_service import TDSDeterminationService

    _with_tds(monkeypatch, "DETERMINED")
    APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store)).tds_verification_required(_invoice(), "invapprA")
    row = SimpleNamespace(determination_status="DETERMINED", payment_nature_id=1, tds_rule_id=None,
                          tds_rate_rule_id=None, tds_applicable=False, tds_rate=None, tds_amount=None, remarks=None)
    service = TDSDeterminationService(FakeSession())
    service.tds_dao = SimpleNamespace(get_invoice_tds_by_invoice_id_locked=lambda invoice_id: row)
    service.invoice_dao = SimpleNamespace(create_audit_log=lambda log: log)

    service.verify(42, "finexec1")

    [n] = store.rows
    assert row.determination_status == "VERIFIED" and n.resolved_at is not None


def test_payment_failure_notifies_creator_and_escalates_to_finance_manager(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    payment = SimpleNamespace(payment_id=3, vendor_id=9, total_amount=Decimal("100"), created_by="payer1",
                              payment_invoice=[SimpleNamespace(invoice_id=42)])
    ev.payment_failed(payment, "finmgr1")
    [failed] = store.for_user(U_PAYMENT, nt.PAYMENT_FAILED)
    assert failed.priority == nt.CRITICAL
    # finmgr1 is the actor -> excluded from the escalation
    assert store.for_user(U_FIN_MGR) == []

    store.rows.clear()
    ev.payment_failed(payment, "payer1")
    assert store.for_user(U_PAYMENT) == []  # actor
    [escalation] = store.for_user(U_FIN_MGR, nt.FINANCE_ESCALATION)
    assert escalation.priority == nt.CRITICAL


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_duplicate_event_does_not_create_duplicate_notification(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    pr = SimpleNamespace(id=5, pr_number="PR-000005", priority="NORMAL", required_by=None)
    ev.pr_approved(pr, "manager1")
    ev.pr_approved(pr, "manager1")
    assert len(store.for_user(U_PO_1, nt.PR_APPROVED_SOURCING)) == 1
    assert len(store.rows) == 2  # one per officer, not four


def test_dedupe_key_contains_recipient_type_entity_and_event():
    key = build_dedupe_key(U_PO_1, nt.PR_APPROVED_SOURCING, nt.ENTITY_PURCHASE_REQUISITION, 71, "approved")
    assert key == f"{U_PO_1}:PR_APPROVED_SOURCING:PURCHASE_REQUISITION:71:approved"
    assert nt.threshold_bucket("due-in-days", 3) == "due-in-days:3"


def test_real_dao_insert_is_on_conflict_do_nothing():
    captured = {}

    class _Db:
        def execute(self, stmt):
            captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    NotificationDAO(_Db()).insert_if_absent({
        "recipient_user_uuid": U_PO_1, "notification_type": "X", "title": "t", "message": "m",
        "priority": "LOW", "entity_type": "E", "entity_id": "1", "dedupe_key": "k", "payload": None,
    })
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in captured["sql"]


# ---------------------------------------------------------------------------
# Lifecycle: completed work stops being actionable
# ---------------------------------------------------------------------------


def test_completed_workflow_resolves_pending_action_notifications(wf, store):
    pr, rfq, _ = _run_rfq_to_vendor_selection(wf)
    [selection] = store.for_user(U_PO_1, nt.VENDOR_SELECTION_REQUIRED)
    quotation_notes = store.for_user(U_PO_1, nt.QUOTATION_RECEIVED)
    [po_needed] = store.for_user(U_PO_1, nt.PO_GENERATION_REQUIRED)

    # vendor selected -> selection + quotation-review items resolved
    assert selection.resolved_at is not None
    assert all(n.resolved_at is not None for n in quotation_notes)
    assert po_needed.resolved_at is None

    wf.procurement_service.generate_purchase_order(pr.id, user_id="officer1")
    assert po_needed.resolved_at is not None

    # replaying the completed transition creates nothing new
    before = len(store.rows)
    APNotificationEvents(FakeSession()).vendor_selected(
        wf.procurement_dao.get_purchase_requisition_by_id(pr.id),
        wf.procurement_dao.get_quotation_by_id(pr.selected_quotation_id), [], "officer2",
    )
    assert len(store.rows) == before


def test_invoice_approval_notifications_resolve_when_step_decided(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    step = SimpleNamespace(id=11, level_number=1, approval_rule="ALL")
    ev.approval_step_pending(_invoice(), step, [U_INV_APPROVER_A, U_INV_APPROVER_B], "apexec1")

    ev.approval_decided(step, U_INV_APPROVER_A, step_closed=False)
    a, b = store.for_user(U_INV_APPROVER_A)[0], store.for_user(U_INV_APPROVER_B)[0]
    assert a.resolved_at is not None and b.resolved_at is None

    ev.approval_decided(step, U_INV_APPROVER_B, step_closed=True)
    assert b.resolved_at is not None


# ---------------------------------------------------------------------------
# Failure isolation / transaction semantics
# ---------------------------------------------------------------------------


def test_notification_failure_never_breaks_business_action(wf, monkeypatch):
    class _Boom:
        def insert_if_absent(self, values):
            raise RuntimeError("db down")

    monkeypatch.setattr(
        events_module, "NotificationDispatcher",
        lambda db: NotificationDispatcher(db, dao=_Boom(), directory_dao=FakeDirectoryDAO()),
    )
    pr = wf.create_approved_pr()  # would raise if notification errors propagated
    assert pr.status.status_code == "APPROVED"


def test_notification_is_written_inside_a_savepoint_of_the_callers_transaction(store):
    session = FakeSession()
    _dispatcher(store, db=session).notify(
        nt.PR_APPROVED_SOURCING, entity_type=nt.ENTITY_PURCHASE_REQUISITION, entity_id=1,
        entity_display_id="PR-1", message="m", event_id="approved", actor_user_id="manager1",
    )
    assert session.savepoints == 1
    assert session.commits == 0  # the business service owns the commit


def test_emission_happens_before_the_service_commit(wf, store):
    commits_seen = []
    wf.procurement_service.db.commit = lambda: commits_seen.append(len(store.rows))
    wf.create_approved_pr()
    # at the approval commit both officers' sourcing items are already staged
    # (alongside the approver's earlier submission item)
    assert commits_seen[-1] == 3
    assert sum(1 for n in store.rows if n.notification_type == nt.PR_APPROVED_SOURCING) == 2


# ---------------------------------------------------------------------------
# Notification Center service: read / mark read / unread count / isolation
# ---------------------------------------------------------------------------


def _center(store):
    return NotificationService(FakeSession(), dao=store, directory_dao=store.directory)


def _seed(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    for pr_id in (1, 2, 3):
        ev.pr_approved(SimpleNamespace(id=pr_id, pr_number=f"PR-{pr_id}", priority="NORMAL", required_by=None), "manager1")


def test_unread_count_mark_read_and_mark_all_read(store):
    _seed(store)
    center = _center(store)
    assert center.unread_count("officer1") == 3

    rows, total, unread = center.list_notifications("officer1")
    assert total == 3 and unread == 3
    assert [r.entity_id for r in rows] == ["3", "2", "1"]  # newest first

    read = center.mark_read("officer1", rows[0].id)
    assert read.is_read is True and read.read_at is not None
    assert center.unread_count("officer1") == 2
    center.mark_read("officer1", rows[0].id)  # idempotent
    assert center.unread_count("officer1") == 2

    unread_rows, unread_total, _ = center.list_notifications("officer1", is_read=False)
    assert unread_total == 2 and all(not r.is_read for r in unread_rows)

    assert center.mark_all_read("officer1") == 2
    assert center.unread_count("officer1") == 0
    # officer2's copies are untouched
    assert center.unread_count("officer2") == 3


def test_list_filters_and_pagination(store):
    _seed(store)
    center = _center(store)
    rows, total, _ = center.list_notifications("officer1", page=2, page_size=2)
    assert total == 3 and len(rows) == 1
    assert center.list_notifications("officer1", priority="critical")[1] == 0
    assert center.list_notifications("officer1", notification_type="pr_approved_sourcing")[1] == 3
    with pytest.raises(ValueError):
        center.list_notifications("officer1", priority="URGENT")
    with pytest.raises(ValueError):
        center.list_notifications("officer1", page_size=1000)


def test_user_cannot_access_another_users_notification(store):
    _seed(store)
    center = _center(store)
    officer2_id = store.for_user(U_PO_2)[0].id

    with pytest.raises(ValueError, match="Notification not found"):
        center.mark_read("officer1", officer2_id)
    assert store.for_user(U_PO_2)[0].is_read is False
    assert all(r.recipient_user_uuid == U_PO_1 for r in center.list_notifications("officer1")[0])


def test_unresolvable_identity_is_rejected(store):
    with pytest.raises(NotificationIdentityError):
        _center(store).unread_count("ghost")


def test_real_dao_queries_are_scoped_to_the_recipient():
    dao = NotificationDAO(Session())
    sql = str(dao._recipient_query(U_PO_1, is_read=False).statement.compile(dialect=postgresql.dialect()))
    assert "ap.notification.recipient_user_uuid = %(recipient_user_uuid_1)s" in sql

    captured = []
    dao = NotificationDAO(SimpleNamespace(execute=lambda stmt: captured.append(stmt) or SimpleNamespace(rowcount=0)))
    dao.mark_all_read(U_PO_1)
    assert "recipient_user_uuid" in str(captured[0].compile(dialect=postgresql.dialect()))


# ---------------------------------------------------------------------------
# API: recipient always derived from the JWT
# ---------------------------------------------------------------------------


@pytest.fixture
def client(store, monkeypatch):
    from Backend.API_Layer.routes import notification_route

    monkeypatch.setattr(
        notification_route, "NotificationService",
        lambda db: NotificationService(db, dao=store, directory_dao=store.directory),
    )
    app = FastAPI()
    current = {"user": {"user_id": "officer1"}}

    @app.middleware("http")
    async def _auth(request, call_next):
        request.state.user = current["user"]
        request.state.db = FakeSession()
        return await call_next(request)

    app.include_router(notification_route.router, prefix="/apm/notifications")
    test_client = TestClient(app)
    test_client.current = current
    return test_client


def test_api_lists_only_the_authenticated_users_notifications(client, store):
    _seed(store)
    response = client.get(
        "/apm/notifications", params={"recipient_user_uuid": str(U_PO_2), "page_size": 10}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3 and body["unread_count"] == 3
    item = body["items"][0]
    for field in ("id", "title", "message", "priority", "notification_type", "entity_type", "entity_id",
                  "entity_display_id", "is_read", "created_at", "read_at", "action_label", "deep_link", "payload"):
        assert field in item
    ids = {n.id for n in store.for_user(U_PO_1)}
    assert {i["id"] for i in body["items"]} == ids  # recipient_user_uuid query param ignored


def test_api_mark_read_other_users_notification_is_404(client, store):
    _seed(store)
    other = store.for_user(U_PO_2)[0]
    assert client.patch(f"/apm/notifications/{other.id}/read").status_code == 404
    assert other.is_read is False

    mine = store.for_user(U_PO_1)[0]
    response = client.patch(f"/apm/notifications/{mine.id}/read")
    assert response.status_code == 200 and response.json()["is_read"] is True


def test_api_unread_count_and_read_all(client, store):
    _seed(store)
    assert client.get("/apm/notifications/unread-count").json() == {"unread_count": 3}
    assert client.patch("/apm/notifications/read-all").json()["updated"] == 3
    assert client.get("/apm/notifications/unread-count").json() == {"unread_count": 0}
    assert store.directory.get_user_uuid_by_user_id("officer2") == U_PO_2
    client.current["user"] = {"user_id": "officer2"}
    assert client.get("/apm/notifications/unread-count").json() == {"unread_count": 3}


def test_api_unknown_identity_is_403(client):
    client.current["user"] = {"user_id": "ghost"}
    assert client.get("/apm/notifications").status_code == 403


# ===========================================================================
# Unified cross-module stream: one user, one stream, every AP module
# ===========================================================================


def test_every_notification_type_maps_to_exactly_one_known_module():
    assert set(nt.MODULES) == {
        "PROCUREMENT", "VENDOR_MANAGEMENT", "INVOICE_MANAGEMENT", "PAYMENTS", "SYSTEM_CONFIGURATION",
    }
    for code, definition in nt.CATALOG.items():
        assert definition.module in nt.MODULES, code
        assert nt.module_for(code) == definition.module
    assert nt.module_for("NOT_A_TYPE") is None
    # entity_type alone is ambiguous (INVOICE carries three modules) - the
    # module is derived from notification_type instead.
    assert nt.module_for(nt.INVOICE_REVIEW_REQUIRED) == nt.MODULE_INVOICE_MANAGEMENT
    assert nt.module_for(nt.PAYMENT_READY) == nt.MODULE_PAYMENTS
    assert nt.module_for(nt.WORKFLOW_CONFIGURATION_BLOCKED) == nt.MODULE_SYSTEM_CONFIGURATION
    assert nt.module_for(nt.VENDOR_ONBOARDING_COMPLETED) == nt.MODULE_VENDOR_MANAGEMENT
    assert nt.module_for(nt.NDA_REQUIRED) == nt.MODULE_PROCUREMENT


def _po_officer_cross_module_stream(store):
    """officer1: a Procurement action (PR approved) and a Vendor Management
    outcome for their own onboarding request (onboarding completed)."""
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.pr_approved(SimpleNamespace(id=71, pr_number="PR-000071", priority="NORMAL", required_by=None), "manager1")
    ev.onboarding_status_changed(_onboarding_request(id=24, pr_id=71, assigned_to="intake1"), "COMPLETED", "intake1")
    return ev


def test_one_user_receives_notifications_from_multiple_modules_in_one_stream(store):
    ev = _po_officer_cross_module_stream(store)
    # the same user also holds an invoice approval step
    ev.approval_step_pending(_invoice(), SimpleNamespace(id=11, level_number=1, approval_rule="ANY_ONE"),
                             [U_PO_1], "apexec1")

    rows, total, unread = _center(store).list_notifications("officer1")
    assert total == 3 and unread == 3
    assert {nt.module_for(r.notification_type) for r in rows} == {
        nt.MODULE_PROCUREMENT, nt.MODULE_VENDOR_MANAGEMENT, nt.MODULE_INVOICE_MANAGEMENT,
    }


def test_module_filter_is_a_view_over_the_same_stream(store):
    _po_officer_cross_module_stream(store)
    center = _center(store)
    rows, total, unread = center.list_notifications("officer1", module="vendor_management")
    assert total == 1 and rows[0].notification_type == nt.VENDOR_ONBOARDING_COMPLETED
    assert unread == 2  # unread badge always covers the whole stream
    assert center.list_notifications("officer1", module="PROCUREMENT")[1] == 1
    with pytest.raises(ValueError):
        center.list_notifications("officer1", module="DASHBOARD")


def test_api_exposes_module_on_every_notification(client, store):
    _po_officer_cross_module_stream(store)
    body = client.get("/apm/notifications").json()
    assert {(i["notification_type"], i["module"]) for i in body["items"]} == {
        (nt.PR_APPROVED_SOURCING, "PROCUREMENT"),
        (nt.VENDOR_ONBOARDING_COMPLETED, "VENDOR_MANAGEMENT"),
    }
    assert client.get("/apm/notifications", params={"module": "PROCUREMENT"}).json()["total"] == 1
    assert client.get("/apm/notifications", params={"module": "NOPE"}).status_code == 422


def test_real_dao_module_filter_is_recipient_scoped_in_clause():
    dao = NotificationDAO(Session())
    sql = str(dao._recipient_query(U_PO_1, notification_types=nt.types_for_module(nt.MODULE_PAYMENTS))
              .statement.compile(dialect=postgresql.dialect()))
    assert "recipient_user_uuid = " in sql
    assert "notification_type IN" in sql


# ---------------------------------------------------------------------------
# PO Officer vs Vendor Intaker responsibility
# ---------------------------------------------------------------------------


def test_vendor_intaker_only_work_never_reaches_po_officers(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    request = _onboarding_request()  # raised by officer1, unassigned
    ev.onboarding_created(request, "officer1")
    request.assigned_to = "intake1"
    ev.onboarding_assigned(request, "intake2")
    ev.onboarding_status_changed(request, "NEED_INFORMATION", "intake2", "missing PAN")
    ev.onboarding_status_changed(request, "PRE_SCREEN_PENDING", "intake2")

    assert store.rows
    assert store.for_user(U_PO_1) == [] and store.for_user(U_PO_2) == []
    assert {nt.module_for(r.notification_type) for r in store.rows} == {nt.MODULE_VENDOR_MANAGEMENT}


def test_po_officer_receives_only_procurement_relevant_vendor_management_outcomes(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.onboarding_status_changed(_onboarding_request(assigned_to="intake1"), "FAILED", "intake1", "sanctioned")
    [failed] = store.for_user(U_PO_1)
    assert failed.notification_type == nt.VENDOR_ONBOARDING_FAILED
    assert nt.module_for(failed.notification_type) == nt.MODULE_VENDOR_MANAGEMENT
    # concrete owner (the requesting PO officer) overrides the role fallback
    assert store.for_user(U_PO_2) == []


def test_onboarding_completed_by_someone_else_does_not_notify_the_intaker(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.onboarding_status_changed(_onboarding_request(assigned_to="intake1"), "COMPLETED", "admin1")
    assert store.for_user(U_INTAKE_1) == []  # "no further action" is not actionable
    assert [n.notification_type for n in store.for_user(U_PO_1)] == [nt.VENDOR_ONBOARDING_COMPLETED]


def test_concrete_owner_overrides_role_and_role_is_fallback_only(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.onboarding_status_changed(_onboarding_request(created_by="officer2"), "COMPLETED", "intake1")
    assert {n.recipient_user_uuid for n in store.rows} == {U_PO_2}

    store.rows.clear()
    ev.onboarding_status_changed(_onboarding_request(id=8, created_by="unknown-user"), "COMPLETED", "intake1")
    assert {n.recipient_user_uuid for n in store.rows} == {U_PO_1, U_PO_2}  # existing role fallback


# ---------------------------------------------------------------------------
# Resolution across modules
# ---------------------------------------------------------------------------


def test_inviting_the_onboarded_vendor_resolves_continue_rfq(wf, store):
    pr = wf.create_approved_pr()
    request = _onboarding_request(id=24, pr_id=pr.id, vendor_id=1, created_by="officer1")
    store.onboarding_requests.append(request)
    APNotificationEvents(FakeSession()).onboarding_status_changed(request, "COMPLETED", "intake1")
    [done] = store.for_user(U_PO_1, nt.VENDOR_ONBOARDING_COMPLETED)

    rfq = wf.rfq_service.create_rfq(pr.id, due_date=None, user_id="officer1")
    wf.rfq_service.invite_vendors(rfq.id, [2], user_id="officer1")
    assert done.resolved_at is None  # a different vendor
    wf.rfq_service.invite_vendors(rfq.id, [1], user_id="officer1")
    assert done.resolved_at is not None


def test_failed_onboarding_resolves_on_new_request_or_pr_closure(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    first = _onboarding_request(id=1, assigned_to="intake1")
    store.onboarding_requests.append(first)
    ev.onboarding_status_changed(first, "FAILED", "intake1", "bad bank details")
    [failed] = store.for_user(U_PO_1, nt.VENDOR_ONBOARDING_FAILED)

    retry = _onboarding_request(id=2, assigned_to="intake1")
    store.onboarding_requests.append(retry)
    ev.onboarding_created(retry, "officer1")
    assert failed.resolved_at is not None

    ev.onboarding_status_changed(retry, "FAILED", "intake1", "again")
    [failed_again] = [n for n in store.for_user(U_PO_1, nt.VENDOR_ONBOARDING_FAILED) if n.entity_id == "2"]
    ev.pr_closed(SimpleNamespace(id=first.pr_id))
    assert failed_again.resolved_at is not None


def test_successful_resend_resolves_procurement_blocked(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    rfq = SimpleNamespace(id=5, rfq_number="RFQ-000005", pr_id=3, created_by="officer1", due_date=None)
    ev.rfq_send_failures(rfq, None, 2, 2, True, "officer2")
    [blocked] = store.for_user(U_PO_1, nt.PROCUREMENT_BLOCKED)
    ev.rfq_send_failures(rfq, None, 0, 2, False, "officer2")
    assert blocked.resolved_at is not None
    assert store.for_user(U_PO_1, nt.RFQ_VENDOR_EMAIL_FAILURE) == []  # nothing failed on resend


# ---------------------------------------------------------------------------
# System Configuration (Admin)
# ---------------------------------------------------------------------------


def test_admin_receives_configuration_notification_and_it_resolves_once_approval_starts(store):
    dispatcher = _dispatcher(store)
    dispatcher.notify(
        nt.WORKFLOW_CONFIGURATION_BLOCKED, entity_type=nt.ENTITY_INVOICE, entity_id=42,
        entity_display_id="INV-42", message="no policy", event_id="blocked:x", actor_user_id="apexec1",
    )
    [blocked] = store.for_user(U_ADMIN)
    assert nt.module_for(blocked.notification_type) == nt.MODULE_SYSTEM_CONFIGURATION

    APNotificationEvents(FakeSession(), dispatcher=dispatcher).approval_step_pending(
        _invoice(), SimpleNamespace(id=11, level_number=1, approval_rule="ANY_ONE"), [U_INV_APPROVER_A], "apexec1",
    )
    assert blocked.resolved_at is not None


def _cdc_failure(**overrides):
    values = dict(id=9, entity_type="UMS_USER", entity_key="user_id=17", kafka_topic="ums.users",
                  failure_type="VALIDATION", error_message="missing user_uuid", retry_count=5, max_retries=5,
                  status="EXHAUSTED")
    values.update(overrides)
    return SimpleNamespace(**values)


def test_admin_receives_identity_sync_failure_once(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.identity_sync_failed(_cdc_failure())
    ev.identity_sync_failed(_cdc_failure())
    [n] = store.rows
    assert n.recipient_user_uuid == U_ADMIN
    assert n.notification_type == nt.SYSTEM_CONFIGURATION_EXCEPTION
    assert nt.module_for(n.notification_type) == nt.MODULE_SYSTEM_CONFIGURATION
    assert "missing user_uuid" in n.message


def test_cdc_retry_notifies_admin_only_when_retries_are_exhausted(store):
    from Backend.Business_Layer.services.cdc_failure_log_service import CdcFailureLogService

    service = CdcFailureLogService.__new__(CdcFailureLogService)
    service.db = FakeSession()

    def _update(failure, succeeded, error_message=None):
        failure.retry_count += 1
        failure.status = "EXHAUSTED" if failure.retry_count >= failure.max_retries else "RETRYING"

    service.dao = SimpleNamespace(update_failure_after_retry=_update)
    failure = _cdc_failure(retry_count=3, status="RETRYING")
    service.mark_retry_failed(failure, "still broken")
    assert store.rows == []  # still retrying -> background noise, no notification
    service.mark_retry_failed(failure, "still broken")
    assert [n.recipient_user_uuid for n in store.rows] == [U_ADMIN]


# ---------------------------------------------------------------------------
# Payments (Finance)
# ---------------------------------------------------------------------------


def test_scheduling_payment_resolves_ready_and_earlier_failure_notifications(store, monkeypatch):
    from Backend.Data_Access_Layer.dao.payment_dao import PaymentDAO

    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    ev.invoice_approved(_invoice(), "invapprA")
    [ready] = store.for_user(U_PAYMENT, nt.PAYMENT_READY)

    failed_payment = SimpleNamespace(payment_id=3, vendor_id=9, total_amount=Decimal("100"), created_by="payer1",
                                     payment_invoice=[SimpleNamespace(invoice_id=42)])
    ev.payment_failed(failed_payment, "admin1")
    [failed] = store.for_user(U_PAYMENT, nt.PAYMENT_FAILED)
    [escalation] = store.for_user(U_FIN_MGR, nt.FINANCE_ESCALATION)
    assert {nt.module_for(n.notification_type) for n in (ready, failed, escalation)} == {nt.MODULE_PAYMENTS}

    monkeypatch.setattr(PaymentDAO, "get_failed_payment_ids_for_invoices", lambda self, ids: [3] if 42 in ids else [])
    ev.payment_scheduled(SimpleNamespace(payment_id=4), [42])
    assert ready.resolved_at is not None
    assert failed.resolved_at is not None and escalation.resolved_at is not None


def test_cleared_payment_also_resolves_finance_escalation(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    payment = SimpleNamespace(payment_id=3, vendor_id=9, total_amount=Decimal("100"), created_by="payer1",
                              payment_invoice=[])
    ev.payment_failed(payment, "admin1")
    ev.payment_cleared(payment)
    assert store.rows and all(n.resolved_at is not None for n in store.rows)


def test_real_payment_dao_failed_lookup_is_filtered_by_invoice_and_status():
    captured = {}

    class _Query:
        def __init__(self, *a):
            pass

        def join(self, *a):
            return self

        def filter(self, *conditions):
            captured["sql"] = " AND ".join(str(c.compile(dialect=postgresql.dialect())) for c in conditions)
            return self

        def distinct(self):
            return self

        def all(self):
            return [(3,)]

    from Backend.Data_Access_Layer.dao.payment_dao import PaymentDAO

    assert PaymentDAO(SimpleNamespace(query=_Query)).get_failed_payment_ids_for_invoices([42]) == [3]
    assert "invoice_id IN" in captured["sql"] and "status_code" in captured["sql"]
    assert PaymentDAO(SimpleNamespace()).get_failed_payment_ids_for_invoices([]) == []


def test_real_create_payment_emits_payment_scheduled(store, monkeypatch):
    import Backend.Business_Layer.services.payment_service as payment_module

    calls = []
    monkeypatch.setattr(
        APNotificationEvents, "payment_scheduled",
        lambda self, payment, invoice_ids: calls.append((payment.payment_id, list(invoice_ids))),
    )
    service = payment_module.PaymentService.__new__(payment_module.PaymentService)
    service.db = FakeSession()
    invoice = _invoice(status=SimpleNamespace(status_code="READY_FOR_PAYMENT"), amount_paid=Decimal("0"))
    service.vendor_dao = SimpleNamespace(vendor_exists=lambda vendor_id: True)
    service.invoice_dao = SimpleNamespace(get_invoice_by_id_locked=lambda i: invoice,
                                          create_audit_log=lambda log: log)
    service._net_payable = lambda inv: Decimal("5000")

    def _create(payment):
        payment.payment_id = 77

    service.payment_dao = SimpleNamespace(
        get_status_by_module_code=lambda module, code: SimpleNamespace(status_id=1),
        get_pending_committed_amount_for_invoice=lambda invoice_id: Decimal("0"),
        create_payment=_create, create_payment_invoice=lambda a: a, create_audit_log=lambda log: log,
    )
    request = SimpleNamespace(vendor_id=9, vendor_bank_id=1, scheduled_date=None, currency_id=1,
                              payment_method="NEFT", reference_number=None,
                              allocations=[SimpleNamespace(invoice_id=42, allocated_amount=Decimal("100"))])
    service.create_payment(request, "payer1")
    assert calls == [(77, [42])]


# ---------------------------------------------------------------------------
# Audit: every catalogued type is emitted or explicitly documented as unused
# ---------------------------------------------------------------------------


def test_every_catalog_type_is_emitted_or_documented_as_unemitted():
    import inspect
    import re

    source = inspect.getsource(events_module)
    emitted = set(re.findall(r"notify\(\s*nt\.([A-Z_]+)", source))
    emitted |= {code for code in re.findall(r"code = nt\.([A-Z_]+)", source)}
    catalog = set(nt.CATALOG)

    assert emitted <= catalog
    assert emitted.isdisjoint(nt.UNEMITTED_TYPES)
    assert emitted | set(nt.UNEMITTED_TYPES) == catalog


# ---------------------------------------------------------------------------
# NDA resolution
# ---------------------------------------------------------------------------


def _nda(**overrides):
    values = dict(nda_id=21, vendor_id=1, pr_id=None, created_by="officer1", signed_at=None)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_successful_nda_resend_resolves_the_pending_item(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    nda = _nda()
    ev.nda_send_failed(nda, "smtp down", "officer2")
    ev.nda_sent(nda)
    [pending] = store.for_user(U_PO_1, nt.NDA_PENDING)
    assert pending.resolved_at is not None


def test_expired_nda_blocker_resolves_when_a_new_nda_starts_or_is_reused_or_completes(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    expired = _nda(nda_id=21)
    store.ndas.append(expired)

    def blocker():
        store.rows.clear()
        _dispatcher(store).notify(
            nt.NDA_EXPIRED_RFQ_BLOCKED, entity_type=nt.ENTITY_VENDOR_NDA, entity_id=21,
            entity_display_id="NDA-000021", message="m", event_id="expired", owners=["officer1"],
        )
        return store.rows[0]

    for trigger in (
        lambda: ev.nda_required(_nda(nda_id=22), "officer2"),
        lambda: ev.nda_reused(_nda(nda_id=23)),
        lambda: ev.nda_completed(_nda(nda_id=24)),
    ):
        item = blocker()
        trigger()
        assert item.resolved_at is not None


def test_expired_nda_blocker_is_not_resolved_for_another_vendor(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    store.ndas.append(_nda(nda_id=21, vendor_id=1))
    _dispatcher(store).notify(
        nt.NDA_EXPIRED_RFQ_BLOCKED, entity_type=nt.ENTITY_VENDOR_NDA, entity_id=21,
        entity_display_id="NDA-000021", message="m", event_id="expired", owners=["officer1"],
    )
    ev.nda_completed(_nda(nda_id=30, vendor_id=2))
    assert store.rows[0].resolved_at is None


# ---------------------------------------------------------------------------
# Vendor onboarding resolution
# ---------------------------------------------------------------------------


def test_reassignment_moves_the_work_to_the_new_intaker(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    request = _onboarding_request(assigned_to="intake1")
    ev.onboarding_assigned(request, "officer1")

    request.assigned_to = "intake2"
    ev.onboarding_assigned(request, "officer1", previous_assignee="intake1")

    [first] = store.for_user(U_INTAKE_1, nt.VENDOR_ONBOARDING_ASSIGNED)
    [second] = store.for_user(U_INTAKE_2, nt.VENDOR_ONBOARDING_ASSIGNED)
    assert first.resolved_at is not None and second.resolved_at is None

    # ... and back again: the first intaker gets a fresh, open item
    request.assigned_to = "intake1"
    ev.onboarding_assigned(request, "officer1", previous_assignee="intake2")
    open_for_first = [n for n in store.for_user(U_INTAKE_1, nt.VENDOR_ONBOARDING_ASSIGNED) if n.resolved_at is None]
    assert len(open_for_first) == 1
    assert second.resolved_at is not None


def test_reassigning_to_the_same_intaker_is_a_no_op(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    request = _onboarding_request(assigned_to="intake1")
    ev.onboarding_assigned(request, "officer1")
    ev.onboarding_assigned(request, "officer1", previous_assignee="intake1")
    [n] = store.for_user(U_INTAKE_1)
    assert n.resolved_at is None


def test_real_assign_passes_the_previous_assignee(store):
    from Backend.Business_Layer.services.vendor_onboarding_service import VendorOnboardingService

    service = VendorOnboardingService(FakeSession())
    request = _onboarding_request(assigned_to="intake1", status=SimpleNamespace(status_code="ASSIGNED"), status_id=1)
    service.onboarding_dao = SimpleNamespace(get_request_by_id=lambda request_id: request, create_audit_log=lambda log: log)
    APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store)).onboarding_assigned(request, "officer1")

    service.assign(7, "intake2", "officer1")
    assert store.for_user(U_INTAKE_1)[0].resolved_at is not None
    assert store.for_user(U_INTAKE_2, nt.VENDOR_ONBOARDING_ASSIGNED)[0].resolved_at is None


def test_information_and_prescreen_items_resolve_as_the_request_progresses(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    request = _onboarding_request(assigned_to="intake1")

    ev.onboarding_status_changed(request, "PRE_SCREEN_PENDING", "officer1")
    ev.onboarding_status_changed(request, "NEED_INFORMATION", "officer1", "missing GSTIN")
    [prescreen] = store.for_user(U_INTAKE_1, nt.VENDOR_PRESCREEN_REQUIRED)
    [info] = store.for_user(U_INTAKE_1, nt.VENDOR_INFORMATION_REQUIRED)
    assert prescreen.resolved_at is not None and info.resolved_at is None

    ev.onboarding_status_changed(request, "PRE_SCREEN_PENDING", "officer1")
    assert info.resolved_at is not None

    ev.onboarding_status_changed(request, "PASSED", "officer1")
    assert all(n.resolved_at is not None for n in store.for_user(U_INTAKE_1, nt.VENDOR_PRESCREEN_REQUIRED))


# ---------------------------------------------------------------------------
# Invoice validation exception
# ---------------------------------------------------------------------------


def test_a_re_raised_validation_exception_is_a_new_actionable_item(store):
    ev = APNotificationEvents(FakeSession(), dispatcher=_dispatcher(store))
    invoice = _invoice(created_by="apexec1")
    ev.invoice_validation_exception(invoice, "PO_REQUIRED", "no PO", "invapprA", issue_id=1)
    ev.invoice_reviewed(invoice)
    ev.invoice_validation_exception(invoice, "PO_REQUIRED", "no PO", "invapprA", issue_id=2)

    first, second = store.for_user(U_AP_EXEC, nt.INVOICE_VALIDATION_EXCEPTION)
    assert first.resolved_at is not None and second.resolved_at is None
    # the same issue row replayed does not duplicate
    ev.invoice_validation_exception(invoice, "PO_REQUIRED", "no PO", "invapprA", issue_id=2)
    assert len(store.for_user(U_AP_EXEC, nt.INVOICE_VALIDATION_EXCEPTION)) == 2
