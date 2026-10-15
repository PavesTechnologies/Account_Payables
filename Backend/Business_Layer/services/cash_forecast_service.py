# Backend/Business_Layer/services/cash_forecast_service.py
"""Cash needed for AP beyond the invoices already recorded - for the expected-payments forecast.

  recurring   rent / subscriptions a recurring schedule expects whose invoice has not arrived yet:
              one estimate per open period up to the horizon (EXPECTED occurrences, plus periods not yet
              begun), at the schedule's expected amount, due expected date + the agreement's / vendor's
              payment-term days. A late (missing) invoice is still expected - it is placed on today.
              Received or skipped periods are not estimated, so nothing is counted twice: once the
              invoice arrives it is an invoice in the forecast instead.
  tds         TDS to pay to the government (by the 7th of the next month; 30 April for March):
              already deducted and not yet deposited, plus the TDS of open invoices, due the month after
              each invoice's due date (deducted when the vendor is paid).

The estimate's amount is the invoice total; its TDS is part of it (not estimated separately). These are
planning figures only - nothing is posted or stored.
"""
from __future__ import annotations

import calendar
import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def _on_day(period_start: datetime.date, day: int) -> datetime.date:
    return period_start.replace(day=min(max(int(day or 1), 1), calendar.monthrange(period_start.year, period_start.month)[1]))


class CashForecastService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    # ------------------------------------------------------------------ recurring
    def _term_days(self, schedules) -> Dict[int, int]:
        from Backend.Data_Access_Layer.models.master import PaymentTerm
        from Backend.Data_Access_Layer.models.payment_terms import VendorAgreement
        from Backend.Data_Access_Layer.models.vendor import Vendor
        due_days = dict(self.db.execute(select(PaymentTerm.payment_term_id, PaymentTerm.due_days)).all())
        agreements = {a.agreement_id: a for a in self.db.execute(select(VendorAgreement).where(
            VendorAgreement.agreement_id.in_([s.agreement_id for s in schedules if s.agreement_id] or [0]))).scalars()}
        vendor_terms = dict(self.db.execute(select(Vendor.vendor_id, Vendor.payment_term_id).where(
            Vendor.vendor_id.in_([s.vendor_id for s in schedules] or [0]))).all())
        out = {}
        for s in schedules:
            a = agreements.get(s.agreement_id)
            days = a.term_days if a is not None and a.term_days is not None else (
                due_days.get(a.payment_term_id) if a is not None and a.payment_term_id else None)
            if days is None:
                days = due_days.get(vendor_terms.get(s.vendor_id))
            out[s.schedule_id] = int(days or 0)
        return out

    def recurring(self, horizon_end: datetime.date) -> List[dict]:
        from Backend.Business_Layer.services.recurring_service import FREQUENCIES, _add_months, period_of
        from Backend.Data_Access_Layer.models.recurring_schedule import (OCC_EXPECTED, RecurringOccurrence,
                                                                         RecurringSchedule)
        from Backend.Data_Access_Layer.models.vendor import Vendor
        try:
            schedules = self.db.execute(select(RecurringSchedule).where(RecurringSchedule.is_active.is_(True),
                                                                        RecurringSchedule.start_date <= horizon_end)).scalars().all()
        except Exception:  # table not migrated yet
            self.db.rollback()
            return []
        schedules = [s for s in schedules if s.end_date is None or s.end_date >= self.today.replace(day=1)]
        if not schedules:
            return []
        terms = self._term_days(schedules)
        names = dict(self.db.execute(select(Vendor.vendor_id, Vendor.vendor_name).where(
            Vendor.vendor_id.in_([s.vendor_id for s in schedules]))).all())
        occurrences: Dict[tuple, RecurringOccurrence] = {
            (o.schedule_id, o.period_start): o for o in self.db.execute(select(RecurringOccurrence).where(
                RecurringOccurrence.schedule_id.in_([s.schedule_id for s in schedules]))).scalars()}
        out = []
        for s in schedules:
            step = FREQUENCIES[s.frequency]
            open_periods = [p for (sid, p), o in occurrences.items() if sid == s.schedule_id and o.status == OCC_EXPECTED]
            cursor = period_of(s, max(self.today, s.start_date))
            while cursor <= horizon_end and (s.end_date is None or cursor <= s.end_date):
                if (s.schedule_id, cursor) not in occurrences:
                    open_periods.append(cursor)
                cursor = _add_months(cursor, step)
            for period in sorted(set(open_periods)):
                occ = occurrences.get((s.schedule_id, period))
                expected = occ.expected_date if occ is not None else _on_day(period, s.expected_day)
                due = expected + datetime.timedelta(days=terms[s.schedule_id])
                if due > horizon_end:
                    continue
                out.append({"kind": "RECURRING", "schedule_id": s.schedule_id, "name": s.name,
                            "vendor_name": names.get(s.vendor_id), "period_start": period, "expected_date": expected,
                            "due_date": max(due, self.today), "late": expected < self.today,
                            "amount": _money(occ.expected_amount if occ is not None else s.expected_amount),
                            "currency_code": "INR"})
        return sorted(out, key=lambda r: (r["due_date"], r["name"]))

    # ------------------------------------------------------------------ TDS
    def tds(self, horizon_end: datetime.date, open_items: Iterable = ()) -> List[dict]:
        """TDS deposits due up to the horizon, overdue ones included (due_date before today)."""
        from Backend.Business_Layer.utils.statutory_calendar import configured_deposit_days, tds_deposit_due_date
        from Backend.Data_Access_Layer.models.tds import InvoiceTds, InvoiceTdsTracking
        due_day, march_day = configured_deposit_days(self.db)
        by_due: Dict[datetime.date, dict] = {}

        def add(due, amount, deducted: bool):
            if due is None or amount <= 0 or due > horizon_end:
                return
            slot = by_due.setdefault(due, {"kind": "TDS", "due_date": due, "deducted": ZERO, "projected": ZERO,
                                           "invoices": 0, "currency_code": "INR"})
            slot["deducted" if deducted else "projected"] += amount
            slot["invoices"] += 1

        rows = self.db.execute(select(InvoiceTdsTracking.deduction_date, InvoiceTds.tds_amount)
                               .join(InvoiceTds, InvoiceTds.invoice_id == InvoiceTdsTracking.invoice_id)
                               .where(InvoiceTdsTracking.tracking_status == "TDS_DEDUCTED", InvoiceTds.tds_applicable.is_(True))).all()
        for deducted_on, amount in rows:
            add(tds_deposit_due_date(deducted_on or self.today, due_day, march_day), _money(amount), True)
        for f in open_items:
            tracking = getattr(f, "tracking", None)
            if f.tds_amount <= 0 or (tracking is not None and tracking.tracking_status != "TDS_PENDING"):
                continue
            paid_on = max(f.due_date, self.today) if f.due_verified and f.due_date else self.today
            add(tds_deposit_due_date(paid_on, due_day, march_day), _money(f.tds_amount), False)
        out = []
        for slot in sorted(by_due.values(), key=lambda s: s["due_date"]):
            slot["amount"] = slot["deducted"] + slot["projected"]
            slot["overdue"] = slot["due_date"] < self.today and slot["deducted"] > 0
            out.append(slot)
        return out
