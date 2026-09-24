# Backend/API_Layer/interface/goods_receipt_interface.py
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# =====================================================
# Related Purchase Order / Invoice (minimal, read-only nesting)
# =====================================================


# ORM serialization (Pydantic v2). Needed because these DTOs are nested
# inside wrapper responses such as VendorPurchaseOrderListResponse, which
# are CONSTRUCTED IN THE ROUTE from SQLAlchemy objects. FastAPI only
# applies from_attributes to a top-level response_model, so a nested DTO
# without this config rejects an ORM instance with
#   "Input should be a valid dictionary or instance of PurchaseOrderDTO".
class PurchaseOrderSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    po_id: int
    po_number: str
    vendor_id: int
    status_id: Optional[int]


class InvoiceSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    invoice_number: str
    vendor_id: int
    status_id: Optional[int]
    net_amount: float


# =====================================================
# Goods Receipt Line
# =====================================================


class GoodsReceiptLineRequest(BaseModel):
    po_line_id: Optional[int] = None
    item_code: Optional[str] = None
    description: str
    received_quantity: decimal.Decimal


class GoodsReceiptLineDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grn_line_id: int
    grn_id: int
    po_line_id: Optional[int]
    item_code: Optional[str]
    description: str
    received_quantity: decimal.Decimal


# =====================================================
# Goods Receipt
# =====================================================


class GoodsReceiptCreateRequest(BaseModel):
    vendor_id: int
    po_id: Optional[int] = None
    grn_number: Optional[str] = None
    receipt_date: Optional[datetime.date] = None
    lines: List[GoodsReceiptLineRequest] = Field(default_factory=list)


class GoodsReceiptUpdateRequest(BaseModel):
    vendor_id: Optional[int] = None
    po_id: Optional[int] = None
    grn_number: Optional[str] = None
    receipt_date: Optional[datetime.date] = None
    # When provided (including an empty list), replaces the goods
    # receipt's full set of line items. Omit to leave existing lines untouched.
    lines: Optional[List[GoodsReceiptLineRequest]] = None


class GoodsReceiptResponse(BaseModel):
    grn_id: int
    message: str


class DeleteGoodsReceiptResponse(BaseModel):
    message: str


class UploadGoodsReceiptDocumentResponse(BaseModel):
    grn_id: int
    file_path: str
    message: str


class GoodsReceiptDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grn_id: int
    vendor_id: int
    po_id: Optional[int]
    created_at: datetime.datetime
    file_path: Optional[str]
    created_by: Optional[str]
    grn_number: Optional[str]
    receipt_date: Optional[datetime.date]
    # Field names match the GoodsReceipt ORM relationship attributes
    # (po/invoice/goods_receipt_line) so FastAPI can populate them
    # directly from the model instance.
    po: Optional[PurchaseOrderSummaryDTO] = None
    invoice: List[InvoiceSummaryDTO] = Field(default_factory=list)
    goods_receipt_line: List[GoodsReceiptLineDTO] = Field(default_factory=list)
