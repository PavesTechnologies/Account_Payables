# Backend/Data_Access_Layer/dao/cdc_dao.py
"""DAO for the EOS/UMS CDC consumer's tables (Backend/cdc_consumer).

Upserts use Postgres INSERT ... ON CONFLICT DO UPDATE against the unique
constraints on each table's natural business key, so applying the same
CDC event twice (at-least-once delivery) converges to the same row
instead of erroring or duplicating - see cdc_sync_service for the
idempotency contract this exists to support.
"""
import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from Backend.Data_Access_Layer.models.cdc import (
    ApproverDirectory,
    ApproverDirectoryRole,
    CdcFailureLog,
    EosDepartmentCache,
    EosEmployeeCache,
    UmsRoleCache,
    UmsUserCache,
)


class CdcDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # EOS department cache
    # =====================================================

    def upsert_eos_department(
        self,
        department_uuid: UUID,
        department_name: Optional[str],
        is_active: bool,
        raw_payload: dict,
        source_ts_ms: Optional[int],
    ) -> None:
        stmt = pg_insert(EosDepartmentCache).values(
            department_uuid=department_uuid,
            department_name=department_name,
            is_active=is_active,
            raw_payload=raw_payload,
            source_ts_ms=source_ts_ms,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[EosDepartmentCache.department_uuid],
            set_={
                "department_name": stmt.excluded.department_name,
                "is_active": stmt.excluded.is_active,
                "raw_payload": stmt.excluded.raw_payload,
                "source_ts_ms": stmt.excluded.source_ts_ms,
                "synced_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        self.db.execute(stmt)

    def get_eos_department(self, department_uuid: UUID) -> Optional[EosDepartmentCache]:
        return self.db.get(EosDepartmentCache, department_uuid)

    def delete_eos_department(self, department_uuid: UUID) -> None:
        self.db.execute(delete(EosDepartmentCache).where(EosDepartmentCache.department_uuid == department_uuid))

    # =====================================================
    # EOS employee cache
    # =====================================================

    def upsert_eos_employee(
        self,
        employee_uuid: UUID,
        department_uuid: Optional[UUID],
        is_active: bool,
        raw_payload: dict,
        source_ts_ms: Optional[int],
    ) -> None:
        stmt = pg_insert(EosEmployeeCache).values(
            employee_uuid=employee_uuid,
            department_uuid=department_uuid,
            is_active=is_active,
            raw_payload=raw_payload,
            source_ts_ms=source_ts_ms,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[EosEmployeeCache.employee_uuid],
            set_={
                "department_uuid": stmt.excluded.department_uuid,
                "is_active": stmt.excluded.is_active,
                "raw_payload": stmt.excluded.raw_payload,
                "source_ts_ms": stmt.excluded.source_ts_ms,
                "synced_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        self.db.execute(stmt)

    def get_eos_employee(self, employee_uuid: UUID) -> Optional[EosEmployeeCache]:
        return self.db.get(EosEmployeeCache, employee_uuid)

    def delete_eos_employee(self, employee_uuid: UUID) -> None:
        self.db.execute(delete(EosEmployeeCache).where(EosEmployeeCache.employee_uuid == employee_uuid))

    # =====================================================
    # UMS user cache (user_id -> user_uuid, for resolving user_role events)
    # =====================================================

    def upsert_ums_user_cache(
        self,
        user_id: int,
        user_uuid: UUID,
        is_active: bool,
        raw_payload: dict,
        source_ts_ms: Optional[int],
    ) -> None:
        stmt = pg_insert(UmsUserCache).values(
            user_id=user_id,
            user_uuid=user_uuid,
            is_active=is_active,
            raw_payload=raw_payload,
            source_ts_ms=source_ts_ms,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[UmsUserCache.user_id],
            set_={
                "user_uuid": stmt.excluded.user_uuid,
                "is_active": stmt.excluded.is_active,
                "raw_payload": stmt.excluded.raw_payload,
                "source_ts_ms": stmt.excluded.source_ts_ms,
                "synced_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        self.db.execute(stmt)

    def get_ums_user_cache(self, user_id: int) -> Optional[UmsUserCache]:
        return self.db.get(UmsUserCache, user_id)

    def delete_ums_user_cache(self, user_id: int) -> None:
        self.db.execute(delete(UmsUserCache).where(UmsUserCache.user_id == user_id))

    # =====================================================
    # UMS role cache (role_id -> role_name, for resolving user_role events)
    # =====================================================

    def upsert_ums_role_cache(
        self,
        role_id: int,
        role_name: Optional[str],
        raw_payload: dict,
        source_ts_ms: Optional[int],
    ) -> None:
        stmt = pg_insert(UmsRoleCache).values(
            role_id=role_id,
            role_name=role_name,
            raw_payload=raw_payload,
            source_ts_ms=source_ts_ms,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[UmsRoleCache.role_id],
            set_={
                "role_name": stmt.excluded.role_name,
                "raw_payload": stmt.excluded.raw_payload,
                "source_ts_ms": stmt.excluded.source_ts_ms,
                "synced_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        self.db.execute(stmt)

    def get_ums_role_cache(self, role_id: int) -> Optional[UmsRoleCache]:
        return self.db.get(UmsRoleCache, role_id)

    def delete_ums_role_cache(self, role_id: int) -> None:
        self.db.execute(delete(UmsRoleCache).where(UmsRoleCache.role_id == role_id))

    # =====================================================
    # approver_directory (pre-existing table)
    # =====================================================

    def upsert_approver_directory(
        self,
        user_uuid: UUID,
        employee_uuid: UUID,
        department_uuid: Optional[UUID],
        department_name: Optional[str],
        is_user_active: bool,
    ) -> None:
        stmt = pg_insert(ApproverDirectory).values(
            user_uuid=user_uuid,
            employee_uuid=employee_uuid,
            department_uuid=department_uuid,
            department_name=department_name,
            is_user_active=is_user_active,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ApproverDirectory.user_uuid],
            set_={
                "employee_uuid": stmt.excluded.employee_uuid,
                "department_uuid": stmt.excluded.department_uuid,
                "department_name": stmt.excluded.department_name,
                "is_user_active": stmt.excluded.is_user_active,
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        self.db.execute(stmt)

    def set_approver_directory_active(self, user_uuid: UUID, is_user_active: bool) -> None:
        self.db.query(ApproverDirectory).filter(
            ApproverDirectory.user_uuid == user_uuid
        ).update(
            {
                ApproverDirectory.is_user_active: is_user_active,
                ApproverDirectory.updated_at: datetime.datetime.now(datetime.timezone.utc),
            }
        )

    def delete_approver_directory(self, user_uuid: UUID) -> None:
        self.db.execute(delete(ApproverDirectory).where(ApproverDirectory.user_uuid == user_uuid))

    def get_approver_directory(self, user_uuid: UUID) -> Optional[ApproverDirectory]:
        return self.db.execute(
            select(ApproverDirectory).where(ApproverDirectory.user_uuid == user_uuid)
        ).scalar_one_or_none()

    def update_department_for_employee(
        self, employee_uuid: UUID, department_uuid: UUID, department_name: Optional[str]
    ) -> None:
        """Propagates a resolved/changed employee->department link to any
        already-synced directory row for that employee. Only called with a
        non-null department_uuid - approver_directory.department_uuid is
        NOT NULL, so there is nothing safe to write until it's known."""
        self.db.query(ApproverDirectory).filter(
            ApproverDirectory.employee_uuid == employee_uuid
        ).update(
            {
                ApproverDirectory.department_uuid: department_uuid,
                ApproverDirectory.department_name: department_name,
                ApproverDirectory.updated_at: datetime.datetime.now(datetime.timezone.utc),
            }
        )

    def update_department_name_everywhere(self, department_uuid: UUID, department_name: Optional[str]) -> None:
        """Propagates an EOS department rename to any already-synced directory rows."""
        self.db.query(ApproverDirectory).filter(
            ApproverDirectory.department_uuid == department_uuid
        ).update(
            {
                ApproverDirectory.department_name: department_name,
                ApproverDirectory.updated_at: datetime.datetime.now(datetime.timezone.utc),
            }
        )

    # =====================================================
    # approver_directory_role (pre-existing table)
    # =====================================================

    def upsert_approver_directory_role(
        self,
        user_uuid: UUID,
        role_id: int,
        role_code: str,
        is_active: bool,
    ) -> None:
        stmt = pg_insert(ApproverDirectoryRole).values(
            user_uuid=user_uuid,
            role_id=role_id,
            role_code=role_code,
            is_active=is_active,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="approver_directory_role_user_role_key",
            set_={
                "role_code": stmt.excluded.role_code,
                "is_active": stmt.excluded.is_active,
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        self.db.execute(stmt)

    def delete_approver_directory_role(self, user_uuid: UUID, role_id: int) -> None:
        self.db.execute(
            delete(ApproverDirectoryRole).where(
                ApproverDirectoryRole.user_uuid == user_uuid,
                ApproverDirectoryRole.role_id == role_id,
            )
        )

    def update_role_code_everywhere(self, role_id: int, role_code: Optional[str]) -> None:
        """Propagates a UMS role rename to any already-synced assignment rows."""
        if not role_code:
            return
        self.db.query(ApproverDirectoryRole).filter(
            ApproverDirectoryRole.role_id == role_id
        ).update(
            {
                ApproverDirectoryRole.role_code: role_code,
                ApproverDirectoryRole.updated_at: datetime.datetime.now(datetime.timezone.utc),
            }
        )

    # =====================================================
    # CDC failure log
    # =====================================================

    def find_failure_by_kafka_position(
        self, kafka_topic: str, kafka_partition: int, kafka_offset: int
    ) -> Optional[CdcFailureLog]:
        return self.db.execute(
            select(CdcFailureLog).where(
                CdcFailureLog.kafka_topic == kafka_topic,
                CdcFailureLog.kafka_partition == kafka_partition,
                CdcFailureLog.kafka_offset == kafka_offset,
            )
        ).scalar_one_or_none()

    def create_failure(
        self,
        *,
        kafka_topic: str,
        kafka_partition: int,
        kafka_offset: int,
        entity_type: str,
        entity_key: Optional[str],
        operation: Optional[str],
        failure_type: str,
        error_message: str,
        raw_payload: Optional[dict],
        max_retries: int,
    ) -> CdcFailureLog:
        failure = CdcFailureLog(
            kafka_topic=kafka_topic,
            kafka_partition=kafka_partition,
            kafka_offset=kafka_offset,
            entity_type=entity_type,
            entity_key=entity_key,
            operation=operation,
            failure_type=failure_type,
            error_message=error_message[:8000] if error_message else error_message,
            raw_payload=raw_payload,
            retry_count=0,
            max_retries=max_retries,
            status="FAILED",
        )
        self.db.add(failure)
        self.db.flush()
        return failure

    def update_failure_after_retry(
        self,
        failure: CdcFailureLog,
        *,
        succeeded: bool,
        error_message: Optional[str] = None,
    ) -> None:
        failure.updated_at = datetime.datetime.now(datetime.timezone.utc)
        if succeeded:
            failure.status = "RESOLVED"
            return

        failure.retry_count += 1
        failure.error_message = (error_message or failure.error_message)
        if failure.error_message:
            failure.error_message = failure.error_message[:8000]
        failure.status = "EXHAUSTED" if failure.retry_count >= failure.max_retries else "RETRYING"

    def list_retryable_failures(self, limit: int = 100) -> List[CdcFailureLog]:
        return list(
            self.db.execute(
                select(CdcFailureLog)
                .where(CdcFailureLog.status.in_(["FAILED", "RETRYING"]))
                .order_by(CdcFailureLog.created_at.asc())
                .limit(limit)
            ).scalars()
        )
