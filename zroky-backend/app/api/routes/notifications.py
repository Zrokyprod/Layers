from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.db.session import get_db_session, get_db_session_read
from app.schemas.notification import MarkAllReadResponse, MarkReadResponse, NotificationListResponse, NotificationResponse
from app.services.user_identity import require_authenticated_user

router = APIRouter(prefix="/v1/notifications")


def _to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        notification_id=notification.id,
        user_id=notification.user_id,
        project_id=notification.project_id,
        title=notification.title,
        body=notification.body,
        category=notification.category,
        is_read=notification.is_read,
        read_at=notification.read_at,
        action_url=notification.action_url,
        created_at=notification.created_at,
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    request: Request,
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session_read),
) -> NotificationListResponse:
    user = require_authenticated_user(request, db, auto_create=True)
    filters = [Notification.user_id == user.id]
    if unread_only:
        filters.append(Notification.is_read.is_(False))

    total = db.execute(select(func.count(Notification.id)).where(*filters)).scalar_one()
    unread_count = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
    ).scalar_one()
    items = db.execute(
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return NotificationListResponse(
        total=int(total or 0),
        unread_count=int(unread_count or 0),
        items=[_to_response(item) for item in items],
    )


@router.patch("/{notification_id}/read", response_model=MarkReadResponse)
def mark_notification_read(
    notification_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
) -> MarkReadResponse:
    user = require_authenticated_user(request, db, auto_create=True)
    notification = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    now = datetime.now(timezone.utc)
    notification.is_read = True
    notification.read_at = notification.read_at or now
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return MarkReadResponse(notification_id=notification.id, is_read=notification.is_read, read_at=notification.read_at or now)


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db_session),
) -> MarkAllReadResponse:
    user = require_authenticated_user(request, db, auto_create=True)
    items = db.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for item in items:
        item.is_read = True
        item.read_at = item.read_at or now
        db.add(item)
    db.commit()
    return MarkAllReadResponse(marked_count=len(items))


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_notification(
    notification_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
) -> Response:
    user = require_authenticated_user(request, db, auto_create=True)
    notification = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    db.delete(notification)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT, response_model=None)
