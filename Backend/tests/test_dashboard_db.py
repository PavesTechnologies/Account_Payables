# Backend/tests/test_dashboard_db.py
"""AP Dashboard (GET /apm/dashboard/summary). Runs against the REAL configured
database inside the savepoint-isolated `db` fixture (outer transaction always
rolled back). The live DB already holds data, so aggregation tests assert
DELTAS: summary before vs. after inserting known rows.
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.interface.dashboard_interface import DashboardSummaryDTO
from Backend.API_Layer.routes import dashboard_route
from Backend.Business_Layer.services.dashboard_service import DashboardService
from Backend.Data_Access_Layer.models.approval import ApprovalPolicy, InvoiceApproval, InvoiceApprovalStep, InvoiceApprovalStepApprover
from Backend.Data_Access_Layer.models.cdc import UmsUserCache
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.tds import InvoiceTds, TdsPaymentNature
from Backend.tests.test_tds_config_service_db import db, tag  # noqa: F401 - fixtures

TODAY = datetime.date.today()

# Representative permission sets per AP role (UMS owns the real mapping).
ROLES = {
    "admin": {"roles": ["Admin"], "permissions": ["APPROVAL_POLICY_MANAGE"]},
    "ap_executive": {"roles": ["AP_Executive"], "permissions": [
        "INVOICE_VIEW", "INVOICE_CREATE", "INVOICE_OCR_REVIEW", "INVOICE_SEND_FOR_APPROVAL",
        "INVOICE_TDS_VIEW", "INVOICE_TDS_DETERMINE", "INVOICE_TDS_EDIT"]},
    "approver": {"roles": ["Approver"], "permissions": ["INVOICE_VIEW", "INVOICE_APPROVE", "INVOICE_REJECT", "INVOICE_SEND_BACK"]},
    "finance": {"roles": ["Finance_Executive"], "permissions": [
        "INVOICE_VIEW", "INVOICE_TDS_VIEW", "INVOICE_TDS_VERIFY", "PAYMENT_VIEW", "PAYMENT_PROCESS",
        "TDS_TRACKING_VIEW", "TDS_TRACKING_UPDATE"]},
    "procurement_officer": {"roles": ["Procurement_Officer"], "permissions": [
        "QUOTATION_VIEW", "QUOTATION_CREATE", "VENDOR_SELECTION_VIEW", "PO_VIEW", "PO_CREATE", "PR_APPROVAL_VIEW"]},
    "pr_requestor": {"roles": ["PR_Requestor"], "permissions": ["PR_VIEW", "PR_CREATE", "PR_EDIT", "PR_SUBMIT", "PR_TRACK"]},
    "nobody": {"roles": [], "permissions": []},
}

PAYMENT_KEYS = {"payments_ready", "payments_outstanding_payable", "payments_paid"}
PAYMENT_FINANCIAL_KEYS = {"payable_outstanding", "paid_total", "tds_on_payable", "paid_in_period"}


def _user(role, user_id="900000001"):
    return {"user_id": user_id, **ROLES[role]}


def _summary(db, role, user_id="900000001", **kwargs):
    out = DashboardService(db).get_summary(_user(role, user_id), **kwargs)
    DashboardSummaryDTO.model_validate(out)  # every response matches the published schema
    return out


def _keys(out, section):
    return {w["key"] for w in out[section]}


def _value(out, section, key):
    return next(w for w in out[section] if w["key"] == key)["value"]


def _amount(out, section, key, currency="INR"):
    widget = next(w for w in out[section] if w["key"] == key)
    return sum((Decimal(a["amount"]) for a in widget["amounts"] if a["currency_code"] == currency), Decimal("0"))


def _status_id(db, code, module="INVOICE"):
    return db.query(StatusMaster).filter(StatusMaster.module_name == module, StatusMaster.status_code == code).one().status_id


def _invoice(db, tag, status, net="1000.00", paid="0", tds=None, determination="VERIFIED", invoice_date=TODAY):
    invoice = Invoice(
        invoice_number=f"{tag}-{uuid.uuid4().hex[:6]}", vendor_id=15, invoice_type="NON_PO",
        invoice_date=invoice_date, due_date=invoice_date, currency_id=1,
        gross_amount=Decimal(net), discount_amount=Decimal("0"), tax_amount=Decimal("0"),
        net_amount=Decimal(net), amount_paid=Decimal(paid), status_id=_status_id(db, status), created_by="test-suite",
    )
    db.add(invoice)
    db.flush()
    if tds is not None:
        nature = db.query(TdsPaymentNature).order_by(TdsPaymentNature.id).first()
        db.add(InvoiceTds(invoice_id=invoice.invoice_id, tds_applicable=Decimal(tds) > 0, payment_nature_id=nature.id,
                          tds_amount=Decimal(tds) if Decimal(tds) > 0 else None, determination_status=determination))
    db.flush()
    return invoice


# =========================================================
# Permission-aware shape
# =========================================================

def test_user_without_relevant_permissions_gets_nothing(db):
    out = _summary(db, "nobody")
    assert out["sections"] == []
    for section in ("kpis", "action_required", "status_summary", "financial_summary", "trends", "recent_activity"):
        assert out[section] == [], section


def test_admin_dashboard_is_vendor_management_only(db):
    out = _summary(db, "admin")
    assert out["sections"] == ["vendors"]
    assert {"vendors_active", "vendors_pending", "vendor_onboarding_open"} <= _keys(out, "kpis")
    assert not any(k.startswith(("invoices_", "payments_", "tds_")) for k in _keys(out, "kpis"))
    assert out["financial_summary"] == [] and out["trends"] == []


def test_ap_executive_dashboard(db):
    out = _summary(db, "ap_executive")
    actions = _keys(out, "action_required")
    assert {"invoices_ocr_review_pending", "invoices_ocr_failed", "invoices_returned_for_review",
            "invoices_pending_submission", "tds_determination_pending"} <= actions
    assert "tds_verification_pending" not in actions          # Finance's job
    assert "invoices_awaiting_my_approval" not in actions     # no INVOICE_APPROVE
    assert not (PAYMENT_KEYS & _keys(out, "kpis"))
    assert not (PAYMENT_FINANCIAL_KEYS & _keys(out, "financial_summary"))
    assert "invoice_status_distribution" in _keys(out, "status_summary")


def test_approver_dashboard_has_no_payment_or_tds_money(db):
    out = _summary(db, "approver")
    assert "invoices_awaiting_my_approval" in _keys(out, "action_required")
    assert not (PAYMENT_KEYS & _keys(out, "kpis"))
    assert not (PAYMENT_FINANCIAL_KEYS & _keys(out, "financial_summary"))
    assert "tds_total" not in _keys(out, "financial_summary")
    assert {t["key"] for t in out["trends"]} == {"invoice_count_trend", "invoice_amount_trend"}


def test_finance_executive_dashboard(db):
    out = _summary(db, "finance")
    assert {"payments_ready", "payments_outstanding_payable", "tds_verified", "tds_not_yet_filed"} <= _keys(out, "kpis")
    assert {"tds_verification_pending", "payments_to_record", "invoices_to_mark_ready", "tds_tracking_to_update"} <= _keys(out, "action_required")
    assert PAYMENT_FINANCIAL_KEYS <= _keys(out, "financial_summary")
    assert "tds_determination_pending" not in _keys(out, "action_required")  # AP Executive's job
    assert {"payment_amount_trend", "tds_amount_trend"} <= {t["key"] for t in out["trends"]}


def test_procurement_officer_dashboard(db):
    out = _summary(db, "procurement_officer")
    assert out["sections"] == ["pr_approval", "sourcing"]
    assert {"prs_awaiting_sourcing", "rfqs_awaiting_responses", "vendor_selection_pending", "po_generation_pending"} <= _keys(out, "action_required")
    assert "prs_awaiting_approval" not in _keys(out, "action_required")  # PR_APPROVAL_VIEW only, no PR_APPROVE
    assert not any(k.startswith(("invoices_", "payments_")) for k in _keys(out, "kpis"))
    assert out["financial_summary"] == []


def test_pr_requestor_sees_only_their_own_prs(db, tag):
    from Backend.Data_Access_Layer.models.purchase import PurchaseRequisition
    me, other = "900000777", "900000778"
    base_me = _summary(db, "pr_requestor", user_id=me)
    pr_template = db.query(PurchaseRequisition).first()
    for creator, status in ((me, "DRAFT"), (me, "RETURNED"), (other, "DRAFT")):
        db.add(PurchaseRequisition(
            pr_number=f"{tag}-{uuid.uuid4().hex[:6]}", department_id=pr_template.department_id,
            purchase_category_id=pr_template.purchase_category_id, status_id=_status_id(db, status, "PURCHASE_REQUISITION"),
            priority="NORMAL", estimated_total=Decimal("0"), created_by=creator,
        ))
    db.flush()
    after = _summary(db, "pr_requestor", user_id=me)
    assert _value(after, "action_required", "my_draft_prs") - _value(base_me, "action_required", "my_draft_prs") == 1
    assert _value(after, "action_required", "my_returned_prs") - _value(base_me, "action_required", "my_returned_prs") == 1
    assert _value(after, "kpis", "my_open_prs") - _value(base_me, "kpis", "my_open_prs") == 2


# =========================================================
# Approver queue = actual assignment, not the permission
# =========================================================

def _assign(db, invoice, approver_uuids, pending_uuids):
    policy_id = db.query(ApprovalPolicy.id).order_by(ApprovalPolicy.id).first()[0]
    approval = InvoiceApproval(invoice_id=invoice.invoice_id, approval_policy_id=policy_id, status="IN_PROGRESS")
    db.add(approval)
    db.flush()
    step = InvoiceApprovalStep(invoice_approval_id=approval.invoice_approval_id, level_number=1, approver_type="USER",
                               approval_rule="ANY_ONE", status="PENDING")
    db.add(step)
    db.flush()
    for u in approver_uuids:
        db.add(InvoiceApprovalStepApprover(approval_step_id=step.id, user_uuid=u, status="PENDING" if u in pending_uuids else "APPROVED"))
    db.flush()


def test_approver_sees_only_invoices_assigned_to_them(db, tag):
    me_id, other_id = 900000101, 900000102
    me_uuid, other_uuid = uuid.uuid4(), uuid.uuid4()
    db.add_all([UmsUserCache(user_id=me_id, user_uuid=me_uuid), UmsUserCache(user_id=other_id, user_uuid=other_uuid)])
    db.flush()
    base_me = _value(_summary(db, "approver", str(me_id)), "action_required", "invoices_awaiting_my_approval")
    base_other = _value(_summary(db, "approver", str(other_id)), "action_required", "invoices_awaiting_my_approval")

    shared = _invoice(db, tag, "PENDING_APPROVAL")
    only_other = _invoice(db, tag, "PENDING_APPROVAL")
    already_decided = _invoice(db, tag, "PENDING_APPROVAL")
    _assign(db, shared, [me_uuid, other_uuid], {me_uuid, other_uuid})
    _assign(db, only_other, [other_uuid], {other_uuid})
    _assign(db, already_decided, [me_uuid], set())  # my decision already recorded

    me = _value(_summary(db, "approver", str(me_id)), "action_required", "invoices_awaiting_my_approval")
    other = _value(_summary(db, "approver", str(other_id)), "action_required", "invoices_awaiting_my_approval")
    assert me - base_me == 1
    assert other - base_other == 2
    # an unknown user (no UMS mapping) gets 0, never someone else's queue
    assert _value(_summary(db, "approver", "123456789012"), "action_required", "invoices_awaiting_my_approval") == 0


# =========================================================
# Aggregation
# =========================================================

def test_status_and_financial_aggregation(db, tag):
    before = _summary(db, "finance")
    _invoice(db, tag, "READY_FOR_PAYMENT", net="100000.00", tds="10000.00")
    _invoice(db, tag, "PARTIALLY_PAID", net="50000.00", paid="20000.00", tds="5000.00")
    _invoice(db, tag, "PAID", net="30000.00", paid="30000.00", tds="0")
    _invoice(db, tag, "APPROVED", net="7000.00", tds="700.00", determination="DETERMINED")
    after = _summary(db, "finance")

    def delta(section, key):
        return _value(after, section, key) - _value(before, section, key)

    def money_delta(section, key):
        return _amount(after, section, key) - _amount(before, section, key)

    assert delta("kpis", "invoices_total") == 4
    assert delta("kpis", "payments_ready") == 1
    assert delta("kpis", "payments_partially_paid") == 1
    assert delta("kpis", "payments_paid") == 1
    assert delta("action_required", "payments_to_record") == 2
    assert delta("kpis", "tds_verification_pending") == 1
    # outstanding payable (net of TDS) = (100000-10000-0) + (50000-5000-20000) = 115000
    assert money_delta("financial_summary", "payable_outstanding") == Decimal("115000.00")
    assert money_delta("financial_summary", "tds_on_payable") == Decimal("15000.00")
    assert money_delta("financial_summary", "paid_total") == Decimal("50000.00")
    assert money_delta("financial_summary", "invoice_value_total") == Decimal("187000.00")
    assert money_delta("financial_summary", "invoice_value_approved") == Decimal("7000.00")
    assert money_delta("financial_summary", "tds_total") == Decimal("15700.00")

    chart = {i["status_code"]: i["count"] for i in next(s for s in after["status_summary"] if s["key"] == "invoice_status_distribution")["items"]}
    chart_before = {i["status_code"]: i["count"] for i in next(s for s in before["status_summary"] if s["key"] == "invoice_status_distribution")["items"]}
    for code in ("READY_FOR_PAYMENT", "PARTIALLY_PAID", "PAID", "APPROVED"):
        assert chart.get(code, 0) - chart_before.get(code, 0) == 1
    labels = {i["status_code"]: i["label"] for i in next(s for s in after["status_summary"] if s["key"] == "invoice_status_distribution")["items"]}
    assert labels["READY_FOR_PAYMENT"] == "Ready for Payment"  # from ap.status_master


def test_date_filter_applies_to_trends_only_not_current_state(db, tag):
    window_from, window_to = TODAY - datetime.timedelta(days=6), TODAY
    before = _summary(db, "finance", from_date=window_from, to_date=window_to)
    _invoice(db, tag, "READY_FOR_PAYMENT", net="1000.00", tds="100.00", invoice_date=TODAY - datetime.timedelta(days=2))
    _invoice(db, tag, "READY_FOR_PAYMENT", net="5000.00", tds="500.00", invoice_date=TODAY - datetime.timedelta(days=60))
    after = _summary(db, "finance", from_date=window_from, to_date=window_to)

    assert after["period"] == {"from_date": window_from, "to_date": window_to, "granularity": "day"}

    def trend_total(out, key):
        trend = next(t for t in out["trends"] if t["key"] == key)
        return sum(Decimal(p["value"]) for s in trend["series"] for p in s["points"])

    assert trend_total(after, "invoice_count_trend") - trend_total(before, "invoice_count_trend") == 1
    assert trend_total(after, "invoice_amount_trend") - trend_total(before, "invoice_amount_trend") == Decimal("1000.00")
    assert trend_total(after, "tds_amount_trend") - trend_total(before, "tds_amount_trend") == Decimal("100.00")
    # current-state widgets ignore the period: both invoices count
    assert _value(after, "kpis", "payments_ready") - _value(before, "kpis", "payments_ready") == 2


@pytest.mark.parametrize("span, granularity", [(7, "day"), (90, "week"), (300, "month")])
def test_trend_granularity(span, granularity):
    _, _, g = DashboardService.resolve_period(TODAY - datetime.timedelta(days=span - 1), TODAY)
    assert g == granularity


def test_invalid_periods_rejected():
    with pytest.raises(ValueError, match="on or before"):
        DashboardService.resolve_period(TODAY, TODAY - datetime.timedelta(days=1))
    with pytest.raises(ValueError, match="cannot exceed"):
        DashboardService.resolve_period(TODAY - datetime.timedelta(days=400), TODAY)
    assert DashboardService.resolve_period(None, None)[0] == TODAY - datetime.timedelta(days=29)


def test_recent_activity_is_filtered_to_visible_modules(db):
    out = _summary(db, "procurement_officer", from_date=TODAY - datetime.timedelta(days=365), to_date=TODAY)
    assert all(a["entity_type"] == "purchase_requisition" for a in out["recent_activity"])
    out = _summary(db, "approver", from_date=TODAY - datetime.timedelta(days=365), to_date=TODAY)
    assert all(a["entity_type"] == "invoice" for a in out["recent_activity"])


# =========================================================
# Empty data (fake DAO - every query returns nothing)
# =========================================================

class _EmptyDAO:
    def __getattr__(self, name):
        if name.endswith("_count") or name == "approvals_pending_for_user":
            return lambda *a, **k: 0
        if name in ("status_labels", "invoice_numbers", "pr_numbers", "vendor_names"):
            return lambda *a, **k: {}
        return lambda *a, **k: []


def test_empty_data_dashboard_is_all_zero_and_well_formed():
    service = DashboardService(db=None)
    service.dao = _EmptyDAO()
    service.resolver = type("R", (), {"resolve_user_uuid": lambda self, u: None})()
    all_perms = sorted({p for r in ROLES.values() for p in r["permissions"]})
    out = service.get_summary({"user_id": "1", "permissions": all_perms, "roles": ["Admin"]})
    DashboardSummaryDTO.model_validate(out)
    assert all(k.get("value", 0) == 0 for k in out["kpis"] if k["type"] == "count")
    assert all(k["amounts"] == [] for k in out["kpis"] if k["type"] == "amount")
    assert all(a["value"] == 0 for a in out["action_required"])
    assert all(f["amounts"] == [] for f in out["financial_summary"])
    assert out["recent_activity"] == []


# =========================================================
# Route
# =========================================================

def _client(db, user):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if user is not None:
                request.state.user = user
            request.state.db = db
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(dashboard_route.router, prefix="/dashboard")
    return TestClient(app)


def test_route_requires_authentication_and_validates_dates(db):
    assert _client(db, None).get("/dashboard/summary").status_code == 401
    client = _client(db, _user("finance"))
    response = client.get("/dashboard/summary")
    assert response.status_code == 200 and "payments" in response.json()["sections"]
    bad = client.get("/dashboard/summary", params={"from_date": TODAY.isoformat(), "to_date": (TODAY - datetime.timedelta(days=3)).isoformat()})
    assert bad.status_code == 422


def test_route_ignores_client_supplied_user_id(db):
    """The approval queue is always the caller's - a user_id query param has no effect."""
    client = _client(db, _user("approver", "900000555"))
    plain = client.get("/dashboard/summary").json()
    spoofed = client.get("/dashboard/summary", params={"user_id": "5100031"}).json()
    get = lambda out: next(a["value"] for a in out["action_required"] if a["key"] == "invoices_awaiting_my_approval")
    assert get(plain) == get(spoofed) == 0
