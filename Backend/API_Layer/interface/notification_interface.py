# Backend/API_Layer/interface/notification_interface.py
import datetime
from typing import Any, List, Optional

from pydantic import BaseModel

from Backend.Business_Layer.utils.notification_types import module_for


class NotificationDTO(BaseModel):
    id: int
    notification_type: str
    module: Optional[str] = None
    title: str
    message: str
    priority: str
    entity_type: str
    entity_id: str
    entity_display_id: Optional[str] = None
    action_label: Optional[str] = None
    deep_link: Optional[str] = None
    deadline: Optional[str] = None
    is_read: bool
    is_resolved: bool
    created_at: datetime.datetime
    read_at: Optional[datetime.datetime] = None
    resolved_at: Optional[datetime.datetime] = None
    payload: Optional[dict[str, Any]] = None

    @classmethod
    def from_model(cls, notification) -> "NotificationDTO":
        payload = notification.payload or {}
        return cls(
            id=notification.id,
            notification_type=notification.notification_type,
            module=module_for(notification.notification_type),
            title=notification.title,
            message=notification.message,
            priority=notification.priority,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            entity_display_id=payload.get("entity_display_id"),
            action_label=payload.get("action_label"),
            deep_link=payload.get("deep_link"),
            deadline=payload.get("deadline"),
            is_read=bool(notification.is_read),
            is_resolved=notification.resolved_at is not None,
            created_at=notification.created_at,
            read_at=notification.read_at,
            resolved_at=notification.resolved_at,
            payload=payload or None,
        )


class NotificationListResponse(BaseModel):
    items: List[NotificationDTO]
    total: int
    unread_count: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated: int
    message: str
