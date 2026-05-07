from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    notification_id: str
    user_id: str
    project_id: str | None
    title: str
    body: str | None
    category: str
    is_read: bool
    read_at: datetime | None
    action_url: str | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    total: int
    unread_count: int
    items: list[NotificationResponse]


class MarkReadResponse(BaseModel):
    notification_id: str
    is_read: bool
    read_at: datetime


class MarkAllReadResponse(BaseModel):
    marked_count: int
