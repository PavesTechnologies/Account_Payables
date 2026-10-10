# Backend/API_Layer/interface/invoice_bulk_upload_interface.py
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BatchCounts(BaseModel):
    queued: int = 0
    created: int = 0
    vendor_not_found: int = 0
    duplicate: int = 0
    failed: int = 0
    skipped: int = 0


class BatchSummary(BaseModel):
    batch_id: int
    source_type: str
    source_name: Optional[str] = None
    status: str
    total_files: int
    uploaded_by: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    created_at: datetime.datetime
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    counts: BatchCounts


class BatchItem(BaseModel):
    item_id: int
    sequence_no: int
    file_name: str
    file_size: Optional[int] = None
    status: str
    stalled: bool = False
    attempt_count: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    can_retry: bool
    can_skip: bool
    invoice_id: Optional[int] = None
    invoice_number: Optional[str] = None
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    vendor_gstin: Optional[str] = None
    is_valid: Optional[bool] = None
    validation_issues: List[str] = Field(default_factory=list)
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None


class BatchDetail(BatchSummary):
    items: List[BatchItem]


class BatchList(BaseModel):
    items: List[BatchSummary]
    total: int
    page: int
    page_size: int


class BulkUploadLimits(BaseModel):
    max_files: int
    max_file_mb: int
    max_zip_mb: int
    accepted_extensions: List[str]
