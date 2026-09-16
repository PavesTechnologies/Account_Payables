# Backend/Business_Layer/services/approver_resolver_service.py
"""Turns one approval level's/step's approver_type into concrete,
currently-eligible user_uuids.

ROLE and USER resolve against ap.approver_directory /
ap.approver_directory_role - the CDC-synced approver identity source
(Backend/cdc_consumer/), never a local user table.

DEPARTMENT_APPROVER resolves against ap.department_approver - an
AP-owned admin-configured mapping, NOT a UMS role. Investigated and
confirmed (2026-09-16): UMS has no department-scoped, non-role
assignment primitive to reuse, so inventing a UMS role here would exist
only for this one purpose and require staying in sync out of band. A
user_uuid in that mapping is still cross-checked against
ap.approver_directory.is_user_active below - a mapping row surviving an
employee's departure/deactivation must not make them a phantom approver.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from Backend.Data_Access_Layer.dao.approver_directory_dao import ApproverDirectoryDAO
from Backend.Data_Access_Layer.dao.department_approver_dao import DepartmentApproverDAO


class ApproverResolverService:
    def __init__(self, db):
        self.db = db
        self.dao = ApproverDirectoryDAO(db)
        self.department_approver_dao = DepartmentApproverDAO(db)

    def resolve_user_uuid(self, user_id) -> Optional[UUID]:
        """Resolves the JWT's numeric user_id/sub claim to the user_uuid
        approver_directory is keyed by - see ApproverDirectoryDAO for why
        this goes through ap.ums_user_cache rather than trusting the JWT
        to carry a user_uuid claim directly."""
        return self.dao.get_user_uuid_by_user_id(user_id)

    def resolve(
        self,
        approver_type: str,
        *,
        role_code: Optional[str] = None,
        user_uuid: Optional[UUID] = None,
        department_id: Optional[int] = None,
    ) -> List[UUID]:
        """Returns the list of user_uuids eligible for one level, right
        now. An empty list means "no eligible approver" - the caller
        (InvoiceApprovalService.send_for_approval) must abort rather than
        create a step nobody can act on."""

        if approver_type == "DEPARTMENT_APPROVER":
            if department_id is None:
                raise ValueError("Cannot resolve a DEPARTMENT_APPROVER level: department_id is missing")
            configured = self.department_approver_dao.get_active_user_uuids_for_department(department_id)
            return [u for u in configured if self.dao.is_user_active(u)]

        if approver_type == "ROLE":
            if not role_code:
                raise ValueError("Cannot resolve a ROLE level: role_code is missing")
            return self.dao.get_active_users_by_role(role_code)

        if approver_type == "USER":
            if user_uuid is None:
                raise ValueError("Cannot resolve a USER level: user_uuid is missing")
            return [user_uuid] if self.dao.is_user_active(user_uuid) else []

        raise ValueError(f"Unknown approver_type: {approver_type!r}")

    def is_eligible_now(
        self,
        user_uuid: UUID,
        approver_type: str,
        role_code: Optional[str] = None,
        department_id: Optional[int] = None,
    ) -> bool:
        """Re-checked at decision time (approve/reject) - an approver
        resolved at send-for-approval time may have gone inactive, or had
        their department-approver mapping removed, since (spec section
        20: no silent auto-skip/reassign for MVP, just a clear error)."""
        if not self.dao.is_user_active(user_uuid):
            return False
        if approver_type == "ROLE" and role_code:
            return self.dao.has_active_role(user_uuid, role_code)
        if approver_type == "DEPARTMENT_APPROVER" and department_id is not None:
            mapping = self.department_approver_dao.get_by_department_and_user(department_id, user_uuid)
            return mapping is not None and mapping.is_active
        return True
