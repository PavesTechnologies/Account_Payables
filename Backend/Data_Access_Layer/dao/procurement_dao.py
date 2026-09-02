# Backend/Data_Access_Layer/dao/procurement_dao.py

from typing import List, Optional, Set

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.purchase import (
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Quotation,
    department_purchase_category,
)
from Backend.Data_Access_Layer.models.vendor import Vendor


class ProcurementDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Purchase Requisition
    # =====================================================

    def create_purchase_requisition(self, pr: PurchaseRequisition) -> PurchaseRequisition:
        self.db.add(pr)
        self.db.flush()
        return pr

    def get_purchase_requisition_by_id(self, pr_id: int) -> Optional[PurchaseRequisition]:
        return (
            self.db.query(PurchaseRequisition)
            .options(
                selectinload(PurchaseRequisition.purchase_requisition_line),
                selectinload(PurchaseRequisition.quotation),
                selectinload(PurchaseRequisition.status),
            )
            .filter(PurchaseRequisition.id == pr_id)
            .first()
        )

    def get_all_purchase_requisitions(
        self,
        department_id: Optional[int] = None,
        purchase_category_id: Optional[int] = None,
        status_id: Optional[int] = None,
        created_by: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PurchaseRequisition]:

        query = self.db.query(PurchaseRequisition).options(
            selectinload(PurchaseRequisition.purchase_requisition_line),
            selectinload(PurchaseRequisition.quotation),
            selectinload(PurchaseRequisition.status),
        )

        if department_id is not None:
            query = query.filter(PurchaseRequisition.department_id == department_id)
        if purchase_category_id is not None:
            query = query.filter(PurchaseRequisition.purchase_category_id == purchase_category_id)
        if status_id is not None:
            query = query.filter(PurchaseRequisition.status_id == status_id)
        if created_by is not None:
            query = query.filter(PurchaseRequisition.created_by == created_by)
        if search:
            query = query.filter(PurchaseRequisition.pr_number.ilike(f"%{search}%"))

        return (
            query.order_by(PurchaseRequisition.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_pending_approval_requisitions(
        self,
        department_id: Optional[int] = None,
    ) -> List[PurchaseRequisition]:

        query = (
            self.db.query(PurchaseRequisition)
            .join(StatusMaster, PurchaseRequisition.status_id == StatusMaster.status_id)
            .options(
                selectinload(PurchaseRequisition.purchase_requisition_line),
                selectinload(PurchaseRequisition.status),
            )
            .filter(
                StatusMaster.module_name == "PURCHASE_REQUISITION",
                StatusMaster.status_code == "PENDING_APPROVAL",
            )
        )

        if department_id is not None:
            query = query.filter(PurchaseRequisition.department_id == department_id)

        return query.order_by(PurchaseRequisition.id.asc()).all()

    def delete_purchase_requisition(self, pr: PurchaseRequisition) -> None:
        self.db.delete(pr)
        self.db.flush()

    # =====================================================
    # Purchase Requisition Line
    # =====================================================

    def create_purchase_requisition_line(
        self, line: PurchaseRequisitionLine
    ) -> PurchaseRequisitionLine:
        self.db.add(line)
        self.db.flush()
        return line

    def get_line_by_id(self, line_id: int) -> Optional[PurchaseRequisitionLine]:
        return (
            self.db.query(PurchaseRequisitionLine)
            .filter(PurchaseRequisitionLine.id == line_id)
            .first()
        )

    def get_lines_by_pr_id(self, pr_id: int) -> List[PurchaseRequisitionLine]:
        return (
            self.db.query(PurchaseRequisitionLine)
            .filter(PurchaseRequisitionLine.pr_id == pr_id)
            .order_by(PurchaseRequisitionLine.id.asc())
            .all()
        )

    def delete_purchase_requisition_line(self, line: PurchaseRequisitionLine) -> None:
        self.db.delete(line)
        self.db.flush()

    # =====================================================
    # Quotation
    # =====================================================

    def create_quotation(self, quotation: Quotation) -> Quotation:
        self.db.add(quotation)
        self.db.flush()
        return quotation

    def get_quotation_by_id(self, quotation_id: int) -> Optional[Quotation]:
        return (
            self.db.query(Quotation)
            .filter(Quotation.id == quotation_id)
            .first()
        )

    def get_quotations_by_pr_id(self, pr_id: int) -> List[Quotation]:
        return (
            self.db.query(Quotation)
            .filter(Quotation.pr_id == pr_id)
            .order_by(Quotation.id.asc())
            .all()
        )

    def delete_quotation(self, quotation: Quotation) -> None:
        self.db.delete(quotation)
        self.db.flush()

    # =====================================================
    # Related reference lookups (FK / business-rule validation)
    # =====================================================

    def get_allowed_category_ids_for_department(self, department_id: int) -> Set[int]:
        rows = (
            self.db.query(department_purchase_category.c.purchase_category_id)
            .filter(department_purchase_category.c.department_id == department_id)
            .all()
        )
        return {row[0] for row in rows}

    def get_vendor_by_id(self, vendor_id: int) -> Optional[Vendor]:
        return (
            self.db.query(Vendor)
            .options(selectinload(Vendor.status))
            .filter(Vendor.vendor_id == vendor_id)
            .first()
        )

    def get_status_by_id(self, status_id: int) -> Optional[StatusMaster]:
        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.status_id == status_id)
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
