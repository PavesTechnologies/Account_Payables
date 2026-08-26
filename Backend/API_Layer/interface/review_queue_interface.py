# Backend/API_Layer/interface/review_queue_interface.py
"""OCR review queue — derived entirely from existing invoice/inbound_document/
status_master rows (no dedicated queue table). See
Business_Layer/services/invoice_process_service.get_review_queue.
"""
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel


class ReviewQueueItem(BaseModel):
    path: str  # "PATH_A" (invoice created, awaiting OCR confirmation) | "PATH_B" (vendor never matched)
    inbound_document_id: Optional[int] = None
    invoice_id: Optional[int] = None
    invoice_number: Optional[str] = None
    vendor_id: Optional[int] = None
    file_name: Optional[str] = None
    status_code: Optional[str] = None
    net_amount: Optional[decimal.Decimal] = None
    extraction_confidence: Optional[decimal.Decimal] = None
    created_at: datetime.datetime


class ReviewQueueResponse(BaseModel):
    total_path_a: int
    total_path_b: int
    skip: int
    limit: int
    items: List[ReviewQueueItem]
