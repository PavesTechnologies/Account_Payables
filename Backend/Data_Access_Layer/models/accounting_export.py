# Backend/Data_Access_Layer/models/accounting_export.py
"""Accounting export (P3) - AP vouchers handed to the books (Tally / Zoho Books / CSV).

  accounting_export       one file Finance downloaded: format, voucher-date range, who, when
  accounting_export_item  each voucher in it: invoice booking, payment, credit / debit note, TDS challan

The items let the next export default to "not yet exported", so nothing is posted twice; re-exporting
is allowed (Tally alters a voucher it already has - the vouchers carry a stable REMOTEID).
Created by migration_accounting_export.sql (create_all also creates the tables).
"""
from typing import Optional
import datetime
from decimal import Decimal

from sqlalchemy import (Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, String,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

SOURCE_INVOICE, SOURCE_PAYMENT, SOURCE_NOTE, SOURCE_CHALLAN = "INVOICE", "PAYMENT", "NOTE", "CHALLAN"
SOURCE_TYPES = (SOURCE_INVOICE, SOURCE_PAYMENT, SOURCE_NOTE, SOURCE_CHALLAN)


class AccountingExport(Base):
    __tablename__ = "accounting_export"
    __table_args__ = (
        PrimaryKeyConstraint("export_id", name="accounting_export_pkey"),
        {"schema": "ap"},
    )

    export_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_format: Mapped[str] = mapped_column(String(20), nullable=False)  # TALLY_XML / ZOHO_CSV / GENERIC_CSV
    date_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_to: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    voucher_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))


class AccountingExportItem(Base):
    __tablename__ = "accounting_export_item"
    __table_args__ = (
        ForeignKeyConstraint(["export_id"], ["ap.accounting_export.export_id"], ondelete="CASCADE",
                             name="accounting_export_item_export_fk"),
        PrimaryKeyConstraint("item_id", name="accounting_export_item_pkey"),
        Index("idx_accounting_export_item_export", "export_id"),
        Index("idx_accounting_export_item_source", "source_type", "source_id"),
        {"schema": "ap"},
    )

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(10), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    voucher_number: Mapped[str] = mapped_column(String(40), nullable=False)
    voucher_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
