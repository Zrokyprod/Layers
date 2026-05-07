"""Notification center API.

Provides CRUD for user notifications scoped by user identity.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_context, TenantContext
from app.db.models import Notification, User
from app.db.session import get_db_session
from app.schemas.notification import (
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationListResponse,
    NotificationResponse,
)

router = APIRouter(prefix="/v1/notifications")


def _notification_to_response(n: Notification) -> NotificationResponse:
    return NotificationResponse(
        notification_id=n.id,
        user_id=n.user_id,
        project_id=n.project_id,
        title=n.title,
        body=n.body,
        category=n.category,
        is_read=n.is_read,
        read_at=n.read_at,
        action_url=n.action_url,
        created_at=n.created_at,
    )


def _resolve_current_user_id(db: Session, context: TenantContext) -> str:
    """Resolve the DB user_id from the tenant context subject."""
    if not context.subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Notification center requires a bearer token.",
        )
    user = db.execute(select(User).where(User.subject == context.subject)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found for notification lookup.",
        )
    return str(user.id)


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> NotificationListResponse:
    user_id = _resolve_current_user_id(db, context)

    total_query = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
    if unread_only:
        total_query = total_query.where(Notification.is_read.is_(False))
    total = db.execute(total_query).scalar() or 0

    unread_query = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    unread_count = db.execute(unread_query).scalar() or 0

    items_query = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        items_query = items_query.where(Notification.is_read.is_(False))

    items = db.execute(items_query).scalars().all()
    return NotificationListResponse(
        total=total,
        unread_count=unread_count,
        items=[_notification_to_response(n) for n in items],
    )


@router.patch("/{notification_id}/read", response_model=MarkReadResponse)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> MarkReadResponse:
    user_id = _resolve_current_user_id(db, context)

    notification = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notification)

    return MarkReadResponse(
        notification_id=notification.id,
        is_read=notification.is_read,
        read_at=notification.read_at,
    )


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
def mark_all_read(
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> MarkAllReadResponse:
    user_id = _resolve_current_user_id(db, context)

    now = datetime.now(UTC)
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=now)
    )
    db.commit()

    return MarkAllReadResponse(marked_count=result.rowcount)


@router.delete("/{notification_id}", status_code=status.HTTP_200_OK)
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> None:
    user_id = _resolve_current_user_id(db, context)

    notification = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    db.delete(notification)
    db.commit()
