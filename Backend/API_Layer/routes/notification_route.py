# Backend/API_Layer/routes/notification_route.py
"""Notification Center API - the authenticated user's own IN-APP
notifications only.

Authorization is ownership, enforced in the backend: the recipient is
always derived from the JWT (request.state.user, set by JWTMiddleware) and
resolved to a UMS user_uuid server-side. No endpoint accepts a recipient
from the client, and every lookup/update is scoped to that recipient, so
changing a notification id in the URL can never reach another user's row
(it just 404s, exactly like an id that doesn't exist).

No permission_based_access dependency on purpose: every authenticated AP
user may read their own notifications; there is nothing else to grant.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from Backend.API_Layer.interface.notification_interface import (
    MarkAllReadResponse,
    NotificationDTO,
    NotificationListResponse,
    UnreadCountResponse,
)
from Backend.Business_Layer.services.notification_service import (
    NotificationIdentityError,
    NotificationService,
)

router = APIRouter()


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _identity_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=403, detail=str(e))


@router.get("", response_model=NotificationListResponse)
def list_my_notifications(
    http_request: Request,
    is_read: Optional[bool] = Query(None, description="false = unread only, true = read only"),
    priority: Optional[str] = Query(None, description="LOW | MEDIUM | HIGH | CRITICAL"),
    notification_type: Optional[str] = Query(None),
    module: Optional[str] = Query(
        None,
        description="Optional filter: PROCUREMENT | VENDOR_MANAGEMENT | INVOICE_MANAGEMENT | PAYMENTS | SYSTEM_CONFIGURATION",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=NotificationService.MAX_PAGE_SIZE),
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        rows, total, unread = NotificationService(db).list_notifications(
            user_id, is_read=is_read, priority=priority, notification_type=notification_type,
            page=page, page_size=page_size, module=module,
        )
        return NotificationListResponse(
            items=[NotificationDTO.from_model(row) for row in rows],
            total=total, unread_count=unread, page=page, page_size=page_size,
        )

    except NotificationIdentityError as e:
        raise _identity_error(e)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_my_unread_count(http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        return UnreadCountResponse(unread_count=NotificationService(db).unread_count(user_id))

    except NotificationIdentityError as e:
        raise _identity_error(e)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Declared BEFORE /{notification_id}/read so "read-all" is never captured as an id.
@router.patch("/read-all", response_model=MarkAllReadResponse)
def mark_all_my_notifications_read(http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        updated = NotificationService(db).mark_all_read(user_id)
        return MarkAllReadResponse(updated=updated, message=f"{updated} notification(s) marked as read")

    except NotificationIdentityError as e:
        db.rollback()
        raise _identity_error(e)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{notification_id}/read", response_model=NotificationDTO)
def mark_my_notification_read(notification_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)
        notification = NotificationService(db).mark_read(user_id, notification_id)
        return NotificationDTO.from_model(notification)

    except NotificationIdentityError as e:
        db.rollback()
        raise _identity_error(e)

    except ValueError as e:
        db.rollback()
        status_code = 404 if "not found" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
