# Backend/Business_Layer/services/role_dashboard_service.py
"""Role dashboards - one point of view per person (APM_AUTOMATION_PLAN.md 3.5):

  my_work      AP Executive: what to process next (intake, OCR review, TDS, send for approval)
  approvals    Approver: what waits for my decision, how fast I decide
  finance      Finance Executive: APReportingService.finance_dashboard (what to pay today)
  management   CEO / Chief Product Officer: financial position, outflow, efficiency, compliance

Each view is granted by the permissions its own module already enforces (plus the new
AP_MANAGEMENT_DASHBOARD_VIEW for management) and computes only its own data - nothing is
returned for the frontend to hide. Money reuses APReportingService's row model, so every
total agrees with the Finance view and the Reports page; one base currency per tile, never
converted.
"""
from __future__ import annotations

import datetime
import statistics
from collections import OrderedDict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from Backend.API_Layer.middleware.permission_base_access import has_permissions
from Backend.Business_Layer.services.ap_reporting_service import (
    APPROVED_LIABILITY,
    BASE_CURRENCY,
    EXCEPTION_STATUSES,
    FINANCE_PERMISSIONS,
    OPEN_LIABILITY,
    REASON_TEXT,
    STAGE_LABELS,
    APReportingService,
    _n,
)
from Backend.Business_Layer.services.approver_resolver_service import ApproverResolverService
from Backend.Business_Layer.utils.vendor_auto_onboarding import get_numeric_system_config
from Backend.Data_Access_Layer.dao.role_dashboard_dao import RoleDashboardDAO

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")

MY_WORK_PERMISSIONS = ["INVOICE_CREATE", "INVOICE_OCR_REVIEW", "INVOICE_SEND_FOR_APPROVAL", "INVOICE_TDS_DETERMINE"]
APPROVER_PERMISSIONS = ["INVOICE_APPROVE", "INVOICE_REJECT", "INVOICE_SEND_BACK"]
MANAGEMENT_PERMISSIONS = ["AP_MANAGEMENT_DASHBOARD_VIEW"]

VIEWS = OrderedDict([
    ("management", {"label": "Management", "permissions": MANAGEMENT_PERMISSIONS}),
    ("finance", {"label": "Finance", "permissions": FINANCE_PERMISSIONS}),
    ("approvals", {"label": "Approvals", "permissions": APPROVER_PERMISSIONS}),
    ("my_work", {"label": "My work", "permissions": MY_WORK_PERMISSIONS}),
])

HIGH_VALUE_CONFIG_KEY = "HIGH_VALUE_INVOICE_THRESHOLD"
DEFAULT_HIGH_VALUE = Decimal("100000")
REVIEW_STATUSES = ("OCR_REVIEW_PENDING", "OCR_FAILED", "RETURNED_FOR_REVIEW", "OCR_REVIEWED")
TREND_MONTHS = 6
LIST_LIMIT = 8


def _money(value) -> Decimal:
    return (Decimal(str(value)) if value is not None else ZERO).quantize(CENTS)


def _date(value) -> Optional[datetime.date]:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime.datetime) else value


def _days_between(start, end) -> Optional[float]:
    if start is None or end is None:
        return None
    if isinstance(start, datetime.datetime) and isinstance(end, datetime.datetime):
        start = start.replace(tzinfo=None)
        end = end.replace(tzinfo=None)
        return max((end - start).total_seconds() / 86400, 0.0)
    return float(max((_date(end) - _date(start)).days, 0))


def _median(values: List[float]) -> Optional[float]:
    return round(statistics.median(values), 1) if values else None


def _kpi(key, label, value, fmt="count", subtitle=None, tone="gray", link=None, currency=BASE_CURRENCY) -> dict:
    return {"key": key, "label": label, "value": value, "format": fmt, "subtitle": subtitle, "tone": tone,
            "link": link, "currency_code": currency}


