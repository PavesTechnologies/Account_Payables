# Backend/Data_Access_Layer/models/tds_challan.py
"""Shared TDS challan and quarterly return filing (APM_AUTOMATION_PLAN.md 3.4 / D4, Phase 5).

One challan (ITNS 281) usually pays the TDS of many invoices; one quarterly statement (26Q / 27Q)
covers every deposited invoice of the quarter. These tables record that shared document and which
invoices it covers. Per-invoice status stays in invoice_tds_tracking (the system of record): when
a challan / filing is confirmed, the existing record_deposit / record_filing runs for each invoice
in the same transaction.

Tables are created by migration_tds_challan.sql; mapped here to match exactly.
"""
from typing import Optional
import datetime
import decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

CHALLAN_STATUSES = ("CONFIRMED",)
FILING_FORMS = ("26Q", "27Q", "24Q", "27EQ")


class TdsChallan(Base):
    __tablename__ = "tds_challan"
    __table_args__ = (
        PrimaryKeyConstraint("challan_id", name="tds_challan_pkey"),
        CheckConstraint("status IN ('CONFIRMED')", name="tds_challan_status_chk"),
        CheckConstraint("bsr_code ~ '^[0-9]{7}$'", name="tds_challan_bsr_chk"),
        CheckConstraint("challan_serial_no ~ '^[0-9]{1,5}$'", name="tds_challan_serial_chk"),
        CheckConstraint("tax_amount >= 0 AND total_amount >= 0", name="tds_challan_amounts_chk"),
        Index("uq_tds_challan_identity", "bsr_code", "deposit_date", "challan_serial_no", unique=True),
        Index("idx_tds_challan_deposit_date", "deposit_date"),
        {"schema": "ap"},
    )

    challan_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challan_serial_no: Mapped[str] = mapped_column(String(5), nullable=False)
    bsr_code: Mapped[str] = mapped_column(String(7), nullable=False)
    deposit_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    # CIN = BSR code + deposit date (DDMMYYYY) + challan serial number.
    cin: Mapped[str] = mapped_column(String(25), nullable=False)
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'CONFIRMED'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    surcharge: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    cess: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    interest: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    fee: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    tan: Mapped[Optional[str]] = mapped_column(String(10))
    assessment_year: Mapped[Optional[str]] = mapped_column(String(9))
    minor_head: Mapped[Optional[str]] = mapped_column(String(3))
    section_code: Mapped[Optional[str]] = mapped_column(String(20))
    tax_period: Mapped[Optional[datetime.date]] = mapped_column(Date)  # first day of the deduction month
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(20))  # MANUAL | BULK_IMPORT
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    allocations: Mapped[list["TdsChallanAllocation"]] = relationship("TdsChallanAllocation", back_populates="challan")


class TdsChallanAllocation(Base):
    __tablename__ = "tds_challan_allocation"
    __table_args__ = (
        ForeignKeyConstraint(["challan_id"], ["ap.tds_challan.challan_id"], name="tds_challan_allocation_challan_fk"),
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], name="tds_challan_allocation_invoice_fk"),
        PrimaryKeyConstraint("allocation_id", name="tds_challan_allocation_pkey"),
        CheckConstraint("allocated_tds_amount > 0", name="tds_challan_allocation_amount_chk"),
        # An invoice's TDS is deposited through one active challan.
        Index("uq_tds_challan_allocation_invoice", "invoice_id", unique=True, postgresql_where=text("is_active")),
        Index("idx_tds_challan_allocation_challan", "challan_id"),
        {"schema": "ap"},
    )

    allocation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challan_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_tds_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))

    challan: Mapped["TdsChallan"] = relationship("TdsChallan", back_populates="allocations")


class TdsReturnFiling(Base):
    __tablename__ = "tds_return_filing"
    __table_args__ = (
        PrimaryKeyConstraint("filing_id", name="tds_return_filing_pkey"),
        CheckConstraint("form_type IN ('26Q','27Q','24Q','27EQ')", name="tds_return_filing_form_chk"),
        CheckConstraint("quarter BETWEEN 1 AND 4", name="tds_return_filing_quarter_chk"),
        CheckConstraint("status IN ('CONFIRMED')", name="tds_return_filing_status_chk"),
        Index("uq_tds_return_filing_ack", "acknowledgement_no", unique=True),
        Index("idx_tds_return_filing_period", "financial_year", "quarter"),
        {"schema": "ap"},
    )

    filing_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    form_type: Mapped[str] = mapped_column(String(5), nullable=False)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)  # e.g. 2026-27
    quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    acknowledgement_no: Mapped[str] = mapped_column(String(30), nullable=False)  # provisional receipt / token no.
    filing_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'CONFIRMED'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    tan: Mapped[Optional[str]] = mapped_column(String(10))
    is_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(20))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    invoices: Mapped[list["TdsReturnFilingInvoice"]] = relationship("TdsReturnFilingInvoice", back_populates="filing")


class TdsReturnFilingInvoice(Base):
    __tablename__ = "tds_return_filing_invoice"
    __table_args__ = (
        ForeignKeyConstraint(["filing_id"], ["ap.tds_return_filing.filing_id"], name="tds_return_filing_invoice_filing_fk"),
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], name="tds_return_filing_invoice_invoice_fk"),
        PrimaryKeyConstraint("id", name="tds_return_filing_invoice_pkey"),
        Index("uq_tds_return_filing_invoice", "filing_id", "invoice_id", unique=True),
        Index("idx_tds_return_filing_invoice_invoice", "invoice_id"),
        {"schema": "ap"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)

    filing: Mapped["TdsReturnFiling"] = relationship("TdsReturnFiling", back_populates="invoices")
