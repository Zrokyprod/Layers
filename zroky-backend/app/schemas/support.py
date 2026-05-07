from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SupportMessageItem(BaseModel):
    message_id: str
    sender_type: str
    sender_subject: str | None = None
    body: str
    is_internal: bool
    created_at: datetime


class SupportTicketItem(BaseModel):
    ticket_id: str
    tenant_id: str | None = None
    user_id: str | None = None
    subject: str | None = None
    email: str | None = None
    title: str
    description: str | None = None
    category: str
    priority: str
    status: str
    assigned_to: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class SupportTicketDetailResponse(BaseModel):
    ticket: SupportTicketItem
    messages: list[SupportMessageItem]


class SupportTicketListResponse(BaseModel):
    items: list[SupportTicketItem]
    total: int


class SupportTicketCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    category: str = Field(default="general", max_length=64)
    priority: str = Field(default="medium", max_length=16)


class SupportMessageCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


class SupportTicketUpdateRequest(BaseModel):
    status: str | None = Field(None, max_length=32)
    priority: str | None = Field(None, max_length=16)
    assigned_to: str | None = Field(None, max_length=255)
