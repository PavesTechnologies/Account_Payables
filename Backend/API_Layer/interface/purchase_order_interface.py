# Backend/API_Layer/interface/purchase_order_interface.py
import datetime
import decimal
from typing import List, Optional

from pydantic import BaseModel, Field

# =====================================================
# Related Invoice / Goods Receipt (minimal, read-only nesting)
# =====================================================


class InvoiceSummaryDTO(BaseModel):
    invoice_id: int
    invoice_number: str
    vendor_id: int
    status_id: Optional[int]
    net_amount: float


class GoodsReceiptSummaryDTO(BaseModel):
    grn_id: int
    vendor_id: int
    po_id: Optional[int]
    created_at: datetime.datetime
    file_path: Optional[str]


# =====================================================
# Purchase Order Line
# =====================================================


class PurchaseOrderLineRequest(BaseModel):
    item_code: Optional[str] = None
    description: str
    quantity: decimal.Decimal = Field(default=decimal.Decimal("1"))
    unit_price: decimal.Decimal
    tax_amount: decimal.Decimal = Field(default=decimal.Decimal("0"))
    line_amount: decimal.Decimal


class PurchaseOrderLineDTO(BaseModel):
    po_line_id: int
    po_id: int
    item_code: Optional[str]
    description: str
    quantity: decimal.Decimal
    unit_price: decimal.Decimal
    tax_amount: decimal.Decimal
    line_amount: decimal.Decimal


# =====================================================
# Purchase Order
# =====================================================


class PurchaseOrderCreateRequest(BaseModel):
    po_number: str
    vendor_id: int
    status_id: Optional[int] = None
    po_date: Optional[datetime.date] = None
    expected_delivery_date: Optional[datetime.date] = None
    currency_id: Optional[int] = None
    subtotal: Optional[decimal.Decimal] = None
    tax_amount: Optional[decimal.Decimal] = None
    total_amount: Optional[decimal.Decimal] = None
    lines: List[PurchaseOrderLineRequest] = Field(default_factory=list)


class PurchaseOrderUpdateRequest(BaseModel):
    po_number: Optional[str] = None
    vendor_id: Optional[int] = None
    status_id: Optional[int] = None
    po_date: Optional[datetime.date] = None
    expected_delivery_date: Optional[datetime.date] = None
    currency_id: Optional[int] = None
    subtotal: Optional[decimal.Decimal] = None
    tax_amount: Optional[decimal.Decimal] = None
    total_amount: Optional[decimal.Decimal] = None
    # When provided (including an empty list), replaces the purchase
    # order's full set of line items. Omit to leave existing lines untouched.
    lines: Optional[List[PurchaseOrderLineRequest]] = None


class PurchaseOrderStatusUpdateRequest(BaseModel):
    status_id: int


class PurchaseOrderResponse(BaseModel):
    po_id: int
    message: str


class DeletePurchaseOrderResponse(BaseModel):
    message: str


class UploadPurchaseOrderDocumentResponse(BaseModel):
    po_id: int
    file_path: str
    message: str


class PurchaseOrderDTO(BaseModel):
    po_id: int
    po_number: str
    vendor_id: int
    created_at: datetime.datetime
    file_path: Optional[str]
    status_id: Optional[int]
    created_by: Optional[str]
    po_date: Optional[datetime.date]
    expected_delivery_date: Optional[datetime.date]
    currency_id: Optional[int]
    subtotal: Optional[decimal.Decimal]
    tax_amount: Optional[decimal.Decimal]
    total_amount: Optional[decimal.Decimal]
    # Field names match the PurchaseOrder ORM relationship attributes
    # (purchase_order_line/goods_receipt/invoice) so FastAPI can populate
    # them directly from the model instance.
    purchase_order_line: List[PurchaseOrderLineDTO] = Field(default_factory=list)
    goods_receipt: List[GoodsReceiptSummaryDTO] = Field(default_factory=list)
    invoice: List[InvoiceSummaryDTO] = Field(default_factory=list)
