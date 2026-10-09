"""Role dashboards (Business_Layer/services/role_dashboard_service.py): who sees which view, and
each view's figures from its own data only - Approvals, My work (AP Executive), Management."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import role_dashboard_service as rds
from Backend.Business_Layer.services.ap_reporting_service import InvoiceFigures
from Backend.Business_Layer.services.role_dashboard_service import RoleDashboardService

D = datetime.date
UTC = datetime.timezone.utc
TODAY = D(2026, 10, 9)


def _now_minus(days):
    return datetime.datetime.now(UTC) - datetime.timedelta(days=days)


def _invoice(invoice_id, net="1000", created_by="7", created_days_ago=0, due=D(2026, 10, 20)):
    return SimpleNamespace(invoice_id=invoice_id, invoice_number=f"INV-{invoice_id}", net_amount=Decimal(net),
                           due_date=due, created_by=created_by,
                           created_at=datetime.datetime.now() - datetime.timedelta(days=created_days_ago))


class _FakeDAO:
    def __init__(self, **data):
        self.data = data

    def approver_queue(self, user_uuid):
        return self.data.get("queue", [])

    def approver_decisions(self, user_uuid, since):
        return self.data.get("decisions", [])

    def pending_steps(self):
        return self.data.get("pending_steps", [])

    def cycle_rows(self, since):
        return self.data.get("cycles", [])

    def work_queue(self, statuses):
        return self.data.get("work", [])

    def intake_rows(self, since):
        return self.data.get("intake", [])

    def status_counts(self):
        return self.data.get("counts", [])


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setattr(rds, "get_numeric_system_config", lambda db, key, default=None: default)
    monkeypatch.setattr(rds.ApproverResolverService, "resolve_user_uuid", lambda self, user_id: "uuid-1")

    def factory(**data):
        service = RoleDashboardService(db=None, today=TODAY)
        service.dao = _FakeDAO(**data)
        return service
    return factory


def test_views_follow_permissions():
    views = lambda perms: [v["key"] for v in RoleDashboardService.views_for({"permissions": perms})]
    assert views(["INVOICE_OCR_REVIEW"]) == ["my_work"]
    assert views(["INVOICE_APPROVE"]) == ["approvals"]
    assert views(["PAYMENT_VIEW"]) == ["finance"]
    assert views(["AP_MANAGEMENT_DASHBOARD_VIEW"]) == ["management"]
    assert views(["PAYMENT_PROCESS", "INVOICE_APPROVE"]) == ["finance", "approvals"]
    assert views(["PR_VIEW"]) == []


def test_build_refuses_views_the_user_may_not_open(make):
    with pytest.raises(PermissionError):
        make().build("management", {"permissions": ["PAYMENT_VIEW"]})
    with pytest.raises(ValueError):
        make().build("nope", {"permissions": []})


def test_approvals_queue_wait_and_decisions(make):
    queue = [
        (_invoice(1, "250000"), "Vertex", "IT", 1, _now_minus(5), "INR"),
        (_invoice(2, "1000"), "Skyline", None, 2, _now_minus(0.2), "INR"),
    ]
    decided = datetime.datetime(2026, 10, 2, 10, tzinfo=UTC)
    decisions = [
        (decided, "APPROVED", "APPROVED", decided - datetime.timedelta(days=2), 1, Decimal("1"), "INR"),
        (decided, "REJECTED", "CANCELLED", decided - datetime.timedelta(days=1), 2, Decimal("1"), "INR"),  # sent back
        (decided, "REJECTED", "REJECTED", decided - datetime.timedelta(days=3), 3, Decimal("1"), "INR"),
    ]
    data = make(queue=queue, decisions=decisions).build("approvals", {"user_id": "7", "permissions": ["INVOICE_APPROVE"]})
    kpis = {k["key"]: k for k in data["kpis"]}
    assert kpis["awaiting"]["value"] == 2
    assert kpis["queue_value"]["value"] == Decimal("251000.00")
    assert kpis["oldest"]["value"] >= 4.9 and kpis["oldest"]["tone"] == "rose"
    assert kpis["high_value"]["value"] == 1
    assert kpis["decided"]["value"] == 3
    assert kpis["decided"]["subtitle"] == "1 approved · 1 rejected · 1 sent back"
    assert kpis["turnaround"]["value"] == 2.0
    assert data["queue"][0]["department"] == "IT" and data["queue"][1]["department"] == "Unassigned"
    aging = {b["key"]: b["count"] for b in data["waiting_aging"]}
    assert aging == {"lt1": 1, "1to3": 0, "4to7": 1, "gt7": 0}
    oct_ = data["decisions_trend"][-1]
    assert (oct_["approved"], oct_["rejected"], oct_["sent_back"]) == (1, 1, 1)


def test_my_work_buckets_by_next_step(make, monkeypatch):
    work = [
        (_invoice(1, created_days_ago=4), "A", "OCR_REVIEW_PENDING", None, "INR"),
        (_invoice(2, created_by="9"), "B", "RETURNED_FOR_REVIEW", None, "INR"),
        (_invoice(3), "C", "OCR_REVIEWED", None, "INR"),                                          # TDS not determined
        (_invoice(4), "D", "OCR_REVIEWED", SimpleNamespace(determination_status="DETERMINED"), "INR"),  # ready to send
        (_invoice(5), "E", "OCR_FAILED", None, "INR"),
    ]
    now = datetime.datetime.now()
    intake = [(now, "7", "OCR_REVIEW_PENDING"), (now, "9", "PAID"), (now - datetime.timedelta(days=400), "7", "PAID")]
    service = make(work=work, intake=intake, counts=[("PENDING_APPROVAL", 4), ("APPROVED", 1), ("READY_FOR_PAYMENT", 2)])
    monkeypatch.setattr(service.reporting, "invoice_figures", lambda *a, **k: [])
    data = service.build("my_work", {"user_id": "7", "permissions": ["INVOICE_OCR_REVIEW"]})
    kpis = {k["key"]: k["value"] for k in data["kpis"]}
    assert kpis == {"to_review": 1, "returned": 1, "tds": 1, "ready_to_send": 1, "uploaded": 2}
    assert "1 uploaded by me" in data["kpis"][-1]["subtitle"] and "1 OCR failed" in data["kpis"][-1]["subtitle"]
    pipeline = {p["key"]: p["count"] for p in data["pipeline"]}
    assert pipeline == {"review": 3, "reviewed": 2, "approval": 4, "approved": 3}
    assert data["oldest"][0]["invoice_id"] == 1 and data["oldest"][0]["mine"] is True


def _figure(invoice_id, stage, outstanding, due, vendor="V1", vendor_id=1, term_status=None, verified=True):
    return InvoiceFigures(
        invoice_id=invoice_id, invoice_number=f"INV-{invoice_id}", vendor_id=vendor_id, vendor_name=vendor,
        invoice_type="NON_PO", invoice_date=D(2026, 8, 1), due_date=due, due_verified=verified,
        status_code={"PAYABLE": "READY_FOR_PAYMENT", "APPROVED": "APPROVED", "IN_APPROVAL": "PENDING_APPROVAL"}[stage],
        status_name=None, stage=stage, currency_code="INR", symbol="₹", net_amount=Decimal(outstanding),
        tds_amount=Decimal("0"), net_payable=Decimal(outstanding), paid=Decimal("0"), reserved=Decimal("0"),
        outstanding=Decimal(outstanding), department=None, category=None, term_status=term_status,
        term_reason=None, statutory_due_date=None)


def test_management_position_outflow_efficiency(make, monkeypatch):
    figures = [
        _figure(1, "PAYABLE", "300000", D(2026, 9, 1)),                       # overdue, high value
        _figure(2, "APPROVED", "100", D(2026, 10, 20), vendor="V2", vendor_id=2),
        _figure(3, "IN_APPROVAL", "50", D(2026, 11, 25), vendor="V3", vendor_id=3),
        _figure(4, "IN_APPROVAL", "10", None, vendor="V4", vendor_id=4, verified=False),
    ]
    created = datetime.datetime(2026, 8, 1, 9)
    cycles = [(1, created, datetime.datetime(2026, 8, 5, 9, tzinfo=UTC), D(2026, 8, 20)),
              (2, created, datetime.datetime(2026, 8, 3, 9, tzinfo=UTC), None)]
    steps = [(1, "IT", _now_minus(6), Decimal("50"), "INR"), (1, "IT", _now_minus(1), Decimal("10"), "INR")]
    service = make(cycles=cycles, pending_steps=steps)
    monkeypatch.setattr(service.reporting, "invoice_figures", lambda *a, **k: figures)
    monkeypatch.setattr(service.reporting, "report_summary", lambda *a, **k: {
        "kpis": [{"key": "on_time", "value": 80.0}, {"key": "days_to_pay", "value": 20.0}, {"key": "invoiced", "value": Decimal("500")}],
        "monthly": [], "by_department": []})
    monkeypatch.setattr(service.reporting, "finance_dashboard", lambda user: {
        "action_cards": [{"key": "term_exceptions", "amounts": []}, {"key": "msme_due", "count": 0, "amounts": []}],
        "tds": {"items": [{"key": "deposit_overdue", "count": 1}]}, "term_exception_count": 0,
        "receipts_missing": {"count": 2}})
    data = service.build("management", {"permissions": ["AP_MANAGEMENT_DASHBOARD_VIEW"]})
    kpis = {k["key"]: k for k in data["kpis"]}
    assert kpis["liability"]["value"] == Decimal("300160.00")
    assert kpis["overdue"]["value"] == Decimal("300000.00")
    assert kpis["overdue"]["subtitle"].startswith("100%")
    assert kpis["due_30"]["value"] == Decimal("100.00")
    assert kpis["on_time"]["tone"] == "amber"
    outflow = {o["key"]: o for o in data["outflow"]}
    assert outflow["overdue"]["approved"] == Decimal("300000.00")
    assert outflow["d60"]["pipeline"] == Decimal("50.00")
    assert outflow["unverified"]["count"] == 1
    assert data["top5_share"] == 100.0
    assert data["efficiency"]["median_days_to_approve"] == 3.0
    assert data["efficiency"]["median_days_approval_to_payment"] == 15.0
    assert data["efficiency"]["bottlenecks"][0]["count"] == 2
    assert data["high_value_exceptions"][0]["invoice_id"] == 1
    compliance = {c["key"]: c["count"] for c in data["compliance"]}
    assert compliance["tds_overdue"] == 1 and compliance["receipts"] == 2
