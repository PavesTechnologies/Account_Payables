# Backend/Business_Layer/services/dashboard_service.py
"""AP Dashboard: one permission-aware summary per authenticated user.

The backend decides what each user receives. A section is computed - and
its queries run - only if the caller holds a permission that the matching
module's own APIs already enforce (or, for Vendor Management, the role the
existing AP role model uses). Nothing is returned "just in case" for the
frontend to hide.

    section       granted by (any of)
    -----------   ----------------------------------------------------------
    invoices      INVOICE_VIEW                         (invoice_details_route)
    ocr           INVOICE_OCR_REVIEW                   (invoice_process_route)
    submission    INVOICE_SEND_FOR_APPROVAL            (invoice_approval_route)
    approvals     INVOICE_APPROVE / REJECT / SEND_BACK (invoice_approval_route)
    tds           INVOICE_TDS_VIEW / DETERMINE / EDIT / VERIFY   (tds_route)
    tds_determine INVOICE_TDS_DETERMINE
    tds_verify    INVOICE_TDS_VERIFY
    tds_tracking  TDS_TRACKING_VIEW / UPDATE            (tds_tracking_route)
    payments      PAYMENT_VIEW / PAYMENT_PROCESS        (payment_route)
    payment_ops   PAYMENT_PROCESS
    pr_own        PR_VIEW / PR_CREATE / PR_EDIT / PR_SUBMIT / PR_TRACK
    pr_approval   PR_APPROVAL_VIEW / PR_APPROVE / PR_REJECT
    sourcing      QUOTATION_VIEW / QUOTATION_CREATE / VENDOR_SELECTION_VIEW / PO_VIEW / PO_CREATE
    vendors       role Admin / Vendor_Intake, or ONBOARDING_VIEW / ONBOARDING_PROCESS
                  (vendor routes carry no backend permission yet - the AP
                  frontend's AP_VENDOR_MANAGER_ROLES is the existing boundary)

Money is never summed across currencies: every amount widget carries one
entry per currency. Amounts reuse the existing rules (payable = net_amount -
TDS when applicable; amount_paid only counts CLEARED payments; SCHEDULED/SENT
allocations are "pending").
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional

from Backend.API_Layer.middleware.permission_base_access import has_permissions
from Backend.Business_Layer.services.approver_resolver_service import ApproverResolverService
from Backend.Data_Access_Layer.dao.dashboard_dao import DashboardDAO

MAX_RANGE_DAYS = 366
DEFAULT_RANGE_DAYS = 30
RECENT_ACTIVITY_LIMIT = 15

VENDOR_MANAGER_ROLES = ["Admin", "Vendor_Intake"]

SECTION_PERMISSIONS = {
    "invoices": ["INVOICE_VIEW"],
    "ocr": ["INVOICE_OCR_REVIEW"],
    "submission": ["INVOICE_SEND_FOR_APPROVAL"],
    "approvals": ["INVOICE_APPROVE", "INVOICE_REJECT", "INVOICE_SEND_BACK"],
    "tds": ["INVOICE_TDS_VIEW", "INVOICE_TDS_DETERMINE", "INVOICE_TDS_EDIT", "INVOICE_TDS_VERIFY"],
    "tds_determine": ["INVOICE_TDS_DETERMINE"],
    "tds_verify": ["INVOICE_TDS_VERIFY"],
    "tds_tracking": ["TDS_TRACKING_VIEW", "TDS_TRACKING_UPDATE"],
    "tds_tracking_update": ["TDS_TRACKING_UPDATE"],
    "payments": ["PAYMENT_VIEW", "PAYMENT_PROCESS"],
    "payment_ops": ["PAYMENT_PROCESS"],
    "pr_own": ["PR_VIEW", "PR_CREATE", "PR_EDIT", "PR_SUBMIT", "PR_TRACK"],
    "pr_approval": ["PR_APPROVAL_VIEW", "PR_APPROVE", "PR_REJECT"],
    "pr_approve": ["PR_APPROVE"],
    "sourcing": ["QUOTATION_VIEW", "QUOTATION_CREATE", "VENDOR_SELECTION_VIEW", "PO_VIEW", "PO_CREATE"],
    "po_create": ["PO_CREATE"],
    "onboarding": ["ONBOARDING_VIEW", "ONBOARDING_PROCESS", "ONBOARDING_ASSIGN"],
    "onboarding_process": ["ONBOARDING_PROCESS"],
    "onboarding_assign": ["ONBOARDING_ASSIGN"],
}

# Invoice status display order for the status chart (ap.status_master codes).
INVOICE_STATUSES = [
    "DRAFT", "OCR_REVIEW_PENDING", "OCR_FAILED", "OCR_REVIEWED", "PENDING_APPROVAL", "APPROVED",
    "RETURNED_FOR_REVIEW", "READY_FOR_PAYMENT", "PARTIALLY_PAID", "PAID", "DISPUTED", "REJECTED",
]
PAYABLE_STATUSES = ("READY_FOR_PAYMENT", "PARTIALLY_PAID")
# Where a TDS determination must be complete before the next step (send for approval).
TDS_DETERMINATION_STATUSES = ("OCR_REVIEWED", "RETURNED_FOR_REVIEW")
PR_OPEN_STATUSES = {"DRAFT", "PENDING_APPROVAL", "APPROVED", "VENDOR_SELECTION", "RETURNED"}
RFQ_OPEN_STATUSES = {"DRAFT", "SENT", "RESPONSE_RECEIVED"}
ONBOARDING_CLOSED_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}

# Recent activity: meaningful business events only (audit_log also carries
# noise such as EMAIL_SENT / NDA_DOCUMENT_ACCESSED), per section.
ACTIVITY_SOURCES = {
    "invoices": {
        "invoice": [
            "INVOICE_CREATED", "INVOICE_OCR_REVIEWED", "INVOICE_SENT_FOR_APPROVAL", "INVOICE_APPROVED",
            "INVOICE_REJECTED", "INVOICE_SENT_BACK", "INVOICE_RESUBMITTED", "INVOICE_READY_FOR_PAYMENT",
            "INVOICE_TDS_DETERMINED", "INVOICE_TDS_VERIFIED", "INVOICE_PAYMENT_RECORDED", "INVOICE_PAYMENT_CLEARED",
        ],
    },
    "payments": {"invoice": ["INVOICE_READY_FOR_PAYMENT", "INVOICE_PAYMENT_RECORDED", "INVOICE_PAYMENT_CLEARED"]},
    "tds": {"invoice": ["INVOICE_TDS_DETERMINED", "INVOICE_TDS_VERIFIED"]},
    "tds_tracking": {
        "invoice": ["INVOICE_TDS_DEDUCTION_RECORDED", "INVOICE_TDS_DEPOSIT_RECORDED", "INVOICE_TDS_FILING_RECORDED"],
    },
    "pr_own": {"purchase_requisition": ["PR_REQUEST_RAISED", "SUBMITTED_FOR_APPROVAL", "PR_APPROVED", "PR_REJECTED",
                                         "PR_SENT_BACK_FOR_CLARIFICATION", "PR_RESUBMITTED"]},
    "pr_approval": {"purchase_requisition": ["SUBMITTED_FOR_APPROVAL", "PR_APPROVED", "PR_REJECTED",
                                              "PR_SENT_BACK_FOR_CLARIFICATION", "PR_RESUBMITTED"]},
    "sourcing": {"purchase_requisition": ["RFQ_SENT", "QUOTATION_RECEIVED", "VENDOR_SELECTED"]},
    "vendors": {"vendor": ["CREATE", "STATUS_CHANGE"]},
}

ACTIVITY_LABELS = {
    "INVOICE_CREATED": "Invoice created",
    "INVOICE_OCR_REVIEWED": "Invoice OCR reviewed",
    "INVOICE_SENT_FOR_APPROVAL": "Invoice sent for approval",
    "INVOICE_APPROVED": "Invoice approved",
    "INVOICE_REJECTED": "Invoice rejected",
    "INVOICE_SENT_BACK": "Invoice returned for review",
    "INVOICE_RESUBMITTED": "Invoice resubmitted",
    "INVOICE_READY_FOR_PAYMENT": "Invoice moved to Ready for Payment",
    "INVOICE_TDS_DETERMINED": "TDS determined",
    "INVOICE_TDS_VERIFIED": "TDS verified",
    "INVOICE_PAYMENT_RECORDED": "Payment recorded",
    "INVOICE_PAYMENT_CLEARED": "Payment cleared",
    "INVOICE_TDS_DEDUCTION_RECORDED": "TDS deduction recorded",
    "INVOICE_TDS_DEPOSIT_RECORDED": "TDS payment (challan) recorded",
    "INVOICE_TDS_FILING_RECORDED": "TDS filing recorded",
    "PR_REQUEST_RAISED": "PR created",
    "SUBMITTED_FOR_APPROVAL": "PR submitted for approval",
    "PR_APPROVED": "PR approved",
    "PR_REJECTED": "PR rejected",
    "PR_SENT_BACK_FOR_CLARIFICATION": "PR returned for clarification",
    "PR_RESUBMITTED": "PR resubmitted",
    "RFQ_SENT": "RFQ sent",
    "QUOTATION_RECEIVED": "Quotation received",
    "VENDOR_SELECTED": "Vendor selected",
    "CREATE": "Vendor created",
    "STATUS_CHANGE": "Vendor status changed",
}

_ENTITY_BY_TABLE = {"invoice": "invoice", "purchase_requisition": "purchase_requisition", "vendor": "vendor"}


def _money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _amounts(per_currency: dict) -> list:
    """{(code, symbol): Decimal} -> [{currency_code, currency_symbol, amount}] sorted by code."""
    return [
        {"currency_code": code, "currency_symbol": symbol, "amount": _money(amount)}
        for (code, symbol), amount in sorted(per_currency.items(), key=lambda kv: kv[0][0] or "")
    ]


class DashboardService:
    def __init__(self, db):
        self.db = db
        self.dao = DashboardDAO(db)
        self.resolver = ApproverResolverService(db)
        self._memo: dict = {}
        self._labels: dict = {}

    def _once(self, key, fn):
        """Run an aggregate query at most once per request when two widgets need it."""
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    # =========================================================
    # Access
    # =========================================================

    @staticmethod
    def capabilities(user: dict) -> set:
        granted = {section for section, perms in SECTION_PERMISSIONS.items() if has_permissions(user, perms)}
        roles = user.get("roles", []) if user else []
        roles = [roles] if isinstance(roles, str) else roles
        normalized_roles = {r.strip().lower() for r in roles if isinstance(r, str)}
        if normalized_roles & {r.lower() for r in VENDOR_MANAGER_ROLES} or "onboarding" in granted:
            granted.add("vendors")
        return granted

    @staticmethod
    def resolve_period(from_date: Optional[datetime.date], to_date: Optional[datetime.date], today=None):
        today = today or datetime.date.today()
        to_date = to_date or today
        from_date = from_date or (to_date - datetime.timedelta(days=DEFAULT_RANGE_DAYS - 1))
        if from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
            raise ValueError(f"The date range cannot exceed {MAX_RANGE_DAYS} days")
        span = (to_date - from_date).days + 1
        granularity = "day" if span <= 31 else "week" if span <= 186 else "month"
        return from_date, to_date, granularity

    # =========================================================
    # Summary
    # =========================================================

    def get_summary(self, user: dict, from_date=None, to_date=None) -> dict:
        user_id = str(user.get("user_id") or user.get("sub") or "") or None
        caps = self.capabilities(user)
        period_from, period_to, granularity = self.resolve_period(from_date, to_date)

        out = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc),
            "period": {"from_date": period_from, "to_date": period_to, "granularity": granularity},
            "sections": sorted(caps & {"invoices", "approvals", "tds", "tds_tracking", "payments", "pr_own",
                                       "pr_approval", "sourcing", "vendors"}),
            "kpis": [],
            "action_required": [],
            "status_summary": [],
            "financial_summary": [],
            "trends": [],
            "recent_activity": [],
        }
        labels = self._labels = self.dao.status_labels(
            ["INVOICE", "PURCHASE_REQUISITION", "PAYMENT", "RFQ", "PO", "VENDOR", "VENDOR_ONBOARDING"]
        )

        invoice_rows = None
        if caps & {"invoices", "ocr", "submission", "payments", "payment_ops"}:
            invoice_rows = self.dao.invoice_status_totals()
            self._invoice_sections(out, caps, invoice_rows, labels)
        if caps & {"payments"}:
            self._payment_sections(out, caps, invoice_rows, period_from, period_to)
        if "approvals" in caps:
            pending = self.dao.approvals_pending_for_user(self.resolver.resolve_user_uuid(user_id))
            self._action(out, "invoices_awaiting_my_approval", "Invoices Awaiting My Approval", pending,
                         "INVOICE_APPROVE", {"entity": "invoice", "assigned_to_me": True}, "high")
        if caps & {"tds", "tds_determine", "tds_verify"}:
            self._tds_sections(out, caps)
        if "tds_tracking" in caps:
            self._tds_tracking_sections(out, caps)
        if caps & {"pr_own", "pr_approval", "sourcing"}:
            self._procurement_sections(out, caps, user_id, labels)
        if "vendors" in caps:
            self._vendor_sections(out, caps, user_id, labels)
        if caps & {"invoices", "payments", "tds"}:
            self._trends(out, caps, granularity, period_from, period_to)
        self._recent_activity(out, caps, period_from, period_to)

        out["action_required"] = [a for a in out["action_required"] if a["value"] > 0] + \
                                 [a for a in out["action_required"] if a["value"] == 0]
        return out

    # =========================================================
    # Widget helpers
    # =========================================================

    @staticmethod
    def _kpi(out, key, title, value, permission, module, filter_=None):
        out["kpis"].append({"key": key, "title": title, "type": "count", "value": int(value), "module": module,
                            "permission": permission, "filter": filter_})

    @staticmethod
    def _amount_kpi(out, key, title, per_currency, permission, module, scope="current"):
        out["kpis"].append({"key": key, "title": title, "type": "amount", "amounts": _amounts(per_currency),
                            "module": module, "permission": permission, "scope": scope, "filter": None})

    @staticmethod
    def _action(out, key, title, value, permission, filter_, priority="medium"):
        out["action_required"].append({"key": key, "title": title, "type": "count", "value": int(value),
                                       "permission": permission, "priority": priority, "filter": filter_})

    @staticmethod
    def _status_chart(key, title, module, counts: dict, order, labels, permission):
        items = []
        known = [c for c in order if c in counts] + sorted(c for c in counts if c not in order)
        for code in known:
            name = labels.get((module, code), (code.replace("_", " ").title() if code else "Unknown", 999))[0]
            items.append({"status_code": code, "label": name, "count": int(counts[code])})
        return {"key": key, "title": title, "module": module.lower(), "permission": permission, "items": items}

    # =========================================================
    # Invoices
    # =========================================================

    def _invoice_sections(self, out, caps, rows, labels):
        counts: dict = {}
        for status, _cur, _sym, count, *_ in rows:
            counts[status] = counts.get(status, 0) + count

        def c(code):
            return counts.get(code, 0)

        if "invoices" in caps:
            self._kpi(out, "invoices_total", "Total Invoices", sum(counts.values()), "INVOICE_VIEW", "invoice", {"entity": "invoice"})
            for code, title in (
                ("DRAFT", "Draft"), ("OCR_REVIEW_PENDING", "OCR Review Pending"), ("OCR_FAILED", "OCR Failed"),
                ("PENDING_APPROVAL", "Pending Approval"), ("APPROVED", "Approved"),
                ("RETURNED_FOR_REVIEW", "Returned for Review"), ("READY_FOR_PAYMENT", "Ready for Payment"),
                ("PARTIALLY_PAID", "Partially Paid"), ("PAID", "Paid"), ("DISPUTED", "Disputed"), ("REJECTED", "Rejected"),
            ):
                self._kpi(out, f"invoices_{code.lower()}", f"{title} Invoices", c(code), "INVOICE_VIEW", "invoice",
                          {"entity": "invoice", "status": code})
            out["status_summary"].append(self._status_chart(
                "invoice_status_distribution", "Invoices by Status", "INVOICE", counts, INVOICE_STATUSES, labels, "INVOICE_VIEW"))

            totals: dict = {}
            approved: dict = {}
            for status, cur, sym, _count, net, _paid, _tds in rows:
                totals[(cur, sym)] = totals.get((cur, sym), Decimal(0)) + Decimal(net)
                if status == "APPROVED":
                    approved[(cur, sym)] = approved.get((cur, sym), Decimal(0)) + Decimal(net)
            out["financial_summary"].append({"key": "invoice_value_total", "title": "Total Invoice Value",
                                             "scope": "current", "permission": "INVOICE_VIEW", "amounts": _amounts(totals)})
            out["financial_summary"].append({"key": "invoice_value_approved", "title": "Approved (awaiting payment readiness)",
                                             "scope": "current", "permission": "INVOICE_VIEW", "amounts": _amounts(approved)})

        if "ocr" in caps:
            self._action(out, "invoices_ocr_review_pending", "Invoices Pending OCR Review", c("OCR_REVIEW_PENDING"),
                         "INVOICE_OCR_REVIEW", {"entity": "invoice", "status": "OCR_REVIEW_PENDING"}, "high")
            self._action(out, "invoices_ocr_failed", "OCR Failed Invoices", c("OCR_FAILED"),
                         "INVOICE_OCR_REVIEW", {"entity": "invoice", "status": "OCR_FAILED"}, "high")
            self._action(out, "invoices_returned_for_review", "Invoices Returned for Review", c("RETURNED_FOR_REVIEW"),
                         "INVOICE_OCR_REVIEW", {"entity": "invoice", "status": "RETURNED_FOR_REVIEW"}, "high")
        if "submission" in caps:
            self._action(out, "invoices_pending_submission", "Reviewed Invoices to Send for Approval", c("OCR_REVIEWED"),
                         "INVOICE_SEND_FOR_APPROVAL", {"entity": "invoice", "status": "OCR_REVIEWED"})

    # =========================================================
    # Payments
    # =========================================================

    def _payment_sections(self, out, caps, invoice_rows, period_from, period_to):
        counts: dict = {}
        payable: dict = {}
        paid: dict = {}
        tds_on_payable: dict = {}
        for status, cur, sym, count, net, amount_paid, tds in invoice_rows or []:
            counts[status] = counts.get(status, 0) + count
            key = (cur, sym)
            if status in PAYABLE_STATUSES:
                payable[key] = payable.get(key, Decimal(0)) + Decimal(net) - Decimal(tds) - Decimal(amount_paid)
                tds_on_payable[key] = tds_on_payable.get(key, Decimal(0)) + Decimal(tds)
            paid[key] = paid.get(key, Decimal(0)) + Decimal(amount_paid)
        symbols = {cur: sym for (cur, sym) in payable}
        for cur, reserved in self.dao.pending_payment_allocations(PAYABLE_STATUSES):
            key = (cur, symbols.get(cur))
            payable[key] = payable.get(key, Decimal(0)) - Decimal(reserved)

        payment_counts = dict(self.dao.payment_status_counts())
        pending_payments = payment_counts.get("SCHEDULED", 0) + payment_counts.get("SENT", 0)

        self._kpi(out, "payments_ready", "Ready for Payment", counts.get("READY_FOR_PAYMENT", 0), "PAYMENT_VIEW", "payment",
                  {"entity": "invoice", "status": "READY_FOR_PAYMENT"})
        self._kpi(out, "payments_partially_paid", "Partially Paid", counts.get("PARTIALLY_PAID", 0), "PAYMENT_VIEW", "payment",
                  {"entity": "invoice", "status": "PARTIALLY_PAID"})
        self._kpi(out, "payments_paid", "Paid Invoices", counts.get("PAID", 0), "PAYMENT_VIEW", "payment",
                  {"entity": "invoice", "status": "PAID"})
        self._kpi(out, "payments_pending_clearance", "Payments Scheduled / Sent (not cleared)", pending_payments,
                  "PAYMENT_VIEW", "payment", {"entity": "payment", "status": "SCHEDULED,SENT"})
        self._amount_kpi(out, "payments_outstanding_payable", "Outstanding Payable (net of TDS)", payable, "PAYMENT_VIEW", "payment")

        out["financial_summary"].append({"key": "payable_outstanding", "title": "Outstanding Payable (net of TDS)",
                                         "scope": "current", "permission": "PAYMENT_VIEW", "amounts": _amounts(payable)})
        out["financial_summary"].append({"key": "paid_total", "title": "Paid to Vendors (all time)",
                                         "scope": "current", "permission": "PAYMENT_VIEW", "amounts": _amounts(paid)})
        out["financial_summary"].append({"key": "tds_on_payable", "title": "TDS Withheld on Payable Invoices",
                                         "scope": "current", "permission": "PAYMENT_VIEW", "amounts": _amounts(tds_on_payable)})
        period_paid = {(cur, sym): Decimal(v) for cur, sym, v in self.dao.cleared_payments_total(period_from, period_to)}
        out["financial_summary"].append({"key": "paid_in_period", "title": "Paid in Period",
                                         "scope": "period", "permission": "PAYMENT_VIEW", "amounts": _amounts(period_paid)})
        out["status_summary"].append(self._status_chart(
            "payment_status_distribution", "Payments by Status", "PAYMENT", payment_counts,
            ["SCHEDULED", "SENT", "CLEARED", "FAILED"], self._labels, "PAYMENT_VIEW"))

        if "payment_ops" in caps:
            self._action(out, "payments_to_record", "Invoices Ready for Payment",
                         counts.get("READY_FOR_PAYMENT", 0) + counts.get("PARTIALLY_PAID", 0), "PAYMENT_PROCESS",
                         {"entity": "invoice", "status": "READY_FOR_PAYMENT,PARTIALLY_PAID"}, "high")
            self._action(out, "invoices_to_mark_ready", "Approved Invoices to Mark Ready for Payment",
                         self.dao.approved_awaiting_ready_count(), "PAYMENT_PROCESS",
                         {"entity": "invoice", "status": "APPROVED", "tds_status": "VERIFIED"})

    # =========================================================
    # TDS
    # =========================================================

    def _tds_sections(self, out, caps):
        if "tds" in caps:
            rows = self.dao.tds_determination_totals()
            applicable = sum(r[4] for r in rows if r[1])
            verified = sum(r[4] for r in rows if r[0] == "VERIFIED")
            tds_amount: dict = {}
            for _status, is_applicable, cur, sym, _count, amount in rows:
                if is_applicable:
                    tds_amount[(cur, sym)] = tds_amount.get((cur, sym), Decimal(0)) + Decimal(amount)
            self._kpi(out, "tds_applicable_invoices", "TDS-Applicable Invoices", applicable, "INVOICE_TDS_VIEW", "tds",
                      {"entity": "invoice", "tds_applicable": True})
            self._kpi(out, "tds_verified", "TDS Verified", verified, "INVOICE_TDS_VIEW", "tds",
                      {"entity": "invoice", "tds_status": "VERIFIED"})
            self._kpi(out, "tds_verification_pending", "TDS Verification Pending", self._once("tds_to_verify", self.dao.tds_verification_pending_count),
                      "INVOICE_TDS_VIEW", "tds", {"entity": "invoice", "tds_status": "DETERMINED"})
            self._kpi(out, "tds_determination_pending", "TDS Determination Pending",
                      self._once("tds_incomplete", lambda: self.dao.tds_determination_incomplete_count(TDS_DETERMINATION_STATUSES)), "INVOICE_TDS_VIEW", "tds",
                      {"entity": "invoice", "status": ",".join(TDS_DETERMINATION_STATUSES), "tds_status": "INCOMPLETE"})
            self._amount_kpi(out, "tds_amount_withheld", "TDS Withheld (determined)", tds_amount, "INVOICE_TDS_VIEW", "tds")
            out["financial_summary"].append({"key": "tds_total", "title": "TDS Withheld (all determined)",
                                             "scope": "current", "permission": "INVOICE_TDS_VIEW", "amounts": _amounts(tds_amount)})
        if "tds_determine" in caps:
            self._action(out, "tds_determination_pending", "Invoices Needing TDS Determination",
                         self._once("tds_incomplete", lambda: self.dao.tds_determination_incomplete_count(TDS_DETERMINATION_STATUSES)), "INVOICE_TDS_DETERMINE",
                         {"entity": "invoice", "status": ",".join(TDS_DETERMINATION_STATUSES), "tds_status": "INCOMPLETE"}, "high")
        if "tds_verify" in caps:
            self._action(out, "tds_verification_pending", "TDS Determinations to Verify", self._once("tds_to_verify", self.dao.tds_verification_pending_count),
                         "INVOICE_TDS_VERIFY", {"entity": "invoice", "tds_status": "DETERMINED"}, "high")

    def _tds_tracking_sections(self, out, caps):
        counts = dict(self.dao.tds_tracking_status_counts())
        order = ["TDS_PENDING", "TDS_DEDUCTED", "TDS_DEPOSITED", "TDS_FILED"]
        names = {"TDS_PENDING": "TDS Pending", "TDS_DEDUCTED": "TDS Deducted", "TDS_DEPOSITED": "TDS Deposited", "TDS_FILED": "TDS Return Filed"}
        out["status_summary"].append({
            "key": "tds_tracking_distribution", "title": "TDS Tracking", "module": "tds_tracking", "permission": "TDS_TRACKING_VIEW",
            "items": [{"status_code": s, "label": names[s], "count": int(counts.get(s, 0))} for s in order],
        })
        not_filed = sum(counts.get(s, 0) for s in order[:3])
        self._kpi(out, "tds_not_yet_filed", "TDS Not Yet Filed", not_filed, "TDS_TRACKING_VIEW", "tds_tracking",
                  {"entity": "tds_tracking", "tds_status": "TDS_PENDING,TDS_DEDUCTED,TDS_DEPOSITED"})
        if "tds_tracking_update" in caps:
            self._action(out, "tds_tracking_to_update", "TDS Awaiting Deduction / Deposit / Filing", not_filed,
                         "TDS_TRACKING_UPDATE", {"entity": "tds_tracking", "tds_status": "TDS_PENDING,TDS_DEDUCTED,TDS_DEPOSITED"})

    # =========================================================
    # Procurement
    # =========================================================

    def _procurement_sections(self, out, caps, user_id, labels):
        all_counts: dict = {}
        mine: dict = {}
        for status, is_mine, count in self.dao.pr_status_counts(user_id):
            all_counts[status] = all_counts.get(status, 0) + count
            if is_mine:
                mine[status] = mine.get(status, 0) + count

        if "pr_own" in caps:
            self._kpi(out, "my_open_prs", "My Open PRs", sum(v for k, v in mine.items() if k in PR_OPEN_STATUSES), "PR_VIEW",
                      "procurement", {"entity": "purchase_requisition", "mine": True})
            self._kpi(out, "my_prs_pending_approval", "My PRs Pending Approval", mine.get("PENDING_APPROVAL", 0), "PR_VIEW",
                      "procurement", {"entity": "purchase_requisition", "mine": True, "status": "PENDING_APPROVAL"})
            self._action(out, "my_draft_prs", "My Draft PRs", mine.get("DRAFT", 0), "PR_VIEW",
                         {"entity": "purchase_requisition", "mine": True, "status": "DRAFT"})
            self._action(out, "my_returned_prs", "My PRs Returned for Clarification", mine.get("RETURNED", 0), "PR_VIEW",
                         {"entity": "purchase_requisition", "mine": True, "status": "RETURNED"}, "high")
            out["status_summary"].append(self._status_chart(
                "my_pr_status_distribution", "My PRs by Status", "PURCHASE_REQUISITION", mine,
                ["DRAFT", "PENDING_APPROVAL", "RETURNED", "APPROVED", "VENDOR_SELECTION", "PO_GENERATED", "REJECTED", "CANCELLED"],
                labels, "PR_VIEW"))

        if "pr_approval" in caps:
            self._kpi(out, "prs_pending_approval", "PRs Pending Approval", all_counts.get("PENDING_APPROVAL", 0),
                      "PR_APPROVAL_VIEW", "procurement", {"entity": "purchase_requisition", "status": "PENDING_APPROVAL"})
            if "pr_approve" in caps:
                # PR approval has no per-user assignment (any PR_APPROVE holder may decide any
                # PENDING_APPROVAL PR - see ProcurementService.approve_purchase_requisition), so the
                # queue is the same PENDING_APPROVAL set the approval list endpoint returns.
                self._action(out, "prs_awaiting_approval", "PRs Awaiting Approval", all_counts.get("PENDING_APPROVAL", 0),
                             "PR_APPROVE", {"entity": "purchase_requisition", "status": "PENDING_APPROVAL"}, "high")

        if "sourcing" in caps:
            rfq = dict(self.dao.rfq_status_counts())
            po = dict(self.dao.po_status_counts())
            awaiting_po = self.dao.pr_vendor_selected_awaiting_po_count()
            self._kpi(out, "prs_awaiting_sourcing", "Approved PRs Awaiting Sourcing", all_counts.get("APPROVED", 0),
                      "QUOTATION_VIEW", "procurement", {"entity": "purchase_requisition", "status": "APPROVED"})
            self._kpi(out, "rfqs_open", "Open RFQs", sum(v for k, v in rfq.items() if k in RFQ_OPEN_STATUSES), "QUOTATION_VIEW",
                      "procurement", {"entity": "rfq", "status": ",".join(sorted(RFQ_OPEN_STATUSES))})
            self._kpi(out, "prs_vendor_selection", "PRs in Vendor Selection", all_counts.get("VENDOR_SELECTION", 0),
                      "VENDOR_SELECTION_VIEW", "procurement", {"entity": "purchase_requisition", "status": "VENDOR_SELECTION"})
            self._kpi(out, "pos_open", "Open Purchase Orders", po.get("OPEN", 0), "PO_VIEW", "procurement",
                      {"entity": "purchase_order", "status": "OPEN"})
            self._action(out, "prs_awaiting_sourcing", "Approved PRs Awaiting Sourcing", all_counts.get("APPROVED", 0),
                         "QUOTATION_VIEW", {"entity": "purchase_requisition", "status": "APPROVED"}, "high")
            self._action(out, "rfqs_awaiting_responses", "RFQs Awaiting Quotations", rfq.get("SENT", 0), "QUOTATION_VIEW",
                         {"entity": "rfq", "status": "SENT"})
            self._action(out, "vendor_selection_pending", "Vendor Selection Pending",
                         all_counts.get("VENDOR_SELECTION", 0) - awaiting_po, "VENDOR_SELECTION_VIEW",
                         {"entity": "purchase_requisition", "status": "VENDOR_SELECTION", "vendor_selected": False})
            if "po_create" in caps:
                self._action(out, "po_generation_pending", "PO Generation Pending", awaiting_po, "PO_CREATE",
                             {"entity": "purchase_requisition", "status": "VENDOR_SELECTION", "vendor_selected": True})
            out["status_summary"].append(self._status_chart(
                "pr_status_distribution", "PRs by Status", "PURCHASE_REQUISITION", all_counts,
                ["DRAFT", "PENDING_APPROVAL", "RETURNED", "APPROVED", "VENDOR_SELECTION", "PO_GENERATED", "REJECTED", "CANCELLED"],
                labels, "QUOTATION_VIEW"))

    # =========================================================
    # Vendors
    # =========================================================

    def _vendor_sections(self, out, caps, user_id, labels):
        vendors = dict(self.dao.vendor_status_counts())
        onboarding: dict = {}
        assigned_to_me = 0
        unassigned = 0
        for status, is_mine, is_unassigned, count in self.dao.onboarding_status_counts(user_id):
            onboarding[status] = onboarding.get(status, 0) + count
            if status not in ONBOARDING_CLOSED_STATUSES:
                assigned_to_me += count if is_mine else 0
                unassigned += count if is_unassigned else 0
        open_requests = sum(v for k, v in onboarding.items() if k not in ONBOARDING_CLOSED_STATUSES)

        self._kpi(out, "vendors_active", "Active Vendors", vendors.get("ACTIVE", 0), "VENDOR_MANAGEMENT", "vendor",
                  {"entity": "vendor", "status": "ACTIVE"})
        self._kpi(out, "vendors_pending", "Vendors Pending Activation", vendors.get("PENDING", 0), "VENDOR_MANAGEMENT", "vendor",
                  {"entity": "vendor", "status": "PENDING"})
        self._kpi(out, "vendor_onboarding_open", "Open Onboarding Requests", open_requests, "VENDOR_MANAGEMENT", "vendor",
                  {"entity": "vendor_onboarding"})
        self._action(out, "vendor_onboarding_failed", "Onboarding Requests Needing Attention (Pre-Screen Pending)",
                     onboarding.get("PRE_SCREEN_PENDING", 0), "VENDOR_MANAGEMENT",
                     {"entity": "vendor_onboarding", "status": "PRE_SCREEN_PENDING"})
        if "onboarding_process" in caps or "onboarding" not in caps:
            # Vendor_Intake / Admin by role, or ONBOARDING_PROCESS: the requests this user works on.
            self._action(out, "vendor_onboarding_assigned_to_me", "Onboarding Requests Assigned to Me", assigned_to_me,
                         "ONBOARDING_PROCESS", {"entity": "vendor_onboarding", "assigned_to_me": True}, "high")
        if "onboarding_assign" in caps:
            self._action(out, "vendor_onboarding_unassigned", "Unassigned Onboarding Requests", unassigned,
                         "ONBOARDING_ASSIGN", {"entity": "vendor_onboarding", "assigned": False})
        out["status_summary"].append(self._status_chart(
            "vendor_status_distribution", "Vendors by Status", "VENDOR", vendors,
            ["PENDING", "ACTIVE", "INACTIVE", "BLOCKED"], labels, "VENDOR_MANAGEMENT"))
        out["status_summary"].append(self._status_chart(
            "vendor_onboarding_distribution", "Onboarding Requests by Status", "VENDOR_ONBOARDING", onboarding,
            ["CREATED", "ASSIGNED", "IN_PROGRESS", "PRE_SCREENING", "PRE_SCREEN_PENDING", "PASSED", "NDA_PENDING",
             "COMPLETED", "FAILED", "CANCELLED"], labels, "VENDOR_MANAGEMENT"))

    # =========================================================
    # Trends
    # =========================================================

    def _trends(self, out, caps, granularity, period_from, period_to):
        def series(rows_by_currency):
            return [
                {"currency_code": cur, "points": [{"period": p, "value": v} for p, v in sorted(points.items())]}
                for cur, points in sorted(rows_by_currency.items(), key=lambda kv: kv[0] or "")
            ]

        if caps & {"invoices", "tds"}:
            rows = self.dao.invoice_trend(granularity, period_from, period_to)
            counts: dict = {}
            amounts: dict = {}
            tds: dict = {}
            for period, cur, count, net, tds_amount in rows:
                day = period.date() if hasattr(period, "date") else period
                counts[day] = counts.get(day, 0) + int(count)
                amounts.setdefault(cur, {})[day] = _money(Decimal(amounts.get(cur, {}).get(day, 0)) + Decimal(net))
                tds.setdefault(cur, {})[day] = _money(Decimal(tds.get(cur, {}).get(day, 0)) + Decimal(tds_amount))
            if "invoices" in caps:
                out["trends"].append({"key": "invoice_count_trend", "title": "Invoices Received", "type": "count",
                                      "granularity": granularity, "permission": "INVOICE_VIEW",
                                      "series": [{"currency_code": None, "points": [{"period": p, "value": v} for p, v in sorted(counts.items())]}]})
                out["trends"].append({"key": "invoice_amount_trend", "title": "Invoice Value", "type": "amount",
                                      "granularity": granularity, "permission": "INVOICE_VIEW", "series": series(amounts)})
            if "tds" in caps:
                out["trends"].append({"key": "tds_amount_trend", "title": "TDS Withheld", "type": "amount",
                                      "granularity": granularity, "permission": "INVOICE_TDS_VIEW", "series": series(tds)})
        if "payments" in caps:
            paid: dict = {}
            for period, cur, amount in self.dao.payment_trend(granularity, period_from, period_to):
                day = period.date() if hasattr(period, "date") else period
                paid.setdefault(cur, {})[day] = _money(Decimal(paid.get(cur, {}).get(day, 0)) + Decimal(amount))
            out["trends"].append({"key": "payment_amount_trend", "title": "Payments Cleared", "type": "amount",
                                  "granularity": granularity, "permission": "PAYMENT_VIEW", "series": series(paid)})

    # =========================================================
    # Recent activity
    # =========================================================

    def _recent_activity(self, out, caps, period_from, period_to):
        sources: dict = {}
        for section, tables in ACTIVITY_SOURCES.items():
            if section in caps:
                for table, actions in tables.items():
                    sources.setdefault(table, set()).update(actions)
        rows = self.dao.recent_audit(sources, period_from, period_to, RECENT_ACTIVITY_LIMIT)
        invoice_numbers = self.dao.invoice_numbers(r.record_id for r in rows if r.table_name == "invoice")
        pr_numbers = self.dao.pr_numbers(r.record_id for r in rows if r.table_name == "purchase_requisition")
        vendor_names = self.dao.vendor_names(r.record_id for r in rows if r.table_name == "vendor")
        reference = {"invoice": invoice_numbers, "purchase_requisition": pr_numbers, "vendor": vendor_names}
        for row in rows:
            out["recent_activity"].append({
                "id": row.audit_log_id,
                "action": row.action,
                "title": ACTIVITY_LABELS.get(row.action, row.action.replace("_", " ").capitalize()),
                "entity_type": _ENTITY_BY_TABLE.get(row.table_name, row.table_name),
                "entity_id": row.record_id,
                "reference": reference.get(row.table_name, {}).get(row.record_id),
                "actor": row.changed_by,
                "occurred_at": row.changed_at,
            })
