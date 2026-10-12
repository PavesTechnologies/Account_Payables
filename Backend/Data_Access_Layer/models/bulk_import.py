# Backend/Data_Access_Layer/models/bulk_import.py
"""Bulk import of payments / TDS challans / TDS filings from an Excel sheet plus documents
(APM_AUTOMATION_PLAN.md 6.7). Tracks only the import: every payment, challan or filing is still
recorded by the existing services (PaymentTrackingService.record_payment, TdsChallanService).

Tables are created by migration_bulk_import.sql; mapped here to match exactly.
"""
from typing import Optional
import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

KIND_PAYMENTS = "PAYMENTS"
KIND_TDS_CHALLANS = "TDS_CHALLANS"
KIND_TDS_FILINGS = "TDS_FILINGS"
KINDS = (KIND_PAYMENTS, KIND_TDS_CHALLANS, KIND_TDS_FILINGS)

SOURCE_MANUAL = "MANUAL_UPLOAD"
SOURCE_SHAREPOINT = "SHAREPOINT"

JOB_VALIDATING = "VALIDATING"
JOB_VALIDATED = "VALIDATED"
JOB_RECORDING = "RECORDING"
JOB_COMPLETED = "COMPLETED"
JOB_NEEDS_REVIEW = "NEEDS_REVIEW"
JOB_FAILED = "FAILED"

ROW_PENDING = "PENDING"
ROW_READY = "READY"
ROW_NEEDS_REVIEW = "NEEDS_REVIEW"
ROW_ERROR = "ERROR"
ROW_RECORDED = "RECORDED"
ROW_SKIPPED = "SKIPPED"


class BulkImportJob(Base):
    __tablename__ = "bulk_import_job"
    __table_args__ = (
        PrimaryKeyConstraint("job_id", name="bulk_import_job_pkey"),
        CheckConstraint("kind IN ('PAYMENTS','TDS_CHALLANS','TDS_FILINGS')", name="bulk_import_job_kind_chk"),
        CheckConstraint("source IN ('MANUAL_UPLOAD','SHAREPOINT')", name="bulk_import_job_source_chk"),
        CheckConstraint("status IN ('VALIDATING','VALIDATED','RECORDING','COMPLETED','NEEDS_REVIEW','FAILED')",
                        name="bulk_import_job_status_chk"),
        Index("idx_bulk_import_job_created", "created_at"),
        # A SharePoint file version is imported once, however many runners are scheduled.
        Index("uq_bulk_import_job_source_ref", "source", "source_reference", unique=True,
              postgresql_where=text("source_reference IS NOT NULL")),
        {"schema": "ap"},
    )

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'MANUAL_UPLOAD'::character varying"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'VALIDATING'::character varying"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    auto_record: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source_reference: Mapped[Optional[str]] = mapped_column(String(500))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_by_name: Mapped[Optional[str]] = mapped_column(String(200))
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    rows: Mapped[list["BulkImportRow"]] = relationship("BulkImportRow", back_populates="job", order_by="BulkImportRow.row_number")


class BulkImportRow(Base):
    __tablename__ = "bulk_import_row"
    __table_args__ = (
        ForeignKeyConstraint(["job_id"], ["ap.bulk_import_job.job_id"], name="bulk_import_row_job_fk"),
        PrimaryKeyConstraint("row_id", name="bulk_import_row_pkey"),
        CheckConstraint("status IN ('PENDING','READY','NEEDS_REVIEW','ERROR','RECORDED','SKIPPED')", name="bulk_import_row_status_chk"),
        Index("idx_bulk_import_row_job", "job_id"),
        {"schema": "ap"},
    )

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)  # spreadsheet row (header = 1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)         # the row as read from the sheet
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    group_key: Mapped[Optional[str]] = mapped_column(String(200))     # rows recorded together (one challan / filing / UTR)
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer)
    document_name: Mapped[Optional[str]] = mapped_column(String(255))
    document_path: Mapped[Optional[str]] = mapped_column(String(500))  # S3 key of the receipt / challan / acknowledgement
    extracted: Mapped[Optional[dict]] = mapped_column(JSONB)          # what the document says
    messages: Mapped[Optional[list]] = mapped_column(JSONB)           # [{severity, message}]
    result_reference: Mapped[Optional[str]] = mapped_column(String(100))  # payment / challan / filing id once recorded
    recorded_by: Mapped[Optional[str]] = mapped_column(String(100))
    recorded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    job: Mapped["BulkImportJob"] = relationship("BulkImportJob", back_populates="rows")
