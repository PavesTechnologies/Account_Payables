# Backend/Data_Access_Layer/dao/vendor_intake_dao.py

from typing import List, Optional

from Backend.Data_Access_Layer.models.purchase import Department, PurchaseCategory
from Backend.Data_Access_Layer.models.vendor import VendorEngagement
from Backend.Data_Access_Layer.models.vendor_screening_rule import VendorScreeningRule


class VendorIntakeDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Department / Purchase Category (read-only, for intake validation)
    # =====================================================

    def get_department_by_id(self, department_id: int) -> Optional[Department]:
        return (
            self.db.query(Department)
            .filter(Department.id == department_id)
            .first()
        )

    def get_purchase_category_by_id(self, purchase_category_id: int) -> Optional[PurchaseCategory]:
        return (
            self.db.query(PurchaseCategory)
            .filter(PurchaseCategory.id == purchase_category_id)
            .first()
        )

    # =====================================================
    # Vendor Engagement
    # =====================================================

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

    def get_engagement_by_id(self, engagement_id: int) -> Optional[VendorEngagement]:
        return (
            self.db.query(VendorEngagement)
            .filter(VendorEngagement.vendor_category_mapping_id == engagement_id)
            .first()
        )

    def get_other_engagement(
        self,
        engagement_id: int,
        vendor_id: int,
        department_id: int,
        purchase_category_id: int,
    ) -> Optional[VendorEngagement]:
        """Any *other* row sharing the same vendor+department+category scope -
        a defensive re-check for Pre-Screen's duplicate check, on top of the
        DB unique constraint that already prevents this at write time."""

        return (
            self.db.query(VendorEngagement)
            .filter(
                VendorEngagement.vendor_id == vendor_id,
                VendorEngagement.department_id == department_id,
                VendorEngagement.purchase_category_id == purchase_category_id,
                VendorEngagement.vendor_category_mapping_id != engagement_id,
            )
            .first()
        )

    def get_engagements_by_vendor(self, vendor_id: int) -> List[VendorEngagement]:
        return (
            self.db.query(VendorEngagement)
            .filter(VendorEngagement.vendor_id == vendor_id)
            .order_by(VendorEngagement.vendor_category_mapping_id.asc())
            .all()
        )

    def create_engagement(self, engagement: VendorEngagement) -> VendorEngagement:
        self.db.add(engagement)
        self.db.flush()
        return engagement

    # =====================================================
    # Vendor Screening Rule (NDA recommendation Business Rule Engine)
    # =====================================================

    def create_screening_rule(self, rule: VendorScreeningRule) -> VendorScreeningRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_screening_rule_by_id(self, rule_id: int) -> Optional[VendorScreeningRule]:
        return (
            self.db.query(VendorScreeningRule)
            .filter(VendorScreeningRule.id == rule_id)
            .first()
        )

    def get_screening_rule_by_name(self, name: str) -> Optional[VendorScreeningRule]:
        return (
            self.db.query(VendorScreeningRule)
            .filter(VendorScreeningRule.name == name)
            .first()
        )

    def get_all_screening_rules(self) -> List[VendorScreeningRule]:
        return (
            self.db.query(VendorScreeningRule)
            .order_by(VendorScreeningRule.name.asc())
            .all()
        )

    def get_active_screening_rules_for_scope(
        self,
        department_id: Optional[int],
        purchase_category_id: Optional[int],
    ) -> List[VendorScreeningRule]:
        """All active rules whose scope is either a wildcard (NULL) or an
        exact match for the given department/category - the caller picks
        the most specific one. Kept as a plain list (rather than resolving
        to a single row here) so the specificity ranking - the actual
        "engine" logic - lives in the service layer, next to the rest of
        Pre-Screen's business logic."""

        query = self.db.query(VendorScreeningRule).filter(
            VendorScreeningRule.is_active.is_(True)
        )
        query = query.filter(
            (VendorScreeningRule.department_id.is_(None))
            | (VendorScreeningRule.department_id == department_id)
        )
        query = query.filter(
            (VendorScreeningRule.purchase_category_id.is_(None))
            | (VendorScreeningRule.purchase_category_id == purchase_category_id)
        )
        return query.all()
