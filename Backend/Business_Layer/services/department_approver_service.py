# Backend/Business_Layer/services/department_approver_service.py
"""Admin CRUD for DepartmentApprover - "which users can approve for
department X" - independent of the UMS role system (see
Data_Access_Layer/models/approval.py's module docstring for why)."""
from __future__ import annotations

import datetime
from typing import List, Optional
from uuid import UUID

from Backend.Data_Access_Layer.dao.approver_directory_dao import ApproverDirectoryDAO
from Backend.Data_Access_Layer.dao.department_approver_dao import DepartmentApproverDAO
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.approval import DepartmentApprover


class DepartmentApproverService:
    def __init__(self, db):
        self.db = db
        self.dao = DepartmentApproverDAO(db)
        self.master_dao = MasterDAO(db)
        self.directory_dao = ApproverDirectoryDAO(db)

    def add(self, department_id: int, user_uuid: UUID, created_by: Optional[str]) -> DepartmentApprover:
        department = self.master_dao.get_department_by_id(department_id)
        if department is None:
            raise ValueError("Department not found for the given department_id")
        if not department.is_active:
            raise ValueError("Department is not active")

        if not self.directory_dao.is_user_active(user_uuid):
            raise ValueError("user_uuid does not match an active user in the approver directory")

        existing = self.dao.get_by_department_and_user(department_id, user_uuid)
        if existing is not None:
            if existing.is_active:
                raise ValueError("This user is already a department approver for this department")
            existing.is_active = True
            existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        mapping = DepartmentApprover(
            department_id=department_id, user_uuid=user_uuid, created_by=created_by, is_active=True,
        )
        self.dao.create(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def remove(self, mapping_id: int) -> None:
        mapping = self.dao.get_by_id(mapping_id)
        if mapping is None:
            raise ValueError("Department approver mapping not found")
        self.dao.delete(mapping)
        self.db.commit()

    def list_for_department(self, department_id: int, is_active: Optional[bool] = None) -> List[DepartmentApprover]:
        department = self.master_dao.get_department_by_id(department_id)
        if department is None:
            raise ValueError("Department not found for the given department_id")
        return self.dao.list_for_department(department_id, is_active)
