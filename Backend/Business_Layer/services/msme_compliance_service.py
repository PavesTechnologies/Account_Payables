# Backend/Business_Layer/services/msme_compliance_service.py
"""MSME payment compliance (P3) - MSMED Act s.15/16, Income-tax s.43B(h) and MCA MSME Form-1.

Only MICRO and SMALL enterprises (vendor.msme_registered + msme_category) are covered; medium
enterprises are not under s.15. The statutory due date per invoice is the one payment-term compliance
already keeps (invoice_payment_term.statutory_due_date: the agreed date, at most 45 days; 15 days with no
agreement). Amount due to the supplier = net - TDS - applied notes (the payables figure), discharged
by cleared payments on their payment date.

  invoice_status   per invoice: paid on time / paid late / overdue / due soon / not due, days late,
                   and s.16 interest (compound, monthly rests, 3 x RBI bank rate - MSME_BANK_RATE)
  s43bh            for a financial year: what was unpaid at year end and how much is disallowed
                   (not paid within the s.15 limit -> deductible only in the year actually paid)
  form1            MCA MSME Form-1 for a half year (Apr-Sep due 31 Oct, Oct-Mar due 30 Apr):
                   amounts outstanding beyond the s.15 limit at the half-year end, per supplier
These are read-only views - nothing is stored.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
MSE_CATEGORIES = ("MICRO", "SMALL")
BANK_RATE_KEY = "MSME_BANK_RATE"
DEFAULT_BANK_RATE = Decimal("5.75")  # RBI bank rate; confirm the current notified rate in system configuration
DUE_SOON_DAYS = 7
DAYS_PER_MONTH = Decimal("365") / Decimal("12")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def s16_interest(amount: Decimal, days_late: int, bank_rate: Decimal) -> Decimal:
    """MSMED s.16: compound interest with monthly rests at three times the RBI bank rate."""
    if amount <= 0 or days_late <= 0:
        return ZERO
    monthly = Decimal("3") * bank_rate / Decimal("100") / Decimal("12")
    months = Decimal(days_late) / DAYS_PER_MONTH
    factor = Decimal(str((1 + float(monthly)) ** float(months)))
    return _money(amount * (factor - 1))


def fy_bounds(day: datetime.date) -> Tuple[datetime.date, datetime.date]:
    start = datetime.date(day.year if day.month >= 4 else day.year - 1, 4, 1)
    return start, datetime.date(start.year + 1, 3, 31)


def half_year(day: datetime.date) -> Tuple[datetime.date, datetime.date, datetime.date]:
    """(start, end, Form-1 due date) of the half year containing the day."""
    if 4 <= day.month <= 9:
        return datetime.date(day.year, 4, 1), datetime.date(day.year, 9, 30), datetime.date(day.year, 10, 31)
    start_year = day.year if day.month >= 10 else day.year - 1
    return datetime.date(start_year, 10, 1), datetime.date(start_year + 1, 3, 31), datetime.date(start_year + 1, 4, 30)


@dataclass
class MsmeInvoice:
    invoice_id: int
    invoice_number: str
    invoice_date: datetime.date
    vendor_id: int
    vendor_name: str
    pan: Optional[str]
    udyam: Optional[str]
    category: str
    due: Decimal                                   # amount due to the supplier (net - TDS - notes)
    statutory_due: datetime.date
    rule: Optional[str]
    stage: Optional[str]
    settlements: List[Tuple[datetime.date, Decimal]] = field(default_factory=list)  # (date, amount), chronological

    def paid_by(self, day: datetime.date) -> Decimal:
        return sum((a for d, a in self.settlements if d <= day), ZERO)

    def outstanding_at(self, day: datetime.date) -> Decimal:
        return max(self.due - self.paid_by(day), ZERO)

    def late_parts(self, as_of: datetime.date) -> List[Tuple[Decimal, int]]:
        """(amount, days late) for every part paid after - or still unpaid past - the statutory date."""
        parts, remaining = [], self.due
        for day, amount in self.settlements:
            if day > as_of or remaining <= 0:
                break
            take = min(amount, remaining)
            remaining -= take
            if day > self.statutory_due:
                parts.append((take, (day - self.statutory_due).days))
        if remaining > 0 and as_of > self.statutory_due:
            parts.append((remaining, (as_of - self.statutory_due).days))
        return parts


class MsmeComplianceService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    def bank_rate(self) -> Decimal:
        from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
        try:
            row = MasterDAO(self.db).get_system_config_by_key(BANK_RATE_KEY)
            return Decimal(row.config_value) if row is not None and row.config_value else DEFAULT_BANK_RATE
        except Exception:
            return DEFAULT_BANK_RATE

    # ------------------------------------------------------------------ data
    def invoices(self, invoice_from: Optional[datetime.date] = None, invoice_to: Optional[datetime.date] = None) -> List[MsmeInvoice]:
        from Backend.Business_Layer.services.ap_reporting_service import STAGE_LABELS, APReportingService
        from Backend.Data_Access_Layer.models.vendor import Vendor
        vendors = {v.vendor_id: v for v in self.db.execute(select(Vendor).where(
            Vendor.msme_registered.is_(True), Vendor.msme_category.in_(MSE_CATEGORIES))).scalars()}
        if not vendors:
            return []
        figures = APReportingService(self.db, today=self.today).invoice_figures(invoice_from=invoice_from, invoice_to=invoice_to)
        out = []
        for f in figures:
            v = vendors.get(f.vendor_id)
            term = f.term
            if v is None or term is None or term.statutory_due_date is None or f.status_code in ("REJECTED", "CANCELLED"):
                continue
            out.append(MsmeInvoice(f.invoice_id, f.invoice_number, f.invoice_date, f.vendor_id, f.vendor_name, v.pan_number,
                                   v.udyam_number, v.msme_category, _money(f.net_payable), term.statutory_due_date,
                                   term.statutory_rule, STAGE_LABELS.get(f.stage, f.stage)))
        self._load_settlements(out)
        return out

    def _load_settlements(self, rows: List[MsmeInvoice]) -> None:
        from Backend.Data_Access_Layer.models.master import StatusMaster
        from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice
        by_id = {r.invoice_id: r for r in rows}
        if not by_id:
            return
        for invoice_id, day, amount in self.db.execute(
                select(PaymentInvoice.invoice_id, Payment.payment_date, PaymentInvoice.allocated_amount)
                .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
                .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
                .where(StatusMaster.status_code == "CLEARED", PaymentInvoice.invoice_id.in_(list(by_id)))).all():
            if day is not None:
                by_id[invoice_id].settlements.append((day, _money(amount)))
        for r in rows:
            r.settlements.sort()

    # ------------------------------------------------------------------ views
    def invoice_status(self, inv: MsmeInvoice, as_of: Optional[datetime.date] = None) -> dict:
        as_of = as_of or self.today
        outstanding = inv.outstanding_at(as_of)
        parts = inv.late_parts(as_of)
        rate = self.bank_rate()
        interest = sum((s16_interest(a, d, rate) for a, d in parts), ZERO)
        days_late = max((d for _a, d in parts), default=0)
        last_paid = max((d for d, _a in inv.settlements if d <= as_of), default=None)
        if outstanding <= 0:
            status = "Paid late" if parts else "Paid on time"
        elif as_of > inv.statutory_due:
            status = "Overdue"
        elif (inv.statutory_due - as_of).days <= DUE_SOON_DAYS:
            status = "Due soon"
        else:
            status = "Not yet due"
        return {"invoice_id": inv.invoice_id, "invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date,
                "vendor_name": inv.vendor_name, "msme_category": inv.category.title(), "udyam_number": inv.udyam,
                "statutory_due_date": inv.statutory_due, "paid_on": last_paid if outstanding <= 0 else None,
                "status": status, "days_late": days_late, "amount_due": inv.due, "paid": inv.paid_by(as_of),
                "outstanding": outstanding, "late_amount": sum((a for a, _d in parts), ZERO), "interest_s16": interest,
                "currency_code": "INR"}

    def s43bh(self, fy_start: datetime.date, fy_end: datetime.date) -> List[dict]:
        """Invoices of the year (expense booked in it) and the 43B(h) outcome at year end."""
        out = []
        for inv in self.invoices(fy_start, fy_end):
            unpaid = inv.outstanding_at(fy_end)
            if unpaid <= 0:
                continue  # paid within the year - deductible in the year, whether on time or late
            # paid after year end: allowed only if paid within the s.15 limit
            remaining, on_time, late, settled_after = unpaid, ZERO, ZERO, ZERO
            for day, amount in inv.settlements:
                if day <= fy_end or remaining <= 0:
                    continue
                take = min(amount, remaining)
                remaining -= take
                settled_after += take
                if day <= inv.statutory_due:
                    on_time += take
                else:
                    late += take
            still_open = remaining
            if still_open and self.today > inv.statutory_due:
                outcome, disallowed, at_risk = "Disallowed - unpaid past the s.15 date", late + still_open, ZERO
            elif still_open:
                outcome, disallowed, at_risk = f"At risk - pay by {inv.statutory_due:%d %b %Y}", late, still_open
            else:
                outcome = "Disallowed - paid after the s.15 date" if late else "Allowed - paid within the s.15 date"
                disallowed, at_risk = late, ZERO
            out.append({"invoice_id": inv.invoice_id, "invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date,
                        "vendor_id": inv.vendor_id, "vendor_name": inv.vendor_name, "msme_category": inv.category.title(), "udyam_number": inv.udyam,
                        "statutory_due_date": inv.statutory_due, "unpaid_at_year_end": unpaid, "paid_in_time_after_year_end": on_time,
                        "disallowed": disallowed, "at_risk": at_risk, "outcome": outcome, "currency_code": "INR"})
        return out

    def form1(self, period_end: datetime.date) -> List[dict]:
        """MSME Form-1: dues to micro / small suppliers outstanding beyond 45 days (the s.15 date) at the half-year end."""
        rows = []
        for inv in self.invoices(None, period_end):
            amount = inv.outstanding_at(period_end)
            if amount <= 0 or period_end <= inv.statutory_due:
                continue
            rows.append({"vendor_id": inv.vendor_id, "vendor_name": inv.vendor_name, "pan": inv.pan, "udyam_number": inv.udyam,
                         "msme_category": inv.category.title(), "invoice_number": inv.invoice_number,
                         "invoice_date": inv.invoice_date, "due_from": inv.statutory_due + datetime.timedelta(days=1),
                         "days_outstanding": (period_end - inv.statutory_due).days, "amount_due": amount,
                         "reason": f"Invoice at {inv.stage}" if inv.stage else "", "currency_code": "INR"})
        return sorted(rows, key=lambda r: (r["vendor_name"], r["invoice_date"]))

    def attention(self) -> Dict[str, object]:
        """Form-1 due within 15 days with something to report (the s.15 payment items are already on the dashboard)."""
        start, end, due = half_year(self.today - datetime.timedelta(days=45))
        if not (end < self.today <= due) or (due - self.today).days > 15:
            return {}
        rows = self.form1(end)
        return {"period_start": start, "period_end": end, "due": due, "suppliers": len({r["vendor_name"] for r in rows}),
                "invoices": len(rows), "amount": sum((r["amount_due"] for r in rows), ZERO)}
