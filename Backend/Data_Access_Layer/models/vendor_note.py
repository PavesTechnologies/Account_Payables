# Backend/Data_Access_Layer/models/vendor_note.py
"""Credit and debit notes (P2).

  CREDIT_NOTE  issued by the vendor (GST credit note, s.34): reduces what we owe and the GST
               input credit we may claim.
  DEBIT_NOTE   raised by us on the vendor (short supply, rate difference, penalty): a commercial
               recovery - reduces what we owe; no GST effect unless the vendor issues a credit note.

A note is recorded OPEN, then APPLIED to one unpaid invoice of the same vendor (usually the one it
refers to; a later one when the referenced invoice is already paid). Applying it lowers that
invoice's payable - net amount - TDS - applied notes - and, while TDS is not yet deducted, the TDS
base. Created by migration_vendor_note.sql (create_all also creates it).
"""
from typing import Optional
import datetime
from decimal import Decimal

from sqlalchemy import (CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric,
                        PrimaryKeyConstraint, String, Text, text)
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

CREDIT_NOTE, DEBIT_NOTE = "CREDIT_NOTE", "DEBIT_NOTE"
NOTE_TYPES = (CREDIT_NOTE, DEBIT_NOTE)
NOTE_OPEN, NOTE_APPLIED, NOTE_CANCELLED = "OPEN", "APPLIED", "CANCELLED"


class VendorNote(Base):
    __tablename__ = "vendor_note"
    __table_args__ = (
        ForeignKeyConstraint(["vendor_id"], ["ap.vendor.vendor_id"], name="vendor_note_vendor_fk"),
        ForeignKeyConstraint(["reference_invoice_id"], ["ap.invoice.invoice_id"], name="vendor_note_reference_fk"),
        ForeignKeyConstraint(["applied_invoice_id"], ["ap.invoice.invoice_id"], name="vendor_note_applied_fk"),
        PrimaryKeyConstraint("note_id", name="vendor_note_pkey"),
        CheckConstraint("note_type IN ('CREDIT_NOTE','DEBIT_NOTE')", name="vendor_note_type_chk"),
        CheckConstraint("status IN ('OPEN','APPLIED','CANCELLED')", name="vendor_note_status_chk"),
        CheckConstraint("total_amount > 0", name="vendor_note_amount_chk"),
        Index("uq_vendor_note_number", "vendor_id", "note_type", "note_number", unique=True),
        Index("idx_vendor_note_applied", "applied_invoice_id"),
        {"schema": "ap"},
    )

    note_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    note_number: Mapped[str] = mapped_column(String(60), nullable=False)
    note_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'OPEN'::character varying"))
    tds_adjusted: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    reference_invoice_id: Mapped[Optional[int]] = mapped_column(Integer)
    applied_invoice_id: Mapped[Optional[int]] = mapped_column(Integer)
    tds_note: Mapped[Optional[str]] = mapped_column(String(300))
    itc_period: Mapped[Optional[datetime.date]] = mapped_column(Date)  # GSTR-3B period the credit note's GST reduced ITC
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    applied_by: Mapped[Optional[str]] = mapped_column(String(100))
    applied_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    cancelled_by: Mapped[Optional[str]] = mapped_column(String(100))
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(500))
