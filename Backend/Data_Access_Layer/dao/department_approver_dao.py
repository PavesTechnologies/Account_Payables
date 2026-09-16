# Backend/Data_Access_Layer/dao/department_approver_dao.py
from typing import List, Optional
from uuid import UUID

from Backend.Data_Access_Layer.models.approval import DepartmentApprover


class DepartmentApproverDAO:
    def __init__(self, db):
        self.db = db

    def create(self, mapping: DepartmentApprover) -> DepartmentApprover:
        self.db.add(mapping)
        self.db.flush()
        return mapping

    def get_by_id(self, mapping_id: int) -> Optional[DepartmentApprover]:
        return self.db.query(DepartmentApprover).filter(DepartmentApprover.id == mapping_id).first()

    def get_by_department_and_user(self, department_id: int, user_uuid: UUID) -> Optional[DepartmentApprover]:
        return (
            self.db.query(DepartmentApprover)
            .filter(
                DepartmentApprover.department_id == department_id,
                DepartmentApprover.user_uuid == user_uuid,
            )
            .first()
        )

    def list_for_department(self, department_id: int, is_active: Optional[bool] = None) -> List[DepartmentApprover]:
        query = self.db.query(DepartmentApprover).filter(DepartmentApprover.department_id == department_id)
        if is_active is not None:
            query = query.filter(DepartmentApprover.is_active.is_(is_active))
        return query.order_by(DepartmentApprover.created_at.asc()).all()

    def get_active_user_uuids_for_department(self, department_id: int) -> List[UUID]:
        rows = (
            self.db.query(DepartmentApprover.user_uuid)
            .filter(
                DepartmentApprover.department_id == department_id,
                DepartmentApprover.is_active.is_(True),
            )
            .all()
        )
        return [row[0] for row in rows]

    def delete(self, mapping: DepartmentApprover) -> None:
        self.db.delete(mapping)
