# Backend/Business_Layer/services/approval_policy_service.py
"""Admin CRUD for ApprovalPolicy/ApprovalPolicyLevel, and the matching
logic that picks the one policy applicable to an invoice.

Overlapping active policies for the same department+purchase_category
are rejected at write time (create/update/reactivate), not resolved by
priority at match time (spec section 35) - so match_policy() can always
expect at most one candidate whose amount range actually contains the
invoice's amount; more than one is treated as a defensive/should-never-
happen ambiguity error, not silently resolved.
"""
from __future__ import annotations

import datetime
import decimal
from typing import List, Optional

from Backend.Data_Access_Layer.dao.approval_policy_dao import ApprovalPolicyDAO
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.approval import ApprovalPolicy, ApprovalPolicyLevel

VALID_APPROVER_TYPES = {"DEPARTMENT_APPROVER", "ROLE", "USER"}
VALID_APPROVAL_RULES = {"ANY_ONE", "ALL"}

_NEG_INF = decimal.Decimal("-Infinity")
_POS_INF = decimal.Decimal("Infinity")


def _ranges_overlap(a_min, a_max, b_min, b_max) -> bool:
    a_min = a_min if a_min is not None else _NEG_INF
    a_max = a_max if a_max is not None else _POS_INF
    b_min = b_min if b_min is not None else _NEG_INF
    b_max = b_max if b_max is not None else _POS_INF
    return a_min <= b_max and b_min <= a_max


