# Backend/Data_Access_Layer/dao/vendor_onboarding_dao.py

from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.purchase import PurchaseRequisition
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorEngagement
from Backend.Data_Access_Layer.models.vendor_onboarding import VendorOnboardingRequest

VENDOR_STATUS_MODULE = "VENDOR"
VENDOR_STATUS_ACTIVE = "ACTIVE"
PRE_SCREEN_PASS = "PASS"


class VendorOnboardingDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Vendor availability (reuses Vendor + VendorEngagement)
    # =====================================================

    def get_eligible_vendors(
        self,
        department_id: int,
        purchase_category_id: int,
    ) -> List[Vendor]:
        """Active vendors already engaged for this department + purchase
        category with a passed Pre-Screen - i.e. vendors a PR Officer may go
        straight to RFQ with. Department/category come from the PR itself, so
        nothing about them is hardcoded."""

        return (
            self.db.query(Vendor)
            .join(VendorEngagement, VendorEngagement.vendor_id == Vendor.vendor_id)
            .join(StatusMaster, StatusMaster.status_id == Vendor.status_id)
            .filter(
                VendorEngagement.department_id == department_id,
                VendorEngagement.purchase_category_id == purchase_category_id,
                VendorEngagement.pre_screen_status == PRE_SCREEN_PASS,
                StatusMaster.module_name == VENDOR_STATUS_MODULE,
                StatusMaster.status_code == VENDOR_STATUS_ACTIVE,
            )
            .order_by(Vendor.vendor_name.asc())
            .all()
        )

    def get_engagement(
        self,
        vendor_id: int,
        department_id: int,
        purchase_category_id: int,
    ) -> Optional[VendorEngagement]:

        return (
            self.db.query(VendorEngagement)
            .filter(
                VendorEngagement.vendor_id == vendor_id,
                VendorEngagement.department_id == department_id,
                VendorEngagement.purchase_category_id == purchase_category_id,
            )
            .first()
        )

    # =====================================================
    # Purchase Requisition / Vendor lookups (read-only)
    # =====================================================

    def get_pr_by_id(self, pr_id: int) -> Optional[PurchaseRequisition]:
        return (
            self.db.query(PurchaseRequisition)
            .options(selectinload(PurchaseRequisition.status))
            .filter(PurchaseRequisition.id == pr_id)
            .first()
        )

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

    # =====================================================
    # Vendor Onboarding Request
    # =====================================================

    def create_request(self, request: VendorOnboardingRequest) -> VendorOnboardingRequest:
        self.db.add(request)
        self.db.flush()
        return request

    def get_request_by_id(self, request_id: int) -> Optional[VendorOnboardingRequest]:
        return (
            self.db.query(VendorOnboardingRequest)
            .options(selectinload(VendorOnboardingRequest.status))
            .filter(VendorOnboardingRequest.id == request_id)
            .first()
        )

    def get_open_request(
        self,
        pr_id: int,
        department_id: int,
        purchase_category_id: int,
    ) -> Optional[VendorOnboardingRequest]:
        """An onboarding request that has not reached a terminal state. Mirrors
        the partial unique index (WHERE closed_at IS NULL) so the service can
        raise a friendly error before the database has to."""

        return (
            self.db.query(VendorOnboardingRequest)
            .filter(
                VendorOnboardingRequest.pr_id == pr_id,
                VendorOnboardingRequest.department_id == department_id,
                VendorOnboardingRequest.purchase_category_id == purchase_category_id,
                VendorOnboardingRequest.closed_at.is_(None),
            )
            .first()
        )

    def get_open_requests_for_pr(self, pr_id: int) -> List[VendorOnboardingRequest]:
        return (
            self.db.query(VendorOnboardingRequest)
            .options(selectinload(VendorOnboardingRequest.status))
            .filter(
                VendorOnboardingRequest.pr_id == pr_id,
                VendorOnboardingRequest.closed_at.is_(None),
            )
            .all()
        )

    def get_all_requests(
        self,
        pr_id: Optional[int] = None,
        status_id: Optional[int] = None,
        assigned_to: Optional[str] = None,
        vendor_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[VendorOnboardingRequest]:

        query = self.db.query(VendorOnboardingRequest).options(
            selectinload(VendorOnboardingRequest.status)
        )

        if pr_id is not None:
            query = query.filter(VendorOnboardingRequest.pr_id == pr_id)
        if status_id is not None:
            query = query.filter(VendorOnboardingRequest.status_id == status_id)
        if assigned_to is not None:
            query = query.filter(VendorOnboardingRequest.assigned_to == assigned_to)
        if vendor_id is not None:
            query = query.filter(VendorOnboardingRequest.vendor_id == vendor_id)

        return (
            query.order_by(VendorOnboardingRequest.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    # =====================================================
    # Audit Log
    # =====================================================

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
