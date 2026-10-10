"""Touchless PO invoices (Step B): PO / line linking, controls, the existing review -> TDS -> send
order, auto-approval at / below the threshold, exception reasons, settings and permissions.
In-memory fakes only - no DB."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.interface.matching_interface import LineMatchResult, LineMatchStatus, MatchResult, MatchType, OverallMatchStatus
from Backend.API_Layer.routes import ap_automation_route as route
from Backend.Business_Layer.services import ap_automation_service as svc
from Backend.Business_Layer.services import ap_automation_settings_service as settings_mod
from Backend.Business_Layer.services import invoice_approval_service as approval_mod
from Backend.Business_Layer.services.ap_automation_settings_service import AutomationSettings
from Backend.Data_Access_Layer.dao.ap_automation_dao import normalize_po_number
from Backend.Data_Access_Layer.models.audit import AuditLog

ON = AutomationSettings(enabled=True, auto_approve_max_amount=Decimal("50000"))


# ======================================================================
# Pure helpers
# ======================================================================
def _il(i, desc, price="10"):
    return SimpleNamespace(invoice_line_id=i, description=desc, unit_price=Decimal(price))


def _pl(i, name, price="10", desc=None):
    return SimpleNamespace(po_line_id=i, item_name=name, description=desc, unit_price=Decimal(price))


def test_link_lines_only_confident_pairs():
    assert svc.link_lines([_il(1, "anything")], [_pl(9, "Laptop")]) == {1: 9}
    links = svc.link_lines(
        [_il(1, "Dell Latitude 5440 laptop", "65000"), _il(2, "USB-C docking station", "9000"), _il(3, "Installation charges")],
        [_pl(10, "USB C Docking Station", "9000"), _pl(11, "Dell Latitude 5440 Laptop", "65000"), _pl(12, "Wireless mouse")],
    )
    assert links == {1: 11, 2: 10}  # installation charges has no counterpart -> left unlinked


def test_po_number_normalisation():
    assert normalize_po_number(" po-2026/0042 ") == "PO20260042" == normalize_po_number("PO 2026 0042")


def _line(status, **kw):
    base = dict(invoice_line_id=1, line_number=3, po_line_id=11, ordered_quantity=Decimal("10"),
                po_unit_price=Decimal("1200"), invoiced_quantity=Decimal("10"), invoice_unit_price=Decimal("1250"),
                price_variance=Decimal("50"), quantity_variance=Decimal("0"), status=status)
    base.update(kw)
    return LineMatchResult(**base)


def _match(status=OverallMatchStatus.MATCHED, kind=MatchType.THREE_WAY, lines=None, messages=None):
    return MatchResult(invoice_id=7, po_id=1, po_number="PO-1", match_type=kind, po_mandatory=False, grn_mandatory=False,
                       overall_status=status, lines=lines if lines is not None else [_line(LineMatchStatus.MATCHED, received_quantity=Decimal("10"))],
                       messages=messages or [])


def test_evaluate_match_reasons():
    assert svc.evaluate_match(_match(), ON) == []
    assert svc.evaluate_match(_match(kind=MatchType.TWO_WAY), ON) == ["No goods receipt (GRN) recorded for this PO yet"]
    assert svc.evaluate_match(_match(kind=MatchType.TWO_WAY), AutomationSettings(require_grn=False)) == []
    reasons = svc.evaluate_match(_match(OverallMatchStatus.VARIANCE_DETECTED, lines=[_line(LineMatchStatus.PRICE_VARIANCE)]), ON)
    assert reasons == ["Line 3: unit price 1,250.00 vs PO 1,200.00 (+4.2%)"]


# ======================================================================
# Run (one invoice)
# ======================================================================
class World:
    def __init__(self):
        self.invoice = SimpleNamespace(invoice_id=7, invoice_type="PO", status_id=1, vendor_id=5, po_id=None, po=None,
                                       net_amount=Decimal("40000"), inbound_document_id=70,
                                       currency=SimpleNamespace(currency_code="INR"))
        self.status = "OCR_REVIEW_PENDING"
        self.item = SimpleNamespace(validation_result={"is_valid": True, "issues": []},
                                    extracted_data={"reference": {"po_number": "PO-1"}})
        self.po = SimpleNamespace(po_id=1, po_number="PO-1", purchase_order_line=[_pl(11, "Laptop")])
        self.lines = [SimpleNamespace(invoice_line_id=71, line_number=1, description="Laptop", unit_price=Decimal("10"), po_line_id=None)]
        self.match = _match()
        self.billed = {}
        self.issues = []
        self.policy_error = None
        self.tds_problem = None
        self.send_error = None
        self.calls = []
        self.audit = []


@pytest.fixture
def world(monkeypatch):
    w = World()

    class Db:
        def add(self, obj):
            if isinstance(obj, AuditLog):
                w.audit.append(obj.new_values)

        def commit(self):
            pass

        def rollback(self):
            pass

    class InvoiceDAO:
        def __init__(self, db):
            pass

        def get_invoice_by_id(self, i):
            return w.invoice

        def get_status_details(self, sid):
            return SimpleNamespace(status_code=w.status)

        def get_open_invoice_issues(self, i):
            return w.issues

    class AutoDAO:
        def __init__(self, db):
            pass

        def upload_item_for_invoice(self, i):
            return w.item

        def find_open_po(self, vendor, number):
            return w.po if normalize_po_number(number) == "PO1" else None

        def lines(self, i):
            return w.lines

        def invoiced_quantity_elsewhere(self, ids, i):
            return w.billed

    class WorkbenchDAO:
        def __init__(self, db):
            pass

        def po_coding(self, ids):
            return {1: (10, 101, "PO-1")}

        def inbound_document_ids(self, ids):
            return {}

    class Policy:
        def __init__(self, db):
            pass

        def match_policy(self, d, c, a):
            if w.policy_error:
                raise ValueError(w.policy_error)
            return SimpleNamespace(name="P")

    class Approvals:
        def __init__(self, db):
            pass

        def send_for_approval(self, i, actor):
            if w.send_error:
                raise ValueError(w.send_error)
            w.calls.append(("send", actor))
            w.status = "PENDING_APPROVAL"

        def auto_approve(self, i, actor, reason):
            w.calls.append(("auto_approve", reason))

    def review(inbound, request, db, actor):
        w.calls.append(("review", inbound, request.invoice_type.value, request.po_id, actor))

    def tds(db, i, actor):
        w.calls.append(("tds", actor))
        return w.tds_problem

    monkeypatch.setattr(svc, "InvoiceDAO", InvoiceDAO)
    monkeypatch.setattr(svc, "APAutomationDAO", AutoDAO)
    monkeypatch.setattr(svc, "ReviewWorkbenchDAO", WorkbenchDAO)
    monkeypatch.setattr(svc, "ApprovalPolicyService", Policy)
    monkeypatch.setattr(svc, "InvoiceApprovalService", Approvals)
    monkeypatch.setattr(svc.invoice_process_service, "apply_ocr_review", review)
    monkeypatch.setattr(svc, "auto_determine_tds", tds)
    monkeypatch.setattr(svc.APAutomationService, "_match", lambda self, i: w.match)
    w.db = Db()
    return w


def _run(world, settings=ON, **kw):
    return svc.APAutomationService(world.db, settings=settings).run(7, **kw)


def test_off_by_default_does_nothing(world):
    assert _run(world, settings=AutomationSettings()) is None
    assert world.calls == [] and world.invoice.po_id is None


def test_matched_and_below_threshold_is_auto_approved_through_the_existing_steps(world):
    result = _run(world)
    assert result["outcome"] == "AUTO_APPROVED" and result["po_number"] == "PO-1"
    assert world.invoice.po_id == 1 and world.lines[0].po_line_id == 11  # PO and line linked
    assert [c[0] for c in world.calls] == ["review", "tds", "send", "auto_approve"]
    assert world.calls[0] == ("review", 70, "PO", 1, "AP_AUTOMATION")
    assert "three-way" in world.calls[-1][1] and world.audit[-1]["outcome"] == "AUTO_APPROVED"


def test_above_threshold_is_only_sent(world):
    world.invoice.net_amount = Decimal("75000")
    result = _run(world)
    assert result["outcome"] == "AUTO_SENT" and "auto-approval limit" in result["reasons"][0]
    assert [c[0] for c in world.calls] == ["review", "tds", "send"]


def test_zero_threshold_never_auto_approves_and_foreign_currency_is_not_auto_approved(world):
    assert _run(world, settings=AutomationSettings(enabled=True))["outcome"] == "AUTO_SENT"
    world.calls.clear()
    world.status = "OCR_REVIEW_PENDING"
    world.invoice.currency = SimpleNamespace(currency_code="USD")
    result = _run(world)
    assert result["outcome"] == "AUTO_SENT" and "Not in INR" in result["reasons"][0]


@pytest.mark.parametrize("setup,expected", [
    (lambda w: setattr(w, "match", _match(kind=MatchType.TWO_WAY)), "No goods receipt"),
    (lambda w: setattr(w, "match", _match(OverallMatchStatus.VARIANCE_DETECTED, lines=[_line(LineMatchStatus.PRICE_VARIANCE)])), "unit price 1,250.00 vs PO 1,200.00"),
    (lambda w: setattr(w, "billed", {11: Decimal("4")}), "possible double billing"),
    (lambda w: setattr(w, "item", SimpleNamespace(validation_result={"is_valid": False, "issues": ["Tax total mismatch"]}, extracted_data={"reference": {"po_number": "PO-1"}})), "Tax total mismatch"),
    (lambda w: setattr(w, "issues", [object()]), "Open invoice issues"),
    (lambda w: setattr(w, "policy_error", "No applicable approval policy found for this invoice."), "No applicable approval policy"),
])
def test_any_failed_control_is_an_exception_and_nothing_is_reviewed(world, setup, expected):
    setup(world)
    result = _run(world)
    assert result["outcome"] == "EXCEPTION" and any(expected in r for r in result["reasons"])
    assert world.calls == []


def test_unknown_po_number_is_an_exception(world):
    world.item.extracted_data = {"reference": {"po_number": "PO-999"}}
    result = _run(world)
    assert result["outcome"] == "EXCEPTION" and "PO-999" in result["reasons"][0] and world.invoice.po_id is None


def test_tds_or_send_problems_leave_it_reviewed(world):
    world.tds_problem = "TDS needs review: no payment nature"
    assert _run(world)["outcome"] == "REVIEWED_NOT_SENT"
    world.calls.clear()
    world.tds_problem, world.send_error = None, "No active approver found for level 1"
    result = _run(world)
    assert result["outcome"] == "REVIEWED_NOT_SENT" and "No active approver" in result["reasons"][0]


def test_only_po_invoices_waiting_for_review(world):
    world.status = "OCR_REVIEWED"
    assert _run(world) is None
    world.status, world.invoice.invoice_type = "OCR_REVIEW_PENDING", "NON_PO"
    assert _run(world) is None


def test_stats_and_touchless_rate(monkeypatch):
    class DAO:
        def __init__(self, db):
            pass

        def results_since(self, since):
            return [(1, {"outcome": "AUTO_APPROVED"}), (2, {"outcome": "AUTO_SENT"}), (2, {"outcome": "EXCEPTION"}),
                    (3, {"outcome": "EXCEPTION", "reasons": ["No goods receipt (GRN) recorded for this PO yet"]}),
                    (4, {"outcome": "EXCEPTION", "reasons": ["Line 2: unit price 10.00 vs PO 9.00 (+11.1%)"]})]
    monkeypatch.setattr(svc, "APAutomationDAO", DAO)
    stats = svc.APAutomationService(None, settings=ON).stats()
    assert stats["processed"] == 4 and stats["touchless_rate"] == 50.0  # invoice 2 counts by its latest result
    assert {e["reason"] for e in stats["top_exceptions"]} == {"No goods receipt (GRN)", "Price variance"}


# ======================================================================
# Settings
# ======================================================================
class _CfgDb:
    def __init__(self):
        self.rows, self.audit = {}, []

    def add(self, obj):
        (self.audit.append(obj) if isinstance(obj, AuditLog) else self.rows.__setitem__(obj.config_key, obj))

    def commit(self):
        pass


@pytest.fixture
def cfg(monkeypatch):
    db = _CfgDb()

    class MasterDAO:
        def __init__(self, d):
            pass

        def get_system_config_by_key(self, key):
            return db.rows.get(key)
    monkeypatch.setattr(settings_mod, "MasterDAO", MasterDAO)
    return db


def test_settings_defaults_update_and_audit(cfg):
    service = settings_mod.APAutomationSettingsService(cfg)
    s = service.get()
    assert s.enabled is False and s.price_tolerance_pct == Decimal("1") and s.price_tolerance_amount == Decimal("100")
    assert s.require_grn is True and s.auto_approve_max_amount == Decimal("0")
    after = service.update({"enabled": True, "auto_approve_max_amount": "25000"}, "u-1", "Finance Manager")
    assert after.enabled and after.auto_approve_max_amount == Decimal("25000")
    assert service.get().auto_approve_max_amount == Decimal("25000")
    assert cfg.audit[-1].new_values == {"enabled": "True", "auto_approve_max_amount": "25000"}
    with pytest.raises(ValueError, match="price tolerance pct"):
        service.update({"price_tolerance_pct": "25"}, "u-1")


# ======================================================================
# Auto-approve completes the workflow without a human decision
# ======================================================================
def test_auto_approve_marks_steps_approved_and_approvers_skipped(monkeypatch):
    approvers = [SimpleNamespace(status="PENDING", decided_at=None, comments=None), SimpleNamespace(status="WAITING", decided_at=None, comments=None)]
    steps = [SimpleNamespace(id=1, level_number=1, status="PENDING", started_at=None, completed_at=None),
             SimpleNamespace(id=2, level_number=2, status="WAITING", started_at=None, completed_at=None)]
    instance = SimpleNamespace(invoice_approval_id=9, invoice_id=7, steps=steps, status="IN_PROGRESS", completed_at=None)
    invoice = SimpleNamespace(status_id=1, updated_by=None)
    events, audits = [], []
    service = approval_mod.InvoiceApprovalService.__new__(approval_mod.InvoiceApprovalService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.approval_dao = SimpleNamespace(get_approvers_for_step=lambda sid: [approvers[sid - 1]],
                                           get_invoice_approval_by_id=lambda i: instance,
                                           create_audit_log=lambda a: audits.append(a))
    service.invoice_dao = SimpleNamespace(get_invoice_by_id_locked=lambda i: invoice, get_status_by_code=lambda c: SimpleNamespace(status_id=42))
    monkeypatch.setattr(service, "_require_active_instance", lambda i: instance)
    monkeypatch.setattr(approval_mod, "APNotificationEvents", lambda db: SimpleNamespace(
        invoice_approved=lambda inv, a: events.append("approved"), tds_verification_required=lambda inv, a: events.append("tds")))
    service.auto_approve(7, "AP_AUTOMATION", "3-way match within tolerance")
    assert instance.status == "APPROVED" and invoice.status_id == 42
    assert [s.status for s in steps] == ["APPROVED", "APPROVED"] and [a.status for a in approvers] == ["SKIPPED", "SKIPPED"]
    assert "Auto-approved by AP automation" in approvers[0].comments
    assert audits[0].action == "INVOICE_AUTO_APPROVED" and events == ["approved", "tds"]


# ======================================================================
# Routes
# ======================================================================
def _client(permissions, monkeypatch, enabled=True):
    class Fake:
        def __init__(self, db):
            self.settings = AutomationSettings(enabled=enabled)

        def stats(self, days):
            return {"days": days, "processed": 0, "auto_approved": 0, "auto_sent": 0, "reviewed_not_sent": 0,
                    "exceptions": 0, "touchless_rate": None, "top_exceptions": []}

        def sweep(self):
            return []

        def run(self, invoice_id):
            return {"invoice_id": invoice_id, "outcome": "EXCEPTION", "reasons": ["No goods receipt (GRN) recorded for this PO yet"]}
    monkeypatch.setattr(route, "APAutomationService", Fake)

    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-1", "permissions": permissions}
            request.state.db = None
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(route.router, prefix="/ap-automation")
    return TestClient(app)


def test_route_permissions(monkeypatch):
    executive = _client(["INVOICE_OCR_REVIEW"], monkeypatch)
    assert executive.get("/ap-automation/settings").status_code == 403
    assert executive.put("/ap-automation/settings", json={"enabled": True}).status_code == 403
    assert executive.post("/ap-automation/run").status_code == 403
    assert executive.post("/ap-automation/invoices/7/run").json()["outcome"] == "EXCEPTION"  # re-check allowed
    manager = _client(["AP_AUTOMATION_MANAGE"], monkeypatch)
    assert manager.get("/ap-automation/stats").status_code == 200
    assert manager.post("/ap-automation/run").status_code == 200
    off = _client(["AP_AUTOMATION_MANAGE"], monkeypatch, enabled=False)
    assert off.post("/ap-automation/run").status_code == 409


def test_automation_dao_queries_compile(monkeypatch):
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Query, Session

    from Backend.Data_Access_Layer import models  # noqa: F401
    from Backend.Data_Access_Layer.dao.ap_automation_dao import APAutomationDAO

    compiled = []

    def capture(self):
        compiled.append(str(self.statement.compile(dialect=postgresql.dialect())))
        return []
    monkeypatch.setattr(Query, "all", capture)
    monkeypatch.setattr(Query, "first", lambda self: capture(self) or None)
    dao = APAutomationDAO(Session())
    dao.open_pos_for_vendor(5); dao.lines(7); dao.invoiced_quantity_elsewhere([1], 7); dao.upload_item_for_invoice(7)
    dao.pending_po_invoices(10); dao.latest_results([7]); dao.results_since(datetime.datetime(2026, 1, 1))
    assert len(compiled) == 7 and "audit_log" in compiled[-1]
