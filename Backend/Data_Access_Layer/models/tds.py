# Backend/Data_Access_Layer/models/tds.py
"""TDS (India withholding-tax) determination models.

Deliberately separate from the generic ap.tax_rule/tax_rate_rule/tax_rule_condition
framework rather than a parallel schema: a TDS rate is just a TaxRule row with
rule_category='TDS_RATE' and a TaxRuleCondition (condition_type='PAYMENT_NATURE'),
matched by TDSDeterminationService the same way GST rates are matched in
invoice_extraction_dao.py. Only the TDS-specific business objects below are new:

- TdsPaymentNature / PurchaseCategoryTdsMapping: the classification layer
  (purchase_category only *suggests* a payment nature - see spec section 2).
- VendorTdsProfile: PAN/residency/exemption/lower-deduction-certificate facts
  about a vendor, independent of any one invoice.
- InvoiceTds: the per-invoice determination *snapshot* - once written it is not
  silently recalculated when tax_rule/vendor data changes later (see
  TDSDeterminationService).

Tables already exist live (created ahead of the SQLAlchemy models via raw SQL -
see migration_tds_foundation.sql); mapped here to match exactly, same as every
other model in this package.
"""
from typing import Optional, TYPE_CHECKING
import datetime
import decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.purchase import PurchaseCategory
    from Backend.Data_Access_Layer.models.vendor import Vendor
    from Backend.Data_Access_Layer.models.invoice import Invoice
    from Backend.Data_Access_Layer.models.master import TaxRule, TaxRateRule


