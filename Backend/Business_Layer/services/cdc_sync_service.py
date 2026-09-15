# Backend/Business_Layer/services/cdc_sync_service.py
"""Business logic that applies one normalized CdcEvent to the approver
directory. This module is the ONLY place that talks to CdcDAO for CDC
purposes - both the live consumer (Backend/cdc_consumer/consumer.py) and
CdcRetryService call these same functions, so synchronization logic is
never duplicated between the "happens live" and "happens on retry" paths.

Field-name mapping caveat (EOS side): eos_cdc.eos.employee_details and
eos_cdc.eos.departments have no stg.* mirror in this database, so their
exact column names have NOT been confirmed against a real sample message
(the broker is in-cluster-only). _first_present() below tries a small set
of plausible names and keeps the full raw payload in JSONB regardless, so
correcting a name later is a one-line change here, not a schema change.
The UMS side (ums.user / ums.role / ums.user_role) IS confirmed, via the
stg schema populated by postgres-stg-sink from the same topics.

user<->employee link (confirmed): eos.employee_details.employee_uuid is
the same value as ums.user.user_uuid for every real, EOS-onboarded
employee (cross-checked against a live EOS sample) - that's the real
design, not a guess. A minority of legacy users instead carry a plain
legacy integer in an "employee_id"/"emp_uuid"-shaped payload field
(pre-dating the UUID system); _resolve_employee_uuid_for_user() falls
back to the shared-identity assumption (user_uuid as employee_uuid) for
those, since that field isn't a usable UUID link.

System/admin accounts (SYSTEM_USER_IDS below, e.g. user_id 1 "Paves
Admin", user_id 2 "System Internal") are not real EOS-onboarded
employees at all - there is no offer_letter_details/employee_details
row for them, and forcing one in would mean fabricating a fake offer
(salary, joining date, approving manager). They're synced straight into
approver_directory with department_uuid=NULL ("applies to every
department") instead of going through the EOS employee/department
lookup.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from Backend.Business_Layer.utils.cdc_exceptions import (
    MalformedCdcEventError,
    MissingDependencyError,
    UnknownCdcTopicError,
)
from Backend.cdc_consumer.cdc_event import CdcEvent
from Backend.Data_Access_Layer.dao.cdc_dao import CdcDAO

logger = logging.getLogger(__name__)

ENTITY_DEPARTMENT = "DEPARTMENT"
ENTITY_EMPLOYEE = "EMPLOYEE"
ENTITY_USER = "USER"
ENTITY_ROLE = "ROLE"
ENTITY_USER_ROLE = "USER_ROLE"

# ums.user ids that are system/admin accounts, not real EOS-onboarded
# employees - see the module docstring. Synced with department_uuid=NULL
# instead of requiring an EOS employee/department match.
SYSTEM_USER_IDS = frozenset({1, 2})


def _first_present(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _as_uuid(value: Any, *, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise MalformedCdcEventError(f"Could not parse {field}={value!r} as a UUID") from exc


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "active"}
    return default


def _resolve_employee_uuid_for_user(user_uuid: UUID, data: Dict[str, Any]) -> UUID:
    explicit = _first_present(data, "employee_uuid", "employee_id", "emp_uuid")
    if explicit is not None:
        try:
            return _as_uuid(explicit, field="employee_uuid")
        except MalformedCdcEventError:
            # Some legacy user rows carry a plain legacy integer in this
            # field (e.g. "5100001") instead of a real EOS employee_uuid.
            # That's not a usable link, so fall back to the shared-identity
            # assumption rather than permanently failing the whole event.
            logger.warning(
                "user_uuid=%s: explicit employee reference %r is not a UUID, "
                "falling back to user_uuid as employee_uuid",
                user_uuid, explicit,
            )
    return user_uuid


def process_department_event(db, event: CdcEvent) -> None:
    dao = CdcDAO(db)
    data = event.data

    department_uuid_raw = _first_present(data, "department_uuid", "uuid", "id")
    if department_uuid_raw is None:
        raise MalformedCdcEventError("department event is missing a department identifier")
    department_uuid = _as_uuid(department_uuid_raw, field="department_uuid")

    if event.is_delete:
        dao.delete_eos_department(department_uuid)
        return

    department_name = _first_present(data, "department_name", "name")
    is_active = _as_bool(_first_present(data, "is_active", "status"), default=True)

    dao.upsert_eos_department(department_uuid, department_name, is_active, data, event.source_ts_ms)
    dao.update_department_name_everywhere(department_uuid, department_name)


def process_employee_event(db, event: CdcEvent) -> None:
    dao = CdcDAO(db)
    data = event.data

    employee_uuid_raw = _first_present(data, "employee_uuid", "uuid", "id")
    if employee_uuid_raw is None:
        raise MalformedCdcEventError("employee event is missing an employee identifier")
    employee_uuid = _as_uuid(employee_uuid_raw, field="employee_uuid")

    if event.is_delete:
        dao.delete_eos_employee(employee_uuid)
        return

    department_uuid_raw = _first_present(data, "department_uuid", "department_id")
    department_uuid = (
        _as_uuid(department_uuid_raw, field="department_uuid") if department_uuid_raw is not None else None
    )
    is_active = _as_bool(_first_present(data, "is_active", "status"), default=True)

    dao.upsert_eos_employee(employee_uuid, department_uuid, is_active, data, event.source_ts_ms)

    if department_uuid is not None:
        department_cache = dao.get_eos_department(department_uuid)
        department_name = (
            department_cache.department_name if department_cache else _first_present(data, "department_name")
        )
        dao.update_department_for_employee(employee_uuid, department_uuid, department_name)


def process_user_event(db, event: CdcEvent) -> None:
    dao = CdcDAO(db)
    data = event.data

    user_id_raw = _first_present(data, "user_id", "id")
    user_uuid_raw = _first_present(data, "user_uuid", "uuid")
    if user_id_raw is None or user_uuid_raw is None:
        raise MalformedCdcEventError("user event is missing user_id/user_uuid")

    user_id = int(user_id_raw)
    user_uuid = _as_uuid(user_uuid_raw, field="user_uuid")

    if event.is_delete:
        dao.delete_ums_user_cache(user_id)
        dao.delete_approver_directory(user_uuid)
        return

    is_active = _as_bool(_first_present(data, "is_active", "status"), default=True)
    dao.upsert_ums_user_cache(user_id, user_uuid, is_active, data, event.source_ts_ms)
    # Committed independently of the approver_directory upsert below: caching
    # user_id -> user_uuid has no dependency on EOS employee/department data,
    # but a MissingDependencyError raised further down causes the caller to
    # roll back the whole transaction. Without this commit, that rollback
    # would also discard this cache write, so user_role events for this user
    # could never resolve (user cached=False) until EOS data arrives *and*
    # this exact USER event is retried again afterwards.
    db.commit()

    if user_id in SYSTEM_USER_IDS:
        # Not a real EOS employee - no employee/department lookup to do.
        dao.upsert_approver_directory(
            user_uuid=user_uuid,
            employee_uuid=user_uuid,
            department_uuid=None,
            department_name=None,
            is_user_active=is_active,
        )
        return

    employee_uuid = _resolve_employee_uuid_for_user(user_uuid, data)
    employee_cache = dao.get_eos_employee(employee_uuid)
    if employee_cache is None or employee_cache.department_uuid is None:
        raise MissingDependencyError(
            f"No synced EOS employee/department yet for employee_uuid={employee_uuid} "
            f"(user_id={user_id}, user_uuid={user_uuid})"
        )

    department_cache = dao.get_eos_department(employee_cache.department_uuid)
    department_name = department_cache.department_name if department_cache else None

    dao.upsert_approver_directory(
        user_uuid=user_uuid,
        employee_uuid=employee_uuid,
        department_uuid=employee_cache.department_uuid,
        department_name=department_name,
        is_user_active=is_active,
    )


def process_role_event(db, event: CdcEvent) -> None:
    dao = CdcDAO(db)
    data = event.data

    role_id_raw = _first_present(data, "role_id", "id")
    if role_id_raw is None:
        raise MalformedCdcEventError("role event is missing role_id")
    role_id = int(role_id_raw)

    if event.is_delete:
        dao.delete_ums_role_cache(role_id)
        return

    role_name = _first_present(data, "role_name", "name")
    dao.upsert_ums_role_cache(role_id, role_name, data, event.source_ts_ms)
    dao.update_role_code_everywhere(role_id, role_name)


def process_user_role_event(db, event: CdcEvent) -> None:
    dao = CdcDAO(db)
    data = event.data

    user_id_raw = _first_present(data, "user_id")
    role_id_raw = _first_present(data, "role_id")
    if user_id_raw is None or role_id_raw is None:
        raise MalformedCdcEventError("user_role event is missing user_id/role_id")

    user_id = int(user_id_raw)
    role_id = int(role_id_raw)

    if event.is_delete:
        user_cache = dao.get_ums_user_cache(user_id)
        if user_cache is None:
            # Can't tell, without a user_uuid, whether there's really nothing
            # to remove or whether approver_directory_role still has a stale
            # row for this user (e.g. from an earlier bulk load, or because
            # the user's own CDC event just hasn't been processed yet). Treat
            # this as retryable rather than assuming the delete's goal is
            # already satisfied - silently returning here would permanently
            # lose the delete with no record of it in cdc_failure_log.
            raise MissingDependencyError(
                f"Cannot resolve user_id={user_id} to delete role_id={role_id} yet "
                f"(user cached=False)"
            )
        dao.delete_approver_directory_role(user_cache.user_uuid, role_id)
        return

    user_cache = dao.get_ums_user_cache(user_id)
    role_cache = dao.get_ums_role_cache(role_id)
    if user_cache is None or role_cache is None:
        raise MissingDependencyError(
            f"Cannot resolve user_id={user_id}/role_id={role_id} yet "
            f"(user cached={user_cache is not None}, role cached={role_cache is not None})"
        )

    dao.upsert_approver_directory_role(
        user_uuid=user_cache.user_uuid,
        role_id=role_id,
        role_code=role_cache.role_name or f"ROLE_{role_id}",
        is_active=True,
    )


PROCESSORS: Dict[str, Callable[[Any, CdcEvent], None]] = {
    ENTITY_DEPARTMENT: process_department_event,
    ENTITY_EMPLOYEE: process_employee_event,
    ENTITY_USER: process_user_event,
    ENTITY_ROLE: process_role_event,
    ENTITY_USER_ROLE: process_user_role_event,
}


def process_event(db, entity_type: str, event: CdcEvent) -> None:
    processor = PROCESSORS.get(entity_type)
    if processor is None:
        raise UnknownCdcTopicError(f"No processor registered for entity_type={entity_type!r}")
    processor(db, event)


def describe_entity_key(entity_type: str, data: Dict[str, Any]) -> Optional[str]:
    """Best-effort human-readable key for a CdcFailureLog row - never raises."""
    try:
        if entity_type == ENTITY_DEPARTMENT:
            return str(_first_present(data, "department_uuid", "uuid", "id"))
        if entity_type == ENTITY_EMPLOYEE:
            return str(_first_present(data, "employee_uuid", "uuid", "id"))
        if entity_type == ENTITY_USER:
            return str(_first_present(data, "user_uuid", "uuid", "user_id", "id"))
        if entity_type == ENTITY_ROLE:
            return str(_first_present(data, "role_id", "id"))
        if entity_type == ENTITY_USER_ROLE:
            return f"user_id={_first_present(data, 'user_id')},role_id={_first_present(data, 'role_id')}"
    except Exception:  # noqa: BLE001 - this is a debugging aid, never fatal
        return None
    return None
