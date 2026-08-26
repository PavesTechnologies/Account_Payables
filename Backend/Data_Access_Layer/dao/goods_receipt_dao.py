# Backend/Data_Access_Layer/dao/goods_receipt_dao.py

from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.purchase_order import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from Backend.Data_Access_Layer.models.vendor import Vendor


class GoodsReceiptDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Goods Receipt
    # =====================================================

    def create_goods_receipt(self, goods_receipt: GoodsReceipt) -> GoodsReceipt:
        self.db.add(goods_receipt)
        self.db.flush()
        return goods_receipt

    def get_goods_receipt_by_id(self, grn_id: int) -> Optional[GoodsReceipt]:
        return (
            self.db.query(GoodsReceipt)
            .options(
                selectinload(GoodsReceipt.po),
                selectinload(GoodsReceipt.invoice),
                selectinload(GoodsReceipt.goods_receipt_line),
            )
            .filter(GoodsReceipt.grn_id == grn_id)
            .first()
        )

    def get_all_goods_receipts(
        self,
        vendor_id: Optional[int] = None,
        po_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[GoodsReceipt]:

        query = self.db.query(GoodsReceipt).options(
            selectinload(GoodsReceipt.po),
            selectinload(GoodsReceipt.invoice),
            selectinload(GoodsReceipt.goods_receipt_line),
        )

        if vendor_id is not None:
            query = query.filter(GoodsReceipt.vendor_id == vendor_id)
        if po_id is not None:
            query = query.filter(GoodsReceipt.po_id == po_id)

        return (
            query.order_by(GoodsReceipt.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def delete_goods_receipt(self, goods_receipt: GoodsReceipt) -> None:
        self.db.delete(goods_receipt)
        self.db.flush()

    # =====================================================
    # Goods Receipt Line
    # =====================================================

    def create_goods_receipt_line(self, line: GoodsReceiptLine) -> GoodsReceiptLine:
        self.db.add(line)
        self.db.flush()
        return line

    def delete_goods_receipt_lines(self, grn_id: int) -> None:
        self.db.query(GoodsReceiptLine).filter(
            GoodsReceiptLine.grn_id == grn_id
        ).delete()
        self.db.flush()

    # =====================================================
    # Related reference lookups (FK validation)
    # =====================================================

    def vendor_exists(self, vendor_id: int) -> bool:
        return (
            self.db.query(Vendor.vendor_id)
            .filter(Vendor.vendor_id == vendor_id)
            .first()
            is not None
        )

    def get_purchase_order_by_id(self, po_id: int) -> Optional[PurchaseOrder]:
        return (
            self.db.query(PurchaseOrder)
            .filter(PurchaseOrder.po_id == po_id)
            .first()
        )

    def get_purchase_order_line_by_id(self, po_line_id: int) -> Optional[PurchaseOrderLine]:
        return (
            self.db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.po_line_id == po_line_id)
            .first()
        )

    # =====================================================
    # Audit Log
    # =====================================================

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
