# Backend/Data_Access_Layer/models/vendor_bank_verification.py
"""Vendor bank account verification and change control (P3) - the main control against payment fraud.

One row per vendor bank account:
  * how it was verified - PENNY_DROP (live bank check: the name at the bank) or DOCUMENT (cancelled
    cheque / bank letter checked by Finance) - and the result (VERIFIED / NAME_MISMATCH / FAILED);
  * approval by a second person, different from whoever added or last changed the account.
Only an APPROVED account may receive money through a payment run. Editing the account resets
the row. Created by migration_vendor_bank_verification.sql (create_all also creates it).
"""
from typing import Optional
import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Numeric, PrimaryKeyConstraint, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

UNVERIFIED, VERIFIED, NAME_MISMATCH, FAILED = "UNVERIFIED", "VERIFIED", "NAME_MISMATCH", "FAILED"
PENNY_DROP, DOCUMENT = "PENNY_DROP", "DOCUMENT"
APPROVAL_PENDING, APPROVED, REJECTED = "PENDING", "APPROVED", "REJECTED"


class VendorBankVerification(Base):
    __tablename__ = "vendor_bank_verification"
    __table_args__ = (
        ForeignKeyConstraint(["vendor_bank_id"], ["ap.vendor_bank.vendor_bank_id"], ondelete="CASCADE",
                             name="vendor_bank_verification_bank_fk"),
        PrimaryKeyConstraint("vendor_bank_id", name="vendor_bank_verification_pkey"),
        CheckConstraint("status IN ('UNVERIFIED','VERIFIED','NAME_MISMATCH','FAILED')", name="vendor_bank_verification_status_chk"),
        CheckConstraint("approval_status IN ('PENDING','APPROVED','REJECTED')", name="vendor_bank_verification_approval_chk"),
        {"schema": "ap"},
    )

    vendor_bank_id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'UNVERIFIED'::character varying"))
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    changed_by: Mapped[Optional[str]] = mapped_column(String(100))  # who added / last changed the account
    method: Mapped[Optional[str]] = mapped_column(String(20))
    name_at_bank: Mapped[Optional[str]] = mapped_column(String(200))
    name_match_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    reference: Mapped[Optional[str]] = mapped_column(String(100))  # penny-drop UTR / transaction id
    message: Mapped[Optional[str]] = mapped_column(Text)
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    approval_remarks: Mapped[Optional[str]] = mapped_column(String(500))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
