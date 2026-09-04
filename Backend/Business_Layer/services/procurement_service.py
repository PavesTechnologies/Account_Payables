# Backend/Business_Layer/services/procurement_service.py
import datetime
import uuid
from typing import List, Optional

from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.dao.procurement_dao import ProcurementDAO
from Backend.Data_Access_Layer.dao.purchase_order_dao import PurchaseOrderDAO
from Backend.Data_Access_Layer.dao.rfq_dao import RFQDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.purchase import (
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Quotation,
)
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from Backend.Business_Layer.services.rfq_service import RFQ_STATUS_MODULE

PR_STATUS_MODULE = "PURCHASE_REQUISITION"
QUOTATION_STATUS_MODULE = "QUOTATION"
PO_STATUS_MODULE = "PO"

PR_TRANSITIONS = {
    "DRAFT": {"PENDING_APPROVAL", "CANCELLED"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED", "RETURNED", "CANCELLED"},
    "RETURNED": {"PENDING_APPROVAL"},
    "APPROVED": {"VENDOR_SELECTION", "CANCELLED"},
    "VENDOR_SELECTION": {"PO_GENERATED", "CANCELLED"},
    "PO_GENERATED": set(),
    "REJECTED": set(),
    "CANCELLED": set(),
}

PR_HISTORY_TABLE = "purchase_requisition"

VALID_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}


