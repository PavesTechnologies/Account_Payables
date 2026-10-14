# Backend/Business_Layer/services/recurring_service.py
"""Recurring invoice schedules (P2) - expect, match, check and (optionally) fast-track the invoices
a vendor sends every period: rent, SaaS subscriptions, cloud bills.

Nothing here creates or pays an invoice. Every period still needs the vendor's own tax invoice
(GST input credit and TDS are per invoice); the schedule only says what to expect:

  ensure_occurrences   one EXPECTED row per schedule and billing period, created as periods begin
  match_invoice        called when an invoice is created / reviewed: links it to its period, records
                       the amount variance and pre-fills department / category (never raises)
  tds_nature_for       the TDS payment nature the schedule prescribes (used by auto TDS determination)
  fast_track           after send-for-approval: an in-tolerance invoice of a fast-track schedule under
                       an active agreement is auto-approved (Finance still verifies TDS)
  overview / summary   EXPECTED -> DUE -> MISSING (past expected date + grace days), RECEIVED, SKIPPED

Every change is written to audit_log (table recurring_schedule / invoice).
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
from Backend.Data_Access_Layer.models.payment_terms import VendorAgreement
from Backend.Data_Access_Layer.models.recurring_schedule import (
    FREQUENCIES,
    OCC_EXPECTED,
    OCC_RECEIVED,
    OCC_SKIPPED,
    VARIANCE_OVER,
    VARIANCE_UNDER,
    VARIANCE_WITHIN,
    RecurringOccurrence,
    RecurringSchedule,
)
from Backend.Data_Access_Layer.models.vendor import Vendor

logger = logging.getLogger(__name__)

ACTOR = "RECURRING_SCHEDULE"
MANAGE_PERMISSIONS = ["RECURRING_INVOICE_MANAGE", "AP_AUTOMATION_MANAGE"]
VIEW_PERMISSIONS = MANAGE_PERMISSIONS + ["INVOICE_VIEW", "PAYMENT_VIEW", "PAYMENT_PROCESS"]
EDITABLE = ("name", "frequency", "expected_day", "expected_amount", "tolerance_pct", "grace_days", "start_date",
            "end_date", "agreement_id", "department_id", "purchase_category_id", "payment_nature_code",
            "match_keyword", "fast_track", "notes")
CENTS = Decimal("0.01")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def _add_months(day: datetime.date, months: int) -> datetime.date:
    index = day.year * 12 + day.month - 1 + months
    return datetime.date(index // 12, index % 12 + 1, 1)


def period_of(schedule: RecurringSchedule, day: datetime.date) -> datetime.date:
    """First day of the billing period that contains `day` (periods start at the schedule's start month)."""
    step = FREQUENCIES[schedule.frequency]
    first = schedule.start_date.replace(day=1)
    months = (day.year - first.year) * 12 + day.month - first.month
    return _add_months(first, (months // step) * step)


def variance(expected: Decimal, received: Decimal, tolerance_pct: Decimal) -> Tuple[Decimal, str]:
    expected, received = _money(expected), _money(received)
    if expected == 0:
        return Decimal("0"), VARIANCE_WITHIN
    pct = ((received - expected) / expected * 100).quantize(CENTS, ROUND_HALF_UP)
    if abs(pct) <= Decimal(str(tolerance_pct)):
        return pct, VARIANCE_WITHIN
    return pct, VARIANCE_OVER if pct > 0 else VARIANCE_UNDER


def _safe_rollback(db) -> None:
    try:
        db.rollback()
    except Exception:  # a failed hook must never break the invoice flow that called it
        pass


def pick_schedules(schedules, invoice_text: str):
    """A keyword (e.g. "a/c 4417") picks one of a vendor's several schedules; an invoice that carries
    none of the keywords only matches a schedule without one - never a guess."""
    text = (invoice_text or "").lower()
    keyed = [s for s in schedules if s.match_keyword and s.match_keyword.lower() in text]
    return keyed or [s for s in schedules if not s.match_keyword]


class RecurringService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    # ================================================================ schedules
    def _audit(self, table, record_id, action, user_id, old=None, new=None):
        self.db.add(AuditLog(table_name=table, record_id=record_id, action=action, changed_by=str(user_id),
                             old_values=old, new_values=new))

    @staticmethod
    def _snapshot(s: RecurringSchedule) -> dict:
        return {k: (str(v) if isinstance(v, (Decimal, datetime.date)) else v)
                for k, v in ((f, getattr(s, f)) for f in EDITABLE + ("is_active",))}

    def _validate(self, values: Dict[str, Any], current: Optional[RecurringSchedule] = None) -> Dict[str, Any]:
        merged = {**(self._snapshot(current) if current else {}), **values}
        if not str(merged.get("name") or "").strip():
            raise ValueError("Name is required")
        if merged.get("frequency", "MONTHLY") not in FREQUENCIES:
            raise ValueError(f"Frequency must be one of {', '.join(FREQUENCIES)}")
        day = int(merged.get("expected_day") or 1)
        if not 1 <= day <= 28:
            raise ValueError("Expected day must be between 1 and 28")
        if _money(merged.get("expected_amount")) <= 0:
            raise ValueError("Expected amount must be greater than zero")
        tol = Decimal(str(merged.get("tolerance_pct", 5)))
        if not 0 <= tol <= 100:
            raise ValueError("Tolerance must be between 0 and 100 %")
        start, end = merged.get("start_date"), merged.get("end_date")
        if isinstance(start, str):
            start = datetime.date.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.date.fromisoformat(end)
        if start is None:
            raise ValueError("Start date is required")
        if end is not None and end < start:
            raise ValueError("End date cannot be before the start date")
        agreement_id = merged.get("agreement_id")
        if agreement_id:
            vendor_id = values.get("vendor_id") or (current.vendor_id if current else None)
            agreement = self.db.get(VendorAgreement, int(agreement_id))
            if agreement is None or agreement.vendor_id != vendor_id:
                raise ValueError("The agreement does not belong to this vendor")
        return values

    def create(self, data: Dict[str, Any], user_id) -> RecurringSchedule:
        vendor_id = data.get("vendor_id")
        if not vendor_id or self.db.get(Vendor, int(vendor_id)) is None:
            raise ValueError("Vendor not found")
        self._validate(data)
        schedule = RecurringSchedule(vendor_id=int(vendor_id), created_by=str(user_id), updated_by=str(user_id),
                                     **{k: data[k] for k in EDITABLE if k in data and data[k] is not None})
        self.db.add(schedule)
        self.db.flush()
        self._audit("recurring_schedule", schedule.schedule_id, "RECURRING_SCHEDULE_CREATED", user_id,
                    new={"vendor_id": schedule.vendor_id, **self._snapshot(schedule)})
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def update(self, schedule_id: int, data: Dict[str, Any], user_id) -> RecurringSchedule:
        schedule = self._require(schedule_id)
        changes = {k: v for k, v in data.items() if k in EDITABLE + ("is_active",)}
        self._validate(changes, schedule)
        before = self._snapshot(schedule)
        for key, value in changes.items():
            setattr(schedule, key, value)
        schedule.updated_by, schedule.updated_at = str(user_id), _now()
        after = self._snapshot(schedule)
        diff = {k: after[k] for k in after if after[k] != before[k]}
        if diff:
            self._audit("recurring_schedule", schedule_id, "RECURRING_SCHEDULE_UPDATED", user_id,
                        old={k: before[k] for k in diff}, new=diff)
            # The new amount applies to periods not yet received.
            if "expected_amount" in diff:
                for occ in schedule.occurrences:
                    if occ.status == OCC_EXPECTED:
                        occ.expected_amount = schedule.expected_amount
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def _require(self, schedule_id: int) -> RecurringSchedule:
        schedule = self.db.get(RecurringSchedule, schedule_id)
        if schedule is None:
            raise LookupError(f"Recurring schedule {schedule_id} not found")
        return schedule

    # ================================================================ occurrences
    def _periods(self, schedule: RecurringSchedule, until: datetime.date) -> List[datetime.date]:
        step = FREQUENCIES[schedule.frequency]
        last = min(until, schedule.end_date) if schedule.end_date else until
        out, cursor = [], period_of(schedule, schedule.start_date)
        while cursor <= last:
            out.append(cursor)
            cursor = _add_months(cursor, step)
        return out

    def ensure_occurrences(self, until: Optional[datetime.date] = None, schedules=None) -> int:
        """Creates the EXPECTED rows for every period that has begun (idempotent)."""
        until = until or self.today
        schedules = schedules if schedules is not None else self.db.execute(
            select(RecurringSchedule).where(RecurringSchedule.is_active.is_(True))).scalars().all()
        created = 0
        for schedule in schedules:
            have = set(self.db.execute(select(RecurringOccurrence.period_start).where(
                RecurringOccurrence.schedule_id == schedule.schedule_id)).scalars())
            for period in self._periods(schedule, until):
                if period in have:
                    continue
                # through the relationship, so schedule.occurrences stays in step within this session
                schedule.occurrences.append(RecurringOccurrence(
                    period_start=period, expected_amount=schedule.expected_amount,
                    expected_date=period.replace(day=schedule.expected_day), status=OCC_EXPECTED))
                created += 1
        if created:
            self.db.flush()
        return created

    def state(self, occ: RecurringOccurrence, grace_days: int) -> str:
        if occ.status != OCC_EXPECTED:
            return occ.status
        if self.today > occ.expected_date + datetime.timedelta(days=grace_days):
            return "MISSING"
        return "DUE" if self.today >= occ.expected_date else "UPCOMING"

    # ================================================================ matching
    def occurrence_for_invoice(self, invoice_id: int) -> Optional[RecurringOccurrence]:
        return self.db.execute(select(RecurringOccurrence).where(RecurringOccurrence.invoice_id == invoice_id)).scalar_one_or_none()

    def match_invoice(self, invoice_id: int, user_id=ACTOR) -> Optional[RecurringOccurrence]:
        """Links a new / reviewed invoice to its schedule period. Never raises."""
        try:
            return self._match(invoice_id, user_id)
        except Exception:
            _safe_rollback(self.db)
            logger.exception("Recurring match failed for invoice %s", invoice_id)
            return None

    def _match(self, invoice_id: int, user_id) -> Optional[RecurringOccurrence]:
        if self.occurrence_for_invoice(invoice_id) is not None:
            return None
        invoice = self.db.get(Invoice, invoice_id)
        if invoice is None or invoice.vendor_id is None or invoice.invoice_date is None:
            return None
        schedules = [s for s in self.db.execute(select(RecurringSchedule).where(
            RecurringSchedule.vendor_id == invoice.vendor_id, RecurringSchedule.is_active.is_(True))).scalars().all()
            if s.start_date.replace(day=1) <= invoice.invoice_date and (s.end_date is None or invoice.invoice_date <= s.end_date)]
        if not schedules:
            return None
        self.ensure_occurrences(max(invoice.invoice_date, self.today), schedules)
        text = " ".join([invoice.invoice_number or ""] + [l.description or "" for l in self.db.execute(
            select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)).scalars().all()]).lower()
        schedules = pick_schedules(schedules, text)
        if not schedules:
            return None

        amount = _money(invoice.net_amount)
        candidates = []
        for s in schedules:
            period = period_of(s, invoice.invoice_date)
            open_occ = sorted((o for o in s.occurrences if o.status == OCC_EXPECTED and o.period_start <= period),
                              key=lambda o: o.period_start, reverse=True)
            if open_occ:  # this period first, else the latest earlier period still waiting (late invoice)
                occ = next((o for o in open_occ if o.period_start == period), open_occ[0])
                gap = abs(amount - _money(occ.expected_amount)) / max(_money(occ.expected_amount), Decimal("1"))
                candidates.append((gap, occ, s))
        if not candidates:
            return None
        _gap, occ, schedule = min(candidates, key=lambda c: c[0])
        pct, status = variance(occ.expected_amount, amount, schedule.tolerance_pct)
        occ.status, occ.invoice_id, occ.received_amount = OCC_RECEIVED, invoice_id, amount
        occ.variance_pct, occ.variance_status = pct, status
        occ.matched_by, occ.matched_at, occ.updated_at = str(user_id), _now(), _now()
        prefilled = []
        if invoice.invoice_type != "PO":
            if invoice.department_id is None and schedule.department_id:
                invoice.department_id = schedule.department_id
                prefilled.append("department")
            if invoice.purchase_category_id is None and schedule.purchase_category_id:
                invoice.purchase_category_id = schedule.purchase_category_id
                prefilled.append("purchase category")
        self._audit("invoice", invoice_id, "RECURRING_INVOICE_MATCHED", user_id, new={
            "schedule_id": schedule.schedule_id, "schedule": schedule.name, "period": occ.period_start.isoformat(),
            "expected_amount": str(occ.expected_amount), "received_amount": str(amount), "variance_pct": str(pct),
            "variance_status": status, "prefilled": prefilled})
        self.db.commit()
        return occ

    def tds_nature_for(self, invoice_id: int) -> Optional[str]:
        try:
            occ = self.occurrence_for_invoice(invoice_id)
            return occ.schedule.payment_nature_code if occ is not None else None
        except Exception:
            _safe_rollback(self.db)
            return None

    def fast_track(self, invoice_id: int) -> Optional[str]:
        """Auto-approves an in-tolerance invoice of a fast-track schedule under an active agreement.
        Returns the reason when it did; never raises."""
        try:
            occ = self.occurrence_for_invoice(invoice_id)
            if occ is None or not occ.schedule.fast_track or occ.variance_status != VARIANCE_WITHIN:
                return None
            schedule, invoice = occ.schedule, self.db.get(Invoice, invoice_id)
            if schedule.agreement_id:
                agreement = self.db.get(VendorAgreement, schedule.agreement_id)
                valid = (agreement is not None and agreement.status == "ACTIVE" and agreement.valid_from <= invoice.invoice_date
                         and (agreement.valid_to is None or invoice.invoice_date <= agreement.valid_to))
                if not valid:
                    return None
            from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService
            reason = (f"recurring '{schedule.name}' for {occ.period_start:%b %Y}, {occ.variance_pct:+}% of the "
                      f"expected amount (tolerance {schedule.tolerance_pct}%)")
            InvoiceApprovalService(self.db).auto_approve(invoice_id, ACTOR, reason, label="recurring schedule")
            return reason
        except Exception:
            _safe_rollback(self.db)
            logger.exception("Recurring fast-track failed for invoice %s", invoice_id)
            return None

    def skip(self, occurrence_id: int, reason: str, user_id) -> RecurringOccurrence:
        occ = self.db.get(RecurringOccurrence, occurrence_id)
        if occ is None:
            raise LookupError(f"Occurrence {occurrence_id} not found")
        if occ.status != OCC_EXPECTED:
            raise ValueError("Only an expected (not yet received) period can be skipped")
        if len((reason or "").strip()) < 5:
            raise ValueError("Give a reason (at least 5 characters) for skipping this period")
        occ.status, occ.skip_reason, occ.skipped_by, occ.updated_at = OCC_SKIPPED, reason.strip()[:500], str(user_id), _now()
        self._audit("recurring_schedule", occ.schedule_id, "RECURRING_PERIOD_SKIPPED", user_id,
                    new={"period": occ.period_start.isoformat(), "reason": occ.skip_reason})
        self.db.commit()
        return occ

    def link(self, occurrence_id: int, invoice_id: int, user_id) -> RecurringOccurrence:
        occ = self.db.get(RecurringOccurrence, occurrence_id)
        invoice = self.db.get(Invoice, invoice_id)
        if occ is None or invoice is None:
            raise LookupError("Period or invoice not found")
        if occ.status == OCC_RECEIVED:
            raise ValueError("This period already has an invoice")
        if invoice.vendor_id != occ.schedule.vendor_id:
            raise ValueError("The invoice is from a different vendor")
        if self.occurrence_for_invoice(invoice_id) is not None:
            raise ValueError("This invoice is already linked to a recurring period")
        amount = _money(invoice.net_amount)
        pct, status = variance(occ.expected_amount, amount, occ.schedule.tolerance_pct)
        occ.status, occ.invoice_id, occ.received_amount, occ.variance_pct, occ.variance_status = OCC_RECEIVED, invoice_id, amount, pct, status
        occ.matched_by, occ.matched_at, occ.updated_at = str(user_id), _now(), _now()
        self._audit("invoice", invoice_id, "RECURRING_INVOICE_MATCHED", user_id, new={
            "schedule_id": occ.schedule_id, "schedule": occ.schedule.name, "period": occ.period_start.isoformat(),
            "variance_pct": str(pct), "variance_status": status, "manual": True})
        self.db.commit()
        return occ

    # ================================================================ views
    def _row(self, occ: RecurringOccurrence, schedule: RecurringSchedule, invoices: Dict[int, Invoice]) -> dict:
        invoice = invoices.get(occ.invoice_id) if occ.invoice_id else None
        return {"occurrence_id": occ.occurrence_id, "period_start": occ.period_start, "expected_date": occ.expected_date,
                "expected_amount": occ.expected_amount, "state": self.state(occ, schedule.grace_days),
                "invoice_id": occ.invoice_id, "invoice_number": invoice.invoice_number if invoice else None,
                "received_amount": occ.received_amount, "variance_pct": occ.variance_pct,
                "variance_status": occ.variance_status, "skip_reason": occ.skip_reason}

    def overview(self) -> Dict[str, Any]:
        self.ensure_occurrences()
        self.db.commit()
        schedules = self.db.execute(select(RecurringSchedule).order_by(RecurringSchedule.vendor_id,
                                                                       RecurringSchedule.name)).scalars().all()
        ids = [o.invoice_id for s in schedules for o in s.occurrences if o.invoice_id]
        invoices = {i.invoice_id: i for i in self.db.execute(select(Invoice).where(Invoice.invoice_id.in_(ids))).scalars()} if ids else {}
        rows, totals = [], {"MISSING": 0, "DUE": 0, "RECEIVED_THIS_PERIOD": 0, "VARIANCE": 0}
        horizon = [_add_months(self.today.replace(day=1), m) for m in range(1, 4)]
        upcoming = {m: Decimal("0") for m in horizon}
        for s in schedules:
            occs = [self._row(o, s, invoices) for o in s.occurrences]
            current = next((o for o in reversed(occs) if o["period_start"] <= self.today), None)
            for o in occs:
                if o["state"] == "MISSING":
                    totals["MISSING"] += 1
                if o["state"] == "DUE":
                    totals["DUE"] += 1
                if o["variance_status"] in (VARIANCE_OVER, VARIANCE_UNDER) and o["period_start"] >= _add_months(self.today.replace(day=1), -2):
                    totals["VARIANCE"] += 1
            if current and current["state"] == OCC_RECEIVED:
                totals["RECEIVED_THIS_PERIOD"] += 1
            if s.is_active:
                for m in horizon:
                    if (s.end_date is None or m <= s.end_date) and period_of(s, m) == m and m >= s.start_date.replace(day=1):
                        upcoming[m] += _money(s.expected_amount)
            rows.append({
                "schedule_id": s.schedule_id, "vendor_id": s.vendor_id, "vendor_name": s.vendor.vendor_name if s.vendor else None,
                "name": s.name, "frequency": s.frequency, "expected_day": s.expected_day, "expected_amount": s.expected_amount,
                "tolerance_pct": s.tolerance_pct, "grace_days": s.grace_days, "start_date": s.start_date, "end_date": s.end_date,
                "agreement_id": s.agreement_id, "department_id": s.department_id, "purchase_category_id": s.purchase_category_id,
                "payment_nature_code": s.payment_nature_code, "match_keyword": s.match_keyword, "fast_track": s.fast_track,
                "is_active": s.is_active, "notes": s.notes, "current": current, "occurrences": occs[-12:],
            })
        return {"as_of": self.today, "schedules": rows, "totals": totals,
                "upcoming": [{"period": m, "label": m.strftime("%b %Y"), "amount": upcoming[m]} for m in horizon]}

    def attention(self) -> Dict[str, List[dict]]:
        """For the Action Center: missing invoices and recent amount variances."""
        data = self.overview()
        missing, varied = [], []
        for s in data["schedules"]:
            for o in s["occurrences"]:
                if o["state"] == "MISSING":
                    missing.append({"schedule": s["name"], "vendor": s["vendor_name"], **o})
                elif o["variance_status"] in (VARIANCE_OVER, VARIANCE_UNDER) and o["period_start"] >= _add_months(self.today.replace(day=1), -2):
                    varied.append({"schedule": s["name"], "vendor": s["vendor_name"], **o})
        return {"missing": missing, "variance": varied}
