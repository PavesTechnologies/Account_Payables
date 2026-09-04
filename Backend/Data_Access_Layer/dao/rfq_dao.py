# Backend/Data_Access_Layer/dao/rfq_dao.py

from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.rfq import RFQ, RFQVendor
from Backend.Data_Access_Layer.models.vendor import Vendor


class RFQDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # RFQ
    # =====================================================

    def create_rfq(self, rfq: RFQ) -> RFQ:
        self.db.add(rfq)
        self.db.flush()
        return rfq

    def get_rfq_by_id(self, rfq_id: int) -> Optional[RFQ]:
        return (
            self.db.query(RFQ)
            .options(
                selectinload(RFQ.rfq_vendor),
                selectinload(RFQ.quotation),
                selectinload(RFQ.status),
            )
            .filter(RFQ.id == rfq_id)
            .first()
        )

    def get_all_rfqs(
        self,
        pr_id: Optional[int] = None,
        status_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RFQ]:

        query = self.db.query(RFQ).options(
            selectinload(RFQ.rfq_vendor),
            selectinload(RFQ.quotation),
            selectinload(RFQ.status),
        )

        if pr_id is not None:
            query = query.filter(RFQ.pr_id == pr_id)
        if status_id is not None:
            query = query.filter(RFQ.status_id == status_id)

        return (
            query.order_by(RFQ.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    # =====================================================
    # RFQ Vendor (invitation)
    # =====================================================

    def create_rfq_vendor(self, rfq_vendor: RFQVendor) -> RFQVendor:
        self.db.add(rfq_vendor)
        self.db.flush()
        return rfq_vendor

    def get_rfq_vendors(self, rfq_id: int) -> List[RFQVendor]:
        return (
            self.db.query(RFQVendor)
            .options(selectinload(RFQVendor.vendor))
            .filter(RFQVendor.rfq_id == rfq_id)
            .order_by(RFQVendor.id.asc())
            .all()
        )

    def is_vendor_invited(self, rfq_id: int, vendor_id: int) -> bool:
        return (
            self.db.query(RFQVendor.id)
            .filter(RFQVendor.rfq_id == rfq_id, RFQVendor.vendor_id == vendor_id)
            .first()
            is not None
        )

    # =====================================================
    # Related reference lookups (FK / business-rule validation)
    # =====================================================

    def get_vendor_by_id(self, vendor_id: int) -> Optional[Vendor]:
        return (
            self.db.query(Vendor)
            .options(selectinload(Vendor.status))
            .filter(Vendor.vendor_id == vendor_id)
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
