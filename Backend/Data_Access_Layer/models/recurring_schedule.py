# Backend/Data_Access_Layer/models/recurring_schedule.py
"""Recurring invoice schedules - rent, SaaS subscriptions, cloud bills (P2).

A schedule says "this vendor bills us every month, around day N, for about Rs X". It never
creates or pays an invoice: GST needs the vendor's own tax invoice for every period. It is used to

  * expect each period's invoice and flag it MISSING when it doesn't arrive,
  * match the arriving invoice to its period and check the amount against the schedule,
  * pre-fill department / category / TDS nature at review, and
  * optionally fast-track approval of an in-tolerance invoice under an active agreement.

One recurring_occurrence row per schedule and billing period (created as periods begin).
Tables are created by migration_recurring_schedule.sql (create_all also creates them).
"""
from typing import Optional, TYPE_CHECKING
import datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric,
                        PrimaryKeyConstraint, SmallInteger, String, Text, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.vendor import Vendor

FREQUENCIES = {"MONTHLY": 1, "QUARTERLY": 3, "HALF_YEARLY": 6, "YEARLY": 12}

OCC_EXPECTED = "EXPECTED"
OCC_RECEIVED = "RECEIVED"
OCC_SKIPPED = "SKIPPED"
OCC_STATUSES = (OCC_EXPECTED, OCC_RECEIVED, OCC_SKIPPED)

VARIANCE_WITHIN = "WITHIN"
VARIANCE_OVER = "OVER"
VARIANCE_UNDER = "UNDER"


class RecurringSchedule(Base):
    __tablename__ = "recurring_schedule"
    __table_args__ = (
        ForeignKeyConstraint(["vendor_id"], ["ap.vendor.vendor_id"], name="recurring_schedule_vendor_fk"),
        ForeignKeyConstraint(["agreement_id"], ["ap.vendor_agreement.agreement_id"], name="recurring_schedule_agreement_fk"),
        ForeignKeyConstraint(["department_id"], ["ap.department.id"], name="recurring_schedule_department_fk"),
        ForeignKeyConstraint(["purchase_category_id"], ["ap.purchase_category.id"], name="recurring_schedule_category_fk"),
        PrimaryKeyConstraint("schedule_id", name="recurring_schedule_pkey"),
        CheckConstraint("frequency IN ('MONTHLY','QUARTERLY','HALF_YEARLY','YEARLY')", name="recurring_schedule_frequency_chk"),
        CheckConstraint("expected_day BETWEEN 1 AND 28", name="recurring_schedule_day_chk"),
        CheckConstraint("tolerance_pct >= 0 AND tolerance_pct <= 100", name="recurring_schedule_tolerance_chk"),
        Index("idx_recurring_schedule_vendor", "vendor_id"),
        {"schema": "ap"},
    )

    schedule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'MONTHLY'::character varying"))
    # Day of the billing month the invoice is dated / expected (1-28).
    expected_day: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    # Expected invoice total (incl. GST), and how far an invoice may differ and still be "as expected".
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("5"))
    # Days after the expected date before a missing invoice is flagged.
    grace_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("5"))
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fast_track: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    agreement_id: Mapped[Optional[int]] = mapped_column(Integer)
    department_id: Mapped[Optional[int]] = mapped_column(Integer)
    purchase_category_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_nature_code: Mapped[Optional[str]] = mapped_column(String(50))
    # Text that identifies this schedule on the invoice when a vendor bills several (e.g. "a/c 4417").
    match_keyword: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    vendor: Mapped["Vendor"] = relationship("Vendor", foreign_keys=[vendor_id])
    occurrences: Mapped[list["RecurringOccurrence"]] = relationship(
        "RecurringOccurrence", back_populates="schedule", order_by="RecurringOccurrence.period_start")


class RecurringOccurrence(Base):
    __tablename__ = "recurring_occurrence"
    __table_args__ = (
        ForeignKeyConstraint(["schedule_id"], ["ap.recurring_schedule.schedule_id"], name="recurring_occurrence_schedule_fk"),
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], name="recurring_occurrence_invoice_fk"),
        PrimaryKeyConstraint("occurrence_id", name="recurring_occurrence_pkey"),
        CheckConstraint("status IN ('EXPECTED','RECEIVED','SKIPPED')", name="recurring_occurrence_status_chk"),
        Index("uq_recurring_occurrence_period", "schedule_id", "period_start", unique=True),
        Index("uq_recurring_occurrence_invoice", "invoice_id", unique=True, postgresql_where=text("invoice_id IS NOT NULL")),
        {"schema": "ap"},
    )

    occurrence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'EXPECTED'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer)
    received_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    variance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 2))
    variance_status: Mapped[Optional[str]] = mapped_column(String(10))
    matched_by: Mapped[Optional[str]] = mapped_column(String(100))
    matched_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    skip_reason: Mapped[Optional[str]] = mapped_column(String(500))
    skipped_by: Mapped[Optional[str]] = mapped_column(String(100))

    schedule: Mapped["RecurringSchedule"] = relationship("RecurringSchedule", back_populates="occurrences")
