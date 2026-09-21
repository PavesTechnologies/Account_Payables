# Backend/API_Layer/interface/nda_interface.py
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NdaGenerateRequest(BaseModel):
    vendor_id: int
    pr_id: Optional[int] = None
    # Omitted department/category are derived from the PR so the NDA scope
    # always matches the engagement the requirement was decided against.
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    template_code: Optional[str] = None
    recipient_email: Optional[str] = None


class NdaStatusUpdateRequest(BaseModel):
    status_code: str
    signed_document_key: Optional[str] = None
    reason: Optional[str] = None


class VendorNdaDTO(BaseModel):
    nda_id: int
    vendor_id: int
    pr_id: Optional[int]
    department_id: Optional[int]
    purchase_category_id: Optional[int]
    nda_required: bool
    nda_status_id: int
    status_code: Optional[str]
    template_id: Optional[int]
    template_version: Optional[str]
    # S3 object keys, never URLs - use /document for short-lived access.
    document_key: Optional[str]
    signed_document_key: Optional[str]
    recipient_email: Optional[str]
    valid_from: Optional[datetime.date]
    valid_until: Optional[datetime.date]
    sent_at: Optional[datetime.datetime]
    signed_at: Optional[datetime.datetime]
    completed_at: Optional[datetime.datetime]
    created_at: datetime.datetime
    updated_at: datetime.datetime


class NdaGenerateResponse(BaseModel):
    nda_id: int
    status_code: Optional[str]
    nda_required: bool
    reused: bool
    document_key: Optional[str]
    message: str


class NdaSendResponse(BaseModel):
    nda_id: int
    status_code: Optional[str]
    sent: bool
    recipient_email: Optional[str]
    error: Optional[str] = None
    message: str


class NdaStatusUpdateResponse(BaseModel):
    nda_id: int
    status_code: Optional[str]
    message: str


class NdaSignedUploadResponse(BaseModel):
    nda_id: int
    status_code: Optional[str]
    # S3 object key only - fetch a short-lived URL via /{nda_id}/document?signed=true
    signed_document_key: Optional[str]
    signed_at: Optional[datetime.datetime]
    message: str
    nda: VendorNdaDTO


class NdaDocumentUrlResponse(BaseModel):
    nda_id: int
    url: str
    expires_in_seconds: int


class ExistingNdaResponse(BaseModel):
    vendor_id: int
    outcome: str
    reason: Optional[str] = None
    nda: Optional[VendorNdaDTO] = None
    ndas: List[VendorNdaDTO] = Field(default_factory=list)
