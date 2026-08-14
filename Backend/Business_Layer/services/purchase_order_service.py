# Backend/Business_Layer/services/purchase_order_service.py
from typing import List, Optional

from Backend.Data_Access_Layer.dao.purchase_order_dao import PurchaseOrderDAO
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderService:
    def __init__(self, db):
        self.db = db
        self.po_dao = PurchaseOrderDAO(db)

    def list_purchase_orders(
        self,
        vendor_id: Optional[int] = None,
        status_id: Optional[int] = None,
        po_number: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PurchaseOrder]:
        return self.po_dao.get_all_purchase_orders(vendor_id, status_id, po_number, skip, limit)

    def get_purchase_order(self, po_id: int) -> PurchaseOrder:
        po = self.po_dao.get_purchase_order_by_id(po_id)
        if po is None:
            raise ValueError("Purchase order not found")
        return po

    def get_purchase_order_by_number(self, po_number: str) -> PurchaseOrder:
        po = self.po_dao.get_purchase_order_by_number(po_number)
        if po is None:
            raise ValueError("Purchase order not found")
        return po

    def get_lines(self, po_id: int) -> List[PurchaseOrderLine]:
        self.get_purchase_order(po_id)
        return self.po_dao.get_lines_by_po_id(po_id)