class TdsPaymentNature(Base):
    """Business nature of a payment (CONTRACTOR, PROFESSIONAL_SERVICE, ...).
    A purchase category only *suggests* one of these (PurchaseCategoryTdsMapping);
    it never determines the final TDS rule directly (spec section 2)."""

    __tablename__ = "tds_payment_nature"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="tds_payment_nature_pkey"),
        UniqueConstraint("code", name="tds_payment_nature_code_key"),
        {"schema": "ap"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    description: Mapped[Optional[str]] = mapped_column(Text)

    category_mappings: Mapped[list["PurchaseCategoryTdsMapping"]] = relationship(
        "PurchaseCategoryTdsMapping", back_populates="tds_payment_nature"
    )
    invoice_tds: Mapped[list["InvoiceTds"]] = relationship("InvoiceTds", back_populates="payment_nature")


class PurchaseCategoryTdsMapping(Base):
    """The suggestion layer: which TdsPaymentNature a purchase_category defaults
    to. is_default marks the one row TDSDeterminationService auto-applies when
    the AP Executive hasn't confirmed/corrected a payment nature explicitly."""

    __tablename__ = "purchase_category_tds_mapping"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_category_id"], ["ap.purchase_category.id"],
            ondelete="CASCADE", name="purchase_category_tds_mapping_category_fk",
        ),
        ForeignKeyConstraint(
            ["tds_payment_nature_id"], ["ap.tds_payment_nature.id"],
            ondelete="RESTRICT", name="purchase_category_tds_mapping_nature_fk",
        ),
        PrimaryKeyConstraint("id", name="purchase_category_tds_mapping_pkey"),
        UniqueConstraint("purchase_category_id", "tds_payment_nature_id", name="purchase_category_tds_mapping_unique"),
        Index("idx_purchase_category_tds_mapping_category", "purchase_category_id"),
        Index("idx_purchase_category_tds_mapping_nature", "tds_payment_nature_id"),
        {"schema": "ap"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tds_payment_nature_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    purchase_category: Mapped["PurchaseCategory"] = relationship("PurchaseCategory")
    tds_payment_nature: Mapped["TdsPaymentNature"] = relationship("TdsPaymentNature", back_populates="category_mappings")


class VendorTdsProfile(Base):
    """PAN/residency/exemption/lower-deduction-certificate facts about a vendor,
    independent of any one invoice. One row per vendor (unique vendor_id).
    TDSDeterminationService auto-creates a default row (pan_status derived from
    Vendor.pan_number) the first time an invoice for that vendor is determined,
    if nothing was seeded for it - there is no CRUD API for this table in
    Phase 1 (see migration_tds_foundation.sql / implementation report)."""

    __tablename__ = "vendor_tds_profile"
    __table_args__ = (
        ForeignKeyConstraint(["vendor_id"], ["ap.vendor.vendor_id"], ondelete="CASCADE", name="vendor_tds_profile_vendor_fk"),
        PrimaryKeyConstraint("id", name="vendor_tds_profile_pkey"),
        UniqueConstraint("vendor_id", name="vendor_tds_profile_vendor_unique"),
        CheckConstraint(
            "certificate_valid_to IS NULL OR certificate_valid_from IS NULL OR certificate_valid_to >= certificate_valid_from",
            name="vendor_tds_certificate_dates_chk",
        ),
        CheckConstraint("certificate_rate IS NULL OR certificate_rate >= 0", name="vendor_tds_certificate_rate_chk"),
        Index("idx_vendor_tds_profile_vendor", "vendor_id"),
        {"schema": "ap"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    residency_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'RESIDENT'::character varying"))
    pan_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'VALID'::character varying"))
    lower_deduction_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    certificate_number: Mapped[Optional[str]] = mapped_column(String(100))
    certificate_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(7, 4))
    certificate_valid_from: Mapped[Optional[datetime.date]] = mapped_column(Date)
    certificate_valid_to: Mapped[Optional[datetime.date]] = mapped_column(Date)
    tds_exemption_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    exemption_reason: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    vendor: Mapped["Vendor"] = relationship("Vendor")


class InvoiceTds(Base):
    """One determination *snapshot* per invoice (unique invoice_id). Written by
    TDSDeterminationService.determine()/update_inputs(); once determination_status
    reaches VERIFIED it is immutable (see the service) - a later tax_rule edit
    must never silently change an already-verified historical invoice."""

    __tablename__ = "invoice_tds"
    __table_args__ = (
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], ondelete="CASCADE", name="invoice_tds_invoice_fk"),
        ForeignKeyConstraint(["payment_nature_id"], ["ap.tds_payment_nature.id"], ondelete="RESTRICT", name="invoice_tds_payment_nature_fk"),
        ForeignKeyConstraint(["tds_rule_id"], ["ap.tax_rule.tax_rule_id"], ondelete="RESTRICT", name="invoice_tds_rule_fk"),
        ForeignKeyConstraint(["tds_rate_rule_id"], ["ap.tax_rate_rule.tax_rate_rule_id"], ondelete="RESTRICT", name="invoice_tds_rate_rule_fk"),
        PrimaryKeyConstraint("id", name="invoice_tds_pkey"),
        UniqueConstraint("invoice_id", name="invoice_tds_invoice_unique"),
        CheckConstraint("taxable_base IS NULL OR taxable_base >= 0", name="invoice_tds_amounts_chk"),
        CheckConstraint("tds_rate IS NULL OR tds_rate >= 0", name="invoice_tds_rate_chk"),
        CheckConstraint("tds_amount IS NULL OR tds_amount >= 0", name="invoice_tds_amount_chk"),
        CheckConstraint("determination_status IN ('PENDING','DETERMINED','VERIFIED')", name="invoice_tds_determination_status_chk"),
        Index("idx_invoice_tds_invoice", "invoice_id"),
        Index("idx_invoice_tds_rule", "tds_rule_id"),
        Index("idx_invoice_tds_status", "determination_status"),
        {"schema": "ap"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tds_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    payment_nature_id: Mapped[Optional[int]] = mapped_column(Integer)
    tds_rule_id: Mapped[Optional[int]] = mapped_column(Integer)
    tds_rate_rule_id: Mapped[Optional[int]] = mapped_column(Integer)
    taxable_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    tds_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(7, 4))
    tds_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    threshold_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_period_aggregate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2), server_default=text("0"))
    current_transaction_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    aggregate_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    pan_status: Mapped[Optional[str]] = mapped_column(String(30))
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    # GST registration compliance signal (Sandbox GSTIN search) - a warning
    # surfaced to AP/Finance alongside the determination, never an input to
    # tds_applicable/tds_rate/tds_amount (see TDSDeterminationService).
    # One of the vendor's actual GST status strings (e.g. "Active",
    # "Cancelled"), or "NOT_ON_FILE" (vendor has no GST registration on
    # record) / "CHECK_UNAVAILABLE" (Sandbox API call failed).
    gstin_status: Mapped[Optional[str]] = mapped_column(String(30))
    gstin_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    determination_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'PENDING'::character varying"))
    determination_reason: Mapped[Optional[str]] = mapped_column(Text)
    determined_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    determined_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    invoice: Mapped["Invoice"] = relationship("Invoice")
    payment_nature: Mapped[Optional["TdsPaymentNature"]] = relationship("TdsPaymentNature", back_populates="invoice_tds")
    tds_rule: Mapped[Optional["TaxRule"]] = relationship("TaxRule", foreign_keys=[tds_rule_id])
    tds_rate_rule: Mapped[Optional["TaxRateRule"]] = relationship("TaxRateRule", foreign_keys=[tds_rate_rule_id])
