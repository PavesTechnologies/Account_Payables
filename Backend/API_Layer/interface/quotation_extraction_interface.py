# Backend/API_Layer/interface/quotation_extraction_interface.py

import datetime
import decimal
from typing import Dict, Optional

from pydantic import BaseModel


class QuotationExtractionData(BaseModel):
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    quotation_number: Optional[str] = None
    total_amount: Optional[decimal.Decimal] = None
    quotation_date: Optional[datetime.date] = None
    valid_until: Optional[datetime.date] = None
    delivery_days: Optional[int] = None
    payment_terms: Optional[str] = None
    field_confidence: Optional[Dict[str, float]] = None


class QuotationExtractionResponse(BaseModel):
    success: bool
    message: str
    data: QuotationExtractionData
