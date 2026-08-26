# Backend/Data_Access_Layer/dao/purchase_order_dao.py

from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from Backend.Data_Access_Layer.models.vendor import Vendor
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine

PO_STATUS_MODULE = "PO"


class PurchaseOrderDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Purchase Order
    # =====================================================

    def create_purchase_order(self, purchase_order: PurchaseOrder) -> PurchaseOrder:
        self.db.add(purchase_order)
        self.db.flush()
        return purchase_order

    def get_purchase_order_by_id(self, po_id: int) -> Optional[PurchaseOrder]:
        return (
            self.db.query(PurchaseOrder)
            .options(
                selectinload(PurchaseOrder.purchase_order_line),
                selectinload(PurchaseOrder.goods_receipt),
                selectinload(PurchaseOrder.invoice),
            )
            .filter(PurchaseOrder.po_id == po_id)
            .first()
        )

    def po_number_exists(
        self,
        po_number: str,
        exclude_po_id: Optional[int] = None,
    ) -> bool:

        query = self.db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number == po_number
        )
        if exclude_po_id is not None:
            query = query.filter(PurchaseOrder.po_id != exclude_po_id)

        return query.first() is not None

    def get_all_purchase_orders(
        self,
        vendor_id: Optional[int] = None,
        status_id: Optional[int] = None,
        search: Optional[str] = None,
        po_number: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PurchaseOrder]:

        query = self.db.query(PurchaseOrder).options(
            selectinload(PurchaseOrder.purchase_order_line),
            selectinload(PurchaseOrder.goods_receipt),
            selectinload(PurchaseOrder.invoice),
            selectinload(PurchaseOrder.purchase_order_line)
        )

        if vendor_id is not None:
            query = query.filter(PurchaseOrder.vendor_id == vendor_id)
        if status_id is not None:
            query = query.filter(PurchaseOrder.status_id == status_id)
        if search:
            query = query.filter(PurchaseOrder.po_number.ilike(f"%{search}%"))

        if po_number:
            query = query.filter(PurchaseOrder.po_number == po_number)

        return (
            query.order_by(PurchaseOrder.po_id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def delete_purchase_order(self, purchase_order: PurchaseOrder) -> None:
        self.db.delete(purchase_order)
        self.db.flush()

    # =====================================================
    # Purchase Order Line
    # =====================================================

    def create_purchase_order_line(self, line: PurchaseOrderLine) -> PurchaseOrderLine:
        self.db.add(line)
        self.db.flush()
        return line

    def delete_purchase_order_lines(self, po_id: int) -> None:
        self.db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.po_id == po_id
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

    def currency_exists(self, currency_id: int) -> bool:
        return (
            self.db.query(Currency.currency_id)
            .filter(Currency.currency_id == currency_id)
            .first()
            is not None
        )

    def get_status_by_id(self, status_id: int) -> Optional[StatusMaster]:
        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.status_id == status_id)
            .first()
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

    # =====================================================
    # Audit Log
    # =====================================================

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
