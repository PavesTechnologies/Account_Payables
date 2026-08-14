# Backend/Data_Access_Layer/dao/goods_receipt_dao.py
from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt, GoodsReceiptLine


class GoodsReceiptDAO:
    def __init__(self, db):
        self.db = db

    def get_all_goods_receipts(
        self,
        vendor_id: Optional[int] = None,
        po_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[GoodsReceipt]:

        query = self.db.query(GoodsReceipt).options(
            selectinload(GoodsReceipt.goods_receipt_line)
        )

        if vendor_id is not None:
            query = query.filter(GoodsReceipt.vendor_id == vendor_id)
        if po_id is not None:
            query = query.filter(GoodsReceipt.po_id == po_id)

        return (
            query.order_by(GoodsReceipt.grn_id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_goods_receipt_by_id(self, grn_id: int) -> Optional[GoodsReceipt]:
        return (
            self.db.query(GoodsReceipt)
            .options(selectinload(GoodsReceipt.goods_receipt_line))
            .filter(GoodsReceipt.grn_id == grn_id)
            .first()
        )

    def get_lines_by_grn_id(self, grn_id: int) -> List[GoodsReceiptLine]:
        return (
            self.db.query(GoodsReceiptLine)
            .filter(GoodsReceiptLine.grn_id == grn_id)
            .order_by(GoodsReceiptLine.grn_line_id.asc())
            .all()
        )

    def get_lines_by_po_id(self, po_id: int) -> List[GoodsReceiptLine]:
        """All GRN lines received against any GRN linked to this PO — used by matching."""
        return (
            self.db.query(GoodsReceiptLine)
            .join(GoodsReceipt, GoodsReceiptLine.grn_id == GoodsReceipt.grn_id)
            .filter(GoodsReceipt.po_id == po_id)
            .all()
        )
