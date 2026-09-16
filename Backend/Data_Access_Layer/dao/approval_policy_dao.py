# Backend/Data_Access_Layer/dao/approval_policy_dao.py
from typing import List, Optional

from Backend.Data_Access_Layer.models.approval import ApprovalPolicy, ApprovalPolicyLevel, InvoiceApproval


class ApprovalPolicyDAO:
    def __init__(self, db):
        self.db = db

    def create_policy(self, policy: ApprovalPolicy) -> ApprovalPolicy:
        self.db.add(policy)
        self.db.flush()
        return policy

    def create_level(self, level: ApprovalPolicyLevel) -> ApprovalPolicyLevel:
        self.db.add(level)
        self.db.flush()
        return level

    def get_policy_by_id(self, policy_id: int) -> Optional[ApprovalPolicy]:
        return self.db.query(ApprovalPolicy).filter(ApprovalPolicy.id == policy_id).first()

    def get_policy_by_name(self, name: str) -> Optional[ApprovalPolicy]:
        return self.db.query(ApprovalPolicy).filter(ApprovalPolicy.name == name).first()

    def get_all_policies(
        self,
        department_id: Optional[int] = None,
        purchase_category_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> List[ApprovalPolicy]:
        query = self.db.query(ApprovalPolicy)
        if department_id is not None:
            query = query.filter(ApprovalPolicy.department_id == department_id)
        if purchase_category_id is not None:
            query = query.filter(ApprovalPolicy.purchase_category_id == purchase_category_id)
        if is_active is not None:
            query = query.filter(ApprovalPolicy.is_active.is_(is_active))
        return query.order_by(ApprovalPolicy.name.asc()).all()

    def get_active_policies_for(self, department_id: int, purchase_category_id: int) -> List[ApprovalPolicy]:
        """Candidates for matching one invoice - active policies scoped to
        this exact department+category pair. Amount-range containment and
        overlap validation happen in the service, not here."""
        return (
            self.db.query(ApprovalPolicy)
            .filter(
                ApprovalPolicy.department_id == department_id,
                ApprovalPolicy.purchase_category_id == purchase_category_id,
                ApprovalPolicy.is_active.is_(True),
            )
            .all()
        )

    def get_active_default_policies(self) -> List[ApprovalPolicy]:
        """The catch-all fallback(s) - used by match_policy only when no
        department+category-scoped policy applies. Returns a list (not
        Optional[ApprovalPolicy]) so the service can detect and reject the
        "more than one active default" case explicitly rather than
        silently picking one."""
        return (
            self.db.query(ApprovalPolicy)
            .filter(
                ApprovalPolicy.is_default.is_(True),
                ApprovalPolicy.is_active.is_(True),
            )
            .all()
        )

    def delete_levels_for_policy(self, policy_id: int) -> None:
        self.db.query(ApprovalPolicyLevel).filter(
            ApprovalPolicyLevel.approval_policy_id == policy_id
        ).delete(synchronize_session=False)

    def get_levels_for_policy(self, policy_id: int) -> List[ApprovalPolicyLevel]:
        return (
            self.db.query(ApprovalPolicyLevel)
            .filter(ApprovalPolicyLevel.approval_policy_id == policy_id)
            .order_by(ApprovalPolicyLevel.level_number.asc())
            .all()
        )

    def delete_policy(self, policy: ApprovalPolicy) -> None:
        self.db.delete(policy)

    def policy_has_approval_instances(self, policy_id: int) -> bool:
        return (
            self.db.query(InvoiceApproval.invoice_approval_id)
            .filter(InvoiceApproval.approval_policy_id == policy_id)
            .first()
            is not None
        )
