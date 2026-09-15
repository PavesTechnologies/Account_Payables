# Backend/Data_Access_Layer/models/cdc.py
"""Models backing the EOS/UMS Kafka CDC consumer (Backend/cdc_consumer).

Two groups of tables here:

1. ApproverDirectory / ApproverDirectoryRole - the approval engine's read
   surface. These tables ALREADY EXISTED in the live database before this
   consumer was written; they are mapped here to match the live DDL
   exactly, not redesigned. Each carries a UNIQUE constraint (user_uuid;
   role_id+user_uuid respectively) that the CDC upsert logic's
   ON CONFLICT depends on for idempotency - declared below, and present
   on the live table (see Database/schema.sql for the current DDL).

2. EosDepartmentCache / EosEmployeeCache / UmsUserCache / UmsRoleCache -
   new, small, AP-owned lookup tables. They exist ONLY to correlate CDC
   events that describe the same real-world entity but arrive on
   different topics/partitions with no ordering guarantee between them
   (e.g. a ums.user_role event carries user_id/role_id, but
   approver_directory_role needs user_uuid/role_code - those are only
   known from the ums.user and ums.role topics respectively). They are
   not queried by the approval engine or any route - only by
   cdc_sync_service.

None of these tables are foreign-keyed to each other or to
approver_directory/approver_directory_role: CDC delivery order across
topics is not guaranteed, and a hard FK would reject a perfectly valid,
eventually-consistent event. Missing correlations are handled as
retryable failures (see Backend/Business_Layer/utils/cdc_exceptions.py)
instead.
"""
from typing import Optional
import datetime
import uuid as uuid_module

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base


class ApproverDirectory(Base):
    """Maps the pre-existing ap.approver_directory table (one row per UMS
    user) - do not add columns here without also migrating the live table."""

    __tablename__ = 'approver_directory'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='approver_directory_pkey'),
        UniqueConstraint('user_uuid', name='approver_directory_user_uuid_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    employee_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Nullable: NULL means "not scoped to one department" (e.g. system/admin
    # accounts that aren't real EOS employees - see SYSTEM_USER_IDS in
    # cdc_sync_service.py). Every real, EOS-backed user still gets a
    # concrete department_uuid as before.
    department_uuid: Mapped[Optional[uuid_module.UUID]] = mapped_column(UUID(as_uuid=True))
    is_user_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    department_name: Mapped[Optional[str]] = mapped_column(String(255))


class ApproverDirectoryRole(Base):
    """Maps the pre-existing ap.approver_directory_role table (one row per
    user/role assignment) - do not add columns here without also migrating
    the live table."""

    __tablename__ = 'approver_directory_role'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='approver_directory_role_pkey'),
        UniqueConstraint('role_id', 'user_uuid', name='approver_directory_role_user_role_key'),
        {'schema': 'ap'}
    )

    id: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    user_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role_code: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))


class EosDepartmentCache(Base):
    """AP-owned projection of eos_cdc.eos.departments, used only to enrich
    employee/user events with department_name (EOS field names are best-effort
    - see cdc_event.py - and confirmed against a real sample before go-live)."""

    __tablename__ = 'eos_department_cache'
    __table_args__ = (
        PrimaryKeyConstraint('department_uuid', name='eos_department_cache_pkey'),
        {'schema': 'ap'}
    )

    department_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    department_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_ts_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class EosEmployeeCache(Base):
    """AP-owned projection of eos_cdc.eos.employee_details, used only to
    enrich ums.user events with employee_uuid/department_uuid."""

    __tablename__ = 'eos_employee_cache'
    __table_args__ = (
        PrimaryKeyConstraint('employee_uuid', name='eos_employee_cache_pkey'),
        {'schema': 'ap'}
    )

    employee_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    department_uuid: Mapped[Optional[uuid_module.UUID]] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_ts_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class UmsUserCache(Base):
    """AP-owned projection of ums_cdc.ums.user, keyed by the numeric
    user_id (confirmed via stg.user) - needed to resolve ums.user_role
    events (which only carry user_id/role_id) to a user_uuid."""

    __tablename__ = 'ums_user_cache'
    __table_args__ = (
        PrimaryKeyConstraint('user_id', name='ums_user_cache_pkey'),
        {'schema': 'ap'}
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_ts_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class UmsRoleCache(Base):
    """AP-owned projection of ums_cdc.ums.role, keyed by the numeric
    role_id (confirmed via stg.role) - needed to resolve ums.user_role
    events to a role_code (role_name)."""

    __tablename__ = 'ums_role_cache'
    __table_args__ = (
        PrimaryKeyConstraint('role_id', name='ums_role_cache_pkey'),
        {'schema': 'ap'}
    )

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_name: Mapped[Optional[str]] = mapped_column(String(150))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_ts_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class CdcFailureLog(Base):
    """A CDC event that failed to apply, kept for debugging and replay by
    CdcRetryService. One row per (kafka_topic, kafka_partition,
    kafka_offset) - retries update the same row rather than inserting a
    new one, so a poison message doesn't grow the log unbounded."""

    __tablename__ = 'cdc_failure_log'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='cdc_failure_log_pkey'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kafka_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    kafka_partition: Mapped[int] = mapped_column(Integer, nullable=False)
    kafka_offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_key: Mapped[Optional[str]] = mapped_column(String(255))
    operation: Mapped[Optional[str]] = mapped_column(String(20))
    failure_type: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('5'))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'FAILED'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
