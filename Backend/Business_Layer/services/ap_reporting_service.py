# Backend/Business_Layer/services/ap_reporting_service.py
"""Finance Executive dashboard + AP reports (APM_AUTOMATION_PLAN.md 3.5).

One row model (InvoiceFigures) feeds the dashboard and every report, so a total on
screen always equals the same total in an export. Amount rules are the existing ones:

  tds          = invoice_tds.tds_amount when tds_applicable and DETERMINED/VERIFIED
  net_payable  = net_amount - tds                      (compute_payable_amount)
  paid         = invoice.amount_paid                    (CLEARED allocations only)
  reserved     = SCHEDULED/SENT allocations             (not yet paid)
  outstanding  = max(net_payable - paid - reserved, 0)  (a partly paid invoice counts once)

Due dates: invoice.due_date is the effective due date maintained by
PaymentTermComplianceService; an invoice whose payment-term record has no effective
due date is reported as "due date unverified", never as due or overdue. Money is never
summed across currencies. Forecasts are "expected payments based on recorded invoices
and due dates" - not a guaranteed cash-flow forecast (disputed invoices are excluded
and shown as on hold).
"""
from __future__ import annotations

import datetime
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from Backend.API_Layer.middleware.permission_base_access import has_permissions
from Backend.Business_Layer.services.payment_term_compliance_service import EXCEPTION_STATUSES, REASON_TEXT
from Backend.Business_Layer.utils.statutory_calendar import (
    configured_deposit_days,
    tds_deposit_due_date,
    tds_statement_due_date,
)
from Backend.Data_Access_Layer.dao.ap_reporting_dao import APReportingDAO
from Backend.Data_Access_Layer.dao.payment_term_dao import PaymentTermDAO

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")

PAYABLE = ("READY_FOR_PAYMENT", "PARTIALLY_PAID")
APPROVED = ("APPROVED",)
IN_APPROVAL = ("PENDING_APPROVAL",)
IN_REVIEW = ("OCR_REVIEW_PENDING", "OCR_REVIEWED", "RETURNED_FOR_REVIEW")
ON_HOLD = ("DISPUTED",)
OPEN_LIABILITY = PAYABLE + APPROVED + IN_APPROVAL + IN_REVIEW
APPROVED_LIABILITY = PAYABLE + APPROVED
TDS_REGISTER_EXCLUDED = ("REJECTED", "DRAFT", "OCR_FAILED")

STAGE_OF = {**{s: "PAYABLE" for s in PAYABLE}, "APPROVED": "APPROVED",
            "PENDING_APPROVAL": "IN_APPROVAL", **{s: "IN_REVIEW" for s in IN_REVIEW}, "DISPUTED": "ON_HOLD"}
STAGE_LABELS = {"PAYABLE": "Ready for payment", "APPROVED": "Approved, not yet ready",
                "IN_APPROVAL": "Awaiting approval", "IN_REVIEW": "In review", "ON_HOLD": "Disputed (on hold)"}

AGEING_BUCKETS = (("1-15", 1, 15), ("16-30", 16, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None))
DUE_SOON_DAYS = 7
PAID_TREND_MONTHS = 6
BASE_CURRENCY = "INR"
RECENT_PAYMENTS_LIMIT = 10
RECEIPT_CHECK_DAYS = 90
TOP_INVOICES_PER_BUCKET = 5
MAX_REPORT_ROWS = 10000
FORECAST_NOTE = ("Expected payments based on recorded invoices and their due dates - not a guaranteed cash-flow "
                 "forecast. Disputed invoices are excluded; invoices without a verified due date are shown separately.")

FINANCE_PERMISSIONS = ["PAYMENT_VIEW", "PAYMENT_PROCESS"]
TDS_PERMISSIONS = ["TDS_TRACKING_VIEW", "TDS_TRACKING_UPDATE", "INVOICE_TDS_VIEW", "INVOICE_TDS_VERIFY"]
TERM_PERMISSIONS = ["INVOICE_PAYMENT_TERM_VERIFY", "PAYMENT_VIEW", "PAYMENT_PROCESS"]
# Management (CEO / Chief Product Officer): read every report; exporting needs the export grant.
MANAGEMENT_REPORTS_VIEW = "AP_MANAGEMENT_REPORTS_VIEW"
MANAGEMENT_REPORTS_EXPORT = "AP_MANAGEMENT_REPORTS_EXPORT"


def _money(value) -> Decimal:
    return (Decimal(str(value)) if value is not None else ZERO).quantize(CENTS)


@dataclass
class InvoiceFigures:
    invoice_id: int
    invoice_number: str
    vendor_id: int
    vendor_name: str
    invoice_type: str
    invoice_date: datetime.date
    due_date: Optional[datetime.date]
    due_verified: bool
    status_code: Optional[str]
    status_name: Optional[str]
    stage: Optional[str]
    currency_code: str
    symbol: str
    net_amount: Decimal
    tds_amount: Decimal
    net_payable: Decimal
    paid: Decimal
    reserved: Decimal
    outstanding: Decimal
    department: Optional[str]
    category: Optional[str]
    term_status: Optional[str]
    term_reason: Optional[str]
    statutory_due_date: Optional[datetime.date]
    tds: Any = None
    tracking: Any = None
    term: Any = None
    nature_code: Optional[str] = None
    section: Optional[str] = None

    def days_overdue(self, today: datetime.date) -> Optional[int]:
        if not self.due_verified or self.due_date is None or self.outstanding <= 0:
            return None
        return (today - self.due_date).days if self.due_date < today else 0


