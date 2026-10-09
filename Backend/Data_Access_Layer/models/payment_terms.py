# Backend/Data_Access_Layer/models/payment_terms.py
"""Payment-term compliance models (APM_AUTOMATION_PLAN.md 3.1 / 3.1a).

- VendorAgreement / VendorAgreementDocument: uploaded vendor contracts. Only an
  ACTIVE (verified) agreement valid on the invoice date is an authoritative
  payment-term source for a NON_PO invoice.
- InvoicePaymentTerm: the per-invoice compliance record - the invoice-stated,
  PO, agreement and vendor-master terms side by side, and the contractual /
  statutory / effective due dates kept apart. invoice.due_date mirrors
  effective_due_date so existing due-date queries keep working.

Tables are created by migration_payment_term_compliance.sql; mapped here to
match exactly, same as every other model in this package.
"""
from typing import Optional, TYPE_CHECKING
import datetime
import decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import PaymentTerm
    from Backend.Data_Access_Layer.models.vendor import Vendor


AGREEMENT_TYPES = ("LEASE", "MSA", "SOW", "SUBSCRIPTION", "RATE_CONTRACT", "OTHER")
AGREEMENT_STATUS_DRAFT = "DRAFT"
AGREEMENT_STATUS_PENDING = "PENDING_VERIFICATION"
AGREEMENT_STATUS_ACTIVE = "ACTIVE"
AGREEMENT_STATUS_REJECTED = "REJECTED"
AGREEMENT_STATUS_SUPERSEDED = "SUPERSEDED"
AGREEMENT_STATUSES = (
    AGREEMENT_STATUS_DRAFT, AGREEMENT_STATUS_PENDING, AGREEMENT_STATUS_ACTIVE,
    AGREEMENT_STATUS_REJECTED, AGREEMENT_STATUS_SUPERSEDED,
)
DUE_BASIS_INVOICE_DATE = "INVOICE_DATE"
DUE_BASIS_GRN_DATE = "GRN_DATE"
DUE_BASES = (DUE_BASIS_INVOICE_DATE, DUE_BASIS_GRN_DATE)


class VendorAgreement(Base):
    __tablename__ = "vendor_agreement"
    __table_args__ = (
        ForeignKeyConstraint(["vendor_id"], ["ap.vendor.vendor_id"], name="vendor_agreement_vendor_fk"),
        ForeignKeyConstraint(["payment_term_id"], ["ap.payment_term.payment_term_id"], name="vendor_agreement_payment_term_fk"),
        PrimaryKeyConstraint("agreement_id", name="vendor_agreement_pkey"),
        CheckConstraint(
            "agreement_type IN ('LEASE','MSA','SOW','SUBSCRIPTION','RATE_CONTRACT','OTHER')",
            name="vendor_agreement_type_chk",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PENDING_VERIFICATION','ACTIVE','REJECTED','SUPERSEDED')",
            name="vendor_agreement_status_chk",
        ),
        CheckConstraint("due_basis IN ('INVOICE_DATE','GRN_DATE')", name="vendor_agreement_due_basis_chk"),
        CheckConstraint("term_days IS NULL OR term_days BETWEEN 0 AND 365", name="vendor_agreement_term_days_chk"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="vendor_agreement_validity_chk"),
        Index("idx_vendor_agreement_vendor_status", "vendor_id", "status"),
        {"schema": "ap"},
    )

    agreement_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    agreement_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'OTHER'::character varying"))
    reference_no: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    valid_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[datetime.date]] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    payment_term_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_terms_text: Mapped[Optional[str]] = mapped_column(String(500))
    term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    due_basis: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'INVOICE_DATE'::character varying"))
    status: Mapped[str] = mapped_column(String(25), nullable=False, server_default=text("'PENDING_VERIFICATION'::character varying"))
    extracted_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    extraction_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100))
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    verification_remarks: Mapped[Optional[str]] = mapped_column(Text)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    vendor: Mapped["Vendor"] = relationship("Vendor")
    payment_term: Mapped[Optional["PaymentTerm"]] = relationship("PaymentTerm")
    documents: Mapped[list["VendorAgreementDocument"]] = relationship(
        "VendorAgreementDocument", back_populates="agreement", cascade="all, delete-orphan",
        order_by="VendorAgreementDocument.document_id",
    )

    def is_valid_on(self, on_date: datetime.date) -> bool:
        return self.valid_from <= on_date and (self.valid_to is None or on_date <= self.valid_to)


class VendorAgreementDocument(Base):
    __tablename__ = "vendor_agreement_document"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agreement_id"], ["ap.vendor_agreement.agreement_id"], ondelete="CASCADE",
            name="vendor_agreement_document_agreement_fk",
        ),
        PrimaryKeyConstraint("document_id", name="vendor_agreement_document_pkey"),
        Index("idx_vendor_agreement_document_agreement", "agreement_id"),
        {"schema": "ap"},
    )

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agreement_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100))
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    agreement: Mapped["VendorAgreement"] = relationship("VendorAgreement", back_populates="documents")


class InvoicePaymentTerm(Base):
    __tablename__ = "invoice_payment_term"
    __table_args__ = (
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], ondelete="CASCADE", name="invoice_payment_term_invoice_fk"),
        ForeignKeyConstraint(["agreement_id"], ["ap.vendor_agreement.agreement_id"], name="invoice_payment_term_agreement_fk"),
        ForeignKeyConstraint(
            ["vendor_master_term_id"], ["ap.payment_term.payment_term_id"], name="invoice_payment_term_vendor_term_fk"
        ),
        PrimaryKeyConstraint("invoice_id", name="invoice_payment_term_pkey"),
        CheckConstraint(
            "reference_source IN ('PO','AGREEMENT','VENDOR_MASTER','MANUAL','NONE')", name="invoice_payment_term_source_chk"
        ),
        CheckConstraint("due_basis IN ('INVOICE_DATE','GRN_DATE')", name="invoice_payment_term_basis_chk"),
        CheckConstraint(
            "validation_status IN ('COMPLIANT','MISMATCH','REVIEW_REQUIRED','VERIFIED_OVERRIDE')",
            name="invoice_payment_term_status_chk",
        ),
        Index("idx_invoice_payment_term_status", "validation_status"),
        Index("idx_invoice_payment_term_effective_due", "effective_due_date"),
        {"schema": "ap"},
    )

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_terms_text: Mapped[Optional[str]] = mapped_column(String(500))
    invoice_term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    invoice_due_date_printed: Mapped[Optional[datetime.date]] = mapped_column(Date)
    po_terms_text: Mapped[Optional[str]] = mapped_column(String(500))
    po_term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    vendor_master_term_id: Mapped[Optional[int]] = mapped_column(Integer)
    vendor_master_term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    agreement_id: Mapped[Optional[int]] = mapped_column(Integer)
    agreement_term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    reference_source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'NONE'::character varying"))
    applied_term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    suggested_term_days: Mapped[Optional[int]] = mapped_column(SmallInteger)
    due_basis: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'INVOICE_DATE'::character varying"))
    basis_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    contractual_due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    statutory_due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    statutory_rule: Mapped[Optional[str]] = mapped_column(String(50))
    effective_due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    due_date_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'REVIEW_REQUIRED'::character varying")
    )
    reason_code: Mapped[Optional[str]] = mapped_column(String(50))
    reason_detail: Mapped[Optional[str]] = mapped_column(String(500))
    checked_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    verified_by: Mapped[Optional[str]] = mapped_column(String(100))
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    verification_remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    agreement: Mapped[Optional["VendorAgreement"]] = relationship("VendorAgreement")
