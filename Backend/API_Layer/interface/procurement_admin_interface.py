# Backend/API_Layer/interface/procurement_admin_interface.py
from typing import List, Optional

from pydantic import BaseModel, model_validator

# =====================================================
# Purchase Requisition cleanup (individual + bulk)
# =====================================================


class PurchaseRequisitionBulkDeleteRequest(BaseModel):
    """Exactly one of: a non-empty ``pr_ids`` list, or ``delete_all: true``.
    An omitted ``pr_ids`` is never taken to mean delete-all."""

    pr_ids: Optional[List[int]] = None
    delete_all: bool = False

    @model_validator(mode="after")
    def _one_scope(self):
        if self.delete_all:
            if self.pr_ids is not None:
                raise ValueError("Send either pr_ids or delete_all, not both")
            return self
        if not self.pr_ids:
            raise ValueError("pr_ids must be a non-empty list (or set delete_all to true)")
        if any(pr_id <= 0 for pr_id in self.pr_ids):
            raise ValueError("pr_ids must be positive integers")
        if len(set(self.pr_ids)) != len(self.pr_ids):
            raise ValueError("pr_ids must not contain duplicates")
        return self


class PurchaseRequisitionCleanupCounts(BaseModel):
    purchase_requisitions: int = 0
    purchase_orders: int = 0
    purchase_requisition_lines: int = 0
    quotations: int = 0
    rfqs: int = 0
    vendor_nda: int = 0
    vendor_onboarding_requests: int = 0
    rfq_vendors: int = 0
    purchase_order_lines: int = 0
    goods_receipts: int = 0
    goods_receipt_lines: int = 0


class PurchaseRequisitionCleanupResponse(BaseModel):
    status: str
    message: str
    deleted_counts: PurchaseRequisitionCleanupCounts


class PurchaseRequisitionBulkCleanupResponse(PurchaseRequisitionCleanupResponse):
    requested_pr_count: int
