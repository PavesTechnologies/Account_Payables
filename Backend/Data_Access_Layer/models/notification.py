# Backend/Data_Access_Layer/models/notification.py
"""User-specific, action-based IN-APP notifications (Phase 1 - in-app only,
no email/external channel).

One row = one notification for ONE recipient. recipient_user_uuid is the
UMS user_uuid (the same identity ap.approver_directory / the invoice
approval engine are keyed by) - resolved server-side by
NotificationDispatcher, never supplied by a client.

dedupe_key is UNIQUE and is what makes emission idempotent: it is built
from recipient + notification_type + entity_type + entity_id + an event
identifier (plus a threshold bucket for future deadline reminders), and
rows are inserted with ON CONFLICT (dedupe_key) DO NOTHING, so replaying
the same business event can never produce a second row.

resolved_at is set when the underlying work is completed/cancelled (e.g.
PO generated, approval step decided) - the notification stays in the
user's history but is no longer actionable, and future reminder sweeps
must not re-notify for resolved work.

No FK to any workflow table on purpose: entity_type/entity_id point at
several different tables (PR, RFQ, quotation, NDA, invoice, payment...),
and a notification must survive e.g. a draft PR being deleted.
"""
from typing import Optional
import datetime
import uuid as uuid_module

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Index, PrimaryKeyConstraint,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

NOTIFICATION_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


class Notification(Base):
    __tablename__ = 'notification'
    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name='chk_notification_priority',
        ),
        PrimaryKeyConstraint('id', name='notification_pkey'),
        UniqueConstraint('dedupe_key', name='notification_dedupe_key_key'),
        Index('idx_notification_recipient', 'recipient_user_uuid'),
        Index('idx_notification_recipient_unread', 'recipient_user_uuid', 'is_read'),
        Index('idx_notification_created_at', 'created_at'),
        Index('idx_notification_entity', 'entity_type', 'entity_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recipient_user_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'MEDIUM'::character varying"))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    triggered_by: Mapped[Optional[str]] = mapped_column(String(100))
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