class ProcurementService:
    def __init__(self, db):
        self.db = db
        self.procurement_dao = ProcurementDAO(db)
        self.master_dao = MasterDAO(db)
        self.po_dao = PurchaseOrderDAO(db)
        self.rfq_dao = RFQDAO(db)

    # =========================================================
    # Purchase Requisition
    # =========================================================

    def create_purchase_requisition(self, data, user_id: str) -> PurchaseRequisition:
        self._validate_department_and_category(data.department_id, data.purchase_category_id)
        priority = self._validate_priority(data.priority)
        draft_status = self._require_status(PR_STATUS_MODULE, "DRAFT")

        pr = PurchaseRequisition(
            pr_number=f"PR-TMP-{uuid.uuid4().hex[:12]}",
            department_id=data.department_id,
            purchase_category_id=data.purchase_category_id,
            status_id=draft_status.status_id,
            priority=priority,
            estimated_total=0,
            created_by=user_id,
            required_by=data.required_by,
            delivery_location=data.delivery_location,
            justification=data.justification,
        )
        self.procurement_dao.create_purchase_requisition(pr)
        pr.pr_number = f"PR-{pr.id:06d}"

        estimated_total = 0
        for line_data in data.lines:
            line = self._build_line(pr.id, line_data)
            self.procurement_dao.create_purchase_requisition_line(line)
            if line.estimated_amount is not None:
                estimated_total += line.estimated_amount
        pr.estimated_total = estimated_total

        self.db.commit()
        self.db.refresh(pr)
        return pr

    def get_purchase_requisition(self, pr_id: int) -> PurchaseRequisition:
        return self._require_pr(pr_id)

    def list_purchase_requisitions(
        self,
        department_id: Optional[int] = None,
        purchase_category_id: Optional[int] = None,
        status_id: Optional[int] = None,
        created_by: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PurchaseRequisition]:

        return self.procurement_dao.get_all_purchase_requisitions(
            department_id, purchase_category_id, status_id, created_by, search, skip, limit
        )

    def list_pending_approval(self, department_id: Optional[int] = None) -> List[PurchaseRequisition]:
        return self.procurement_dao.get_pending_approval_requisitions(department_id)

    def update_purchase_requisition(self, pr_id: int, data, user_id: Optional[str] = None) -> PurchaseRequisition:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"DRAFT", "RETURNED"}, "updated")
        if pr.status.status_code == "RETURNED":
            self._require_requester(
                pr, user_id, "Only the purchase requisition's requester can edit it while it is RETURNED"
            )

        if data.department_id is not None or data.purchase_category_id is not None:
            department_id = data.department_id if data.department_id is not None else pr.department_id
            purchase_category_id = (
                data.purchase_category_id if data.purchase_category_id is not None else pr.purchase_category_id
            )
            self._validate_department_and_category(department_id, purchase_category_id)
            pr.department_id = department_id
            pr.purchase_category_id = purchase_category_id

        if data.priority is not None:
            pr.priority = self._validate_priority(data.priority)
        if data.required_by is not None:
            pr.required_by = data.required_by
        if data.delivery_location is not None:
            pr.delivery_location = data.delivery_location
        if data.justification is not None:
            pr.justification = data.justification

        self.db.commit()
        self.db.refresh(pr)
        return pr

    def delete_purchase_requisition(self, pr_id: int) -> None:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"DRAFT"}, "deleted")
        self.procurement_dao.delete_purchase_requisition(pr)
        self.db.commit()

    def submit_purchase_requisition(self, pr_id: int) -> PurchaseRequisition:
        pr = self._require_pr(pr_id)
        lines = self.procurement_dao.get_lines_by_pr_id(pr_id)
        if not lines:
            raise ValueError(
                "Purchase requisition must have at least one line before it can be submitted"
            )
        self._transition_pr(pr, "PENDING_APPROVAL")
        self.db.commit()
        self.db.refresh(pr)
        return pr

    def cancel_purchase_requisition(self, pr_id: int) -> PurchaseRequisition:
        pr = self._require_pr(pr_id)
        self._transition_pr(pr, "CANCELLED")
        self.db.commit()
        self.db.refresh(pr)
        return pr

    # =========================================================
    # Purchase Requisition Line
    # =========================================================

    def add_line(self, pr_id: int, line_data, user_id: Optional[str] = None) -> PurchaseRequisitionLine:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"DRAFT", "RETURNED"}, "modified")
        if pr.status.status_code == "RETURNED":
            self._require_requester(
                pr, user_id, "Only the purchase requisition's requester can add a line while it is RETURNED"
            )

        line = self._build_line(pr_id, line_data)
        self.procurement_dao.create_purchase_requisition_line(line)
        self._recalculate_estimated_total(pr)

        self.db.commit()
        self.db.refresh(line)
        return line

    def update_line(
        self, pr_id: int, line_id: int, line_data, user_id: Optional[str] = None
    ) -> PurchaseRequisitionLine:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"DRAFT", "RETURNED"}, "modified")
        if pr.status.status_code == "RETURNED":
            self._require_requester(
                pr, user_id, "Only the purchase requisition's requester can edit a line while it is RETURNED"
            )

        line = self.procurement_dao.get_line_by_id(line_id)
        if line is None or line.pr_id != pr_id:
            raise ValueError("Purchase requisition line not found")

        validated = self._build_line(pr_id, line_data)
        line.item_name = validated.item_name
        line.description = validated.description
        line.quantity = validated.quantity
        line.uom = validated.uom
        line.estimated_unit_price = validated.estimated_unit_price
        line.estimated_amount = validated.estimated_amount

        self._recalculate_estimated_total(pr)

        self.db.commit()
        self.db.refresh(line)
        return line

    def delete_line(self, pr_id: int, line_id: int, user_id: Optional[str] = None) -> None:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"DRAFT", "RETURNED"}, "modified")
        if pr.status.status_code == "RETURNED":
            self._require_requester(
                pr, user_id, "Only the purchase requisition's requester can delete a line while it is RETURNED"
            )

        line = self.procurement_dao.get_line_by_id(line_id)
        if line is None or line.pr_id != pr_id:
            raise ValueError("Purchase requisition line not found")

        self.procurement_dao.delete_purchase_requisition_line(line)
        self._recalculate_estimated_total(pr)
        self.db.commit()

    # =========================================================
    # PR Approval
    # =========================================================

    def approve_purchase_requisition(
        self, pr_id: int, user_id: str, comment: Optional[str]
    ) -> PurchaseRequisition:

        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"PENDING_APPROVAL"}, "approved")

        self._transition_pr(pr, "APPROVED")
        pr.approved_by = user_id
        pr.approved_at = datetime.datetime.now(datetime.timezone.utc)
        pr.approval_comment = comment
        self._record_pr_history(pr_id, "APPROVED", user_id, comment)

        self.db.commit()
        self.db.refresh(pr)
        return pr

    def reject_purchase_requisition(
        self, pr_id: int, user_id: str, comment: str
    ) -> PurchaseRequisition:

        if not comment or not comment.strip():
            raise ValueError("A comment is required to reject a purchase requisition")

        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"PENDING_APPROVAL"}, "rejected")

        self._transition_pr(pr, "REJECTED")
        pr.approved_by = user_id
        pr.approved_at = datetime.datetime.now(datetime.timezone.utc)
        pr.approval_comment = comment.strip()
        self._record_pr_history(pr_id, "REJECTED", user_id, comment.strip())

        self.db.commit()
        self.db.refresh(pr)
        return pr

    def return_for_clarification(
        self, pr_id: int, user_id: str, reason: str
    ) -> PurchaseRequisition:

        if not reason or not reason.strip():
            raise ValueError("A reason is required to return a purchase requisition for clarification")
        reason = reason.strip()

        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"PENDING_APPROVAL"}, "returned for clarification")

        self._transition_pr(pr, "RETURNED")
        pr.approved_by = user_id
        pr.approved_at = datetime.datetime.now(datetime.timezone.utc)
        pr.approval_comment = reason
        self._record_pr_history(pr_id, "RETURNED", user_id, reason)

        self.db.commit()
        self.db.refresh(pr)
        return pr

    def resubmit_pr(self, pr_id: int, user_id: str) -> PurchaseRequisition:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"RETURNED"}, "resubmitted")
        self._require_requester(pr, user_id, "Only the purchase requisition's requester can resubmit it")

        lines = self.procurement_dao.get_lines_by_pr_id(pr_id)
        if not lines:
            raise ValueError(
                "Purchase requisition must have at least one line before it can be resubmitted"
            )

        previous_return_reason = pr.approval_comment

        self._transition_pr(pr, "PENDING_APPROVAL")
        pr.approved_by = None
        pr.approved_at = None
        pr.approval_comment = None
        self._record_pr_history(pr_id, "RESUBMITTED", user_id, previous_return_reason)

        self.db.commit()
        self.db.refresh(pr)
        return pr

    # =========================================================
    # RFQ or Catalog decision
    # =========================================================

    def record_sourcing_decision(self, pr_id: int, sourcing_type: str) -> PurchaseRequisition:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"APPROVED", "VENDOR_SELECTION"}, "given a sourcing decision")

        sourcing_type = (sourcing_type or "").upper()
        if sourcing_type not in {"CATALOG", "RFQ"}:
            raise ValueError("sourcing_type must be one of ['CATALOG', 'RFQ']")
        if pr.sourcing_type is not None and pr.sourcing_type != sourcing_type:
            raise ValueError(
                f"Purchase requisition sourcing decision is already recorded as {pr.sourcing_type}"
            )

        pr.sourcing_type = sourcing_type

        self.db.commit()
        self.db.refresh(pr)
        return pr

    # =========================================================
    # Quotation
    # =========================================================

    def create_quotation(
        self,
        pr_id: int,
        vendor_id: int,
        file_url: str,
        quotation_number: Optional[str],
        quotation_date,
        valid_until,
        total_amount,
        user_id: str,
        rfq_id: Optional[int] = None,
        delivery_days: Optional[int] = None,
        payment_terms: Optional[str] = None,
    ) -> Quotation:

        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"APPROVED", "VENDOR_SELECTION"}, "given a quotation")
        self._require_active_vendor(vendor_id)

        rfq = None
        if rfq_id is not None:
            rfq = self.rfq_dao.get_rfq_by_id(rfq_id)
            if rfq is None:
                raise ValueError("RFQ not found")
            if rfq.pr_id != pr_id:
                raise ValueError("RFQ does not belong to this purchase requisition")
            if rfq.status.status_code == "CLOSED":
                raise ValueError("RFQ is closed and cannot accept new quotations")
            if not self.rfq_dao.is_vendor_invited(rfq_id, vendor_id):
                raise ValueError("Vendor was not invited to this RFQ")

        received_status = self._require_status(QUOTATION_STATUS_MODULE, "RECEIVED")

        quotation = Quotation(
            pr_id=pr_id,
            vendor_id=vendor_id,
            file_url=file_url,
            status_id=received_status.status_id,
            created_by=user_id,
            quotation_number=quotation_number,
            quotation_date=quotation_date,
            valid_until=valid_until,
            total_amount=total_amount,
            rfq_id=rfq_id,
            delivery_days=delivery_days,
            payment_terms=payment_terms,
        )
        self.procurement_dao.create_quotation(quotation)

        if pr.status.status_code == "APPROVED":
            self._transition_pr(pr, "VENDOR_SELECTION")

        if rfq is not None and rfq.status.status_code == "SENT":
            response_received_status = self._require_rfq_status_row("RESPONSE_RECEIVED")
            rfq.status_id = response_received_status.status_id

        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def get_quotation(self, quotation_id: int) -> Quotation:
        quotation = self.procurement_dao.get_quotation_by_id(quotation_id)
        if quotation is None:
            raise ValueError("Quotation not found")
        return quotation

    def list_quotations(self, pr_id: int) -> List[Quotation]:
        self._require_pr(pr_id)
        return self.procurement_dao.get_quotations_by_pr_id(pr_id)

    def delete_quotation(self, quotation_id: int) -> None:
        quotation = self.get_quotation(quotation_id)
        pr = self._require_pr(quotation.pr_id)

        if quotation.status.status_code != "RECEIVED" or pr.status.status_code != "VENDOR_SELECTION":
            raise ValueError(
                "Only a RECEIVED quotation on a purchase requisition still in VENDOR_SELECTION can be deleted"
            )

        self.procurement_dao.delete_quotation(quotation)
        self.db.commit()

    # =========================================================
    # Vendor Selection
    # =========================================================

    def select_vendor(
        self, pr_id: int, quotation_id: int, reason: Optional[str] = None
    ) -> PurchaseRequisition:

        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"VENDOR_SELECTION"}, "used to select a vendor")

        quotation = self.get_quotation(quotation_id)
        if quotation.pr_id != pr_id:
            raise ValueError("Quotation does not belong to this purchase requisition")
        if quotation.status.status_code != "RECEIVED":
            raise ValueError("Only a RECEIVED quotation can be selected")

        if quotation.rfq_id is not None:
            rfq = self.rfq_dao.get_rfq_by_id(quotation.rfq_id)
            if rfq is not None and rfq.status.status_code != "CLOSED":
                raise ValueError("RFQ must be closed before a vendor can be selected")

        self._require_active_vendor(quotation.vendor_id)

        selected_status = self._require_status(QUOTATION_STATUS_MODULE, "SELECTED")
        rejected_status = self._require_status(QUOTATION_STATUS_MODULE, "REJECTED")

        for sibling in self.procurement_dao.get_quotations_by_pr_id(pr_id):
            if sibling.id == quotation.id:
                sibling.status_id = selected_status.status_id
            elif sibling.status.status_code == "RECEIVED":
                sibling.status_id = rejected_status.status_id

        pr.selected_vendor_id = quotation.vendor_id
        pr.selected_quotation_id = quotation.id
        if reason is not None:
            pr.selection_reason = reason

        self.db.commit()
        self.db.refresh(pr)
        return pr

    # =========================================================
    # Purchase Order Generation
    # =========================================================

    def generate_purchase_order(self, pr_id: int, user_id: str) -> PurchaseOrder:
        pr = self._require_pr(pr_id)
        self._require_pr_status(pr, {"VENDOR_SELECTION"}, "used to generate a purchase order")

        if pr.selected_vendor_id is None or pr.selected_quotation_id is None:
            raise ValueError(
                "Purchase requisition must have a selected vendor and quotation before generating a purchase order"
            )

        po_status = self.po_dao.get_status_by_module_code(PO_STATUS_MODULE, "OPEN")
        if po_status is None:
            raise ValueError("PO status 'OPEN' is not configured")

        lines = self.procurement_dao.get_lines_by_pr_id(pr_id)

        purchase_order = PurchaseOrder(
            po_number=f"PO-TMP-{uuid.uuid4().hex[:12]}",
            pr_id=pr.id,
            quotation_id=pr.selected_quotation_id,
            vendor_id=pr.selected_vendor_id,
            status_id=po_status.status_id,
            created_by=user_id,
            subtotal=pr.estimated_total or 0,
            tax_amount=0,
            total_amount=pr.estimated_total or 0,
        )
        self.po_dao.create_purchase_order(purchase_order)
        purchase_order.po_number = f"PO-{purchase_order.po_id:06d}"

        for pr_line in lines:
            unit_price = pr_line.estimated_unit_price or 0
            line_total = (
                pr_line.estimated_amount
                if pr_line.estimated_amount is not None
                else unit_price * pr_line.quantity
            )
            self.po_dao.create_purchase_order_line(
                PurchaseOrderLine(
                    po_id=purchase_order.po_id,
                    item_name=pr_line.item_name,
                    description=pr_line.description,
                    uom=pr_line.uom,
                    quantity=pr_line.quantity,
                    unit_price=unit_price,
                    tax_rate=0,
                    tax_amount=0,
                    total_amount=line_total,
                    pr_line_id=pr_line.id,
                )
            )

        self._transition_pr(pr, "PO_GENERATED")

        self.db.commit()
        self.db.refresh(purchase_order)
        return purchase_order

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_pr(self, pr_id: int) -> PurchaseRequisition:
        pr = self.procurement_dao.get_purchase_requisition_by_id(pr_id)
        if pr is None:
            raise ValueError("Purchase requisition not found")
        return pr

    @staticmethod
    def _require_pr_status(pr: PurchaseRequisition, allowed_codes: set, action_description: str) -> None:
        if pr.status.status_code not in allowed_codes:
            raise ValueError(
                f"Purchase requisition cannot be {action_description} while in status {pr.status.status_code}"
            )

    def _transition_pr(self, pr: PurchaseRequisition, target_code: str) -> None:
        current_code = pr.status.status_code
        allowed = PR_TRANSITIONS.get(current_code, set())
        if target_code not in allowed:
            raise ValueError(
                f"Purchase requisition cannot move from {current_code} to {target_code}"
            )
        target_status = self._require_status(PR_STATUS_MODULE, target_code)
        pr.status_id = target_status.status_id

    def _require_status(self, module_name: str, status_code: str):
        status = self.procurement_dao.get_status_by_module_code(module_name, status_code)
        if status is None:
            raise ValueError(f"Status '{status_code}' is not configured for module '{module_name}'")
        return status

    @staticmethod
    def _require_requester(pr: PurchaseRequisition, user_id: Optional[str], message: str) -> None:
        # IDs may arrive as different types depending on their source (JWT
        # claim vs. DB column), so compare as strings rather than requiring
        # an exact type match.
        if str(pr.created_by) != str(user_id):
            raise ValueError(message)

    def _require_rfq_status_row(self, status_code: str):
        status = self.rfq_dao.get_status_by_module_code(RFQ_STATUS_MODULE, status_code)
        if status is None:
            raise ValueError(f"Status '{status_code}' is not configured for module '{RFQ_STATUS_MODULE}'")
        return status

    def _record_pr_history(
        self, pr_id: int, action: str, user_id: str, comment: Optional[str] = None
    ) -> None:
        self.procurement_dao.create_audit_log(
            AuditLog(
                table_name=PR_HISTORY_TABLE,
                record_id=pr_id,
                action=action,
                changed_by=user_id,
                new_values={"comment": comment} if comment is not None else None,
            )
        )

    def _require_active_vendor(self, vendor_id: int):
        vendor = self.procurement_dao.get_vendor_by_id(vendor_id)
        if vendor is None:
            raise ValueError("Vendor not found for the given vendor_id")
        if vendor.status is None or vendor.status.status_code != "ACTIVE":
            raise ValueError("Vendor must be ACTIVE to be used in procurement")
        return vendor

    def _validate_department_and_category(self, department_id: int, purchase_category_id: int) -> None:
        department = self.master_dao.get_department_by_id(department_id)
        if department is None:
            raise ValueError("Department not found for the given department_id")
        if not department.is_active:
            raise ValueError("Department is not active")

        purchase_category = self.master_dao.get_purchase_category_by_id(purchase_category_id)
        if purchase_category is None:
            raise ValueError("Purchase category not found for the given purchase_category_id")
        if not purchase_category.is_active:
            raise ValueError("Purchase category is not active")

        allowed_category_ids = self.procurement_dao.get_allowed_category_ids_for_department(department_id)
        if allowed_category_ids and purchase_category_id not in allowed_category_ids:
            raise ValueError("This purchase category is not allowed for the selected department")

    @staticmethod
    def _validate_priority(priority: str) -> str:
        priority = (priority or "NORMAL").upper()
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return priority

    @staticmethod
    def _build_line(pr_id: int, line_data) -> PurchaseRequisitionLine:
        item_name = line_data.item_name.strip() if line_data.item_name else ""
        if not item_name:
            raise ValueError("item_name is required for a purchase requisition line")
        if line_data.quantity <= 0:
            raise ValueError("quantity must be greater than 0 for a purchase requisition line")
        if line_data.estimated_unit_price is not None and line_data.estimated_unit_price < 0:
            raise ValueError("estimated_unit_price cannot be negative")
        if line_data.estimated_amount is not None and line_data.estimated_amount < 0:
            raise ValueError("estimated_amount cannot be negative")

        return PurchaseRequisitionLine(
            pr_id=pr_id,
            item_name=item_name,
            description=line_data.description,
            quantity=line_data.quantity,
            uom=line_data.uom,
            estimated_unit_price=line_data.estimated_unit_price,
            estimated_amount=line_data.estimated_amount,
        )

    def _recalculate_estimated_total(self, pr: PurchaseRequisition) -> None:
        lines = self.procurement_dao.get_lines_by_pr_id(pr.id)
        pr.estimated_total = sum((line.estimated_amount or 0) for line in lines)
