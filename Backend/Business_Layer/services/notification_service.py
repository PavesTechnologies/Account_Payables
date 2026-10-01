# Backend/Business_Layer/services/notification_service.py
"""Phase 1 IN-APP notifications: dispatcher (write side) + Notification
Center service (read side). No email, no external channel.

Flow for every business event:

    AP business event (service layer, state change already applied)
        -> NotificationDispatcher.notify
        -> identify responsible user(s): concrete owner/assignee first,
           UMS role only when the workflow has NO concrete owner
        -> actor exclusion (the user who triggered the event never gets it)
        -> build action notification (what happened / why / action)
        -> dedupe (UNIQUE dedupe_key, INSERT ... ON CONFLICT DO NOTHING)
        -> persist in the CALLER'S transaction, inside a SAVEPOINT

Why the caller's transaction: every AP service commits its own state change.
Notifications are flushed into that same transaction right before its
commit, so a notification exists if and only if the business change
committed - a rolled-back action never leaves an orphan notification, and a
notification is never visible before the change it describes.

Why a savepoint + never raise: notification failure must never change
existing workflow behaviour. Any error (including a DB error, which would
otherwise poison the outer Postgres transaction) is rolled back to the
savepoint and logged; the business commit proceeds untouched.

Identity: workflow columns (created_by, assigned_to, ...) hold the numeric
UMS user_id from the JWT; notifications are keyed by UMS user_uuid, resolved
through the CDC-synced ap.ums_user_cache via the existing
ApproverDirectoryDAO - the same resolution the invoice approval engine uses.
"""
from __future__ import annotations

import contextlib
import datetime
import logging
import uuid as uuid_module
from typing import Iterable, List, Optional, Sequence

from Backend.Business_Layer.utils import notification_types as nt
from Backend.Data_Access_Layer.dao.approver_directory_dao import ApproverDirectoryDAO
from Backend.Data_Access_Layer.dao.notification_dao import NotificationDAO

logger = logging.getLogger(__name__)

