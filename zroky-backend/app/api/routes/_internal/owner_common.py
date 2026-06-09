"""
Owner Dashboard API — all endpoints under /v1/owner/
Protected by require_owner_provisioning_access (PROVISIONING_TOKEN).
Every mutating action writes to AuditLog.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import (
    require_owner_provisioning_access as require_provisioning_access,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import (
    AuditLog, Call, Notification,
    PlatformLlmUsage, Project, ProjectMembership,
    Subscription, SubscriptionPlan, SupportTicket, SupportTicketMessage,
    TenantSubscription, User,
)
from app.db.session import db_healthcheck, get_db_session
from app.services.currency import get_exchange_rate_debug_snapshot
from app.services.redis_client import get_redis_client, redis_healthcheck
from app.worker.celery_app import celery_app

router = APIRouter(prefix="/v1/owner")

# ─── Maintenance mode (stored in Redis, cheap to check) ───────────────────────

_MAINTENANCE_KEY = "zroky:owner:maintenance_mode"



def _redis_ok() -> bool:
    try:
        return redis_healthcheck()
    except Exception:
        return False


class ServiceStatus(BaseModel):
    name: str
    status: str          # "ok" | "degraded" | "down" | "unknown"
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    overall: str
    services: list[ServiceStatus]
    exchange_rate: dict
    maintenance_mode: bool
    checked_at: datetime


class MaintenanceModeRequest(BaseModel):
    enabled: bool
    message: str | None = None


class MaintenanceModeResponse(BaseModel):
    enabled: bool
    message: str | None


class QueueStats(BaseModel):
    queue_name: str
    pending: int
    failed: int


class InfraStatsResponse(BaseModel):
    queues: list[QueueStats]
    worker_count: int
    worker_names: list[str]
    db_table_sizes: dict[str, int]


class OwnerStatsResponse(BaseModel):
    total_users: int
    total_projects: int
    total_calls: int
    calls_last_7d: int
    total_cost_usd: float
    cost_last_7d_usd: float
    new_users_last_7d: int
    active_users_last_7d: int


class OwnerUserItem(BaseModel):
    id: str
    email: str | None
    github_login: str | None
    display_name: str | None
    is_active: bool
    created_at: datetime
    project_count: int


class OwnerUsersResponse(BaseModel):
    users: list[OwnerUserItem]
    total: int


class OwnerProjectItem(BaseModel):
    id: str
    name: str
    owner_ref: str | None
    is_active: bool
    created_at: datetime
    call_count: int
    total_cost_usd: float
    member_count: int


class OwnerProjectsResponse(BaseModel):
    projects: list[OwnerProjectItem]
    total: int


__all__ = [name for name in globals() if not name.startswith("__")]
