# Backend/Business_Layer/services/goods_receipt_service.py
from typing import List, Optional

from Backend.Data_Access_Layer.dao.goods_receipt_dao import GoodsReceiptDAO
from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt, GoodsReceiptLine


class GoodsReceiptService:
    def __init__(self, db):
        self.db = db
        self.grn_dao = GoodsReceiptDAO(db)

    def list_goods_receipts(
        self,
        vendor_id: Optional[int] = None,
        po_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[GoodsReceipt]:
        return self.grn_dao.get_all_goods_receipts(vendor_id, po_id, skip, limit)

    def get_goods_receipt(self, grn_id: int) -> GoodsReceipt:
        grn = self.grn_dao.get_goods_receipt_by_id(grn_id)
        if grn is None:
            raise ValueError("Goods receipt not found")
        return grn

    def get_lines(self, grn_id: int) -> List[GoodsReceiptLine]:
        self.get_goods_receipt(grn_id)
        return self.grn_dao.get_lines_by_grn_id(grn_id)
