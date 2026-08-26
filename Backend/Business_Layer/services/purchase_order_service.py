# Backend/Business_Layer/services/purchase_order_service.py
from typing import List, Optional

from Backend.API_Layer.interface.purchase_order_interface import (
    PurchaseOrderCreateRequest,
    PurchaseOrderLineRequest,
    PurchaseOrderUpdateRequest,
)
from Backend.API_Layer.utils.s3_utils import upload_to_s3
from Backend.Data_Access_Layer.dao.purchase_order_dao import PurchaseOrderDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine

PO_STATUS_MODULE = "PO"
DEFAULT_PO_STATUS_CODE = "OPEN"


class PurchaseOrderService:
    def __init__(self, db):
        self.db = db
        self.po_dao = PurchaseOrderDAO(db)

    # =========================================================
    # Purchase Order
    # =========================================================

    def create_purchase_order(
        self,
        data: PurchaseOrderCreateRequest,
        user_id: str,
    ) -> PurchaseOrder:

        po_number = self._validate_po_number(data.po_number)

        if self.po_dao.po_number_exists(po_number):
            raise ValueError("A purchase order with this po_number already exists")

        if not self.po_dao.vendor_exists(data.vendor_id):
            raise ValueError("Vendor not found for the given vendor_id")

        if data.currency_id is not None and not self.po_dao.currency_exists(data.currency_id):
            raise ValueError("Currency not found for the given currency_id")

        status_id = self._resolve_status_id(data.status_id)

        purchase_order = PurchaseOrder(
            po_number=po_number,
            vendor_id=data.vendor_id,
            status_id=status_id,
            created_by=user_id,
            po_date=data.po_date,
            expected_delivery_date=data.expected_delivery_date,
            currency_id=data.currency_id,
            subtotal=data.subtotal,
            tax_amount=data.tax_amount,
            total_amount=data.total_amount,
        )

        self.po_dao.create_purchase_order(purchase_order)
        self._create_lines(purchase_order.po_id, data.lines)

        self._write_audit(
            record_id=purchase_order.po_id,
            action="CREATE",
            changed_by=user_id,
            new_values=self._snapshot(purchase_order),
        )

        self.db.commit()
        self.db.refresh(purchase_order)

        return purchase_order

    def get_purchase_order(self, po_id: int) -> PurchaseOrder:
        purchase_order = self.po_dao.get_purchase_order_by_id(po_id)

        if purchase_order is None:
            raise ValueError("Purchase order not found")

        return purchase_order

    def list_purchase_orders(
        self,
        vendor_id: Optional[int] = None,
        status_id: Optional[int] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PurchaseOrder]:

        return self.po_dao.get_all_purchase_orders(vendor_id, status_id, search, skip, limit)

    def update_purchase_order(
        self,
        po_id: int,
        data: PurchaseOrderUpdateRequest,
        user_id: str,
    ) -> PurchaseOrder:

        purchase_order = self._require_purchase_order(po_id)
        before = self._snapshot(purchase_order)

        if data.po_number is not None:
            po_number = self._validate_po_number(data.po_number)
            if self.po_dao.po_number_exists(po_number, exclude_po_id=po_id):
                raise ValueError("A purchase order with this po_number already exists")
            purchase_order.po_number = po_number

        if data.vendor_id is not None:
            if not self.po_dao.vendor_exists(data.vendor_id):
                raise ValueError("Vendor not found for the given vendor_id")
            purchase_order.vendor_id = data.vendor_id

        if data.status_id is not None:
            purchase_order.status_id = self._resolve_status_id(data.status_id)

        if data.currency_id is not None:
            if not self.po_dao.currency_exists(data.currency_id):
                raise ValueError("Currency not found for the given currency_id")
            purchase_order.currency_id = data.currency_id

        if data.po_date is not None:
            purchase_order.po_date = data.po_date

        if data.expected_delivery_date is not None:
            purchase_order.expected_delivery_date = data.expected_delivery_date

        if data.subtotal is not None:
            purchase_order.subtotal = data.subtotal

        if data.tax_amount is not None:
            purchase_order.tax_amount = data.tax_amount

        if data.total_amount is not None:
            purchase_order.total_amount = data.total_amount

        if data.lines is not None:
            self.po_dao.delete_purchase_order_lines(po_id)
            self._create_lines(po_id, data.lines)

        after = self._snapshot(purchase_order)
        changed = {key: value for key, value in after.items() if before.get(key) != value}

        if changed or data.lines is not None:
            self._write_audit(
                record_id=purchase_order.po_id,
                action="UPDATE",
                changed_by=user_id,
                old_values={key: before.get(key) for key in changed},
                new_values=changed,
            )

        self.db.commit()
        self.db.refresh(purchase_order)

        return purchase_order

    def change_status(self, po_id: int, status_id: int, user_id: str) -> PurchaseOrder:
        purchase_order = self._require_purchase_order(po_id)

        old_status_id = purchase_order.status_id
        purchase_order.status_id = self._resolve_status_id(status_id)

        self._write_audit(
            record_id=purchase_order.po_id,
            action="STATUS_CHANGE",
            changed_by=user_id,
            old_values={"status_id": old_status_id},
            new_values={"status_id": purchase_order.status_id},
        )

        self.db.commit()
        self.db.refresh(purchase_order)

        return purchase_order

    def delete_purchase_order(self, po_id: int, user_id: str) -> None:
        purchase_order = self._require_purchase_order(po_id)

        self._write_audit(
            record_id=purchase_order.po_id,
            action="DELETE",
            changed_by=user_id,
            old_values=self._snapshot(purchase_order),
        )

        self.po_dao.delete_purchase_order(purchase_order)
        self.db.commit()

    # =========================================================
    # Purchase Order Document
    # =========================================================

    def upload_document(
        self,
        po_id: int,
        filename: str,
        content: bytes,
        content_type: Optional[str],
        user_id: str,
    ) -> PurchaseOrder:

        purchase_order = self._require_purchase_order(po_id)
        before = self._snapshot(purchase_order)

        upload_result = upload_to_s3(filename, content, content_type)
        purchase_order.file_path = upload_result["filepath"]

        self._write_audit(
            record_id=purchase_order.po_id,
            action="UPDATE",
            changed_by=user_id,
            old_values={"file_path": before.get("file_path")},
            new_values={"file_path": purchase_order.file_path},
        )

        self.db.commit()
        self.db.refresh(purchase_order)

        return purchase_order

    def get_document_path(self, po_id: int) -> str:
        purchase_order = self._require_purchase_order(po_id)

        if not purchase_order.file_path:
            raise ValueError("Purchase order has no document uploaded")

        return purchase_order.file_path

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_purchase_order(self, po_id: int) -> PurchaseOrder:
        purchase_order = self.po_dao.get_purchase_order_by_id(po_id)
        if purchase_order is None:
            raise ValueError("Purchase order not found")
        return purchase_order

    def _create_lines(self, po_id: int, lines: List[PurchaseOrderLineRequest]) -> None:
        for line_data in lines:
            description, quantity, unit_price, tax_amount, line_amount = self._validate_line(
                line_data
            )
            self.po_dao.create_purchase_order_line(
                PurchaseOrderLine(
                    po_id=po_id,
                    item_code=line_data.item_code,
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    tax_amount=tax_amount,
                    line_amount=line_amount,
                )
            )

    @staticmethod
    def _validate_line(line_data: PurchaseOrderLineRequest) -> tuple:
        if not line_data.description.strip():
            raise ValueError("description is required for a purchase order line")
        if line_data.quantity <= 0:
            raise ValueError("quantity must be greater than 0 for a purchase order line")
        if line_data.unit_price < 0:
            raise ValueError("unit_price cannot be negative for a purchase order line")
        if line_data.tax_amount < 0:
            raise ValueError("tax_amount cannot be negative for a purchase order line")
        if line_data.line_amount < 0:
            raise ValueError("line_amount cannot be negative for a purchase order line")

        return (
            line_data.description.strip(),
            line_data.quantity,
            line_data.unit_price,
            line_data.tax_amount,
            line_data.line_amount,
        )

    @staticmethod
    def _validate_po_number(po_number: str) -> str:
        if not po_number.strip():
            raise ValueError("po_number is required for a purchase order")
        return po_number.strip()

    def _resolve_status_id(self, status_id: Optional[int]) -> Optional[int]:
        if status_id is not None:
            status = self.po_dao.get_status_by_id(status_id)
            if status is None or status.module_name != PO_STATUS_MODULE:
                raise ValueError(
                    f"status_id must reference a valid {PO_STATUS_MODULE} status"
                )
            return status.status_id

        default_status = self.po_dao.get_status_by_module_code(
            PO_STATUS_MODULE, DEFAULT_PO_STATUS_CODE
        )
        return default_status.status_id if default_status else None

    @staticmethod
    def _snapshot(purchase_order: PurchaseOrder) -> dict:
        return {
            "po_number": purchase_order.po_number,
            "vendor_id": purchase_order.vendor_id,
            "status_id": purchase_order.status_id,
            "file_path": purchase_order.file_path,
            "po_date": str(purchase_order.po_date) if purchase_order.po_date else None,
            "expected_delivery_date": (
                str(purchase_order.expected_delivery_date)
                if purchase_order.expected_delivery_date
                else None
            ),
            "currency_id": purchase_order.currency_id,
            "subtotal": (
                str(purchase_order.subtotal) if purchase_order.subtotal is not None else None
            ),
            "tax_amount": (
                str(purchase_order.tax_amount) if purchase_order.tax_amount is not None else None
            ),
            "total_amount": (
                str(purchase_order.total_amount)
                if purchase_order.total_amount is not None
                else None
            ),
        }

    def _write_audit(
        self,
        record_id: int,
        action: str,
        changed_by: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
    ) -> None:

        self.po_dao.create_audit_log(
            AuditLog(
                table_name="purchase_order",
                record_id=record_id,
                action=action,
                changed_by=changed_by,
                old_values=old_values,
                new_values=new_values,
            )
        )
