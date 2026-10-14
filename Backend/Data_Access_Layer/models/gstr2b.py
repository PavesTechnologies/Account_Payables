# Backend/Data_Access_Layer/models/gstr2b.py
"""GSTR-2B reconciliation (P3) - what each supplier actually filed vs what is in the books.

  gstr2b_import  one downloaded GSTR-2B (JSON from the GST portal, or a CSV) for a return period
  gstr2b_entry   one document in it (invoice / credit note / debit note) and its match:
                   MATCHED       found in the books, tax agrees
                   MISMATCH      found, tax (or taxable value) differs - see the difference
                   NOT_IN_BOOKS  the supplier filed it, we have not booked it - chase the invoice
Invoices in the books with no matching entry are "missing in 2B" (computed, not stored): the supplier
has not filed them, so the input credit cannot be claimed yet (s.16(2)(aa)).
Created by migration_gstr2b.sql (create_all also creates the tables).
"""
from typing import Optional
import datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric,
                        PrimaryKeyConstraint, String, text)
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

MATCHED, MISMATCH, NOT_IN_BOOKS = "MATCHED", "MISMATCH", "NOT_IN_BOOKS"


class Gstr2bImport(Base):
    __tablename__ = "gstr2b_import"
    __table_args__ = (
        PrimaryKeyConstraint("import_id", name="gstr2b_import_pkey"),
        Index("idx_gstr2b_import_period", "return_period"),
        {"schema": "ap"},
    )

    import_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_period: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    source_format: Mapped[Optional[str]] = mapped_column(String(10))  # JSON / CSV
    buyer_gstin: Mapped[Optional[str]] = mapped_column(String(15))
    generated_on: Mapped[Optional[datetime.date]] = mapped_column(Date)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100))


class Gstr2bEntry(Base):
    __tablename__ = "gstr2b_entry"
    __table_args__ = (
        ForeignKeyConstraint(["import_id"], ["ap.gstr2b_import.import_id"], ondelete="CASCADE", name="gstr2b_entry_import_fk"),
        ForeignKeyConstraint(["matched_invoice_id"], ["ap.invoice.invoice_id"], name="gstr2b_entry_invoice_fk"),
        PrimaryKeyConstraint("entry_id", name="gstr2b_entry_pkey"),
        CheckConstraint("match_status IN ('MATCHED','MISMATCH','NOT_IN_BOOKS')", name="gstr2b_entry_status_chk"),
        Index("idx_gstr2b_entry_import", "import_id"),
        Index("idx_gstr2b_entry_invoice", "matched_invoice_id"),
        {"schema": "ap"},
    )

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(5), nullable=False)  # INV / CN / DN
    doc_number: Mapped[str] = mapped_column(String(60), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    cess: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    match_status: Mapped[str] = mapped_column(String(20), nullable=False)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(200))
    doc_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    itc_available: Mapped[Optional[bool]] = mapped_column(Boolean)
    itc_unavailable_reason: Mapped[Optional[str]] = mapped_column(String(200))
    supplier_filed_on: Mapped[Optional[datetime.date]] = mapped_column(Date)
    matched_invoice_id: Mapped[Optional[int]] = mapped_column(Integer)
    tax_difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    note: Mapped[Optional[str]] = mapped_column(String(300))
