# Backend/Data_Access_Layer/dao/notification_dao.py
"""Persistence for ap.notification.

Every read/update here is scoped by recipient_user_uuid - there is
deliberately no "get by id" without a recipient, so a caller can never
read or mutate another user's notification just by changing an id.
"""
import datetime
from typing import Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from Backend.Data_Access_Layer.models.notification import Notification


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class NotificationDAO:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------
    # Write (dispatcher)
    # ---------------------------------------------------------

    def insert_if_absent(self, values: dict) -> Optional[int]:
        """INSERT ... ON CONFLICT (dedupe_key) DO NOTHING.

        Returns the new id, or None when a row with the same dedupe_key
        already exists. Race-safe: two concurrent emissions of the same
        event are serialized by the unique index, not by a read-then-write.
        """
        stmt = (
            pg_insert(Notification)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Notification.dedupe_key])
            .returning(Notification.id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def resolve_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        notification_types: Iterable[str],
        recipient_user_uuid: Optional[UUID] = None,
    ) -> int:
        """Marks still-open notifications for this entity as resolved (the
        work they asked for is done). Read state is left untouched."""
        types = list(notification_types)
        if not types:
            return 0
        stmt = (
            update(Notification)
            .where(
                Notification.entity_type == entity_type,
                Notification.entity_id == str(entity_id),
                Notification.notification_type.in_(types),
                Notification.resolved_at.is_(None),
            )
            .values(resolved_at=_utcnow())
        )
        if recipient_user_uuid is not None:
            stmt = stmt.where(Notification.recipient_user_uuid == recipient_user_uuid)
        return self.db.execute(stmt).rowcount or 0

    # ---------------------------------------------------------
    # Read / update (Notification Center API - always recipient-scoped)
    # ---------------------------------------------------------

    def _recipient_query(
        self,
        recipient_user_uuid: UUID,
        is_read: Optional[bool] = None,
        priority: Optional[str] = None,
        notification_type: Optional[str] = None,
        notification_types: Optional[Iterable[str]] = None,
    ):
        query = self.db.query(Notification).filter(
            Notification.recipient_user_uuid == recipient_user_uuid
        )
        if is_read is not None:
            query = query.filter(Notification.is_read.is_(is_read))
        if priority is not None:
            query = query.filter(Notification.priority == priority)
        if notification_type is not None:
            query = query.filter(Notification.notification_type == notification_type)
        if notification_types is not None:
            query = query.filter(Notification.notification_type.in_(list(notification_types)))
        return query

    def list_for_recipient(
        self,
        recipient_user_uuid: UUID,
        is_read: Optional[bool] = None,
        priority: Optional[str] = None,
        notification_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        notification_types: Optional[Iterable[str]] = None,
    ) -> Tuple[List[Notification], int]:
        query = self._recipient_query(
            recipient_user_uuid, is_read, priority, notification_type, notification_types
        )
        total = query.order_by(None).count()
        rows = (
            query.order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def count_unread(self, recipient_user_uuid: UUID) -> int:
        return (
            self.db.query(func.count(Notification.id))
            .filter(
                Notification.recipient_user_uuid == recipient_user_uuid,
                Notification.is_read.is_(False),
            )
            .scalar()
            or 0
        )

    def get_for_recipient(self, notification_id: int, recipient_user_uuid: UUID) -> Optional[Notification]:
        return (
            self.db.query(Notification)
            .filter(
                Notification.id == notification_id,
                Notification.recipient_user_uuid == recipient_user_uuid,
            )
            .first()
        )

    def mark_all_read(self, recipient_user_uuid: UUID) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.recipient_user_uuid == recipient_user_uuid,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=_utcnow())
        )
        return self.db.execute(stmt).rowcount or 0
