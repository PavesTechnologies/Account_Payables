# Backend/API_Layer/interface/goods_receipt_interface.py
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class GoodsReceiptLineDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grn_line_id: int
    grn_id: int
    description: str
    received_quantity: decimal.Decimal
    po_line_id: Optional[int]
    item_code: Optional[str]


class GoodsReceiptDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grn_id: int
    po_id: Optional[int]
    vendor_id: int
    file_path: Optional[str]
    created_by: Optional[str]
    created_at: datetime.datetime
    grn_number: Optional[str]
    receipt_date: Optional[datetime.date]
    goods_receipt_line: List[GoodsReceiptLineDTO] = []