class _MoneyByCurrency:
    """{currency: {"count", "amount"}} accumulator rendered as the dashboard's list-per-currency."""

    def __init__(self):
        self._data: "OrderedDict[str, dict]" = OrderedDict()

    def add(self, code: str, symbol: str, amount: Decimal, count: int = 1) -> None:
        slot = self._data.setdefault(code, {"currency_code": code, "symbol": symbol, "amount": ZERO, "count": 0})
        slot["amount"] = _money(slot["amount"] + amount)
        slot["count"] += count

    def as_list(self) -> List[dict]:
        return [dict(v) for v in self._data.values()]

    @property
    def count(self) -> int:
        return sum(v["count"] for v in self._data.values())


class APReportingService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.dao = APReportingDAO(db)
        self.today = today or datetime.date.today()

    # =================================================================
    # Row model
    # =================================================================
    def invoice_figures(self, statuses: Optional[Iterable[str]] = None, **filters) -> List[InvoiceFigures]:
        rows = self.dao.invoice_rows(list(statuses) if statuses else None, **filters)
        reserved = self.dao.reserved_by_invoice(r[0].invoice_id for r in rows)
        out = []
        for (invoice, vendor_name, status_code, status_name, currency_code, symbol, tds, term, tracking,
             department, category, nature_code, section) in rows:
            tds_amount = _money(tds.tds_amount) if (
                tds is not None and tds.tds_applicable and tds.determination_status in ("DETERMINED", "VERIFIED")
            ) else ZERO
            net = _money(invoice.net_amount)
            net_payable = _money(net - tds_amount)
            paid = _money(invoice.amount_paid)
            held = _money(reserved.get(invoice.invoice_id, 0))
            outstanding = max(_money(net_payable - paid - held), ZERO)
            due_verified = term is None or term.effective_due_date is not None
            out.append(InvoiceFigures(
                invoice_id=invoice.invoice_id,
                invoice_number=invoice.invoice_number,
                vendor_id=invoice.vendor_id,
                vendor_name=vendor_name,
                invoice_type=invoice.invoice_type,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                due_verified=due_verified,
                status_code=status_code,
                status_name=status_name,
                stage=STAGE_OF.get(status_code),
                currency_code=currency_code or "INR",
                symbol=symbol or "₹",
                net_amount=net,
                tds_amount=tds_amount,
                net_payable=net_payable,
                paid=paid,
                reserved=held,
                outstanding=outstanding,
                department=department,
                category=category,
                term_status=term.validation_status if term is not None else None,
                term_reason=term.reason_code if term is not None else None,
                statutory_due_date=term.statutory_due_date if term is not None else None,
                tds=tds,
                tracking=tracking,
                term=term,
                nature_code=nature_code,
                section=section,
            ))
        return out

    # =================================================================
    # Finance Executive dashboard
    # =================================================================
    def finance_dashboard(self, user) -> Dict[str, Any]:
        today = self.today
        figures = self.invoice_figures(OPEN_LIABILITY + ON_HOLD)
        open_items = [f for f in figures if f.stage != "ON_HOLD" and f.outstanding > 0]

        ready = _MoneyByCurrency()
        ready_due_soon = _MoneyByCurrency()
        ready_overdue = _MoneyByCurrency()
        approved_not_ready = _MoneyByCurrency()
        partially_paid = _MoneyByCurrency()
        overdue = _MoneyByCurrency()
        msme_at_risk = _MoneyByCurrency()
        on_hold = _MoneyByCurrency()
        blocked_by_terms = 0
        ageing = {label: _MoneyByCurrency() for label, *_ in AGEING_BUCKETS}
        not_due = _MoneyByCurrency()
        unverified = _MoneyByCurrency()

        for f in figures:
            if f.stage == "ON_HOLD" and f.outstanding > 0:
                on_hold.add(f.currency_code, f.symbol, f.outstanding)
        for f in open_items:
            late = f.days_overdue(today)
            if f.stage == "PAYABLE":
                ready.add(f.currency_code, f.symbol, f.outstanding)
                if late:
                    ready_overdue.add(f.currency_code, f.symbol, f.outstanding)
                elif f.due_verified and f.due_date is not None and (f.due_date - today).days <= DUE_SOON_DAYS:
                    ready_due_soon.add(f.currency_code, f.symbol, f.outstanding)
                if f.status_code == "PARTIALLY_PAID":
                    partially_paid.add(f.currency_code, f.symbol, f.outstanding)
            if f.stage == "APPROVED":
                approved_not_ready.add(f.currency_code, f.symbol, f.outstanding)
                if f.term_status in EXCEPTION_STATUSES:
                    blocked_by_terms += 1
            if f.stage in ("PAYABLE", "APPROVED"):
                if late:
                    overdue.add(f.currency_code, f.symbol, f.outstanding)
                    for label, low, high in AGEING_BUCKETS:
                        if late >= low and (high is None or late <= high):
                            ageing[label].add(f.currency_code, f.symbol, f.outstanding)
                elif not f.due_verified:
                    unverified.add(f.currency_code, f.symbol, f.outstanding)
                else:
                    not_due.add(f.currency_code, f.symbol, f.outstanding)
            if f.statutory_due_date is not None and f.statutory_due_date <= today + datetime.timedelta(days=DUE_SOON_DAYS):
                msme_at_risk.add(f.currency_code, f.symbol, f.outstanding)

        term_exceptions = [f for f in open_items if f.term_status in EXCEPTION_STATUSES]
        exceptions_money = _MoneyByCurrency()
        for f in term_exceptions:
            exceptions_money.add(f.currency_code, f.symbol, f.outstanding)

        cards = [
            self._card("ready_for_payment", "Ready for payment", ready, "/accounts-payable/payments/ready",
                       detail=[("Due within 7 days", ready_due_soon), ("Overdue", ready_overdue)]),
            self._card("overdue", "Overdue (approved, unpaid)", overdue, "/accounts-payable/payments/ready?overdue=1",
                       tone="danger"),
            self._card("approved_not_ready", "Approved, not yet marked ready", approved_not_ready,
                       "/accounts-payable/invoices?queue=approved",
                       note=f"{blocked_by_terms} blocked by payment-term exceptions" if blocked_by_terms else None),
            self._card("partially_paid", "Partially paid - balance due", partially_paid,
                       "/accounts-payable/payments/ready?status=PARTIALLY_PAID"),
            self._card("term_exceptions", "Payment-term exceptions", exceptions_money,
                       "/accounts-payable/reports?report=payment_term_exceptions", tone="warning"),
            self._card("msme_due", "MSME statutory deadline within 7 days / passed", msme_at_risk, None, tone="warning"),
        ]
        if on_hold.count:
            cards.append(self._card("on_hold", "Disputed (on hold)", on_hold, "/accounts-payable/invoices"))

        cleared = self.dao.cleared_payment_rows(paid_from=today - datetime.timedelta(days=RECEIPT_CHECK_DAYS))
        receipts_missing = len({row[0] for row in cleared if not row[11]})
        recent = self._recent_payments(self.dao.cleared_payment_rows(limit=RECENT_PAYMENTS_LIMIT * 5))[:RECENT_PAYMENTS_LIMIT]

        # ---- headline KPI tiles + paid trend (base currency; other currencies stay on the cards)
        base = BASE_CURRENCY
        due_week = _MoneyByCurrency()
        for f in open_items:
            if f.stage in ("PAYABLE", "APPROVED") and f.due_verified and f.due_date is not None                     and today <= f.due_date <= today + datetime.timedelta(days=DUE_SOON_DAYS):
                due_week.add(f.currency_code, f.symbol, f.outstanding)
        trend_start = self._month_starts(1)[0]
        for _ in range(PAID_TREND_MONTHS - 1):
            trend_start = (trend_start - datetime.timedelta(days=1)).replace(day=1)
        trend = self._paid_trend(self.dao.cleared_payment_rows(paid_from=trend_start), trend_start, base)
        this_month = trend[-1] if trend else {"amount": ZERO, "count": 0}
        tds_overdue = 0
        if result_tds := (self._tds_summary(figures) if has_permissions(user, TDS_PERMISSIONS) else None):
            tds_overdue = sum(i["count"] for i in result_tds["items"] if i["key"] in ("deposit_overdue", "filing_overdue"))
        needs_action = approved_not_ready.count + len(term_exceptions) + tds_overdue
        kpis = [
            _kpi("ready_to_pay", "Ready to pay", ready, base, f"{_n(ready.count, 'invoice')} · {ready_overdue.count} overdue",
                 "indigo", "/accounts-payable/payments/ready"),
            _kpi("due_this_week", "Due in next 7 days", due_week, base, f"{_n(due_week.count, 'approved invoice')}", "amber",
                 "/accounts-payable/payments/ready"),
            _kpi("overdue", "Overdue", overdue, base, f"{_n(overdue.count, 'invoice')} past due", "rose",
                 "/accounts-payable/payments/ready?overdue=1"),
            {"key": "paid_this_month", "label": "Paid this month", "format": "money", "value": this_month["amount"],
             "currency_code": base, "subtitle": f"{_n(this_month['count'], 'payment')} cleared", "tone": "emerald",
             "link": "/accounts-payable/payments/history"},
            {"key": "needs_action", "label": "Needs action", "format": "count", "value": needs_action,
             "currency_code": base, "tone": "amber" if needs_action else "gray", "link": None,
             "subtitle": f"{approved_not_ready.count} to mark ready · {len(term_exceptions)} term exceptions"
                         + (f" · {tds_overdue} TDS overdue" if tds_overdue else "")},
        ]

        result = {
            "as_of": today,
            "base_currency": base,
            "kpis": kpis,
            "paid_trend": trend,
            "action_cards": cards,
            "ageing": {
                "buckets": [{"label": "Not yet due", "amounts": not_due.as_list()}]
                + [{"label": f"{label} days overdue", "amounts": ageing[label].as_list()} for label, *_ in AGEING_BUCKETS]
                + [{"label": "Due date unverified", "amounts": unverified.as_list()}],
            },
            "upcoming": self._upcoming(open_items, months=3),
            "recent_payments": recent,
            "receipts_missing": {"count": receipts_missing, "days": RECEIPT_CHECK_DAYS},
            "term_exceptions": [self._exception_row(f) for f in term_exceptions[:TOP_INVOICES_PER_BUCKET]],
            "term_exception_count": len(term_exceptions),
            "agreements_expiring": self._expiring_agreements(),
            "tds": result_tds,
            "forecast_note": FORECAST_NOTE,
        }
        return result

    def _paid_trend(self, cleared_rows, start: datetime.date, currency: str) -> List[dict]:
        months = []
        cursor = start
        while cursor <= self.today:
            months.append(cursor)
            cursor = (cursor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        buckets = OrderedDict((m.strftime("%Y-%m"), {"period": m.strftime("%Y-%m"), "label": m.strftime("%b"),
                                                      "amount": ZERO, "count": 0, "payment_ids": set()}) for m in months)
        for row in cleared_rows:
            paid_on, amount, code = row[1], row[4], row[9] or "INR"
            slot = buckets.get(paid_on.strftime("%Y-%m")) if paid_on else None
            if slot is None or code != currency:
                continue
            slot["amount"] = _money(slot["amount"] + _money(amount))
            slot["payment_ids"].add(row[0])
        return [{"period": b["period"], "label": b["label"], "amount": b["amount"], "count": len(b["payment_ids"])}
                for b in buckets.values()]

    @staticmethod
    def _card(key, label, money: _MoneyByCurrency, link, tone="default", detail=None, note=None) -> dict:
        return {
            "key": key, "label": label, "count": money.count, "amounts": money.as_list(), "link": link, "tone": tone,
            "detail": [{"label": d_label, "count": m.count, "amounts": m.as_list()} for d_label, m in (detail or [])],
            "note": note,
        }

    def _month_starts(self, months: int) -> List[datetime.date]:
        start = self.today.replace(day=1)
        out = []
        for i in range(months):
            month = start.month - 1 + i
            out.append(datetime.date(start.year + month // 12, month % 12 + 1, 1))
        return out

    def _upcoming(self, items: List[InvoiceFigures], months: int) -> Dict[str, Any]:
        starts = self._month_starts(months + 1)
        buckets: "OrderedDict[str, dict]" = OrderedDict()
        buckets["overdue"] = {"key": "overdue", "label": "Overdue", "start": None, "end": self.today - datetime.timedelta(days=1)}
        for i in range(months):
            start = starts[i] if i else self.today
            end = starts[i + 1] - datetime.timedelta(days=1)
            buckets[f"m{i}"] = {"key": f"m{i}", "label": starts[i].strftime("%b %Y"), "start": start, "end": end}
        buckets["later"] = {"key": "later", "label": f"After {starts[months - 1].strftime('%b %Y')}",
                            "start": starts[months], "end": None}
        buckets["unverified"] = {"key": "unverified", "label": "Due date unverified", "start": None, "end": None}
        for b in buckets.values():
            b.update(approved=_MoneyByCurrency(), pipeline=_MoneyByCurrency(), invoices=[])

        for f in items:
            if not f.due_verified or f.due_date is None:
                key = "unverified"
            elif f.due_date < self.today:
                key = "overdue"
            else:
                key = next((k for k, b in buckets.items() if b["start"] and b["start"] <= f.due_date
                            and (b["end"] is None or f.due_date <= b["end"])), "later")
            bucket = buckets[key]
            (bucket["approved"] if f.stage in ("PAYABLE", "APPROVED") else bucket["pipeline"]).add(
                f.currency_code, f.symbol, f.outstanding)
            bucket["invoices"].append(f)

        out = []
        for b in buckets.values():
            top = sorted(b["invoices"], key=lambda f: f.outstanding, reverse=True)[:TOP_INVOICES_PER_BUCKET]
            out.append({
                "key": b["key"], "label": b["label"], "start": b["start"], "end": b["end"],
                "approved": b["approved"].as_list(), "pipeline": b["pipeline"].as_list(),
                "count": len(b["invoices"]),
                "top_invoices": [self._invoice_brief(f) for f in top],
            })
        return {"months": months, "buckets": out, "note": FORECAST_NOTE}

    def _invoice_brief(self, f: InvoiceFigures) -> dict:
        return {
            "invoice_id": f.invoice_id, "invoice_number": f.invoice_number, "vendor_name": f.vendor_name,
            "due_date": f.due_date if f.due_verified else None, "status_code": f.status_code,
            "stage": f.stage, "outstanding": f.outstanding, "currency_code": f.currency_code, "symbol": f.symbol,
            "days_overdue": f.days_overdue(self.today), "term_status": f.term_status,
        }

    def _exception_row(self, f: InvoiceFigures) -> dict:
        row = self._invoice_brief(f)
        row.update(reason_code=f.term_reason, reason_text=REASON_TEXT.get(f.term_reason or "", f.term_reason))
        return row

    @staticmethod
    def _recent_payments(rows) -> List[dict]:
        by_payment: "OrderedDict[int, dict]" = OrderedDict()
        for (payment_id, paid_on, mode, reference, amount, invoice_id, invoice_number, due_date, vendor_name,
             currency_code, symbol, receipts, *_) in rows:
            entry = by_payment.setdefault(payment_id, {
                "payment_id": payment_id, "paid_on": paid_on, "payment_mode": mode, "reference_number": reference,
                "vendor_name": vendor_name, "currency_code": currency_code, "symbol": symbol, "amount": ZERO,
                "invoices": [], "receipt_count": int(receipts or 0),
            })
            entry["amount"] = _money(entry["amount"] + _money(amount))
            entry["invoices"].append({"invoice_id": invoice_id, "invoice_number": invoice_number})
        return list(by_payment.values())

    def _expiring_agreements(self) -> List[dict]:
        out = []
        for agreement, vendor_name in PaymentTermDAO(self.db).list_expiring_agreements(self.today, 30):
            out.append({"agreement_id": agreement.agreement_id, "vendor_id": agreement.vendor_id,
                        "vendor_name": vendor_name, "title": agreement.title, "valid_to": agreement.valid_to,
                        "days_to_expiry": (agreement.valid_to - self.today).days})
        return out

    def _tds_summary(self, figures: List[InvoiceFigures]) -> dict:
        due_day, march_day = configured_deposit_days(self.db)
        month_end = (self._month_starts(2)[1] - datetime.timedelta(days=1))
        counts = defaultdict(_MoneyByCurrency)
        for f in figures:
            tds = f.tds
            if tds is None or not tds.tds_applicable:
                continue
            if tds.determination_status == "DETERMINED" and f.stage in ("PAYABLE", "APPROVED", "IN_APPROVAL"):
                counts["verification_pending"].add(f.currency_code, f.symbol, f.tds_amount)
            status = f.tracking.tracking_status if f.tracking is not None else "TDS_PENDING"
            if status == "TDS_PENDING" and f.paid > 0:
                counts["deduction_not_recorded"].add(f.currency_code, f.symbol, f.tds_amount)
            if status == "TDS_DEDUCTED":
                due = tds_deposit_due_date(f.tracking.deduction_date, due_day, march_day)
                if due and due < self.today:
                    counts["deposit_overdue"].add(f.currency_code, f.symbol, f.tds_amount)
                elif due and due <= month_end:
                    counts["deposit_due_this_month"].add(f.currency_code, f.symbol, f.tds_amount)
            if status == "TDS_DEPOSITED":
                due = tds_statement_due_date(f.tracking.deduction_date)
                if due and due < self.today:
                    counts["filing_overdue"].add(f.currency_code, f.symbol, f.tds_amount)
                elif due and (due - self.today).days <= 45:
                    counts["filing_due_soon"].add(f.currency_code, f.symbol, f.tds_amount)
        labels = OrderedDict([
            ("verification_pending", "TDS verification pending"),
            ("deduction_not_recorded", "Paid, deduction not recorded"),
            ("deposit_due_this_month", "Deposit due this month"),
            ("deposit_overdue", "Deposit overdue"),
            ("filing_due_soon", "Quarterly statement due within 45 days"),
            ("filing_overdue", "Quarterly statement overdue"),
        ])
        return {"items": [{"key": k, "label": label, "count": counts[k].count, "amounts": counts[k].as_list()}
                          for k, label in labels.items()],
                "link": "/accounts-payable/tds/tracking"}

    # =================================================================
    # Reports
    # =================================================================
    REPORTS = OrderedDict([
        ("outstanding_payables", {"title": "AP liabilities - outstanding payables", "period": "as_of",
                                  "permissions": FINANCE_PERMISSIONS}),
        ("ageing", {"title": "Payables ageing by vendor", "period": "as_of", "permissions": FINANCE_PERMISSIONS}),
        ("expected_payments", {"title": "Expected payments by month", "period": "as_of",
                               "permissions": FINANCE_PERMISSIONS}),
        ("payments_made", {"title": "Payments made", "period": "range", "permissions": FINANCE_PERMISSIONS}),
        ("tds_register", {"title": "TDS register", "period": "range", "permissions": TDS_PERMISSIONS}),
        ("payment_term_exceptions", {"title": "Payment-term exceptions", "period": "as_of",
                                     "permissions": TERM_PERMISSIONS}),
    ])

    def report_summary(self, user, date_from: Optional[datetime.date] = None, date_to: Optional[datetime.date] = None,
                       vendor_id: Optional[int] = None, department_id: Optional[int] = None,
                       currency: str = BASE_CURRENCY) -> Dict[str, Any]:
        """Period overview for the Reports page: KPI tiles, invoiced vs paid by month and spend
        breakdowns. Period amounts use invoice_date (invoiced) and payment date (paid); balances
        (outstanding / overdue) are as of today. One currency per call - nothing is converted."""
        if not has_permissions(user, FINANCE_PERMISSIONS + [MANAGEMENT_REPORTS_VIEW]):
            raise PermissionError("You do not have permission to view AP reports")
        date_to = date_to or self.today
        date_from = date_from or (date_to - datetime.timedelta(days=90))
        if date_from > date_to:
            raise ValueError("from_date must be on or before to_date")
        if (date_to - date_from).days > 731:
            raise ValueError("The report period cannot exceed 2 years")

        invoiced = [f for f in self.invoice_figures(None, invoice_from=date_from, invoice_to=date_to,
                                                     vendor_id=vendor_id, department_id=department_id)
                    if f.status_code not in TDS_REGISTER_EXCLUDED and f.currency_code == currency]
        open_now = [f for f in self.invoice_figures(OPEN_LIABILITY, vendor_id=vendor_id, department_id=department_id)
                    if f.currency_code == currency and f.outstanding > 0]
        paid_rows = [r for r in self.dao.cleared_payment_rows(date_from, date_to, vendor_id)
                     if (r[9] or BASE_CURRENCY) == currency]

        invoiced_total = sum((f.net_amount for f in invoiced), ZERO)
        tds_total = sum((f.tds_amount for f in invoiced), ZERO)
        paid_total = sum((_money(r[4]) for r in paid_rows), ZERO)
        outstanding = sum((f.outstanding for f in open_now), ZERO)
        overdue_items = [f for f in open_now if f.stage in ("PAYABLE", "APPROVED") and f.days_overdue(self.today)]
        overdue_total = sum((f.outstanding for f in overdue_items), ZERO)
        on_time = [r for r in paid_rows if r[7] is None or r[1] <= r[7]]
        days_to_pay = [(r[1] - r[12]).days for r in paid_rows if r[1] and len(r) > 12 and r[12]]
        payment_ids = {r[0] for r in paid_rows}

        kpis = [
            {"key": "invoiced", "label": "Invoiced", "format": "money", "value": _money(invoiced_total),
             "subtitle": f"{_n(len(invoiced), 'invoice')} in period", "tone": "indigo"},
            {"key": "paid", "label": "Paid", "format": "money", "value": _money(paid_total),
             "subtitle": f"{_n(len(payment_ids), 'payment')} cleared", "tone": "emerald"},
            {"key": "outstanding", "label": "Outstanding now", "format": "money", "value": _money(outstanding),
             "subtitle": f"{_n(len(open_now), 'open invoice')}, as of today", "tone": "amber"},
            {"key": "overdue", "label": "Overdue now", "format": "money", "value": _money(overdue_total),
             "subtitle": f"{_n(len(overdue_items), 'approved invoice')} past due", "tone": "rose"},
            {"key": "tds", "label": "TDS withheld", "format": "money", "value": _money(tds_total),
             "subtitle": "On invoices in period", "tone": "gray"},
            {"key": "on_time", "label": "Paid on time", "format": "percent",
             "value": round(100 * len(on_time) / len(paid_rows), 1) if paid_rows else None,
             "subtitle": f"{len(on_time)} of {len(paid_rows)} payment allocations", "tone": "emerald"},
            {"key": "days_to_pay", "label": "Avg days to pay", "format": "days",
             "value": round(sum(days_to_pay) / len(days_to_pay), 1) if days_to_pay else None,
             "subtitle": "Invoice date to payment", "tone": "gray"},
            {"key": "vendors", "label": "Vendors", "format": "count", "value": len({f.vendor_id for f in invoiced}),
             "subtitle": "Invoiced in period", "tone": "gray"},
        ]

        months = OrderedDict()
        cursor = date_from.replace(day=1)
        while cursor <= date_to:
            months[cursor.strftime("%Y-%m")] = {"period": cursor.strftime("%Y-%m"), "label": cursor.strftime("%b %y"),
                                               "invoiced": ZERO, "paid": ZERO, "invoices": 0, "payments": set()}
            cursor = (cursor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        for f in invoiced:
            slot = months.get(f.invoice_date.strftime("%Y-%m"))
            if slot:
                slot["invoiced"] = _money(slot["invoiced"] + f.net_amount)
                slot["invoices"] += 1
        for r in paid_rows:
            slot = months.get(r[1].strftime("%Y-%m")) if r[1] else None
            if slot:
                slot["paid"] = _money(slot["paid"] + _money(r[4]))
                slot["payments"].add(r[0])
        monthly = [{**{k: v for k, v in m.items() if k != "payments"}, "payments": len(m["payments"])}
                   for m in months.values()]

        def breakdown(key_fn, label_fn, items, limit=8):
            grouped = OrderedDict()
            for f in items:
                key = key_fn(f)
                slot = grouped.setdefault(key, {"key": str(key), "label": label_fn(f), "amount": ZERO, "count": 0})
                slot["amount"] = _money(slot["amount"] + f.net_amount)
                slot["count"] += 1
            ranked = sorted(grouped.values(), key=lambda x: x["amount"], reverse=True)
            if len(ranked) > limit:
                rest = ranked[limit - 1:]
                ranked = ranked[:limit - 1] + [{"key": "other", "label": f"Other ({len(rest)})",
                                                "amount": _money(sum((x["amount"] for x in rest), ZERO)),
                                                "count": sum(x["count"] for x in rest)}]
            return ranked

        stage = OrderedDict()
        for f in open_now:
            slot = stage.setdefault(f.stage, {"key": f.stage, "label": STAGE_LABELS.get(f.stage, f.stage),
                                              "amount": ZERO, "count": 0})
            slot["amount"] = _money(slot["amount"] + f.outstanding)
            slot["count"] += 1

        return {
            "period": {"from_date": date_from, "to_date": date_to, "as_of": self.today},
            "currency": currency,
            "kpis": kpis,
            "monthly": monthly,
            "by_vendor": breakdown(lambda f: f.vendor_id, lambda f: f.vendor_name, invoiced),
            "by_department": breakdown(lambda f: f.department or "Unassigned", lambda f: f.department or "Unassigned", invoiced),
            "by_category": breakdown(lambda f: f.category or "Unassigned", lambda f: f.category or "Unassigned", invoiced),
            "outstanding_by_stage": [stage[k] for k in ("PAYABLE", "APPROVED", "IN_APPROVAL", "IN_REVIEW") if k in stage],
            "notes": ["Invoiced and TDS by invoice date; paid by payment date; outstanding and overdue as of today. "
                      f"Amounts in {currency} only - invoices in other currencies are not converted."],
        }

    def available_reports(self, user) -> List[dict]:
        return [{"key": key, "title": spec["title"], "period": spec["period"],
                 "can_export": self.can_export(user, key)}
                for key, spec in self.REPORTS.items() if self.can_view(user, key)]

    def can_view(self, user, key: str) -> bool:
        spec = self.REPORTS.get(key)
        return bool(spec) and (has_permissions(user, spec["permissions"]) or has_permissions(user, [MANAGEMENT_REPORTS_VIEW]))

    def can_export(self, user, key: str) -> bool:
        """A report's own (operational) permission includes export; a management user needs the
        separate AP_MANAGEMENT_REPORTS_EXPORT grant."""
        spec = self.REPORTS.get(key)
        return bool(spec) and (has_permissions(user, spec["permissions"]) or has_permissions(user, [MANAGEMENT_REPORTS_EXPORT]))

    def run_report(self, key: str, user, date_from: Optional[datetime.date] = None,
                   date_to: Optional[datetime.date] = None, vendor_id: Optional[int] = None,
                   department_id: Optional[int] = None, months: int = 3) -> Dict[str, Any]:
        spec = self.REPORTS.get(key)
        if spec is None:
            raise ValueError(f"Unknown report '{key}'")
        if not self.can_view(user, key):
            raise PermissionError("You do not have permission to run this report")
        if spec["period"] == "range":
            date_to = date_to or self.today
            date_from = date_from or (date_to - datetime.timedelta(days=90))
            if date_from > date_to:
                raise ValueError("from_date must be on or before to_date")
            if (date_to - date_from).days > 731:
                raise ValueError("The report period cannot exceed 2 years")
        builder = getattr(self, f"_report_{key}")
        report = builder(date_from=date_from, date_to=date_to, vendor_id=vendor_id,
                         department_id=department_id, months=max(1, min(int(months), 12)))
        if len(report["rows"]) > MAX_REPORT_ROWS:
            report["rows"] = report["rows"][:MAX_REPORT_ROWS]
            report.setdefault("notes", []).append(f"Truncated to the first {MAX_REPORT_ROWS} rows.")
        report.update(key=key, title=spec["title"], generated_at=datetime.datetime.now().replace(microsecond=0),
                      period={"type": spec["period"], "as_of": self.today, "from_date": date_from, "to_date": date_to})
        report["totals"] = self._totals(report)
        return report

    @staticmethod
    def _totals(report) -> List[dict]:
        money_cols = [c["key"] for c in report["columns"] if c["type"] == "money"]
        by_currency: "OrderedDict[str, dict]" = OrderedDict()
        for row in report["rows"]:
            code = row.get("currency_code") or "INR"
            slot = by_currency.setdefault(code, {"currency_code": code, "rows": 0, **{c: ZERO for c in money_cols}})
            slot["rows"] += 1
            for c in money_cols:
                slot[c] = _money(slot[c] + _money(row.get(c)))
        return list(by_currency.values())

    def _due_status(self, f: InvoiceFigures) -> str:
        if not f.due_verified or f.due_date is None:
            return "Due date unverified"
        late = f.days_overdue(self.today)
        if late:
            return f"Overdue {late} day{'s' if late != 1 else ''}"
        days = (f.due_date - self.today).days
        return "Due today" if days == 0 else f"Due in {days} days"

    def _report_outstanding_payables(self, vendor_id=None, department_id=None, **_):
        rows = []
        for f in self.invoice_figures(OPEN_LIABILITY, vendor_id=vendor_id, department_id=department_id):
            if f.outstanding <= 0:
                continue
            rows.append({
                "invoice_number": f.invoice_number, "vendor_name": f.vendor_name, "department": f.department,
                "stage": STAGE_LABELS.get(f.stage, f.stage), "invoice_date": f.invoice_date,
                "due_date": f.due_date if f.due_verified else None, "due_status": self._due_status(f),
                "term_status": f.term_status or "Not checked", "currency_code": f.currency_code,
                "net_amount": f.net_amount, "tds_amount": f.tds_amount, "paid": f.paid, "reserved": f.reserved,
                "outstanding": f.outstanding, "invoice_id": f.invoice_id,
            })
        return {"columns": [
            _col("invoice_number", "Invoice"), _col("vendor_name", "Vendor"), _col("department", "Department"),
            _col("stage", "Stage"), _col("invoice_date", "Invoice date", "date"), _col("due_date", "Due date", "date"),
            _col("due_status", "Due status"), _col("term_status", "Payment terms"), _col("currency_code", "Cur."),
            _col("net_amount", "Invoice amount", "money"), _col("tds_amount", "TDS", "money"),
            _col("paid", "Paid", "money"), _col("reserved", "Scheduled", "money"),
            _col("outstanding", "Outstanding", "money"),
        ], "rows": rows, "notes": ["Outstanding = invoice amount - TDS - paid - scheduled payments."]}

    def _report_ageing(self, vendor_id=None, department_id=None, **_):
        grouped: "OrderedDict[tuple, dict]" = OrderedDict()
        bucket_keys = ["not_due"] + [f"b_{label}" for label, *_ in AGEING_BUCKETS] + ["unverified"]
        for f in sorted(self.invoice_figures(APPROVED_LIABILITY, vendor_id=vendor_id, department_id=department_id),
                        key=lambda x: x.vendor_name.lower()):
            if f.outstanding <= 0:
                continue
            row = grouped.setdefault((f.vendor_id, f.currency_code), {
                "vendor_name": f.vendor_name, "currency_code": f.currency_code, "invoices": 0,
                **{k: ZERO for k in bucket_keys}, "total": ZERO})
            late = f.days_overdue(self.today)
            if not f.due_verified:
                key = "unverified"
            elif not late:
                key = "not_due"
            else:
                key = next(f"b_{label}" for label, low, high in AGEING_BUCKETS if late >= low and (high is None or late <= high))
            row[key] = _money(row[key] + f.outstanding)
            row["total"] = _money(row["total"] + f.outstanding)
            row["invoices"] += 1
        columns = [_col("vendor_name", "Vendor"), _col("currency_code", "Cur."), _col("invoices", "Invoices", "int"),
                   _col("not_due", "Not yet due", "money")]
        columns += [_col(f"b_{label}", f"{label} days", "money") for label, *_ in AGEING_BUCKETS]
        columns += [_col("unverified", "Due date unverified", "money"), _col("total", "Total outstanding", "money")]
        return {"columns": columns, "rows": list(grouped.values()),
                "notes": ["Approved and ready-for-payment invoices only; ageing counts days past the effective due date."]}

    def _report_expected_payments(self, vendor_id=None, department_id=None, months=3, **_):
        items = [f for f in self.invoice_figures(OPEN_LIABILITY, vendor_id=vendor_id, department_id=department_id)
                 if f.outstanding > 0]
        upcoming = self._upcoming(items, months)
        rows = []
        for bucket in upcoming["buckets"]:
            currencies = OrderedDict()
            for kind in ("approved", "pipeline"):
                for m in bucket[kind]:
                    slot = currencies.setdefault(m["currency_code"], {"approved": ZERO, "pipeline": ZERO, "count": 0})
                    slot[kind] = m["amount"]
                    slot["count"] += m["count"]
            for code, slot in currencies.items():
                rows.append({"period": bucket["label"], "from": bucket["start"], "to": bucket["end"],
                             "currency_code": code, "invoices": slot["count"], "approved": slot["approved"],
                             "pipeline": slot["pipeline"], "total": _money(slot["approved"] + slot["pipeline"])})
        return {"columns": [
            _col("period", "Period"), _col("from", "From", "date"), _col("to", "To", "date"),
            _col("currency_code", "Cur."), _col("invoices", "Invoices", "int"),
            _col("approved", "Approved / ready", "money"), _col("pipeline", "Still in review / approval", "money"),
            _col("total", "Total expected", "money"),
        ], "rows": rows, "notes": [FORECAST_NOTE]}

    def _report_payments_made(self, date_from=None, date_to=None, vendor_id=None, **_):
        rows = []
        for (payment_id, paid_on, mode, reference, amount, invoice_id, invoice_number, due_date, vendor_name,
             currency_code, symbol, receipts, *_) in self.dao.cleared_payment_rows(date_from, date_to, vendor_id):
            rows.append({
                "paid_on": paid_on, "invoice_number": invoice_number, "vendor_name": vendor_name,
                "payment_mode": mode, "reference_number": reference, "due_date": due_date,
                "timeliness": ("On time" if due_date is None or paid_on <= due_date
                               else f"{(paid_on - due_date).days} days late"),
                "receipt": "Yes" if receipts else "Missing", "currency_code": currency_code or "INR",
                "amount": _money(amount), "payment_id": payment_id, "invoice_id": invoice_id,
            })
        late = sum(1 for r in rows if r["timeliness"] != "On time")
        notes = [f"{len(rows) - late} of {len(rows)} payment allocations were made on or before the due date."] if rows else []
        return {"columns": [
            _col("paid_on", "Paid on", "date"), _col("invoice_number", "Invoice"), _col("vendor_name", "Vendor"),
            _col("payment_mode", "Mode"), _col("reference_number", "UTR / reference"),
            _col("due_date", "Due date", "date"), _col("timeliness", "On time?"), _col("receipt", "Receipt"),
            _col("currency_code", "Cur."), _col("amount", "Amount", "money"),
        ], "rows": rows, "notes": notes}

    def _report_tds_register(self, date_from=None, date_to=None, vendor_id=None, department_id=None, **_):
        due_day, march_day = configured_deposit_days(self.db)
        rows = []
        for f in self.invoice_figures(None, invoice_from=date_from, invoice_to=date_to, vendor_id=vendor_id,
                                      department_id=department_id, tds_only=True):
            if f.status_code in TDS_REGISTER_EXCLUDED:
                continue
            tds, tracking = f.tds, f.tracking
            deduction = tracking.deduction_date if tracking is not None else None
            deposit_due = tds_deposit_due_date(deduction, due_day, march_day)
            deposit_date = tracking.deposit_date if tracking is not None else None
            rows.append({
                "invoice_number": f.invoice_number, "vendor_name": f.vendor_name, "invoice_date": f.invoice_date,
                "section": f.section, "payment_nature": f.nature_code,
                "taxable_base": _money(tds.taxable_base), "tds_rate": tds.tds_rate,
                "tds_amount": _money(tds.tds_amount), "determination": tds.determination_status,
                "tracking_status": tracking.tracking_status if tracking is not None else "TDS_PENDING",
                "deduction_date": deduction, "challan_number": tracking.challan_number if tracking else None,
                "deposit_date": deposit_date, "deposit_due": deposit_due,
                "deposit_timeliness": ("Late" if deposit_date and deposit_due and deposit_date > deposit_due
                                       else "Overdue" if not deposit_date and deposit_due and deposit_due < self.today
                                       else ""),
                "filing_date": tracking.filing_date if tracking else None,
                "filing_reference": tracking.filing_reference if tracking else None,
                "statement_due": tds_statement_due_date(deduction), "currency_code": f.currency_code,
                "invoice_id": f.invoice_id,
            })
        return {"columns": [
            _col("invoice_number", "Invoice"), _col("vendor_name", "Vendor"), _col("invoice_date", "Invoice date", "date"),
            _col("section", "Section"), _col("payment_nature", "Nature"), _col("taxable_base", "Taxable base", "money"),
            _col("tds_rate", "Rate %", "number"), _col("tds_amount", "TDS", "money"),
            _col("determination", "Determination"), _col("tracking_status", "Tracking"),
            _col("deduction_date", "Deducted", "date"), _col("challan_number", "Challan"),
            _col("deposit_date", "Deposited", "date"), _col("deposit_due", "Deposit due", "date"),
            _col("deposit_timeliness", "Deposit"), _col("filing_date", "Filed", "date"),
            _col("filing_reference", "Filing ack."), _col("statement_due", "Statement due", "date"),
        ], "rows": rows, "notes": [
            "Deposit due: 7th of the month after deduction (30 April for March); quarterly statement: "
            "31 Jul / 31 Oct / 31 Jan / 31 May. Configurable in system configuration."]}

    def _report_payment_term_exceptions(self, vendor_id=None, department_id=None, **_):
        rows = []
        for f in self.invoice_figures(OPEN_LIABILITY, vendor_id=vendor_id, department_id=department_id):
            if f.term_status not in EXCEPTION_STATUSES:
                continue
            term = f.term
            rows.append({
                "invoice_number": f.invoice_number, "vendor_name": f.vendor_name, "stage": STAGE_LABELS.get(f.stage),
                "term_status": f.term_status, "reason": REASON_TEXT.get(f.term_reason or "", f.term_reason),
                "invoice_terms": term.invoice_terms_text or (f"{term.invoice_term_days} days"
                                                             if term.invoice_term_days is not None else None),
                "reference_source": term.reference_source,
                "applied_days": term.applied_term_days if term.applied_term_days is not None else term.suggested_term_days,
                "effective_due_date": term.effective_due_date, "currency_code": f.currency_code,
                "outstanding": f.outstanding, "invoice_id": f.invoice_id,
            })
        return {"columns": [
            _col("invoice_number", "Invoice"), _col("vendor_name", "Vendor"), _col("stage", "Stage"),
            _col("term_status", "Status"), _col("reason", "Reason"), _col("invoice_terms", "Invoice says"),
            _col("reference_source", "Reference"), _col("applied_days", "Applied / suggested days", "int"),
            _col("effective_due_date", "Effective due", "date"), _col("currency_code", "Cur."),
            _col("outstanding", "Outstanding", "money"),
        ], "rows": rows, "notes": ["Resolve each exception on the invoice's Payment Terms panel."]}


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _kpi(key, label, money: "_MoneyByCurrency", currency: str, subtitle: str, tone: str, link) -> dict:
    entry = next((m for m in money.as_list() if m["currency_code"] == currency), None)
    others = [m for m in money.as_list() if m["currency_code"] != currency]
    return {"key": key, "label": label, "format": "money", "value": entry["amount"] if entry else ZERO,
            "currency_code": currency, "subtitle": subtitle, "tone": tone, "link": link,
            "other_currencies": others}


def _col(key: str, label: str, kind: str = "text") -> dict:
    return {"key": key, "label": label, "type": kind}