class RoleDashboardService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()
        self.dao = RoleDashboardDAO(db)
        self.reporting = APReportingService(db, today=self.today)

    # =================================================================
    # Views available to this user
    # =================================================================
    @staticmethod
    def views_for(user) -> List[dict]:
        return [{"key": key, "label": spec["label"]} for key, spec in VIEWS.items()
                if has_permissions(user, spec["permissions"])]

    def build(self, view: str, user) -> Dict[str, Any]:
        spec = VIEWS.get(view)
        if spec is None:
            raise ValueError(f"Unknown dashboard view '{view}'")
        if not has_permissions(user, spec["permissions"]):
            raise PermissionError("You do not have permission to view this dashboard")
        if view == "finance":
            return self.reporting.finance_dashboard(user)
        return getattr(self, f"_{view}")(user)

    # =================================================================
    # Shared helpers
    # =================================================================
    def _month_starts(self, months: int) -> List[datetime.date]:
        cursor = self.today.replace(day=1)
        starts = [cursor]
        for _ in range(months - 1):
            cursor = (cursor - datetime.timedelta(days=1)).replace(day=1)
            starts.insert(0, cursor)
        return starts

    def _high_value(self) -> Decimal:
        value = get_numeric_system_config(self.db, HIGH_VALUE_CONFIG_KEY, DEFAULT_HIGH_VALUE)
        return value if value is not None else DEFAULT_HIGH_VALUE

    def _user_uuid(self, user):
        user_id = str(user.get("user_id") or user.get("sub") or "") or None
        return ApproverResolverService(self.db).resolve_user_uuid(user_id) if user_id else None

    # =================================================================
    # Approver: what waits for my decision
    # =================================================================
    def _approvals(self, user) -> Dict[str, Any]:
        user_uuid = self._user_uuid(user)
        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = self._high_value()
        queue = self.dao.approver_queue(user_uuid)

        items = []
        for invoice, vendor_name, department, level, started_at, currency in queue:
            waiting = _days_between(started_at, now) if started_at else None
            items.append({
                "invoice_id": invoice.invoice_id, "invoice_number": invoice.invoice_number, "vendor_name": vendor_name,
                "department": department or "Unassigned", "level": level, "waiting_days": round(waiting, 1) if waiting is not None else None,
                "amount": _money(invoice.net_amount), "currency_code": currency or BASE_CURRENCY,
                "due_date": invoice.due_date, "high_value": _money(invoice.net_amount) >= threshold,
            })
        base_items = [i for i in items if i["currency_code"] == BASE_CURRENCY]
        queue_value = sum((i["amount"] for i in base_items), ZERO)
        oldest = max((i["waiting_days"] or 0 for i in items), default=0)
        high = [i for i in items if i["high_value"]]

        since = datetime.datetime.combine(self._month_starts(TREND_MONTHS)[0], datetime.time(), tzinfo=datetime.timezone.utc)
        decisions = self.dao.approver_decisions(user_uuid, since)
        month_start = self.today.replace(day=1)
        months = OrderedDict((m.strftime("%Y-%m"), {"period": m.strftime("%Y-%m"), "label": m.strftime("%b"),
                                                    "approved": 0, "rejected": 0, "sent_back": 0})
                             for m in self._month_starts(TREND_MONTHS))
        this_month = {"approved": 0, "rejected": 0, "sent_back": 0}
        turnaround = []
        for decided_at, approver_status, step_status, started_at, *_ in decisions:
            kind = "approved" if approver_status == "APPROVED" else "sent_back" if step_status == "CANCELLED" else "rejected"
            slot = months.get(decided_at.strftime("%Y-%m"))
            if slot:
                slot[kind] += 1
            if _date(decided_at) >= month_start:
                this_month[kind] += 1
            if started_at and _date(decided_at) >= self.today - datetime.timedelta(days=90):
                turnaround.append(_days_between(started_at, decided_at))
        decided_count = sum(this_month.values())

        ageing = [("lt1", "Under 1 day", 0, 1), ("1to3", "1–3 days", 1, 3), ("4to7", "4–7 days", 3, 7), ("gt7", "Over 7 days", 7, None)]
        aging = [{"key": k, "label": label, "count": sum(1 for i in items if i["waiting_days"] is not None
                                                          and i["waiting_days"] >= low and (high_ is None or i["waiting_days"] < high_))}
                 for k, label, low, high_ in ageing]

        by_department = OrderedDict()
        for i in base_items:
            slot = by_department.setdefault(i["department"], {"key": i["department"], "label": i["department"], "amount": ZERO, "count": 0})
            slot["amount"] = _money(slot["amount"] + i["amount"])
            slot["count"] += 1

        return {
            "as_of": self.today, "base_currency": BASE_CURRENCY,
            "kpis": [
                _kpi("awaiting", "Awaiting my approval", len(items), "count", "Oldest first in my queue" if items else "Nothing waiting",
                     "indigo" if items else "gray", "/accounts-payable/invoices?queue=approval"),
                _kpi("queue_value", "Value awaiting decision", queue_value, "money", _n(len(base_items), "invoice"), "blue"),
                _kpi("oldest", "Oldest waiting", round(oldest, 1) if items else None, "days",
                     "Since it reached my level", "rose" if oldest > 3 else "amber" if oldest > 1 else "gray"),
                _kpi("high_value", "High-value pending", len(high), "count",
                     f"At or above {threshold:,.0f} {BASE_CURRENCY}", "amber" if high else "gray"),
                _kpi("decided", "Decided this month", decided_count, "count",
                     f"{this_month['approved']} approved · {this_month['rejected']} rejected · {this_month['sent_back']} sent back",
                     "emerald" if decided_count else "gray"),
                _kpi("turnaround", "My average turnaround", _median(turnaround) if turnaround else None, "days",
                     "Median, last 90 days", "gray"),
            ],
            "queue": items[:25],
            "queue_count": len(items),
            "waiting_aging": aging,
            "decisions_trend": list(months.values()),
            "pending_by_department": sorted(by_department.values(), key=lambda x: x["amount"], reverse=True),
        }

    # =================================================================
    # AP Executive: what to process next
    # =================================================================
    def _my_work(self, user) -> Dict[str, Any]:
        user_id = str(user.get("user_id") or user.get("sub") or "")
        queue = self.dao.work_queue(REVIEW_STATUSES)
        now = datetime.datetime.now()

        def age(invoice) -> float:
            created = invoice.created_at.replace(tzinfo=None) if invoice.created_at else now
            return round(max((now - created).total_seconds() / 86400, 0), 1)

        to_review, returned, failed, tds_to_determine, ready_to_send = [], [], [], [], []
        for invoice, vendor_name, status, tds, currency in queue:
            row = {"invoice_id": invoice.invoice_id, "invoice_number": invoice.invoice_number, "vendor_name": vendor_name,
                   "status_code": status, "age_days": age(invoice), "amount": _money(invoice.net_amount),
                   "currency_code": currency or BASE_CURRENCY, "mine": str(invoice.created_by or "") == user_id}
            if status == "OCR_REVIEW_PENDING":
                to_review.append(row)
            elif status == "RETURNED_FOR_REVIEW":
                returned.append(row)
            elif status == "OCR_FAILED":
                failed.append(row)
            elif status == "OCR_REVIEWED":
                if tds is None or tds.determination_status == "PENDING":
                    tds_to_determine.append(row)
                else:
                    ready_to_send.append(row)

        terms = self.reporting.invoice_figures(REVIEW_STATUSES)
        term_issues = [f for f in terms if f.term_status in EXCEPTION_STATUSES]

        since = datetime.datetime.combine(self._month_starts(TREND_MONTHS)[0], datetime.time())
        intake = OrderedDict((m.strftime("%Y-%m"), {"period": m.strftime("%Y-%m"), "label": m.strftime("%b"), "team": 0, "mine": 0})
                             for m in self._month_starts(TREND_MONTHS))
        for created_at, created_by, _status in self.dao.intake_rows(since):
            slot = intake.get(created_at.strftime("%Y-%m")) if created_at else None
            if slot:
                slot["team"] += 1
                if str(created_by or "") == user_id:
                    slot["mine"] += 1
        this_month = list(intake.values())[-1]

        counts = dict(self.dao.status_counts())
        pipeline = [
            {"key": "review", "label": "In OCR review", "count": len(to_review) + len(returned) + len(failed)},
            {"key": "reviewed", "label": "Reviewed, not sent", "count": len(tds_to_determine) + len(ready_to_send)},
            {"key": "approval", "label": "Awaiting approval", "count": counts.get("PENDING_APPROVAL", 0)},
            {"key": "approved", "label": "Approved / with Finance", "count": counts.get("APPROVED", 0) + counts.get("READY_FOR_PAYMENT", 0)
             + counts.get("PARTIALLY_PAID", 0)},
        ]
        oldest = sorted(to_review + returned + failed + tds_to_determine + ready_to_send, key=lambda r: r["age_days"], reverse=True)

        return {
            "as_of": self.today,
            "kpis": [
                _kpi("to_review", "To review", len(to_review), "count", "Extracted, awaiting OCR review",
                     "indigo" if to_review else "gray", "/accounts-payable/invoices/ocr-review"),
                _kpi("returned", "Returned to AP", len(returned), "count", "Sent back by an approver",
                     "rose" if returned else "gray", "/accounts-payable/invoices?queue=ocr_review"),
                _kpi("tds", "TDS to determine", len(tds_to_determine), "count", "Reviewed, TDS not yet determined",
                     "amber" if tds_to_determine else "gray", "/accounts-payable/invoices"),
                _kpi("ready_to_send", "Ready to send", len(ready_to_send), "count", "Reviewed with TDS, send for approval",
                     "emerald" if ready_to_send else "gray", "/accounts-payable/invoices"),
                _kpi("uploaded", "Received this month", this_month["team"], "count",
                     f"{this_month['mine']} uploaded by me" + (f" · {len(failed)} OCR failed" if failed else ""), "gray",
                     "/accounts-payable/invoices/upload"),
            ],
            "intake_trend": list(intake.values()),
            "pipeline": pipeline,
            "oldest": oldest[:LIST_LIMIT],
            "term_issues": [{"invoice_id": f.invoice_id, "invoice_number": f.invoice_number, "vendor_name": f.vendor_name,
                             "term_status": f.term_status, "reason_text": REASON_TEXT.get(f.term_reason or "", f.term_reason)}
                            for f in term_issues[:LIST_LIMIT]],
            "term_issue_count": len(term_issues),
        }

    # =================================================================
    # Management (CEO / Chief Product Officer): position, outflow, efficiency
    # =================================================================
    def _touchless(self) -> Optional[Dict[str, Any]]:
        """Step B: share of bulk / email PO invoices processed without a person (last 30 days)."""
        try:
            from Backend.Business_Layer.services.ap_automation_service import APAutomationService
            stats = APAutomationService(self.db).stats(30)
        except Exception:
            return None
        if not stats["processed"]:
            return None
        return {k: stats[k] for k in ("processed", "auto_approved", "auto_sent", "exceptions", "touchless_rate")}

    def _management(self, user) -> Dict[str, Any]:
        today = self.today
        base = BASE_CURRENCY
        figures = [f for f in self.reporting.invoice_figures(OPEN_LIABILITY) if f.currency_code == base and f.outstanding > 0]
        liability = sum((f.outstanding for f in figures), ZERO)
        approved = [f for f in figures if f.stage in ("PAYABLE", "APPROVED")]
        approved_total = sum((f.outstanding for f in approved), ZERO)
        overdue = [f for f in approved if f.days_overdue(today)]
        overdue_total = sum((f.outstanding for f in overdue), ZERO)

        windows = [("overdue", "Overdue", None, -1), ("d30", "Next 30 days", 0, 30), ("d60", "31–60 days", 31, 60),
                   ("d90", "61–90 days", 61, 90), ("later", "After 90 days", 91, None), ("unverified", "Due date unverified", None, None)]
        outflow = OrderedDict((k, {"key": k, "label": label, "approved": ZERO, "pipeline": ZERO, "count": 0}) for k, label, *_ in windows)
        for f in figures:
            if not f.due_verified or f.due_date is None:
                key = "unverified"
            else:
                days = (f.due_date - today).days
                key = "overdue" if days < 0 else "d30" if days <= 30 else "d60" if days <= 60 else "d90" if days <= 90 else "later"
            slot = outflow[key]
            field = "approved" if f.stage in ("PAYABLE", "APPROVED") else "pipeline"
            slot[field] = _money(slot[field] + f.outstanding)
            slot["count"] += 1
        due_30 = outflow["d30"]["approved"] + outflow["d30"]["pipeline"]

        # 12-month spend vs paid + on-time / days-to-pay over the last 90 days
        start = self._month_starts(12)[0]
        summary = self.reporting.report_summary({"permissions": FINANCE_PERMISSIONS}, start, today, currency=base)
        recent = self.reporting.report_summary({"permissions": FINANCE_PERMISSIONS}, today - datetime.timedelta(days=90), today, currency=base)
        fy_start = datetime.date(today.year if today.month >= 4 else today.year - 1, 4, 1)
        fy = self.reporting.report_summary({"permissions": FINANCE_PERMISSIONS}, fy_start, today, currency=base)
        kv = lambda s, key: next((k["value"] for k in s["kpis"] if k["key"] == key), None)

        # vendor concentration of what we owe
        by_vendor = OrderedDict()
        for f in figures:
            slot = by_vendor.setdefault(f.vendor_id, {"key": str(f.vendor_id), "label": f.vendor_name, "amount": ZERO, "count": 0})
            slot["amount"] = _money(slot["amount"] + f.outstanding)
            slot["count"] += 1
        ranked = sorted(by_vendor.values(), key=lambda x: x["amount"], reverse=True)
        top5 = sum((v["amount"] for v in ranked[:5]), ZERO)
        top5_share = round(float(top5 / liability * 100), 1) if liability else None

        # process efficiency: received -> approved -> paid (last 180 days), approval bottlenecks
        since = datetime.datetime.combine(today - datetime.timedelta(days=180), datetime.time())
        to_approve, to_pay, end_to_end = [], [], []
        for _id, created_at, approved_at, paid_on in self.dao.cycle_rows(since):
            if approved_at:
                to_approve.append(_days_between(created_at.replace(tzinfo=None), approved_at.replace(tzinfo=None)))
            if approved_at and paid_on:
                to_pay.append(_days_between(_date(approved_at), paid_on))
            if paid_on:
                end_to_end.append(_days_between(_date(created_at), paid_on))
        now = datetime.datetime.now(datetime.timezone.utc)
        bottlenecks = OrderedDict()
        for level, department, started_at, amount, currency in self.dao.pending_steps():
            key = (department or "Unassigned", level)
            slot = bottlenecks.setdefault(key, {"department": key[0], "level": level, "count": 0, "waits": [], "amount": ZERO})
            slot["count"] += 1
            if started_at:
                slot["waits"].append(_days_between(started_at, now))
            if (currency or base) == base:
                slot["amount"] = _money(slot["amount"] + _money(amount))
        bottleneck_rows = sorted(
            ({"department": b["department"], "level": b["level"], "count": b["count"], "amount": b["amount"],
              "avg_wait_days": round(sum(b["waits"]) / len(b["waits"]), 1) if b["waits"] else None,
              "max_wait_days": round(max(b["waits"]), 1) if b["waits"] else None} for b in bottlenecks.values()),
            key=lambda r: (r["max_wait_days"] or 0), reverse=True)

        # compliance + high-value exceptions
        dashboard = self.reporting.finance_dashboard({"permissions": FINANCE_PERMISSIONS + ["TDS_TRACKING_VIEW"]})
        card = {c["key"]: c for c in dashboard["action_cards"]}
        tds_overdue = sum(i["count"] for i in dashboard["tds"]["items"] if "overdue" in i["key"])
        threshold = self._high_value()
        high_value = sorted([f for f in figures if f.outstanding >= threshold and
                             (f.days_overdue(today) or f.term_status in EXCEPTION_STATUSES)],
                            key=lambda f: f.outstanding, reverse=True)[:LIST_LIMIT]

        on_time = kv(recent, "on_time")
        return {
            "as_of": today, "base_currency": base,
            "kpis": [
                _kpi("liability", "Total AP liability", liability, "money", f"{_n(len(figures), 'open invoice')} · net of TDS", "indigo",
                     "/accounts-payable/reports?report=outstanding_payables"),
                _kpi("due_30", "Due in next 30 days", due_30, "money",
                     f"60 d: {outflow['d60']['approved'] + outflow['d60']['pipeline']:,.0f} · 90 d: {outflow['d90']['approved'] + outflow['d90']['pipeline']:,.0f}",
                     "blue", "/accounts-payable/reports?report=expected_payments"),
                _kpi("overdue", "Overdue", overdue_total, "money",
                     f"{round(float(overdue_total / approved_total * 100)) if approved_total else 0}% of approved payables", "rose",
                     "/accounts-payable/reports?report=ageing"),
                _kpi("on_time", "Paid on time", on_time, "percent", "Last 90 days",
                     "emerald" if (on_time or 0) >= 90 else "amber" if (on_time or 0) >= 70 else "rose"),
                _kpi("days_to_pay", "Average days to pay", kv(recent, "days_to_pay"), "days", "Invoice date to payment, last 90 days"),
                _kpi("spend_fy", "Spend this fiscal year", kv(fy, "invoiced"), "money", f"Since {fy_start:%d %b %Y}", "gray",
                     "/accounts-payable/reports"),
            ],
            "outflow": list(outflow.values()),
            "spend_trend": summary["monthly"],
            "by_department": summary["by_department"],
            "vendor_exposure": ranked[:6],
            "top5_share": top5_share,
            "efficiency": {
                "median_days_to_approve": _median(to_approve),
                "median_days_approval_to_payment": _median(to_pay),
                "median_days_end_to_end": _median(end_to_end),
                "sample": len(end_to_end),
                "pending_approvals": sum(r["count"] for r in bottleneck_rows),
                "bottlenecks": bottleneck_rows[:LIST_LIMIT],
                "touchless": self._touchless(),
            },
            "compliance": [
                {"key": "term_exceptions", "label": "Payment-term exceptions", "count": dashboard["term_exception_count"],
                 "amount": next((a["amount"] for a in card["term_exceptions"]["amounts"] if a["currency_code"] == base), ZERO)},
                {"key": "msme", "label": "MSME statutory deadline ≤ 7 days", "count": card["msme_due"]["count"],
                 "amount": next((a["amount"] for a in card["msme_due"]["amounts"] if a["currency_code"] == base), ZERO)},
                {"key": "tds_overdue", "label": "TDS deposit / statement overdue", "count": tds_overdue, "amount": None},
                {"key": "receipts", "label": "Payments without a receipt (90 days)", "count": dashboard["receipts_missing"]["count"], "amount": None},
            ],
            "high_value_exceptions": [{
                "invoice_id": f.invoice_id, "invoice_number": f.invoice_number, "vendor_name": f.vendor_name,
                "outstanding": f.outstanding, "currency_code": f.currency_code, "stage": STAGE_LABELS.get(f.stage, f.stage),
                "days_overdue": f.days_overdue(today) or 0, "term_status": f.term_status,
                "issue": "Overdue" if f.days_overdue(today) else "Payment-term exception",
            } for f in high_value],
            "high_value_threshold": threshold,
            "note": "Read-only management view. Expected outflow is based on recorded invoices and due dates, "
                    "not a guaranteed cash-flow forecast.",
        }
