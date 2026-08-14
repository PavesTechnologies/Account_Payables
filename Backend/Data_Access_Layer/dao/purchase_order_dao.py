# Backend/Data_Access_Layer/dao/purchase_order_dao.py
from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine

PO_STATUS_MODULE = "PO"


class PurchaseOrderDAO:
    def __init__(self, db):
        self.db = db

    def get_all_purchase_orders(
        self,
        vendor_id: Optional[int] = None,
        status_id: Optional[int] = None,
        po_number: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PurchaseOrder]:

        query = self.db.query(PurchaseOrder).options(
            selectinload(PurchaseOrder.purchase_order_line)
        )

        if vendor_id is not None:
            query = query.filter(PurchaseOrder.vendor_id == vendor_id)
        if status_id is not None:
            query = query.filter(PurchaseOrder.status_id == status_id)
        if po_number:
            query = query.filter(PurchaseOrder.po_number.ilike(f"%{po_number}%"))

        return (
            query.order_by(PurchaseOrder.po_id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_purchase_order_by_id(self, po_id: int) -> Optional[PurchaseOrder]:
        return (
            self.db.query(PurchaseOrder)
            .options(selectinload(PurchaseOrder.purchase_order_line))
            .filter(PurchaseOrder.po_id == po_id)
            .first()
        )

    def get_purchase_order_by_number(self, po_number: str) -> Optional[PurchaseOrder]:
        return (
            self.db.query(PurchaseOrder)
            .options(selectinload(PurchaseOrder.purchase_order_line))
            .filter(PurchaseOrder.po_number == po_number)
            .first()
        )

    def get_lines_by_po_id(self, po_id: int) -> List[PurchaseOrderLine]:
        return (
            self.db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.po_id == po_id)
            .order_by(PurchaseOrderLine.po_line_id.asc())
            .all()
        )

    def get_line_by_id(self, po_line_id: int) -> Optional[PurchaseOrderLine]:
        return (
            self.db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.po_line_id == po_line_id)
            .first()
        )

    def get_status_by_module_code(
        self,
        module_name: str,
        status_code: str,
    ) -> Optional[StatusMaster]:

        return (
            self.db.query(StatusMaster)
            .filter(
                StatusMaster.module_name == module_name,
                StatusMaster.status_code == status_code,
            )
            .first()
        )
