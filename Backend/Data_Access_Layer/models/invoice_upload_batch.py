# Backend/Data_Access_Layer/models/invoice_upload_batch.py
"""Bulk invoice upload tracking (APM_AUTOMATION_PLAN.md Phase 3).

A batch is one bulk upload (a ZIP or several files); each file is one item.
These tables only track orchestration - every invoice is still created by the
single-upload operations (extract_invoice_from_s3 -> validate_invoice ->
create_invoice), so invoice / review / approval / TDS / payment data is never
written here.

Tables are created by migration_invoice_bulk_upload.sql; mapped here to match
exactly, same as every other model in this package.
"""
from typing import Optional, TYPE_CHECKING
import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.invoice import Invoice


SOURCE_MANUAL_UPLOAD = "MANUAL_UPLOAD"
SOURCE_EMAIL = "EMAIL"
SOURCE_TYPES = (SOURCE_MANUAL_UPLOAD, SOURCE_EMAIL)

BATCH_QUEUED = "QUEUED"
BATCH_PROCESSING = "PROCESSING"
BATCH_COMPLETED = "COMPLETED"
BATCH_NEEDS_ATTENTION = "NEEDS_ATTENTION"
BATCH_STATUSES = (BATCH_QUEUED, BATCH_PROCESSING, BATCH_COMPLETED, BATCH_NEEDS_ATTENTION)

ITEM_QUEUED = "QUEUED"
ITEM_PROCESSING = "PROCESSING"
ITEM_CREATED = "CREATED"
ITEM_VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
ITEM_DUPLICATE = "DUPLICATE"
ITEM_FAILED = "FAILED"
ITEM_SKIPPED = "SKIPPED"
ITEM_STATUSES = (ITEM_QUEUED, ITEM_PROCESSING, ITEM_CREATED, ITEM_VENDOR_NOT_FOUND,
                 ITEM_DUPLICATE, ITEM_FAILED, ITEM_SKIPPED)
ITEM_PENDING = (ITEM_QUEUED, ITEM_PROCESSING)
ITEM_NEEDS_ATTENTION = (ITEM_VENDOR_NOT_FOUND, ITEM_FAILED)


class InvoiceUploadBatch(Base):
    __tablename__ = "invoice_upload_batch"
    __table_args__ = (
        PrimaryKeyConstraint("batch_id", name="invoice_upload_batch_pkey"),
        CheckConstraint("source_type IN ('MANUAL_UPLOAD','EMAIL')", name="invoice_upload_batch_source_chk"),
        CheckConstraint("status IN ('QUEUED','PROCESSING','COMPLETED','NEEDS_ATTENTION')",
                        name="invoice_upload_batch_status_chk"),
        Index("idx_invoice_upload_batch_created", "created_at"),
        Index("idx_invoice_upload_batch_uploaded_by", "uploaded_by"),
        # One batch per email message, even if two intake runners overlap.
        Index("uq_invoice_upload_batch_source_ref", "source_type", "source_reference", unique=True,
              postgresql_where=text("source_reference IS NOT NULL")),
        {"schema": "ap"},
    )

    batch_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'MANUAL_UPLOAD'::character varying"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'QUEUED'::character varying"))
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    # ZIP file name, "<n> files", or (email intake) the message subject.
    source_name: Mapped[Optional[str]] = mapped_column(String(255))
    # Email intake only: the message's internetMessageId, so a message is never ingested twice.
    source_reference: Mapped[Optional[str]] = mapped_column(String(500))
    email_from: Mapped[Optional[str]] = mapped_column(String(320))
    email_subject: Mapped[Optional[str]] = mapped_column(String(500))
    email_received_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    # False when the sender matches no vendor's email - shown as a warning to reviewers.
    sender_known: Mapped[Optional[bool]] = mapped_column(Boolean)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100))
    uploaded_by_name: Mapped[Optional[str]] = mapped_column(String(200))
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    items: Mapped[list["InvoiceUploadBatchItem"]] = relationship(
        "InvoiceUploadBatchItem", back_populates="batch", order_by="InvoiceUploadBatchItem.sequence_no"
    )


class InvoiceUploadBatchItem(Base):
    __tablename__ = "invoice_upload_batch_item"
    __table_args__ = (
        ForeignKeyConstraint(["batch_id"], ["ap.invoice_upload_batch.batch_id"], name="invoice_upload_batch_item_batch_fk"),
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], name="invoice_upload_batch_item_invoice_fk"),
        ForeignKeyConstraint(["duplicate_of_item_id"], ["ap.invoice_upload_batch_item.item_id"],
                             name="invoice_upload_batch_item_duplicate_fk"),
        PrimaryKeyConstraint("item_id", name="invoice_upload_batch_item_pkey"),
        CheckConstraint(
            "status IN ('QUEUED','PROCESSING','CREATED','VENDOR_NOT_FOUND','DUPLICATE','FAILED','SKIPPED')",
            name="invoice_upload_batch_item_status_chk",
        ),
        Index("idx_invoice_upload_batch_item_batch", "batch_id"),
        Index("idx_invoice_upload_batch_item_status", "status"),
        Index("idx_invoice_upload_batch_item_sha", "file_sha256"),
        Index("idx_invoice_upload_batch_item_path", "file_path"),
        {"schema": "ap"},
    )

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'QUEUED'::character varying"))
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    file_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    # S3 key; NULL when the file was rejected before upload (invalid / duplicate file).
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    error_code: Mapped[Optional[str]] = mapped_column(String(40))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    # Textract output kept so a retry (e.g. after onboarding the vendor) does not re-run extraction.
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    validation_result: Mapped[Optional[dict]] = mapped_column(JSONB)
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer)
    duplicate_of_item_id: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    batch: Mapped["InvoiceUploadBatch"] = relationship("InvoiceUploadBatch", back_populates="items")
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice", foreign_keys=[invoice_id])
