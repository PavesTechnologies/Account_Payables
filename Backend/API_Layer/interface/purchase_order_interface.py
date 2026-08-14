# Backend/API_Layer/interface/purchase_order_interface.py
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class PurchaseOrderLineDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    po_line_id: int
    po_id: int
    description: str
    quantity: decimal.Decimal
    unit_price: decimal.Decimal
    tax_amount: decimal.Decimal
    line_amount: decimal.Decimal
    item_code: Optional[str]


class PurchaseOrderDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    po_id: int
    po_number: str
    vendor_id: int
    status_id: Optional[int]
    file_path: Optional[str]
    created_by: Optional[str]
    created_at: datetime.datetime
    po_date: Optional[datetime.date]
    expected_delivery_date: Optional[datetime.date]
    currency_id: Optional[int]
    subtotal: Optional[decimal.Decimal]
    tax_amount: Optional[decimal.Decimal]
    total_amount: Optional[decimal.Decimal]
    purchase_order_line: List[PurchaseOrderLineDTO] = []