# Sentinel: "use the catalog's fallback role" (None means "no role fallback").
USE_CATALOG_ROLE = object()


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _json_safe(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, uuid_module.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_dedupe_key(recipient_user_uuid, notification_type: str, entity_type: str, entity_id, event_id: str) -> str:
    return ":".join(
        str(part) for part in (recipient_user_uuid, notification_type, entity_type, entity_id, event_id)
    )[:512]


class NotificationDispatcher:
    """Write side. Every public method is best-effort and never raises."""

    def __init__(self, db, dao: Optional[NotificationDAO] = None, directory_dao: Optional[ApproverDirectoryDAO] = None):
        self.db = db
        self.dao = dao or NotificationDAO(db)
        self.directory_dao = directory_dao or ApproverDirectoryDAO(db)

    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------

    def resolve_user_ref(self, ref) -> Optional[uuid_module.UUID]:
        """A workflow user reference (UMS user_uuid, or the numeric UMS
        user_id stored in created_by/assigned_to columns) -> user_uuid."""
        if ref is None:
            return None
        if isinstance(ref, uuid_module.UUID):
            return ref
        text = str(ref).strip()
        if not text:
            return None
        try:
            return uuid_module.UUID(text)
        except ValueError:
            pass
        return self.directory_dao.get_user_uuid_by_user_id(text)

    def resolve_recipients(
        self,
        owners: Optional[Sequence],
        fallback_role: Optional[str],
        actor_user_id,
    ) -> List[uuid_module.UUID]:
        """Concrete owner(s) first; the role only when there is no resolvable
        concrete owner at all. The actor is always excluded - and excluding
        the actor never triggers the role fallback (the owner exists, they
        just performed the action themselves)."""
        concrete = []
        for ref in owners or []:
            resolved = self.resolve_user_ref(ref)
            if resolved is not None and resolved not in concrete:
                concrete.append(resolved)

        if concrete:
            candidates = concrete
        elif fallback_role:
            candidates = list(dict.fromkeys(self.directory_dao.get_active_users_by_role(fallback_role)))
        else:
            candidates = []

        actor_uuid = self.resolve_user_ref(actor_user_id) if actor_user_id is not None else None
        return [c for c in candidates if actor_uuid is None or c != actor_uuid]

    # ---------------------------------------------------------
    # Emit
    # ---------------------------------------------------------

    def notify(
        self,
        notification_type: str,
        *,
        entity_type: str,
        entity_id,
        entity_display_id: str,
        message: str,
        event_id: str,
        actor_user_id=None,
        owners: Optional[Sequence] = None,
        fallback_role=USE_CATALOG_ROLE,
        priority: Optional[str] = None,
        action_label: Optional[str] = None,
        deep_link: Optional[str] = None,
        deadline=None,
        metadata: Optional[dict] = None,
    ) -> int:
        """Returns how many notifications were actually created (0 on any
        failure or when everything was deduplicated)."""
        try:
            definition = nt.CATALOG[notification_type]
            role = definition.fallback_role if fallback_role is USE_CATALOG_ROLE else fallback_role
            final_priority = priority or definition.priority
            if final_priority not in nt.PRIORITIES:
                raise ValueError(f"Invalid notification priority {final_priority!r}")

            payload = _json_safe({
                "action_label": action_label or definition.action_label,
                "deep_link": deep_link if deep_link is not None else nt.deep_link_for(entity_type, entity_id),
                "entity_display_id": entity_display_id,
                "deadline": deadline,
                "metadata": metadata or None,
            })
            title = f"{entity_display_id} — {definition.headline}"

            created = 0
            with self._savepoint():
                recipients = self.resolve_recipients(owners, role, actor_user_id)
                for recipient in recipients:
                    new_id = self.dao.insert_if_absent({
                        "recipient_user_uuid": recipient,
                        "notification_type": notification_type,
                        "title": title[:255],
                        "message": message,
                        "priority": final_priority,
                        "entity_type": entity_type,
                        "entity_id": str(entity_id),
                        "dedupe_key": build_dedupe_key(
                            recipient, notification_type, entity_type, entity_id, event_id
                        ),
                        "triggered_by": str(actor_user_id) if actor_user_id is not None else None,
                        "payload": payload,
                    })
                    if new_id is not None:
                        created += 1
            return created
        except Exception:
            logger.exception(
                "In-app notification %s for %s %s could not be emitted (business action unaffected)",
                notification_type, entity_type, entity_id,
            )
            return 0

    def resolve(
        self,
        entity_type: str,
        entity_id,
        notification_types: Iterable[str],
        recipient_ref=None,
    ) -> int:
        """Marks open notifications for completed/cancelled work as resolved."""
        try:
            with self._savepoint():
                recipient = self.resolve_user_ref(recipient_ref) if recipient_ref is not None else None
                if recipient_ref is not None and recipient is None:
                    return 0
                return self.dao.resolve_for_entity(entity_type, str(entity_id), notification_types, recipient)
        except Exception:
            logger.exception(
                "Could not resolve in-app notifications for %s %s (business action unaffected)",
                entity_type, entity_id,
            )
            return 0

    @contextlib.contextmanager
    def _savepoint(self):
        begin_nested = getattr(self.db, "begin_nested", None)
        if callable(begin_nested):
            with begin_nested():
                yield
        else:
            yield


@contextlib.contextmanager
def independent_dispatcher(db):
    """For events describing a FAILED business action (e.g. an approval
    workflow blocked by configuration): the caller's transaction is about to
    be rolled back by the route, so the notification needs its own committed
    transaction. Only opens a real session when ``db`` is a real SQLAlchemy
    Session - never in unit tests with fake sessions."""
    from sqlalchemy.orm import Session

    if not isinstance(db, Session):
        yield None
        return

    from Backend.Data_Access_Layer.utils.database import SessionLocal

    session = SessionLocal()
    try:
        yield NotificationDispatcher(session)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Independent notification transaction failed")
    finally:
        session.close()


# =============================================================================
# Read side - Notification Center API
# =============================================================================


class NotificationIdentityError(Exception):
    """The authenticated user could not be resolved to a UMS user_uuid."""


class NotificationService:
    """Every method takes the AUTHENTICATED user's id (from the JWT) and
    resolves the recipient from it server-side. No method accepts a
    recipient from the client."""

    MAX_PAGE_SIZE = 100

    def __init__(self, db, dao: Optional[NotificationDAO] = None, directory_dao: Optional[ApproverDirectoryDAO] = None):
        self.db = db
        self.dao = dao or NotificationDAO(db)
        self.directory_dao = directory_dao or ApproverDirectoryDAO(db)

    def resolve_current_user(self, user_id) -> uuid_module.UUID:
        user_uuid = self.directory_dao.get_user_uuid_by_user_id(user_id)
        if user_uuid is None:
            raise NotificationIdentityError(
                "Could not resolve the current user's identity for notifications"
            )
        return user_uuid

    def list_notifications(
        self,
        user_id,
        is_read: Optional[bool] = None,
        priority: Optional[str] = None,
        notification_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        module: Optional[str] = None,
    ):
        """One stream per user: every AP module's notifications for this
        recipient. ``module`` is an optional filter over that same stream."""
        if priority is not None:
            priority = priority.upper()
            if priority not in nt.PRIORITIES:
                raise ValueError(f"priority must be one of {list(nt.PRIORITIES)}")
        if notification_type is not None:
            notification_type = notification_type.upper()
            if notification_type not in nt.CATALOG:
                raise ValueError("Unknown notification_type")
        module_types = None
        if module is not None:
            module = module.upper()
            if module not in nt.MODULES:
                raise ValueError(f"module must be one of {list(nt.MODULES)}")
            module_types = nt.types_for_module(module)
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > self.MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {self.MAX_PAGE_SIZE}")

        recipient = self.resolve_current_user(user_id)
        rows, total = self.dao.list_for_recipient(
            recipient, is_read=is_read, priority=priority, notification_type=notification_type,
            skip=(page - 1) * page_size, limit=page_size, notification_types=module_types,
        )
        return rows, total, self.dao.count_unread(recipient)

    def unread_count(self, user_id) -> int:
        return self.dao.count_unread(self.resolve_current_user(user_id))

    def mark_read(self, user_id, notification_id: int):
        recipient = self.resolve_current_user(user_id)
        notification = self.dao.get_for_recipient(notification_id, recipient)
        if notification is None:
            # Same response whether the id doesn't exist or belongs to someone
            # else - never confirm another user's notification exists.
            raise ValueError("Notification not found")
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = _utcnow()
            self.db.commit()
            self.db.refresh(notification)
        return notification

    def mark_all_read(self, user_id) -> int:
        recipient = self.resolve_current_user(user_id)
        updated = self.dao.mark_all_read(recipient)
        self.db.commit()
        return updated
