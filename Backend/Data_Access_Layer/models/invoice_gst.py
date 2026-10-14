# Backend/Data_Access_Layer/models/invoice_gst.py
"""GST input tax credit (ITC) register - one row per purchase invoice (P2).

The company pays vendors the GST-inclusive total; the GST part is recovered as input tax credit
in the monthly GSTR-3B return. This row records what can be claimed and whether it was:

  * the CGST / SGST / IGST / cess split (from the invoice), supply type and supplier GSTIN,
  * eligibility (ELIGIBLE / REVIEW / BLOCKED - section 17(5) - / NOT_CLAIMABLE - unregistered),
  * e-invoicing: whether the supplier must issue an IRN, and whether the invoice carries one,
  * the claim (GSTR-3B period) and the 180-day rule - credit on an invoice not paid within 180
    days of its date must be reversed, and can be re-claimed once paid (section 16(2)).

Created by migration_invoice_gst.sql (create_all also creates it).
"""
from typing import Optional
import datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric,
                        PrimaryKeyConstraint, String, Text, text)
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

ELIGIBLE, REVIEW, BLOCKED, NOT_CLAIMABLE = "ELIGIBLE", "REVIEW", "BLOCKED", "NOT_CLAIMABLE"
ELIGIBILITIES = (ELIGIBLE, REVIEW, BLOCKED, NOT_CLAIMABLE)
ITC_PENDING, ITC_CLAIMED, ITC_REVERSED = "PENDING", "CLAIMED", "REVERSED"
ITC_STATUSES = (ITC_PENDING, ITC_CLAIMED, ITC_REVERSED, NOT_CLAIMABLE)
IRN_PRESENT, IRN_MISSING, IRN_NOT_REQUIRED, IRN_UNKNOWN = "PRESENT", "MISSING", "NOT_REQUIRED", "UNKNOWN"


class InvoiceGst(Base):
    __tablename__ = "invoice_gst"
    __table_args__ = (
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], ondelete="CASCADE", name="invoice_gst_invoice_fk"),
        PrimaryKeyConstraint("invoice_id", name="invoice_gst_pkey"),
        CheckConstraint("itc_eligibility IN ('ELIGIBLE','REVIEW','BLOCKED','NOT_CLAIMABLE')", name="invoice_gst_eligibility_chk"),
        CheckConstraint("itc_status IN ('PENDING','CLAIMED','REVERSED','NOT_CLAIMABLE')", name="invoice_gst_status_chk"),
        CheckConstraint("irn_status IN ('PRESENT','MISSING','NOT_REQUIRED','UNKNOWN')", name="invoice_gst_irn_chk"),
        Index("idx_invoice_gst_claim_period", "claim_period"),
        Index("idx_invoice_gst_supplier", "supplier_gstin"),
        {"schema": "ap"},
    )

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    cgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    sgst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    igst: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    cess: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    itc_eligibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ELIGIBLE'::character varying"))
    itc_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    irn_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'UNKNOWN'::character varying"))
    reverse_charge: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    eligibility_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    supplier_gstin: Mapped[Optional[str]] = mapped_column(String(15))
    supply_type: Mapped[Optional[str]] = mapped_column(String(10))  # INTRA / INTER
    place_of_supply: Mapped[Optional[str]] = mapped_column(String(2))
    eligibility_reason: Mapped[Optional[str]] = mapped_column(Text)
    eligibility_set_by: Mapped[Optional[str]] = mapped_column(String(100))
    einvoice_applicable: Mapped[Optional[bool]] = mapped_column(Boolean)
    irn: Mapped[Optional[str]] = mapped_column(String(64))
    ack_no: Mapped[Optional[str]] = mapped_column(String(30))
    claim_period: Mapped[Optional[datetime.date]] = mapped_column(Date)
    claimed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100))
    reversal_due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reversal_period: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reversed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    reversed_by: Mapped[Optional[str]] = mapped_column(String(100))
    reclaim_period: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reclaimed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
