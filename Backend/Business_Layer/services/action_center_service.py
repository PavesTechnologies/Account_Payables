# Backend/Business_Layer/services/action_center_service.py
"""Action Center - the top of the AP dashboard: "what should I do now?"

One prioritised to-do list across every AP area this user works in (AP review, approvals,
payments, TDS, management), each line with a count, an amount, a plain-language reason and a link
straight to the filtered list where the work is done. Nothing new is calculated here: every
number comes from the role dashboards (RoleDashboardService / APReportingService.finance_dashboard)
so the Action Center always agrees with the tiles below it.

Severity:  critical - money or compliance at risk now (overdue, statutory deadline passed)
           high     - due soon or someone is waiting on this user
           normal   - routine work in the queue
Areas the user works in with nothing to do are returned as "all clear", and the quick actions
are the shortcuts this user's permissions allow.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from Backend.API_Layer.middleware.permission_base_access import has_permissions
from Backend.Business_Layer.services.ap_reporting_service import (
    BASE_CURRENCY,
    FINANCE_PERMISSIONS,
    TDS_PERMISSIONS,
)
from Backend.Business_Layer.services.role_dashboard_service import (
    APPROVER_PERMISSIONS,
    MANAGEMENT_PERMISSIONS,
    MY_WORK_PERMISSIONS,
    RoleDashboardService,
)

SEVERITY_ORDER = {"critical": 0, "high": 1, "normal": 2}
ZERO = Decimal("0.00")

AREAS = {
    "ap": "Invoice processing",
    "approvals": "Approvals",
    "payments": "Payments",
    "tds": "TDS",
    "gst": "GST input credit",
    "management": "Oversight",
}

# (permission codes - any one, label, route, area)
QUICK_ACTIONS = [
    (["INVOICE_CREATE"], "Upload invoice", "/accounts-payable/invoices/upload", "ap"),
    (["INVOICE_BULK_UPLOAD"], "Bulk upload invoices", "/accounts-payable/invoices/bulk-upload", "ap"),
    (["INVOICE_OCR_REVIEW", "INVOICE_SEND_FOR_APPROVAL"], "Review & send", "/accounts-payable/invoices/review-workbench", "ap"),
    (APPROVER_PERMISSIONS, "Approval queue", "/accounts-payable/invoices?queue=approval", "approvals"),
    (["PAYMENT_PROCESS"], "Pay invoices", "/accounts-payable/payments/ready", "payments"),
    (["PAYMENT_PROCESS", "TDS_TRACKING_UPDATE"], "Bulk import payments / challans", "/accounts-payable/bulk-import", "payments"),
    (["TDS_TRACKING_UPDATE"], "Record TDS challan", "/accounts-payable/tds/challans/new", "tds"),
    (FINANCE_PERMISSIONS + ["AP_MANAGEMENT_REPORTS_VIEW"], "Reports", "/accounts-payable/reports", "management"),
]


def _base_amount(amounts: List[dict]) -> Decimal:
    """The base-currency figure of a multi-currency amount list."""
    return next((Decimal(str(a["amount"])) for a in amounts or [] if a.get("currency_code") == BASE_CURRENCY), ZERO)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _action(key, area, severity, title, detail, count, link, cta, amount=None) -> Dict[str, Any]:
    return {"key": key, "area": area, "area_label": AREAS[area], "severity": severity, "title": title,
            "detail": detail, "count": count, "amount": amount, "currency_code": BASE_CURRENCY,
            "link": link, "cta": cta}


class ActionCenterService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.dashboards = RoleDashboardService(db, today=today)
        self.today = self.dashboards.today

    def build(self, user) -> Dict[str, Any]:
        actions: List[dict] = []
        areas: List[str] = []
        if has_permissions(user, MY_WORK_PERMISSIONS):
            areas.append("ap")
            actions += self._ap(self.dashboards.build("my_work", user))
        if has_permissions(user, APPROVER_PERMISSIONS):
            areas.append("approvals")
            actions += self._approvals(self.dashboards.build("approvals", user))
        finance = None
        if has_permissions(user, FINANCE_PERMISSIONS):
            areas.append("payments")
            finance = self.dashboards.build("finance", user)
            actions += self._payments(finance)
            actions += self._notes()
            if finance.get("tds"):
                areas.append("tds")
                actions += self._tds(finance["tds"])
        if has_permissions(user, MANAGEMENT_PERMISSIONS):
            areas.append("management")
            actions += self._management(self.dashboards.build("management", user))
        if has_permissions(user, MY_WORK_PERMISSIONS + FINANCE_PERMISSIONS):
            actions += self._recurring()
        if has_permissions(user, FINANCE_PERMISSIONS + ["GST_ITC_VIEW", "GST_ITC_MANAGE"]):
            gst = self._gst()
            if gst is not None:
                areas.append("gst")
                actions += gst

        actions.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], -(a["amount"] or 0), -a["count"]))
        busy = {a["area"] for a in actions}
        return {
            "as_of": self.today,
            "base_currency": BASE_CURRENCY,
            "summary": {sev: sum(1 for a in actions if a["severity"] == sev) for sev in SEVERITY_ORDER},
            "actions": actions,
            "all_clear": [{"area": a, "label": AREAS[a]} for a in areas if a not in busy],
            "quick_actions": [{"label": label, "link": link, "area": area}
                              for codes, label, link, area in QUICK_ACTIONS if has_permissions(user, codes)],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _kpis(view) -> Dict[str, dict]:
        return {k["key"]: k for k in view.get("kpis", [])}

    def _ap(self, view) -> List[dict]:
        k = self._kpis(view)
        out = []
        if "assigned_to_me" in k:  # work assignment in use: my queue first, then the unclaimed pool
            mine, pool = k["assigned_to_me"]["value"], k["unassigned"]["value"]
            if mine:
                out.append(_action("ap_mine", "ap", "high", f"Work {_plural(mine, 'invoice')} assigned to you",
                                   k["assigned_to_me"]["subtitle"] + " - review, fix or send each one.", mine,
                                   "/accounts-payable/invoices/review-workbench?assigned=me", "Open my queue"))
            if pool:
                out.append(_action("ap_unassigned", "ap", "normal", f"Claim {_plural(pool, 'unassigned invoice')}",
                                   "No one owns these yet - claim them so they don't wait.", pool,
                                   "/accounts-payable/invoices/review-workbench?assigned=unassigned", "Claim"))
        oldest = max((r["age_days"] for r in view.get("oldest", [])), default=0)
        if n := k["returned"]["value"]:
            out.append(_action("ap_returned", "ap", "high", f"Fix and resubmit {_plural(n, 'returned invoice')}",
                               "An approver sent these back with a comment - read it, correct the invoice, resubmit.",
                               n, "/accounts-payable/invoices?queue=ocr_review", "Open returned"))
        if n := k["to_review"]["value"]:
            out.append(_action("ap_review", "ap", "high" if oldest > 2 else "normal",
                               f"Review {_plural(n, 'uploaded invoice')}",
                               "OCR has read these - check the fields, set department / category, save."
                               + (f" Oldest waiting {oldest:g} days." if oldest > 2 else ""),
                               n, "/accounts-payable/invoices/review-workbench", "Review now"))
        if n := k["tds"]["value"]:
            out.append(_action("ap_tds", "ap", "normal", f"Set TDS on {_plural(n, 'reviewed invoice')}",
                               "TDS must be determined before an invoice can go for approval.",
                               n, "/accounts-payable/invoices/review-workbench", "Determine TDS"))
        if n := k["ready_to_send"]["value"]:
            out.append(_action("ap_send", "ap", "normal", f"Send {_plural(n, 'invoice')} for approval",
                               "Reviewed with TDS set - one click sends them to the right approver.",
                               n, "/accounts-payable/invoices/review-workbench", "Send for approval"))
        if n := view.get("term_issue_count"):
            out.append(_action("ap_terms", "ap", "normal", f"Check payment terms on {_plural(n, 'invoice')}",
                               "The invoice terms differ from the agreement / PO - correct them at review.",
                               n, "/accounts-payable/invoices/review-workbench", "Check terms"))
        return out

    def _approvals(self, view) -> List[dict]:
        k = self._kpis(view)
        n = k["awaiting"]["value"]
        if not n:
            return []
        oldest = k["oldest"]["value"] or 0
        high = k["high_value"]["value"]
        severity = "critical" if oldest > 3 else "high" if oldest > 1 else "normal"
        detail = f"Oldest has waited {oldest:g} days." if oldest else "Just arrived."
        if high:
            detail += f" {high} {'is' if high == 1 else 'are'} high value."
        return [_action("approve", "approvals", severity, f"Approve {_plural(n, 'invoice')} waiting for you",
                        detail + " Payment can't start until you decide.", n,
                        "/accounts-payable/invoices?queue=approval", "Open approval queue",
                        amount=k["queue_value"]["value"])]

    def _payments(self, view) -> List[dict]:
        cards = {c["key"]: c for c in view.get("action_cards", [])}
        out = []

        def card(key):
            c = cards.get(key)
            return (c["count"], _base_amount(c["amounts"]), c) if c else (0, ZERO, None)

        n, amount, _ = card("overdue")
        if n:
            out.append(_action("pay_overdue", "payments", "critical", f"Pay {_plural(n, 'overdue invoice')}",
                               "Past the due date - late payment risks vendor relations and late fees.",
                               n, "/accounts-payable/payments/ready?overdue=1", "Pay now", amount))
        n, amount, c = card("ready_for_payment")
        due_soon = next((d for d in (c or {}).get("detail", []) if d["label"].startswith("Due within")), None)
        if due_soon and due_soon["count"]:
            out.append(_action("pay_due_soon", "payments", "high",
                               f"Pay {_plural(due_soon['count'], 'invoice')} due in the next 7 days",
                               "Ready for payment and due this week.", due_soon["count"],
                               "/accounts-payable/payments/ready", "Review & pay", _base_amount(due_soon["amounts"])))
        elif n:
            out.append(_action("pay_ready", "payments", "normal", f"{_plural(n, 'invoice')} ready for payment",
                               "Approved and marked ready - pay on or before the due date.",
                               n, "/accounts-payable/payments/ready", "Open payments", amount))
        n, amount, c = card("approved_not_ready")
        if n:
            note = (c or {}).get("note")
            out.append(_action("mark_ready", "payments", "high" if note else "normal",
                               f"Mark {_plural(n, 'approved invoice')} ready for payment",
                               "Verify TDS and payment terms, then release for payment." + (f" {note}." if note else ""),
                               n, "/accounts-payable/invoices?queue=approved", "Release for payment", amount))
        n, amount, _ = card("msme_due")
        if n:
            out.append(_action("msme", "payments", "critical", f"{_plural(n, 'MSME invoice')} at the statutory deadline",
                               "MSMED Act: pay within the statutory limit (max 45 days) to avoid interest and tax disallowance.",
                               n, "/accounts-payable/payments/ready", "Pay MSME vendors", amount))
        n, amount, _ = card("term_exceptions")
        if n:
            out.append(_action("terms", "payments", "high", f"Resolve {_plural(n, 'payment-term exception')}",
                               "Invoice terms don't match the agreement / PO - verify the right due date to release payment.",
                               n, "/accounts-payable/reports?report=payment_term_exceptions", "Verify terms", amount))
        n, amount, _ = card("partially_paid")
        if n:
            out.append(_action("balance", "payments", "normal", f"Clear the balance on {_plural(n, 'partly paid invoice')}",
                               "Part of the invoice is paid; the rest is still owed.",
                               n, "/accounts-payable/payments/ready?status=PARTIALLY_PAID", "Pay balance", amount))
        if n := (view.get("receipts_missing") or {}).get("count"):
            out.append(_action("receipts", "payments", "normal", f"Attach receipts to {_plural(n, 'payment')}",
                               "Payment advice / bank receipt missing - needed for audit and vendor queries.",
                               n, "/accounts-payable/payments/history", "Upload receipts"))
        for agreement in (view.get("agreements_expiring") or [])[:3]:
            out.append(_action(f"agreement_{agreement.get('agreement_id', agreement.get('vendor_name'))}", "payments",
                               "high" if agreement["days_to_expiry"] <= 7 else "normal",
                               f"Renew {agreement['vendor_name']} agreement",
                               f"\"{agreement['title']}\" expires in {agreement['days_to_expiry']} days - "
                               "invoices after that need a new agreement.", 1,
                               f"/accounts-payable/vendors/{agreement['vendor_id']}", "Open vendor"))
        return out

    def _tds(self, tds) -> List[dict]:
        items = {i["key"]: i for i in tds.get("items", [])}
        spec = [
            ("deposit_overdue", "critical", "Deposit overdue TDS", "Deposit due by the 7th of the next month - "
             "interest @ 1.5% per month runs from the deduction date.", "/accounts-payable/tds/challans/new", "Record challan"),
            ("filing_overdue", "critical", "File the overdue TDS return", "Late fee Rs 200 per day under section 234E.",
             "/accounts-payable/tds/filings/new", "Record filing"),
            ("deposit_due_this_month", "high", "Deposit this month's TDS", "Due by the 7th of next month.",
             "/accounts-payable/tds/challans/new", "Record challan"),
            ("filing_due_soon", "high", "Prepare the quarterly TDS return (26Q)", "Due within 45 days - all deposits "
             "of the quarter must be in.", "/accounts-payable/tds/filings/new", "Record filing"),
            ("verification_pending", "normal", "Verify TDS on approved invoices", "Finance verification is needed before payment.",
             "/accounts-payable/tds/tracking", "Verify TDS"),
            ("deduction_not_recorded", "normal", "Record TDS deductions on paid invoices", "Paid, but the deduction "
             "isn't recorded - it can't be deposited until it is.", "/accounts-payable/tds/tracking", "Record deduction"),
        ]
        out = []
        for key, severity, title, detail, link, cta in spec:
            item = items.get(key)
            if item and item["count"]:
                out.append(_action(f"tds_{key}", "tds", severity, f"{title} ({_plural(item['count'], 'invoice')})",
                                   detail, item["count"], link, cta, _base_amount(item["amounts"])))
        return out

    def _notes(self) -> List[dict]:
        """Credit / debit notes recorded but not yet set off against an invoice."""
        try:
            from Backend.Business_Layer.services.vendor_note_service import VendorNoteService
            summary = VendorNoteService(self.dashboards.db).list(status="OPEN")["summary"]
        except Exception:  # notes optional (e.g. table not migrated yet)
            try:
                self.dashboards.db.rollback()
            except Exception:
                pass
            return []
        if not summary["open"]:
            return []
        return [_action("notes_open", "payments", "normal", f"Apply {_plural(summary['open'], 'credit / debit note')}",
                        "Recorded but not yet set off - apply each to the vendor's unpaid invoice so we don't overpay.",
                        summary["open"], "/accounts-payable/vendor-notes", "Apply notes", Decimal(str(summary["open_amount"])))]

    def _recurring(self) -> List[dict]:
        """Recurring schedules: invoices that haven't arrived, and amounts that differ from the schedule."""
        try:
            from Backend.Business_Layer.services.recurring_service import RecurringService
            attention = RecurringService(self.dashboards.db, today=self.today).attention()
        except Exception:  # recurring schedules are optional (e.g. tables not migrated yet)
            try:
                self.dashboards.db.rollback()
            except Exception:
                pass
            return []
        out = []
        missing = attention["missing"]
        if missing:
            first = missing[0]
            names = ", ".join(sorted({m["vendor"] or m["schedule"] for m in missing}))
            out.append(_action("recurring_missing", "ap", "high", f"Chase {_plural(len(missing), 'recurring invoice')} not received",
                               f"Expected but not uploaded ({names}) - e.g. {first['schedule']}, due "
                               f"{first['expected_date']:%d %b}. Ask the vendor, or skip the period if nothing was billed.",
                               len(missing), "/accounts-payable/recurring", "Open schedules",
                               sum((Decimal(str(m["expected_amount"])) for m in missing), ZERO)))
        varied = attention["variance"]
        if varied:
            out.append(_action("recurring_variance", "ap", "normal",
                               f"Check {_plural(len(varied), 'recurring invoice')} that differ from schedule",
                               "The amount is outside the schedule's tolerance - confirm the change (new rate, usage) "
                               "before approval, or update the schedule.", len(varied), "/accounts-payable/recurring",
                               "Review differences"))
        return out

    def _gst(self) -> Optional[List[dict]]:
        """GST input credit: claim the month's ITC by the GSTR-3B date, IRNs missing, 180-day rule."""
        try:
            from Backend.Business_Layer.services.gst_itc_service import GstItcService
            s = GstItcService(self.dashboards.db, today=self.today).register()["summary"]
        except Exception:  # register optional (e.g. table not migrated yet)
            try:
                self.dashboards.db.rollback()
            except Exception:
                pass
            return None
        out, link = [], "/accounts-payable/gst"
        if s["reversal_due"]:
            out.append(_action("gst_reversal", "gst", "critical", f"Reverse ITC on {_plural(s['reversal_due'], 'invoice')} unpaid over 180 days",
                               "GST law (s.16(2)): credit on an invoice not paid within 180 days must be reversed in GSTR-3B "
                               "(with interest); it can be re-claimed after payment.", s["reversal_due"], link, "Open ITC register"))
        if s["at_risk"]:
            out.append(_action("gst_at_risk", "gst", "high", f"Pay {_plural(s['at_risk'], 'invoice')} before the 180-day ITC deadline",
                               "Unpaid for 150+ days - pay within 180 days of the invoice date to keep the input credit.",
                               s["at_risk"], link, "See invoices"))
        if s["claimable_count"]:
            days = (datetime.date.fromisoformat(str(s["claim_due"])) - self.today).days
            out.append(_action("gst_claim", "gst", "high" if days <= 7 else "normal",
                               f"Claim {s['claim_period']:%b %Y} input credit in GSTR-3B",
                               f"{_plural(s['claimable_count'], 'invoice')} ready - return due {s['claim_due']:%d %b}"
                               + (f" ({days} days)." if days >= 0 else " (overdue)."), s["claimable_count"], link,
                               "Claim ITC", Decimal(str(s["claimable_now"]))))
        if s["irn_missing"]:
            out.append(_action("gst_irn", "gst", "high", f"Get the IRN for {_plural(s['irn_missing'], 'e-invoice')}",
                               "These suppliers must e-invoice; credit isn't admissible without the IRN. Record it from the "
                               "invoice QR code or ask the vendor for the e-invoice.", s["irn_missing"], link, "Record IRN"))
        if s["review"]:
            out.append(_action("gst_review", "gst", "normal", f"Confirm ITC eligibility on {_plural(s['review'], 'invoice')}",
                               "Looks like a blocked credit under s.17(5) (food, cabs, club, works contract) - confirm or override.",
                               s["review"], link, "Review"))
        return out

    def _management(self, view) -> List[dict]:
        out = []
        high = view.get("high_value_exceptions") or []
        if high:
            total = sum((Decimal(str(h["outstanding"])) for h in high if h["currency_code"] == BASE_CURRENCY), ZERO)
            out.append(_action("mgmt_high_value", "management", "high",
                               f"{_plural(len(high), 'high-value invoice')} overdue or blocked",
                               "Large invoices that are past due or stuck on a payment-term exception.",
                               len(high), "/accounts-payable/reports?report=outstanding_payables", "View invoices", total))
        stuck = [b for b in (view.get("efficiency") or {}).get("bottlenecks", []) if (b.get("max_wait_days") or 0) > 3]
        if stuck:
            b = stuck[0]
            out.append(_action("mgmt_bottleneck", "management", "normal",
                               f"Approvals slow in {b['department']} (level {b['level']})",
                               f"{_plural(b['count'], 'invoice')} waiting, longest {b['max_wait_days']:g} days.",
                               sum(x["count"] for x in stuck), "/accounts-payable/invoices?queue=approval", "See queue"))
        return out