class ApprovalPolicyService:
    def __init__(self, db):
        self.db = db
        self.dao = ApprovalPolicyDAO(db)
        self.master_dao = MasterDAO(db)

    # =========================================================
    # Policy CRUD
    # =========================================================

    def create_policy(self, data) -> ApprovalPolicy:
        is_default = bool(getattr(data, "is_default", False))
        is_active = data.is_active if data.is_active is not None else True

        if is_default:
            self._validate_default_scoping(data.department_id, data.purchase_category_id, data.min_amount, data.max_amount)
        else:
            if data.department_id is None or data.purchase_category_id is None:
                raise ValueError("department_id and purchase_category_id are required unless is_default is true")
            self._validate_department_and_category(data.department_id, data.purchase_category_id)
            self._validate_amount_range(data.min_amount, data.max_amount)

        if self.dao.get_policy_by_name(data.name) is not None:
            raise ValueError(f"An approval policy named '{data.name}' already exists")
        if not data.levels:
            raise ValueError("An approval policy must have at least one level")

        if is_active:
            if is_default:
                self._validate_no_other_active_default()
            else:
                self._validate_no_overlap(data.department_id, data.purchase_category_id, data.min_amount, data.max_amount)

        policy = ApprovalPolicy(
            name=data.name,
            description=data.description,
            is_default=is_default,
            department_id=None if is_default else data.department_id,
            purchase_category_id=None if is_default else data.purchase_category_id,
            min_amount=None if is_default else data.min_amount,
            max_amount=None if is_default else data.max_amount,
            is_active=is_active,
        )
        self.dao.create_policy(policy)
        self.db.flush()

        self._replace_levels(policy.id, data.levels)

        self.db.commit()
        self.db.refresh(policy)
        return policy

    def update_policy(self, policy_id: int, data) -> ApprovalPolicy:
        policy = self._require_policy(policy_id)
        is_default = policy.is_default  # not editable after creation - see note in _replace_levels area

        if is_default:
            # A default policy has no scoping to update - reject an
            # attempt to give it one rather than silently ignoring it.
            self._validate_default_scoping(data.department_id, data.purchase_category_id, data.min_amount, data.max_amount)
        else:
            department_id = data.department_id if data.department_id is not None else policy.department_id
            purchase_category_id = (
                data.purchase_category_id if data.purchase_category_id is not None else policy.purchase_category_id
            )
            min_amount = data.min_amount if data.min_amount is not None else policy.min_amount
            max_amount = data.max_amount if data.max_amount is not None else policy.max_amount

            self._validate_department_and_category(department_id, purchase_category_id)
            self._validate_amount_range(min_amount, max_amount)
            if policy.is_active:
                self._validate_no_overlap(
                    department_id, purchase_category_id, min_amount, max_amount, exclude_policy_id=policy.id
                )
            policy.department_id = department_id
            policy.purchase_category_id = purchase_category_id
            policy.min_amount = min_amount
            policy.max_amount = max_amount

        if data.name is not None and data.name != policy.name:
            if self.dao.get_policy_by_name(data.name) is not None:
                raise ValueError(f"An approval policy named '{data.name}' already exists")
            policy.name = data.name

        if data.description is not None:
            policy.description = data.description
        policy.updated_at = datetime.datetime.now(datetime.timezone.utc)

        if data.levels is not None:
            if not data.levels:
                raise ValueError("An approval policy must have at least one level")
            self._replace_levels(policy.id, data.levels)

        self.db.commit()
        self.db.refresh(policy)
        return policy

    def set_policy_status(self, policy_id: int, is_active: bool) -> ApprovalPolicy:
        policy = self._require_policy(policy_id)
        if is_active and not policy.is_active:
            if policy.is_default:
                self._validate_no_other_active_default(exclude_policy_id=policy.id)
            else:
                self._validate_no_overlap(
                    policy.department_id, policy.purchase_category_id, policy.min_amount, policy.max_amount,
                    exclude_policy_id=policy.id,
                )
        policy.is_active = is_active
        policy.updated_at = datetime.datetime.now(datetime.timezone.utc)
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def delete_policy(self, policy_id: int) -> None:
        policy = self._require_policy(policy_id)
        if self.dao.policy_has_approval_instances(policy_id):
            raise ValueError(
                "This policy has already been used by at least one invoice approval and cannot be "
                "deleted - deactivate it instead"
            )
        self.dao.delete_policy(policy)
        self.db.commit()

    def get_policy(self, policy_id: int) -> ApprovalPolicy:
        return self._require_policy(policy_id)

    def list_policies(
        self,
        department_id: Optional[int] = None,
        purchase_category_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> List[ApprovalPolicy]:
        return self.dao.get_all_policies(department_id, purchase_category_id, is_active)

    # =========================================================
    # Matching
    # =========================================================

    def match_policy(self, department_id: int, purchase_category_id: int, amount: decimal.Decimal) -> ApprovalPolicy:
        candidates = self.dao.get_active_policies_for(department_id, purchase_category_id)
        matching = [
            p for p in candidates
            if (p.min_amount is None or amount >= p.min_amount)
            and (p.max_amount is None or amount <= p.max_amount)
        ]
        if len(matching) > 1:
            names = ", ".join(p.name for p in matching)
            raise ValueError(
                f"Multiple approval policies match this invoice ambiguously ({names}); "
                f"resolve the overlapping policy configuration before retrying."
            )
        if matching:
            return matching[0]

        # No department+category+amount-scoped policy applies - fall back
        # to the single active default policy, if one is configured.
        defaults = self.dao.get_active_default_policies()
        if len(defaults) > 1:
            names = ", ".join(p.name for p in defaults)
            raise ValueError(
                f"Multiple active default approval policies exist ({names}); "
                f"deactivate all but one before retrying."
            )
        if defaults:
            return defaults[0]

        raise ValueError("No applicable approval policy found for this invoice.")

    # =========================================================
    # Internal helpers
    # =========================================================

    def _require_policy(self, policy_id: int) -> ApprovalPolicy:
        policy = self.dao.get_policy_by_id(policy_id)
        if policy is None:
            raise ValueError("Approval policy not found")
        return policy

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

        if purchase_category.department_id != department_id:
            raise ValueError("Purchase category does not belong to the selected department.")

    @staticmethod
    def _validate_default_scoping(department_id, purchase_category_id, min_amount, max_amount) -> None:
        if any(v is not None for v in (department_id, purchase_category_id, min_amount, max_amount)):
            raise ValueError(
                "A default policy cannot have a department, purchase category, or amount range - "
                "it applies only when nothing else matches"
            )

    def _validate_no_other_active_default(self, exclude_policy_id: Optional[int] = None) -> None:
        for other in self.dao.get_active_default_policies():
            if exclude_policy_id is not None and other.id == exclude_policy_id:
                continue
            raise ValueError(
                f"An active default policy already exists ('{other.name}') - deactivate it first"
            )

    @staticmethod
    def _validate_amount_range(min_amount, max_amount) -> None:
        if min_amount is not None and min_amount < 0:
            raise ValueError("min_amount cannot be negative")
        if max_amount is not None and max_amount < 0:
            raise ValueError("max_amount cannot be negative")
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise ValueError("min_amount cannot be greater than max_amount")

    def _validate_no_overlap(
        self,
        department_id: int,
        purchase_category_id: int,
        min_amount,
        max_amount,
        exclude_policy_id: Optional[int] = None,
    ) -> None:
        for other in self.dao.get_active_policies_for(department_id, purchase_category_id):
            if exclude_policy_id is not None and other.id == exclude_policy_id:
                continue
            if _ranges_overlap(min_amount, max_amount, other.min_amount, other.max_amount):
                raise ValueError(
                    f"This amount range overlaps with the active policy '{other.name}' for the same "
                    f"department and purchase category. Adjust the range or deactivate the other policy first."
                )

    def _replace_levels(self, policy_id: int, levels_data) -> None:
        self.dao.delete_levels_for_policy(policy_id)
        self.db.flush()

        seen_numbers = set()
        for level_data in levels_data:
            if level_data.level_number in seen_numbers:
                raise ValueError(f"Duplicate level_number {level_data.level_number} in policy levels")
            seen_numbers.add(level_data.level_number)

            approver_type = self._validate_approver_type(level_data.approver_type)
            approval_rule = self._validate_approval_rule(level_data.approval_rule)
            role_code, user_uuid = self._validate_approver_reference(
                approver_type, level_data.role_code, level_data.user_uuid
            )

            self.dao.create_level(
                ApprovalPolicyLevel(
                    approval_policy_id=policy_id,
                    level_number=level_data.level_number,
                    approver_type=approver_type,
                    approval_rule=approval_rule,
                    role_code=role_code,
                    user_uuid=user_uuid,
                    is_active=level_data.is_active if level_data.is_active is not None else True,
                )
            )

    @staticmethod
    def _validate_approver_type(approver_type: str) -> str:
        approver_type = (approver_type or "").upper()
        if approver_type not in VALID_APPROVER_TYPES:
            raise ValueError(f"approver_type must be one of {sorted(VALID_APPROVER_TYPES)}")
        return approver_type

    @staticmethod
    def _validate_approval_rule(approval_rule: str) -> str:
        approval_rule = (approval_rule or "ANY_ONE").upper()
        if approval_rule not in VALID_APPROVAL_RULES:
            raise ValueError(f"approval_rule must be one of {sorted(VALID_APPROVAL_RULES)}")
        return approval_rule

    @staticmethod
    def _validate_approver_reference(approver_type: str, role_code, user_uuid):
        if approver_type == "ROLE":
            if not role_code:
                raise ValueError("role_code is required when approver_type is ROLE")
            return role_code, None
        if approver_type == "USER":
            if not user_uuid:
                raise ValueError("user_uuid is required when approver_type is USER")
            return None, user_uuid
        # DEPARTMENT_APPROVER: neither field is used - the department is
        # implicitly the policy's own department_id (see approval.py).
        return None, None
