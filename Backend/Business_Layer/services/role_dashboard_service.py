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
import logging
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


logger = logging.getLogger(__name__)

def _kpi(key, label, value, fmt="count", subtitle=None, tone="gray", link=None, currency=BASE_CURRENCY, help=None) -> dict:
    return {"key": key, "label": label, "value": value, "format": fmt, "subtitle": subtitle, "tone": tone,
            "link": link, "currency_code": currency, "help": help}


def _inr(amount) -> str:
    """Rupees the way Indian finance reads them: ₹1.24 Cr, ₹30.6 L, ₹45,530."""
    value = float(amount or 0)
    if abs(value) >= 1_00_00_000:
        return f"₹{value / 1_00_00_000:.2f} Cr"
    if abs(value) >= 1_00_000:
        return f"₹{value / 1_00_000:.1f} L"
    whole = f"{abs(round(value)):d}"
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    text = ",".join(([head] if head else []) + groups + [tail]) if len(whole) > 3 else whole
    return f"{'-' if value < 0 else ''}₹{text}"


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
        # Segregation of duties: invoices this user prepared stay listed but can't be approved by them.
        from Backend.Business_Layer.services.segregation_of_duties_service import SegregationOfDutiesService
        blocked = SegregationOfDutiesService(self.db).blocked_for_approval(
            [row[0].invoice_id for row in queue], str(user.get("user_id") or user.get("sub") or ""))

        items = []
        for invoice, vendor_name, department, level, started_at, currency in queue:
            waiting = _days_between(started_at, now) if started_at else None
            items.append({
                "invoice_id": invoice.invoice_id, "invoice_number": invoice.invoice_number, "vendor_name": vendor_name,
                "department": department or "Unassigned", "level": level, "waiting_days": round(waiting, 1) if waiting is not None else None,
                "amount": _money(invoice.net_amount), "currency_code": currency or BASE_CURRENCY,
                "due_date": invoice.due_date, "high_value": _money(invoice.net_amount) >= threshold,
                "sod_blocked": invoice.invoice_id in blocked,
            })
        conflicts = [i for i in items if i["sod_blocked"]]
        items = [i for i in items if not i["sod_blocked"]]
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
                _kpi("awaiting", "Awaiting my approval", len(items), "count",
                     (f"{len(conflicts)} more you prepared - another approver decides" if conflicts else
                      "Oldest first in my queue" if items else "Nothing waiting"),
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
            "sod_blocked": conflicts[:25],
            "sod_blocked_count": len(conflicts),
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
        owners, assignment_in_use = self._owners([row[0].invoice_id for row in queue])
        for invoice, vendor_name, status, tds, currency in queue:
            row = {"invoice_id": invoice.invoice_id, "invoice_number": invoice.invoice_number, "vendor_name": vendor_name,
                   "status_code": status, "age_days": age(invoice), "amount": _money(invoice.net_amount),
                   "currency_code": currency or BASE_CURRENCY, "mine": str(invoice.created_by or "") == user_id,
                   "assignee": owners.get(invoice.invoice_id),
                   "assigned_to_me": (owners.get(invoice.invoice_id) or {}).get("user_id") == user_id}
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
            {"key": "review", "label": "To review", "count": len(to_review) + len(returned) + len(failed)},
            {"key": "reviewed", "label": "Reviewed, not yet sent", "count": len(tds_to_determine) + len(ready_to_send)},
            {"key": "approval", "label": "Awaiting approval", "count": counts.get("PENDING_APPROVAL", 0)},
            {"key": "approved", "label": "Approved / with Finance", "count": counts.get("APPROVED", 0) + counts.get("READY_FOR_PAYMENT", 0)
             + counts.get("PARTIALLY_PAID", 0)},
        ]
        oldest = sorted(to_review + returned + failed + tds_to_determine + ready_to_send, key=lambda r: r["age_days"], reverse=True)
        open_rows = to_review + returned + failed + tds_to_determine + ready_to_send
        assignment_kpis = []
        unassigned = []
        if assignment_in_use:
            mine_open = [r for r in open_rows if r["assigned_to_me"]]
            unassigned = [r for r in open_rows if r["assignee"] is None]  # for the AP lead (AP Team page), not a card
            assignment_kpis = [
                _kpi("assigned_to_me", "Assigned to me", len(mine_open), "count",
                     f"{sum(1 for r in mine_open if r['status_code'] == 'RETURNED_FOR_REVIEW')} sent back to me" if mine_open else "Nothing assigned",
                     "indigo" if mine_open else "gray", "/accounts-payable/invoices/review-workbench?assigned=me"),
            ]
        ready = tds_to_determine + ready_to_send  # TDS is worked out on review - both are "reviewed, send it"

        return {
            "as_of": self.today,
            "kpis": assignment_kpis + [
                _kpi("to_review", "To review", len(to_review), "count", "New invoices to check",
                     "indigo" if to_review else "gray", "/accounts-payable/invoices/review-workbench"),
                _kpi("returned", "Sent back for correction", len(returned), "count", "An approver asked for changes",
                     "rose" if returned else "gray", "/accounts-payable/invoices?queue=approval"),
                _kpi("ready_to_send", "Ready to send", len(ready), "count", "Reviewed - send for approval",
                     "emerald" if ready else "gray", "/accounts-payable/invoices/review-workbench"),
                _kpi("awaiting_approval", "Waiting for approval", counts.get("PENDING_APPROVAL", 0), "count", "With the approvers",
                     "gray", "/accounts-payable/invoices?queue=approval"),
                _kpi("uploaded", "Received this month", this_month["team"], "count",
                     f"{this_month['mine']} uploaded by me" + (f" · {len(failed)} couldn't be read" if failed else ""), "gray",
                     "/accounts-payable/invoices"),
            ],
            "unassigned_count": len(unassigned),
            "intake_trend": list(intake.values()),
            "pipeline": pipeline,
            "oldest": oldest[:LIST_LIMIT],
            "term_issues": [{"invoice_id": f.invoice_id, "invoice_number": f.invoice_number, "vendor_name": f.vendor_name,
                             "term_status": f.term_status, "reason_text": REASON_TEXT.get(f.term_reason or "", f.term_reason)}
                            for f in term_issues[:LIST_LIMIT]],
            "term_issue_count": len(term_issues),
        }

    def _owners(self, invoice_ids):
        """(invoice -> owner, whether work assignment is in use). Optional: never breaks the view."""
        try:
            from Backend.Business_Layer.services.work_assignment_service import WorkAssignmentService
            service = WorkAssignmentService(self.db)
            owners = service.owners(invoice_ids)
            return owners, bool(owners) or bool(service.rules())
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return {}, False

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

    def _compliance_items(self, card, dashboard, tds_overdue, base) -> List[dict]:
        amount = lambda key: next((a["amount"] for a in card[key]["amounts"] if a["currency_code"] == base), ZERO)
        return [
            {"key": "term_exceptions", "label": "Invoices whose payment terms don't match the contract",
             "count": dashboard["term_exception_count"], "amount": amount("term_exceptions")},
            {"key": "msme", "label": "MSME vendors to pay within 7 days (legal limit)", "count": card["msme_due"]["count"],
             "amount": amount("msme_due")},
            {"key": "tds_overdue", "label": "TDS deposits / returns overdue", "count": tds_overdue, "amount": None},
        ] + self._gst_compliance()

    def _highlights(self, liability, figures, ranked, due_30, estimated_30, overdue_total, overdue_count, overdue_waiting,
                    bottlenecks, on_time, days_to_pay, compliance, card, base) -> List[dict]:
        """'AP at a glance': a few plain sentences a CFO can act on, worst news first. tone: good / warn / bad / info."""
        out: List[dict] = []
        if overdue_total > 0:
            out.append({"tone": "bad", "link": "/accounts-payable/reports?report=ageing",
                        "text": f"{_inr(overdue_total)} on {_n(overdue_count, 'approved invoice')} is past its due date - pay it now."})
        if overdue_waiting > 0:
            worst = max(bottlenecks, key=lambda b: b["max_wait_days"] or 0, default=None)
            where = (f" The longest wait is {worst['max_wait_days']:g} days with {worst['department']} (level {worst['level']})."
                     if worst and worst["max_wait_days"] else "")
            out.append({"tone": "warn", "link": "/accounts-payable/invoices?queue=approval",
                        "text": f"{_inr(overdue_waiting)} of invoices are already past their due date but still in review or "
                                f"approval - they cannot be paid until approved.{where}"})
        msme = card["msme_due"]["count"]
        if msme:
            out.append({"tone": "bad", "link": "/accounts-payable/reports?report=msme_payments",
                        "text": f"{_n(msme, 'MSME invoice')} must be paid within 7 days to stay within the 45-day legal limit."})
        vendors = len(ranked)
        out.append({"tone": "info", "link": "/accounts-payable/reports?report=outstanding_payables",
                    "text": f"We owe {_inr(liability)} to {_n(vendors, 'vendor')} across {_n(len(figures), 'open invoice')}"
                            + (f" - {ranked[0]['label'].title()} is the largest at {_inr(ranked[0]['amount'])}." if ranked else ".")})
        if due_30 > 0:
            out.append({"tone": "info", "link": "/accounts-payable/reports?report=expected_payments",
                        "text": f"Keep {_inr(due_30)} ready for the next 30 days"
                                + (f" ({_inr(estimated_30)} of it is expected rent, subscriptions and TDS not yet invoiced)." if estimated_30 else ".")})
        if on_time is not None:
            good = on_time >= 90
            out.append({"tone": "good" if good else "warn", "link": "/accounts-payable/reports?report=payments_made",
                        "text": f"{on_time:g}% of invoices were paid on time in the last 90 days"
                                + (f", taking {days_to_pay:g} days on average." if days_to_pay is not None else ".")
                                + ("" if good else " Aim for 90% or more.")})
        gst = {c["key"]: c for c in compliance}
        if gst.get("gst_claim") and gst["gst_claim"]["count"]:
            claim = gst["gst_claim"]
            due, period = claim.get("due"), claim.get("period")
            when = (f"overdue since {due:%d %b}" if due and due < self.today else f"claim by {due:%d %b}") if due else ""
            text = f"Recover {_inr(claim['amount'])} of GST paid to vendors" + (f" for {period:%b %Y}" if period else "") + (f" - {when}." if when else ".")
            if gst.get("gst_at_risk") and gst["gst_at_risk"]["count"]:
                text += f" {_inr(gst['gst_at_risk']['amount'])} of credit is at risk."
            out.append({"tone": "bad" if due and due < self.today else "info", "link": "/accounts-payable/gst", "text": text})
        return out

    def _cfo_insights(self, receipts_missing) -> Dict[str, Any]:
        """DPO, control exceptions and month-end accruals (cfo_insights_service) - never breaks the dashboard."""
        from Backend.Business_Layer.services.cfo_insights_service import CfoInsightsService
        svc = CfoInsightsService(self.db, today=self.today)
        out = {"dpo": {}, "controls": [], "accruals": None}
        for key, fn in (("dpo", svc.dpo), ("controls", lambda: svc.controls(receipts_missing)), ("accruals", svc.accruals)):
            try:
                out[key] = fn()
            except Exception:
                logger.exception("CFO insight %s unavailable", key)
                try:
                    self.db.rollback()
                except Exception:
                    pass
        if out["accruals"]:  # the dashboard shows the groups; the line items are in the report
            out["accruals"] = {**out["accruals"], "groups": [{k: v for k, v in g.items() if k != "items"} for g in out["accruals"]["groups"]]}
        return out

    @staticmethod
    def _insight_highlights(insights) -> List[dict]:
        out = []
        alarms = {c["key"]: c["count"] for c in insights["controls"] if c.get("count")}
        if alarms.get("paid_after_bank_change"):
            out.append({"tone": "bad", "link": "/accounts-payable/reports?report=control_exceptions",
                        "text": f"{_n(alarms['paid_after_bank_change'], 'payment')} went out within a week of the vendor changing "
                                "bank details - confirm each change with the vendor by phone."})
        if alarms.get("duplicates"):
            out.append({"tone": "warn", "link": "/accounts-payable/reports?report=control_exceptions",
                        "text": f"{_n(alarms['duplicates'], 'open invoice')} look like duplicates - check before paying twice."})
        dpo = insights["dpo"]
        if dpo.get("value") is not None and dpo.get("band") in ("low", "high"):
            out.append({"tone": "warn", "link": "/accounts-payable/reports?report=ageing",
                        "text": f"We take {dpo['value']:g} days on average to pay vendors (target {dpo['target_min']}-{dpo['target_max']})"
                                + (" - cash is leaving earlier than needed." if dpo["band"] == "low"
                                   else " - vendors are waiting longer than planned; approvals are the usual cause.")})
        acc = insights["accruals"]
        if acc and acc["total"] > 0:
            out.append({"tone": "info", "link": "/accounts-payable/reports?report=month_end_accruals",
                        "text": f"Month-end ({acc['as_of']:%d %b}): {_inr(acc['total'])} of costs are already incurred but not yet "
                                "approved payables - book them as accruals."})
        return out

    def _gst_compliance(self) -> List[dict]:
        """GST input credit for management: what to claim in the open GSTR-3B, and what could be lost."""
        try:
            from Backend.Business_Layer.services.gst_itc_service import GstItcService
            g = GstItcService(self.db, today=self.today).position()
        except Exception:  # GST register not migrated / unavailable - the rest of the dashboard still loads
            try:
                self.db.rollback()
            except Exception:
                pass
            return []
        return [
            {"key": "gst_claim", "label": f"GST input credit to claim ({g['claim_period']:%b %Y}, due {g['claim_due']:%d %b})",
             "count": g["claimable_count"], "amount": g["claimable"], "tone": "good",
             "period": g["claim_period"], "due": g["claim_due"]},
            {"key": "gst_at_risk", "label": "GST credit at risk (180-day rule / IRN / GSTR-2B)", "count": g["at_risk_count"],
             "amount": g["at_risk"]},
        ]

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
        outflow = OrderedDict((k, {"key": k, "label": label, "approved": ZERO, "pipeline": ZERO, "recurring": ZERO, "tds": ZERO,
                                   "count": 0}) for k, label, *_ in windows)
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
        # estimates: recurring invoices not yet received + TDS to deposit (cash_forecast_service)
        for e in self.reporting._estimates(today + datetime.timedelta(days=90), figures):
            days = (e["due_date"] - today).days
            key = "overdue" if days < 0 else "d30" if days <= 30 else "d60" if days <= 60 else "d90"
            field = "recurring" if e["kind"] == "RECURRING" else "tds"
            outflow[key][field] = _money(outflow[key][field] + e["amount"])
        window_total = lambda k: outflow[k]["approved"] + outflow[k]["pipeline"] + outflow[k]["recurring"] + outflow[k]["tds"]
        due_30 = window_total("d30")
        estimated_30 = outflow["d30"]["recurring"] + outflow["d30"]["tds"]

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
        days_to_pay = kv(recent, "days_to_pay")
        compliance = self._compliance_items(card, dashboard, tds_overdue, base)
        insights = self._cfo_insights(dashboard["receipts_missing"]["count"])
        dpo = insights["dpo"]
        overdue_waiting = outflow["overdue"]["pipeline"]
        highlights = self._highlights(liability, figures, ranked, due_30, estimated_30, overdue_total, len(overdue),
                                      overdue_waiting, bottleneck_rows, on_time, days_to_pay, compliance, card, base)
        highlights[1:1] = self._insight_highlights(insights)
        return {
            "as_of": today, "base_currency": base,
            "highlights": highlights,
            "kpis": [
                _kpi("liability", "Total we owe vendors", liability, "money",
                     f"{_n(len(figures), 'open invoice')} · {_n(len(ranked), 'vendor')} · after TDS", "indigo",
                     "/accounts-payable/reports?report=outstanding_payables",
                     help="Everything recorded and not yet paid - including invoices still in review or approval. "
                          "TDS is left out because it is paid to the government, not the vendor."),
                _kpi("due_30", "Cash needed next 30 days", due_30, "money",
                     f"{_inr(estimated_30)} of it estimated · next 31-60 days {_inr(window_total('d60'))}",
                     "blue", "/accounts-payable/reports?report=expected_payments",
                     help="Invoices falling due in the next 30 days, plus estimates for rent and subscriptions whose "
                          "invoice has not arrived yet and TDS to deposit by the 7th. Keep this much ready in the bank."),
                _kpi("overdue", "Overdue", overdue_total, "money",
                     f"{_n(len(overdue), 'approved invoice')} past due · "
                     f"{round(float(overdue_total / approved_total * 100)) if approved_total else 0}% of approved", "rose",
                     "/accounts-payable/reports?report=ageing",
                     help="Approved invoices past their due date and still unpaid. Late payment risks vendor goodwill, "
                          "and for MSME vendors interest and a lost tax deduction."),
                _kpi("on_time", "Paid on time", on_time, "percent", "Share of invoices paid by the due date, last 90 days",
                     "emerald" if (on_time or 0) >= 90 else "amber" if (on_time or 0) >= 70 else "rose",
                     help="Of the invoices paid in the last 90 days, how many were paid on or before their due date. "
                          "90% or more is healthy."),
                _kpi("dpo", "Days to pay vendors (DPO)", dpo.get("value"), "days",
                     ((f"Target {dpo['target_min']}-{dpo['target_max']} days" if dpo.get("target_min") else "Not enough invoices yet")
                      + (f" · {dpo['previous']:g} d 90 days ago" if dpo.get("previous") is not None else "")
                      + (f" · avg {days_to_pay:g} d per paid invoice" if days_to_pay is not None else "")),
                     {"within": "emerald", "low": "amber", "high": "rose"}.get(dpo.get("band"), "gray"),
                     "/accounts-payable/reports?report=ageing",
                     help="Days Payable Outstanding: how long, on average, the company holds cash before paying vendors "
                          "(what we owe / what vendors invoiced in the last 90 days x 90). Below the target, cash leaves "
                          "earlier than needed; above it, vendors wait too long and relationships or MSME rules suffer."),
                _kpi("spend_fy", "Spend this financial year", kv(fy, "invoiced"), "money", f"Invoices dated since {fy_start:%d %b %Y}", "gray",
                     "/accounts-payable/reports",
                     help="Total value of vendor invoices received this financial year (April to March), including GST."),
            ],
            "outflow": list(outflow.values()),
            "spend_trend": summary["monthly"],
            "by_department": summary["by_department"],
            "vendor_exposure": ranked[:6],
            "top5_share": top5_share,
            "vendor_count": len(ranked),
            "efficiency": {
                "median_days_to_approve": _median(to_approve),
                "median_days_approval_to_payment": _median(to_pay),
                "median_days_end_to_end": _median(end_to_end),
                "sample": len(end_to_end),
                "pending_approvals": sum(r["count"] for r in bottleneck_rows),
                "bottlenecks": bottleneck_rows[:LIST_LIMIT],
                "touchless": self._touchless(),
            },
            "compliance": compliance,
            "controls": insights["controls"],
            "accruals": insights["accruals"],
            "high_value_exceptions": [{
                "invoice_id": f.invoice_id, "invoice_number": f.invoice_number, "vendor_name": f.vendor_name,
                "outstanding": f.outstanding, "currency_code": f.currency_code, "stage": STAGE_LABELS.get(f.stage, f.stage),
                "days_overdue": f.days_overdue(today) or 0, "term_status": f.term_status,
                "issue": "Overdue" if f.days_overdue(today) else "Payment-term exception",
            } for f in high_value],
            "high_value_threshold": threshold,
            "note": "A planning figure: recorded invoices by due date, plus estimates for rent and subscriptions not yet "
                    "invoiced and TDS to deposit. Nothing here is posted to the books.",
        }
