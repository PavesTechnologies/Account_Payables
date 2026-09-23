# Backend/Data_Access_Layer/dao/nda_dao.py

import datetime
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import StatusMaster, SystemConfiguration
from Backend.Data_Access_Layer.models.nda import NdaTemplate, VendorNda
from Backend.Data_Access_Layer.models.purchase import PurchaseRequisition
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorEngagement

NDA_STATUS_MODULE = "NDA"


class NdaDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Status (always by module + code, never by id)
    # =====================================================

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

    def get_status_by_id(self, status_id: int) -> Optional[StatusMaster]:
        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.status_id == status_id)
            .first()
        )

    def get_config_value(self, config_key: str) -> Optional[str]:
        config = (
            self.db.query(SystemConfiguration)
            .filter(SystemConfiguration.config_key == config_key)
            .first()
        )
        return config.config_value if config is not None else None

    # =====================================================
    # Reference lookups
    # =====================================================

    def get_vendor_by_id(self, vendor_id: int) -> Optional[Vendor]:
        return (
            self.db.query(Vendor)
            .options(selectinload(Vendor.status))
            .filter(Vendor.vendor_id == vendor_id)
            .first()
        )

    def get_pr_by_id(self, pr_id: int) -> Optional[PurchaseRequisition]:
        return (
            self.db.query(PurchaseRequisition)
            .filter(PurchaseRequisition.id == pr_id)
            .first()
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
    # NDA Template
    # =====================================================

    def get_active_template_by_code(self, code: str) -> Optional[NdaTemplate]:
        return (
            self.db.query(NdaTemplate)
            .filter(NdaTemplate.code == code, NdaTemplate.is_active.is_(True))
            .first()
        )

    def get_template_by_code(self, code: str) -> Optional[NdaTemplate]:
        return (
            self.db.query(NdaTemplate)
            .filter(NdaTemplate.code == code)
            .first()
        )

    def get_template_by_id(self, template_id: int) -> Optional[NdaTemplate]:
        return (
            self.db.query(NdaTemplate)
            .filter(NdaTemplate.id == template_id)
            .first()
        )

    def get_default_active_template(self) -> Optional[NdaTemplate]:
        return (
            self.db.query(NdaTemplate)
            .filter(NdaTemplate.is_active.is_(True))
            .order_by(NdaTemplate.id.asc())
            .first()
        )

    def create_template(self, template: NdaTemplate) -> NdaTemplate:
        self.db.add(template)
        self.db.flush()
        return template

    # =====================================================
    # Vendor NDA
    # =====================================================

    def create_nda(self, nda: VendorNda) -> VendorNda:
        self.db.add(nda)
        self.db.flush()
        return nda

    def get_nda_by_id(self, nda_id: int) -> Optional[VendorNda]:
        return (
            self.db.query(VendorNda)
            .options(selectinload(VendorNda.status))
            .filter(VendorNda.nda_id == nda_id)
            .first()
        )

    def update_nda_content(
        self,
        nda: VendorNda,
        content: str,
        content_version: int,
        user_id: Optional[str],
        updated_at: datetime.datetime,
    ) -> VendorNda:
        """Persist the editable NDA wording and its revision metadata.

        Only the four content columns and ``updated_by``/``updated_at`` are
        touched - document_key, signed_document_key and the status FK are
        never written here. Callers own the transaction (same as create_nda).
        """

        nda.content = content
        nda.content_version = content_version
        nda.content_updated_at = updated_at
        nda.content_updated_by = user_id
        nda.updated_by = user_id
        nda.updated_at = updated_at

        self.db.flush()
        return nda

    def get_ndas_by_vendor(self, vendor_id: int) -> List[VendorNda]:
        return (
            self.db.query(VendorNda)
            .options(selectinload(VendorNda.status))
            .filter(VendorNda.vendor_id == vendor_id)
            .order_by(VendorNda.nda_id.desc())
            .all()
        )

    def get_ndas_in_scope(
        self,
        vendor_id: int,
        department_id: Optional[int],
        purchase_category_id: Optional[int],
    ) -> List[VendorNda]:
        """NDAs for this vendor whose scope covers the given department and
        category. A NULL department/category on the NDA means "applies to any"
        (a company-wide NDA), so those are included alongside exact matches;
        an NDA scoped to a *different* department/category is excluded."""

        return (
            self.db.query(VendorNda)
            .options(selectinload(VendorNda.status))
            .filter(
                VendorNda.vendor_id == vendor_id,
                or_(
                    VendorNda.department_id.is_(None),
                    VendorNda.department_id == department_id,
                ),
                or_(
                    VendorNda.purchase_category_id.is_(None),
                    VendorNda.purchase_category_id == purchase_category_id,
                ),
            )
            .order_by(VendorNda.nda_id.desc())
            .all()
        )

    def expire_ndas_past_validity(self, expired_status_id: int, today: datetime.date) -> int:
        """Flip NDAs whose validity window has closed to EXPIRED. Returns the
        number of rows updated. Callers own the transaction."""

        return (
            self.db.query(VendorNda)
            .filter(
                VendorNda.valid_until.isnot(None),
                VendorNda.valid_until < today,
                VendorNda.nda_status_id != expired_status_id,
            )
            .update({VendorNda.nda_status_id: expired_status_id}, synchronize_session=False)
        )

    # =====================================================
    # Audit Log
    # =====================================================

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
