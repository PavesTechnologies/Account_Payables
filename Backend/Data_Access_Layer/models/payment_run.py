# Backend/Data_Access_Layer/models/payment_run.py
"""Payment runs (P3) - pay many invoices in one approved batch through the bank.

  payment_run       DRAFT -> SUBMITTED -> APPROVED (scheduled payments created) -> SENT (bank file
                    uploaded) -> COMPLETED; REJECTED / CANCELLED. Maker (created_by) and checker
                    (approved_by) are different people.
  payment_run_item  one invoice in the run, its amount, the vendor's approved bank account and - once
                    approved - the scheduled payment (one per vendor) that carries it; UTR and result
                    after the bank confirms.

Money moves only through the existing payment flow (PaymentService SCHEDULED -> SENT -> CLEARED),
so reservations, invoice status and audit stay as they are. Created by migration_payment_run.sql.
"""
from typing import Optional
import datetime
from decimal import Decimal

from sqlalchemy import (CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric,
                        PrimaryKeyConstraint, String, Text, text)
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

RUN_DRAFT, RUN_SUBMITTED, RUN_APPROVED, RUN_SENT, RUN_COMPLETED = "DRAFT", "SUBMITTED", "APPROVED", "SENT", "COMPLETED"
RUN_REJECTED, RUN_CANCELLED = "REJECTED", "CANCELLED"
RUN_OPEN = (RUN_DRAFT, RUN_SUBMITTED, RUN_APPROVED, RUN_SENT)
ITEM_PENDING, ITEM_PAID, ITEM_FAILED = "PENDING", "PAID", "FAILED"


class PaymentRun(Base):
    __tablename__ = "payment_run"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", name="payment_run_pkey"),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','SENT','COMPLETED','REJECTED','CANCELLED')",
                        name="payment_run_status_chk"),
        Index("idx_payment_run_status", "status"),
        {"schema": "ap"},
    )

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    value_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'DRAFT'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    submitted_by: Mapped[Optional[str]] = mapped_column(String(100))
    submitted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    decision_remarks: Mapped[Optional[str]] = mapped_column(String(500))
    file_format: Mapped[Optional[str]] = mapped_column(String(30))
    file_generated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    file_generated_by: Mapped[Optional[str]] = mapped_column(String(100))
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    sent_by: Mapped[Optional[str]] = mapped_column(String(100))
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    notes: Mapped[Optional[str]] = mapped_column(Text)


class PaymentRunItem(Base):
    __tablename__ = "payment_run_item"
    __table_args__ = (
        ForeignKeyConstraint(["run_id"], ["ap.payment_run.run_id"], ondelete="CASCADE", name="payment_run_item_run_fk"),
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], name="payment_run_item_invoice_fk"),
        ForeignKeyConstraint(["vendor_id"], ["ap.vendor.vendor_id"], name="payment_run_item_vendor_fk"),
        ForeignKeyConstraint(["vendor_bank_id"], ["ap.vendor_bank.vendor_bank_id"], name="payment_run_item_bank_fk"),
        ForeignKeyConstraint(["payment_id"], ["ap.payment.payment_id"], name="payment_run_item_payment_fk"),
        PrimaryKeyConstraint("item_id", name="payment_run_item_pkey"),
        CheckConstraint("status IN ('PENDING','PAID','FAILED')", name="payment_run_item_status_chk"),
        CheckConstraint("amount > 0", name="payment_run_item_amount_chk"),
        Index("uq_payment_run_item_invoice", "run_id", "invoice_id", unique=True),
        Index("idx_payment_run_item_invoice", "invoice_id"),
        {"schema": "ap"},
    )

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    vendor_bank_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_id: Mapped[Optional[int]] = mapped_column(Integer)
    utr: Mapped[Optional[str]] = mapped_column(String(50))
    failure_reason: Mapped[Optional[str]] = mapped_column(String(300))
