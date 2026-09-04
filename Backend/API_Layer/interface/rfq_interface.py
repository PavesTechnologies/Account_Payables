# Backend/API_Layer/interface/rfq_interface.py
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# =====================================================
# RFQ Vendor (invitation)
# =====================================================


class RFQVendorDTO(BaseModel):
    id: int
    rfq_id: int
    vendor_id: int
    invited_by: str
    invited_at: datetime.datetime


class InviteVendorsRequest(BaseModel):
    vendor_ids: List[int] = Field(default_factory=list)


# =====================================================
# RFQ
# =====================================================


class CreateRFQRequest(BaseModel):
    pr_id: int
    due_date: Optional[datetime.date] = None


class RFQDTO(BaseModel):
    id: int
    rfq_number: str
    pr_id: int
    status_id: int
    created_by: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    due_date: Optional[datetime.date]
    sent_at: Optional[datetime.datetime]
    closed_by: Optional[str]
    closed_at: Optional[datetime.datetime]
    # Field name matches the RFQ ORM relationship attribute (rfq_vendor) so
    # FastAPI can populate it directly from the model instance.
    rfq_vendor: List[RFQVendorDTO] = Field(default_factory=list)


class RFQResponse(BaseModel):
    id: int
    message: str


# =====================================================
# Send RFQ (email dispatch results)
# =====================================================


class RFQVendorSendResultDTO(BaseModel):
    vendor_id: int
    email: Optional[str] = None
    success: bool
    sent_at: datetime.datetime
    error: Optional[str] = None


class SendRFQResponse(BaseModel):
    id: int
    status_id: int
    message: str
    results: List[RFQVendorSendResultDTO] = Field(default_factory=list)
