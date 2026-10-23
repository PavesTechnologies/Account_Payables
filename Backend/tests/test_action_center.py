"""Action Center: one prioritised to-do list built from the role dashboards, permission-scoped."""
import datetime
from decimal import Decimal

import pytest

from Backend.Business_Layer.services import action_center_service as acs

TODAY = datetime.date(2026, 10, 12)


def _kpi(key, value):
    return {"key": key, "value": value}


VIEWS = {
    "my_work": {"kpis": [_kpi("to_review", 2), _kpi("returned", 1), _kpi("tds", 0), _kpi("ready_to_send", 3)],
                "oldest": [{"age_days": 4.5}], "term_issue_count": 0},
    "approvals": {"kpis": [_kpi("awaiting", 2), _kpi("oldest", 5.0), _kpi("high_value", 1),
                           _kpi("queue_value", Decimal("300000.00"))]},
    "finance": {
        "action_cards": [
            {"key": "overdue", "count": 1, "amounts": [{"currency_code": "INR", "amount": Decimal("154000")}]},
            {"key": "ready_for_payment", "count": 3, "amounts": [{"currency_code": "INR", "amount": Decimal("400000")}],
             "detail": [{"label": "Due within 7 days", "count": 2, "amounts": [{"currency_code": "INR", "amount": Decimal("310000")}]}]},
            {"key": "approved_not_ready", "count": 1, "amounts": [], "note": "1 blocked by payment-term exceptions"},
            {"key": "partially_paid", "count": 0, "amounts": []},
            {"key": "term_exceptions", "count": 0, "amounts": []},
            {"key": "msme_due", "count": 0, "amounts": []},
        ],
        "receipts_missing": {"count": 0},
        "agreements_expiring": [{"agreement_id": 4, "vendor_id": 17, "vendor_name": "WeWork", "title": "Lease", "days_to_expiry": 5}],
        "tds": {"items": [{"key": "deposit_overdue", "count": 2, "amounts": [{"currency_code": "INR", "amount": Decimal("9000")}]},
                          {"key": "filing_due_soon", "count": 0, "amounts": []}]},
    },
    "management": {"high_value_exceptions": [], "efficiency": {"bottlenecks": []}},
}


@pytest.fixture(autouse=True)
def fake_dashboards(monkeypatch):
    built = []

    def build(self, view, user):
        built.append(view)
        return VIEWS[view]
    monkeypatch.setattr(acs.RoleDashboardService, "__init__", lambda self, db, today=None: setattr(self, "today", TODAY))
    monkeypatch.setattr(acs.RoleDashboardService, "build", build)
    return built


def _user(*codes):
    return {"user_id": "5100020", "permissions": list(codes)}


def test_finance_user_gets_payments_and_tds_ordered_by_urgency(fake_dashboards):
    result = acs.ActionCenterService(db=None).build(_user("PAYMENT_PROCESS", "TDS_TRACKING_UPDATE"))
    keys = [a["key"] for a in result["actions"]]
    assert keys[:2] == ["pay_overdue", "tds_deposit_overdue"]  # critical first, larger amount first
    assert {"pay_due_soon", "mark_ready", "agreement_4"} <= set(keys)
    overdue = result["actions"][0]
    assert overdue["link"] == "/accounts-payable/payments/ready?overdue=1" and overdue["amount"] == Decimal("154000")
    assert result["summary"]["critical"] == 2
    assert next(a for a in result["actions"] if a["key"] == "agreement_4")["link"] == "/accounts-payable/vendors/17"
    assert fake_dashboards == ["finance"]  # never builds views the user can't open
    labels = [q["label"] for q in result["quick_actions"]]
    assert "Pay invoices" in labels and "Record TDS challan" in labels and "Upload invoice" not in labels


def test_ap_executive_and_approver_items():
    result = acs.ActionCenterService(db=None).build(_user("INVOICE_CREATE", "INVOICE_OCR_REVIEW", "INVOICE_APPROVE"))
    by_key = {a["key"]: a for a in result["actions"]}
    assert by_key["approve"]["severity"] == "critical"  # waited 5 days
    assert "1 is high value" in by_key["approve"]["detail"]
    assert by_key["ap_review"]["severity"] == "high" and "4.5 days" in by_key["ap_review"]["detail"]
    assert by_key["ap_returned"]["link"] == "/accounts-payable/invoices?queue=approval"  # returned invoices sit in that tab
    assert "ap_tds" not in by_key  # zero -> not listed


def test_quiet_areas_are_all_clear():
    result = acs.ActionCenterService(db=None).build(_user("AP_MANAGEMENT_DASHBOARD_VIEW"))
    assert result["actions"] == [] and result["all_clear"] == [{"area": "management", "label": "Oversight"}]


def test_no_ap_permissions_means_an_empty_center(fake_dashboards):
    result = acs.ActionCenterService(db=None).build(_user("SOMETHING_ELSE"))
    assert result["actions"] == [] and result["all_clear"] == [] and result["quick_actions"] == []
    assert fake_dashboards == []
