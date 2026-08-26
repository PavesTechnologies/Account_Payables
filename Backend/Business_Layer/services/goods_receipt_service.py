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

# Backend/Business_Layer/services/goods_receipt_service.py
from typing import List, Optional

from Backend.API_Layer.interface.goods_receipt_interface import (
    GoodsReceiptCreateRequest,
    GoodsReceiptLineRequest,
    GoodsReceiptUpdateRequest,
)
from Backend.API_Layer.utils.s3_utils import upload_to_s3
from Backend.Data_Access_Layer.dao.goods_receipt_dao import GoodsReceiptDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt, GoodsReceiptLine


class GoodsReceiptService:
    def __init__(self, db):
        self.db = db
        self.grn_dao = GoodsReceiptDAO(db)

    # =========================================================
    # Goods Receipt
    # =========================================================

    def create_goods_receipt(
        self,
        data: GoodsReceiptCreateRequest,
        user_id: str,
    ) -> GoodsReceipt:

        if not self.grn_dao.vendor_exists(data.vendor_id):
            raise ValueError("Vendor not found for the given vendor_id")

        if data.po_id is not None:
            self._require_po_belongs_to_vendor(data.po_id, data.vendor_id)

        goods_receipt = GoodsReceipt(
            vendor_id=data.vendor_id,
            po_id=data.po_id,
            created_by=user_id,
            grn_number=data.grn_number,
            receipt_date=data.receipt_date,
        )

        self.grn_dao.create_goods_receipt(goods_receipt)
        self._create_lines(goods_receipt.grn_id, data.po_id, data.lines)

        self._write_audit(
            record_id=goods_receipt.grn_id,
            action="CREATE",
            changed_by=user_id,
            new_values=self._snapshot(goods_receipt),
        )

        self.db.commit()
        self.db.refresh(goods_receipt)

        return goods_receipt

    def get_goods_receipt(self, grn_id: int) -> GoodsReceipt:
        goods_receipt = self.grn_dao.get_goods_receipt_by_id(grn_id)

        if goods_receipt is None:
            raise ValueError("Goods receipt not found")

        return goods_receipt

    def list_goods_receipts(
        self,
        vendor_id: Optional[int] = None,
        po_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[GoodsReceipt]:

        return self.grn_dao.get_all_goods_receipts(vendor_id, po_id, skip, limit)

    def update_goods_receipt(
        self,
        grn_id: int,
        data: GoodsReceiptUpdateRequest,
        user_id: str,
    ) -> GoodsReceipt:

        goods_receipt = self._require_goods_receipt(grn_id)
        before = self._snapshot(goods_receipt)

        target_vendor_id = (
            data.vendor_id if data.vendor_id is not None else goods_receipt.vendor_id
        )
        target_po_id = data.po_id if data.po_id is not None else goods_receipt.po_id

        if data.vendor_id is not None:
            if not self.grn_dao.vendor_exists(data.vendor_id):
                raise ValueError("Vendor not found for the given vendor_id")

        if target_po_id is not None and (data.vendor_id is not None or data.po_id is not None):
            self._require_po_belongs_to_vendor(target_po_id, target_vendor_id)

        goods_receipt.vendor_id = target_vendor_id
        goods_receipt.po_id = target_po_id

        if data.grn_number is not None:
            goods_receipt.grn_number = data.grn_number

        if data.receipt_date is not None:
            goods_receipt.receipt_date = data.receipt_date

        if data.lines is not None:
            self.grn_dao.delete_goods_receipt_lines(grn_id)
            self._create_lines(grn_id, target_po_id, data.lines)

        after = self._snapshot(goods_receipt)
        changed = {key: value for key, value in after.items() if before.get(key) != value}

        if changed or data.lines is not None:
            self._write_audit(
                record_id=goods_receipt.grn_id,
                action="UPDATE",
                changed_by=user_id,
                old_values={key: before.get(key) for key in changed},
                new_values=changed,
            )

        self.db.commit()
        self.db.refresh(goods_receipt)

        return goods_receipt

    def delete_goods_receipt(self, grn_id: int, user_id: str) -> None:
        goods_receipt = self._require_goods_receipt(grn_id)

        self._write_audit(
            record_id=goods_receipt.grn_id,
            action="DELETE",
            changed_by=user_id,
            old_values=self._snapshot(goods_receipt),
        )

        self.grn_dao.delete_goods_receipt(goods_receipt)
        self.db.commit()

    # =========================================================
    # Goods Receipt Document
    # =========================================================

    def upload_document(
        self,
        grn_id: int,
        filename: str,
        content: bytes,
        content_type: Optional[str],
        user_id: str,
    ) -> GoodsReceipt:

        goods_receipt = self._require_goods_receipt(grn_id)
        before = self._snapshot(goods_receipt)

        upload_result = upload_to_s3(filename, content, content_type)
        goods_receipt.file_path = upload_result["filepath"]

        self._write_audit(
            record_id=goods_receipt.grn_id,
            action="UPDATE",
            changed_by=user_id,
            old_values={"file_path": before.get("file_path")},
            new_values={"file_path": goods_receipt.file_path},
        )

        self.db.commit()
        self.db.refresh(goods_receipt)

        return goods_receipt

    def get_document_path(self, grn_id: int) -> str:
        goods_receipt = self._require_goods_receipt(grn_id)

        if not goods_receipt.file_path:
            raise ValueError("Goods receipt has no document uploaded")

        return goods_receipt.file_path

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_goods_receipt(self, grn_id: int) -> GoodsReceipt:
        goods_receipt = self.grn_dao.get_goods_receipt_by_id(grn_id)
        if goods_receipt is None:
            raise ValueError("Goods receipt not found")
        return goods_receipt

    def _require_po_belongs_to_vendor(self, po_id: int, vendor_id: int) -> None:
        purchase_order = self.grn_dao.get_purchase_order_by_id(po_id)
        if purchase_order is None:
            raise ValueError("Purchase order not found for the given po_id")
        if purchase_order.vendor_id != vendor_id:
            raise ValueError("The selected po_id does not belong to the selected vendor_id")

    def _create_lines(
        self,
        grn_id: int,
        po_id: Optional[int],
        lines: List[GoodsReceiptLineRequest],
    ) -> None:

        for line_data in lines:
            description = self._validate_line(line_data)

            if line_data.po_line_id is not None:
                if po_id is None:
                    raise ValueError(
                        "po_line_id requires the goods receipt to reference a po_id"
                    )
                po_line = self.grn_dao.get_purchase_order_line_by_id(line_data.po_line_id)
                if po_line is None:
                    raise ValueError(
                        "Purchase order line not found for the given po_line_id"
                    )
                if po_line.po_id != po_id:
                    raise ValueError(
                        "The selected po_line_id does not belong to the goods receipt's po_id"
                    )

            self.grn_dao.create_goods_receipt_line(
                GoodsReceiptLine(
                    grn_id=grn_id,
                    po_line_id=line_data.po_line_id,
                    item_code=line_data.item_code,
                    description=description,
                    received_quantity=line_data.received_quantity,
                )
            )

    @staticmethod
    def _validate_line(line_data: GoodsReceiptLineRequest) -> str:
        if not line_data.description.strip():
            raise ValueError("description is required for a goods receipt line")
        if line_data.received_quantity <= 0:
            raise ValueError(
                "received_quantity must be greater than 0 for a goods receipt line"
            )

        return line_data.description.strip()

    @staticmethod
    def _snapshot(goods_receipt: GoodsReceipt) -> dict:
        return {
            "vendor_id": goods_receipt.vendor_id,
            "po_id": goods_receipt.po_id,
            "file_path": goods_receipt.file_path,
            "grn_number": goods_receipt.grn_number,
            "receipt_date": (
                str(goods_receipt.receipt_date) if goods_receipt.receipt_date else None
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

        self.grn_dao.create_audit_log(
            AuditLog(
                table_name="goods_receipt",
                record_id=record_id,
                action=action,
                changed_by=changed_by,
                old_values=old_values,
                new_values=new_values,
            )
        )
