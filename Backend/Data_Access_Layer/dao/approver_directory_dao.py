# Backend/Data_Access_Layer/dao/approver_directory_dao.py
"""Read-only lookups against the CDC-synced approver identity tables
(ap.approver_directory / ap.approver_directory_role), for the approval
engine (Backend/Business_Layer/services/approver_resolver_service.py) and
its admin-lookup API (Backend/API_Layer/routes/approval_policy_route.py).

Deliberately separate from Backend/Data_Access_Layer/dao/cdc_dao.py,
which is scoped to CDC sync writes only (see its own module docstring) -
this DAO only ever reads.
"""
from typing import List, Optional
from uuid import UUID

from Backend.Data_Access_Layer.models.cdc import ApproverDirectory, ApproverDirectoryRole, UmsUserCache


class ApproverDirectoryDAO:
    def __init__(self, db):
        self.db = db

    def get_user_uuid_by_user_id(self, user_id) -> Optional[UUID]:
        """Resolves the numeric ums.user_id every route already gets from
        the JWT (request.state.user['user_id']/['sub']) to the user_uuid
        approver_directory/approver_directory_role are actually keyed by -
        via the CDC-synced ap.ums_user_cache, not by assuming the JWT
        itself carries a user_uuid claim."""
        try:
            numeric_user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        entry = (
            self.db.query(UmsUserCache)
            .filter(UmsUserCache.user_id == numeric_user_id)
            .first()
        )
        return entry.user_uuid if entry else None

    def get_active_users_by_role(self, role_code: str) -> List[UUID]:
        rows = (
            self.db.query(ApproverDirectory.user_uuid)
            .join(ApproverDirectoryRole, ApproverDirectoryRole.user_uuid == ApproverDirectory.user_uuid)
            .filter(
                ApproverDirectory.is_user_active.is_(True),
                ApproverDirectoryRole.role_code == role_code,
                ApproverDirectoryRole.is_active.is_(True),
            )
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def is_user_active(self, user_uuid: UUID) -> bool:
        entry = (
            self.db.query(ApproverDirectory)
            .filter(ApproverDirectory.user_uuid == user_uuid)
            .first()
        )
        return entry is not None and entry.is_user_active

    def has_active_role(self, user_uuid: UUID, role_code: str) -> bool:
        return (
            self.db.query(ApproverDirectoryRole)
            .filter(
                ApproverDirectoryRole.user_uuid == user_uuid,
                ApproverDirectoryRole.role_code == role_code,
                ApproverDirectoryRole.is_active.is_(True),
            )
            .first()
            is not None
        )

    def get_directory_entry(self, user_uuid: UUID) -> Optional[ApproverDirectory]:
        return (
            self.db.query(ApproverDirectory)
            .filter(ApproverDirectory.user_uuid == user_uuid)
            .first()
        )

    def list_active_directory(
        self, department_uuid: Optional[UUID] = None, role_code: Optional[str] = None
    ) -> List[ApproverDirectory]:
        """Backing query for the admin approver-lookup API (GET /apm/approval/approvers)."""
        query = self.db.query(ApproverDirectory).filter(ApproverDirectory.is_user_active.is_(True))
        if department_uuid is not None:
            query = query.filter(ApproverDirectory.department_uuid == department_uuid)
        if role_code is not None:
            query = query.join(
                ApproverDirectoryRole, ApproverDirectoryRole.user_uuid == ApproverDirectory.user_uuid
            ).filter(
                ApproverDirectoryRole.role_code == role_code,
                ApproverDirectoryRole.is_active.is_(True),
            )
        return query.order_by(ApproverDirectory.user_uuid.asc()).distinct().all()

    def list_distinct_role_codes(self) -> List[str]:
        rows = (
            self.db.query(ApproverDirectoryRole.role_code)
            .filter(ApproverDirectoryRole.is_active.is_(True))
            .distinct()
            .order_by(ApproverDirectoryRole.role_code.asc())
            .all()
        )
        return [row[0] for row in rows]
