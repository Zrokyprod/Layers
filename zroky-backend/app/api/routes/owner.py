"""
Owner Dashboard API — all endpoints under /v1/owner/
Protected by require_provisioning_access (PROVISIONING_TOKEN).
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

from app.api.dependencies.provisioning import require_provisioning_access
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import (
    ApiKey, AuditLog, Call, FeatureFlag, Notification,
    PlatformLlmUsage, Project, ProjectMembership,
    SubscriptionPlan, SupportMessage, SupportTicket,
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


# ─── Schemas ──────────────────────────────────────────────────────────────────


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


# ─── Health ───────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
def owner_health(
    _: None = Depends(require_provisioning_access),
) -> HealthResponse:
    services: list[ServiceStatus] = []
    overall = "ok"

    # Database
    t0 = time.perf_counter()
    db_ok = db_healthcheck()
    db_latency = round((time.perf_counter() - t0) * 1000, 1)
    services.append(ServiceStatus(
        name="PostgreSQL",
        status="ok" if db_ok else "down",
        latency_ms=db_latency,
        detail=None if db_ok else "Ping failed",
    ))
    if not db_ok:
        overall = "degraded"

    # Redis
    t0 = time.perf_counter()
    redis_ok = _redis_ok()
    redis_latency = round((time.perf_counter() - t0) * 1000, 1)
    services.append(ServiceStatus(
        name="Redis",
        status="ok" if redis_ok else "down",
        latency_ms=redis_latency,
        detail=None if redis_ok else "Ping failed",
    ))
    if not redis_ok:
        overall = "degraded"

    # Celery workers
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active() or {}
        worker_count = len(active)
        worker_status = "ok" if worker_count > 0 else "down"
        worker_detail = f"{worker_count} worker(s) active" if worker_count > 0 else "No workers responding"
    except Exception as exc:
        worker_status = "unknown"
        worker_detail = str(exc)[:80]
        worker_count = 0
    services.append(ServiceStatus(name="Celery", status=worker_status, detail=worker_detail))
    if worker_status in ("down", "unknown"):
        overall = "degraded"

    # Exchange rate
    exchange_snap = get_exchange_rate_debug_snapshot()
    er_usable = exchange_snap.get("cache_is_usable", False)
    er_stale = exchange_snap.get("cache_is_stale", True)
    er_status = "ok" if er_usable else ("degraded" if not er_stale else "down")
    er_age = exchange_snap.get("cache_age_seconds")
    services.append(ServiceStatus(
        name="Exchange Rate",
        status=er_status,
        detail=f"Age: {er_age}s" if er_age is not None else "No cache",
    ))
    if er_status != "ok":
        overall = "degraded"

    # Maintenance mode
    maintenance = False
    maintenance_msg = None
    if redis_ok:
        try:
            raw = get_redis_client().get(_MAINTENANCE_KEY)
            if raw:
                data = json.loads(raw)
                maintenance = bool(data.get("enabled", False))
                maintenance_msg = data.get("message")
        except Exception:
            pass

    return HealthResponse(
        overall=overall,
        services=services,
        exchange_rate=exchange_snap,
        maintenance_mode=maintenance,
        checked_at=datetime.now(UTC),
    )


@router.post("/maintenance", response_model=MaintenanceModeResponse)
@limiter.limit("10/minute")
def set_maintenance_mode(
    request: Request,
    body: MaintenanceModeRequest,
    _: None = Depends(require_provisioning_access),
) -> MaintenanceModeResponse:
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    payload = json.dumps({"enabled": body.enabled, "message": body.message})
    get_redis_client().set(_MAINTENANCE_KEY, payload)
    return MaintenanceModeResponse(enabled=body.enabled, message=body.message)


# ─── Infrastructure Stats ─────────────────────────────────────────────────────


@router.get("/infra", response_model=InfraStatsResponse)
def owner_infra(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> InfraStatsResponse:
    # Celery workers
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active() or {}
        worker_count = len(active)
        worker_names = list(active.keys())
    except Exception:
        worker_count = 0
        worker_names = []

    # Queue depths (Redis-based)
    queues: list[QueueStats] = []
    if _redis_ok():
        r = get_redis_client()
        for q_name in ("diagnosis_fast", "diagnosis_pattern", "celery"):
            try:
                pending = r.llen(q_name) or 0
            except Exception:
                pending = 0
            # Failed tasks in Redis (result backend stores them with status FAILURE)
            # Failed-task counts require Celery Flower or result-backend scanning;
            # setting to 0 here to avoid misleading data from inspect.reserved().
            queues.append(QueueStats(queue_name=q_name, pending=pending, failed=0))

    # DB table row counts (fast — uses pg stats when available)
    table_names = ["calls", "users", "projects", "api_keys", "project_memberships",
                   "diagnosis_jobs", "audit_logs", "project_alerts"]
    db_table_sizes: dict[str, int] = {}
    for table in table_names:
        try:
            count = db.scalar(text(f"SELECT COUNT(*) FROM {table}")) or 0
            db_table_sizes[table] = int(count)
        except Exception:
            db_table_sizes[table] = -1

    return InfraStatsResponse(
        queues=queues,
        worker_count=worker_count,
        worker_names=worker_names,
        db_table_sizes=db_table_sizes,
    )


# ─── Platform Stats ───────────────────────────────────────────────────────────


@router.get("/stats", response_model=OwnerStatsResponse)
def owner_stats(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerStatsResponse:
    cutoff = datetime.now(UTC) - timedelta(days=7)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    total_calls = db.scalar(select(func.count()).select_from(Call)) or 0
    calls_last_7d = db.scalar(
        select(func.count()).select_from(Call).where(Call.created_at >= cutoff)
    ) or 0
    total_cost_usd = float(db.scalar(select(func.sum(Call.cost_total))) or 0.0)
    cost_last_7d_usd = float(
        db.scalar(select(func.sum(Call.cost_total)).where(Call.created_at >= cutoff)) or 0.0
    )
    new_users_last_7d = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= cutoff)
    ) or 0
    # Active = member of a project that had at least one call in the last 7 days
    active_users_last_7d = db.scalar(
        select(func.count(func.distinct(ProjectMembership.user_id)))
        .where(
            ProjectMembership.project_id.in_(
                select(Call.project_id).where(Call.created_at >= cutoff).distinct()
            )
        )
        .where(ProjectMembership.is_active.is_(True))
    ) or 0

    return OwnerStatsResponse(
        total_users=total_users,
        total_projects=total_projects,
        total_calls=total_calls,
        calls_last_7d=calls_last_7d,
        total_cost_usd=total_cost_usd,
        cost_last_7d_usd=cost_last_7d_usd,
        new_users_last_7d=new_users_last_7d,
        active_users_last_7d=active_users_last_7d,
    )


# ─── Users ────────────────────────────────────────────────────────────────────


@router.get("/users", response_model=OwnerUsersResponse)
def owner_users(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=128),
    is_active: bool | None = Query(default=None),
) -> OwnerUsersResponse:
    pcount_subq = (
        select(ProjectMembership.user_id, func.count().label("pcount"))
        .group_by(ProjectMembership.user_id)
        .subquery()
    )
    base_q = (
        select(User, func.coalesce(pcount_subq.c.pcount, 0).label("project_count"))
        .outerjoin(pcount_subq, pcount_subq.c.user_id == User.id)
    )
    count_q = select(func.count()).select_from(User)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(User.display_name.ilike(pattern), User.github_login.ilike(pattern))
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    if is_active is not None:
        base_q = base_q.where(User.is_active.is_(is_active))
        count_q = count_q.where(User.is_active.is_(is_active))

    total = db.scalar(count_q) or 0
    rows = db.execute(base_q.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    result = [
        OwnerUserItem(
            id=u.id, email=u.email, github_login=u.github_login,
            display_name=u.display_name, is_active=u.is_active,
            created_at=u.created_at, project_count=int(pc),
        )
        for u, pc in rows
    ]
    return OwnerUsersResponse(users=result, total=total)


@router.get("/users/{user_id}", response_model=OwnerUserItem)
def owner_user_detail(
    user_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerUserItem:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    pcount = db.scalar(
        select(func.count()).select_from(ProjectMembership).where(ProjectMembership.user_id == u.id)
    ) or 0
    return OwnerUserItem(
        id=u.id, email=u.email, github_login=u.github_login, display_name=u.display_name,
        is_active=u.is_active, created_at=u.created_at, project_count=pcount,
    )


class UserStatusRequest(BaseModel):
    is_active: bool
    reason: str | None = None


@router.patch("/users/{user_id}/status")
@limiter.limit("10/minute")
def owner_update_user_status(
    request: Request,
    user_id: str,
    body: UserStatusRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    previous = bool(u.is_active)
    u.is_active = body.is_active  # type: ignore[assignment]
    _owner_audit(
        db,
        action="owner.user.activate" if body.is_active else "owner.user.deactivate",
        actor=_resolve_actor(request),
        target_id=user_id,
        metadata={"reason": body.reason, "previous_is_active": previous},
    )
    db.commit()
    return {"ok": True, "user_id": user_id, "is_active": body.is_active}


# ─── Projects ─────────────────────────────────────────────────────────────────


@router.get("/projects", response_model=OwnerProjectsResponse)
def owner_projects(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=128),
    is_active: bool | None = Query(default=None),
) -> OwnerProjectsResponse:
    call_stats_subq = (
        select(
            Call.project_id,
            func.count().label("call_count"),
            func.coalesce(func.sum(Call.cost_total), 0).label("total_cost"),
        )
        .group_by(Call.project_id)
        .subquery()
    )
    member_count_subq = (
        select(ProjectMembership.project_id, func.count().label("member_count"))
        .group_by(ProjectMembership.project_id)
        .subquery()
    )
    base_q = (
        select(
            Project,
            func.coalesce(call_stats_subq.c.call_count, 0).label("call_count"),
            func.coalesce(call_stats_subq.c.total_cost, 0.0).label("total_cost"),
            func.coalesce(member_count_subq.c.member_count, 0).label("member_count"),
        )
        .outerjoin(call_stats_subq, call_stats_subq.c.project_id == Project.id)
        .outerjoin(member_count_subq, member_count_subq.c.project_id == Project.id)
    )
    count_q = select(func.count()).select_from(Project)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(Project.name.ilike(pattern), Project.owner_ref.ilike(pattern))
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    if is_active is not None:
        base_q = base_q.where(Project.is_active.is_(is_active))
        count_q = count_q.where(Project.is_active.is_(is_active))

    total = db.scalar(count_q) or 0
    rows = db.execute(base_q.order_by(Project.created_at.desc()).limit(limit).offset(offset)).all()
    result = [
        OwnerProjectItem(
            id=p.id, name=p.name, owner_ref=p.owner_ref, is_active=p.is_active,
            created_at=p.created_at, call_count=int(cc), total_cost_usd=float(tc), member_count=int(mc),
        )
        for p, cc, tc, mc in rows
    ]
    return OwnerProjectsResponse(projects=result, total=total)


# ─── User Memberships (for user detail page) ──────────────────────────────────


class UserMembershipItem(BaseModel):
    project_id: str
    project_name: str
    role: str
    is_active: bool
    joined_at: datetime


class UserMembershipsResponse(BaseModel):
    memberships: list[UserMembershipItem]


@router.get("/users/{user_id}/memberships", response_model=UserMembershipsResponse)
def owner_user_memberships(
    user_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> UserMembershipsResponse:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    rows = db.execute(
        select(ProjectMembership, Project.name)
        .join(Project, Project.id == ProjectMembership.project_id)
        .where(ProjectMembership.user_id == user_id)
        .order_by(ProjectMembership.created_at.desc())
    ).all()
    items = [
        UserMembershipItem(
            project_id=mem.project_id,
            project_name=name,
            role=mem.role,
            is_active=mem.is_active,
            joined_at=mem.created_at,
        )
        for mem, name in rows
    ]
    return UserMembershipsResponse(memberships=items)


# ─── Project Detail ───────────────────────────────────────────────────────────


@router.get("/projects/{project_id}", response_model=OwnerProjectItem)
def owner_project_detail(
    project_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerProjectItem:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    call_count = db.scalar(select(func.count()).select_from(Call).where(Call.project_id == p.id)) or 0
    total_cost = float(db.scalar(select(func.sum(Call.cost_total)).where(Call.project_id == p.id)) or 0.0)
    member_count = db.scalar(
        select(func.count()).select_from(ProjectMembership).where(ProjectMembership.project_id == p.id)
    ) or 0
    return OwnerProjectItem(
        id=p.id, name=p.name, owner_ref=p.owner_ref, is_active=p.is_active,
        created_at=p.created_at, call_count=call_count, total_cost_usd=total_cost,
        member_count=member_count,
    )


class ProjectStatusRequest(BaseModel):
    is_active: bool
    reason: str | None = None


@router.patch("/projects/{project_id}/status")
@limiter.limit("10/minute")
def owner_update_project_status(
    request: Request,
    project_id: str,
    body: ProjectStatusRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    previous = bool(p.is_active)
    p.is_active = body.is_active  # type: ignore[assignment]
    _owner_audit(
        db,
        action="owner.project.activate" if body.is_active else "owner.project.deactivate",
        actor=_resolve_actor(request),
        target_id=project_id,
        metadata={"reason": body.reason, "project_name": p.name, "previous_is_active": previous},
    )
    db.commit()
    return {"ok": True, "project_id": project_id, "is_active": body.is_active}


class ProjectMemberItem(BaseModel):
    membership_id: str
    user_id: str
    email: str | None
    github_login: str | None
    display_name: str | None
    role: str
    is_active: bool
    joined_at: datetime


class ProjectMembersResponse(BaseModel):
    members: list[ProjectMemberItem]


@router.get("/projects/{project_id}/members", response_model=ProjectMembersResponse)
def owner_project_members(
    project_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> ProjectMembersResponse:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    rows = db.execute(
        select(ProjectMembership, User)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project_id)
        .order_by(ProjectMembership.created_at.desc())
    ).all()
    items = [
        ProjectMemberItem(
            membership_id=mem.id,
            user_id=user.id,
            email=user.email,
            github_login=user.github_login,
            display_name=user.display_name,
            role=mem.role,
            is_active=mem.is_active,
            joined_at=mem.created_at,
        )
        for mem, user in rows
    ]
    return ProjectMembersResponse(members=items)


# ─── Pricing Config ───────────────────────────────────────────────────────────

_DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[4] / "pricing_config.json"


def _pricing_config_path() -> Path:
    env_path = os.environ.get("PRICING_CONFIG_PATH", "")
    if env_path:
        return Path(env_path)
    return _DEFAULT_PRICING_PATH


class PricingConfigResponse(BaseModel):
    config: dict[str, Any]
    path: str
    exists: bool


_PRICING_CONFIG_KEY = "zroky:owner:pricing_config"


@router.get("/pricing", response_model=PricingConfigResponse)
def owner_get_pricing(
    _: None = Depends(require_provisioning_access),
) -> PricingConfigResponse:
    if _redis_ok():
        try:
            raw = get_redis_client().get(_PRICING_CONFIG_KEY)
            if raw:
                return PricingConfigResponse(config=json.loads(raw), path="redis", exists=True)
        except Exception:
            pass
    # Filesystem fallback (migrate to Redis on first read)
    p = _pricing_config_path()
    if not p.exists():
        return PricingConfigResponse(config={}, path=str(p), exists=False)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if _redis_ok():
            try:
                get_redis_client().set(_PRICING_CONFIG_KEY, json.dumps(data))
            except Exception:
                pass
        return PricingConfigResponse(config=data, path=str(p), exists=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read pricing config: {exc}")


class PricingConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


@router.put("/pricing", response_model=PricingConfigResponse)
@limiter.limit("10/minute")
def owner_update_pricing(
    request: Request,
    body: PricingConfigUpdateRequest,
    _: None = Depends(require_provisioning_access),
) -> PricingConfigResponse:
    if not _redis_ok():
        raise HTTPException(status_code=503, detail="Redis unavailable — cannot persist pricing config")
    try:
        get_redis_client().set(_PRICING_CONFIG_KEY, json.dumps(body.config, indent=2))
        return PricingConfigResponse(config=body.config, path="redis", exists=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write pricing config: {exc}")


# ─── Audit Helpers ────────────────────────────────────────────────────────────


def _resolve_actor(request: Request) -> str:
    from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token
    token = extract_bearer_token(request)
    if token:
        try:
            ctx = build_identity_context(decode_jwt_claims(token))
            if ctx.subject:
                return ctx.subject
        except Exception:
            pass
    return "provisioning_token"


def _owner_audit(
    db: Session,
    *,
    action: str,
    actor: str,
    target_id: str,
    metadata: dict[str, Any],
) -> None:
    db.add(AuditLog(
        tenant_id="PLATFORM",
        diagnosis_id="owner_action",
        action=action,
        actor_subject=actor,
        metadata_json=json.dumps({"target_id": target_id, **metadata}, default=str),
    ))


# ─── Rate Limits & Protection Config ─────────────────────────────────────────

_RATE_LIMIT_OVERRIDE_KEY = "zroky:owner:rate_limit_overrides"


class RateLimitConfig(BaseModel):
    ingest_soft_limit_rpm: int
    ingest_burst_limit_rpm: int
    ingest_rate_limit_window_seconds: int
    ingest_sustained_breach_threshold: int
    ingest_backpressure_ttl_seconds: int
    ingest_enforce_rate_limit: bool
    # Runtime overrides stored in Redis (None means "use env default")
    overrides: dict[str, Any]


@router.get("/rate-limits", response_model=RateLimitConfig)
def owner_get_rate_limits(
    _: None = Depends(require_provisioning_access),
) -> RateLimitConfig:
    s = get_settings()
    overrides: dict[str, Any] = {}
    if _redis_ok():
        try:
            raw = get_redis_client().get(_RATE_LIMIT_OVERRIDE_KEY)
            if raw:
                overrides = json.loads(raw)
        except Exception:
            pass
    return RateLimitConfig(
        ingest_soft_limit_rpm=overrides.get("ingest_soft_limit_rpm", s.INGEST_SOFT_LIMIT_RPM),
        ingest_burst_limit_rpm=overrides.get("ingest_burst_limit_rpm", s.INGEST_BURST_LIMIT_RPM),
        ingest_rate_limit_window_seconds=overrides.get(
            "ingest_rate_limit_window_seconds", s.INGEST_RATE_LIMIT_WINDOW_SECONDS
        ),
        ingest_sustained_breach_threshold=overrides.get(
            "ingest_sustained_breach_threshold", s.INGEST_SUSTAINED_BREACH_THRESHOLD
        ),
        ingest_backpressure_ttl_seconds=overrides.get(
            "ingest_backpressure_ttl_seconds", s.INGEST_BACKPRESSURE_TTL_SECONDS
        ),
        ingest_enforce_rate_limit=overrides.get("ingest_enforce_rate_limit", s.INGEST_ENFORCE_RATE_LIMIT),
        overrides=overrides,
    )


class RateLimitOverrideRequest(BaseModel):
    overrides: dict[str, Any]


@router.put("/rate-limits/overrides")
@limiter.limit("10/minute")
def owner_set_rate_limit_overrides(
    request: Request,
    body: RateLimitOverrideRequest,
    _: None = Depends(require_provisioning_access),
) -> dict:
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    # Validate keys
    allowed_keys = {
        "ingest_soft_limit_rpm", "ingest_burst_limit_rpm", "ingest_rate_limit_window_seconds",
        "ingest_sustained_breach_threshold", "ingest_backpressure_ttl_seconds", "ingest_enforce_rate_limit",
    }
    bad_keys = set(body.overrides.keys()) - allowed_keys
    if bad_keys:
        raise HTTPException(status_code=400, detail=f"Unknown override keys: {bad_keys}")
    get_redis_client().set(_RATE_LIMIT_OVERRIDE_KEY, json.dumps(body.overrides))
    return {"ok": True, "overrides": body.overrides}


@router.delete("/rate-limits/overrides")
@limiter.limit("10/minute")
def owner_clear_rate_limit_overrides(
    request: Request,
    _: None = Depends(require_provisioning_access),
) -> dict:
    if _redis_ok():
        get_redis_client().delete(_RATE_LIMIT_OVERRIDE_KEY)
    return {"ok": True}


# ─── Audit Log ────────────────────────────────────────────────────────────────


class AuditLogItem(BaseModel):
    id: str
    tenant_id: str
    diagnosis_id: str
    action: str
    actor_subject: str | None
    metadata_json: str
    created_at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogItem]
    total: int


@router.get("/audit-log", response_model=AuditLogResponse)
def owner_audit_log(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    tenant_id: str | None = None,
) -> AuditLogResponse:
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_q = select(func.count()).select_from(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
        count_q = count_q.where(AuditLog.action == action)
    if tenant_id:
        q = q.where(AuditLog.tenant_id == tenant_id)
        count_q = count_q.where(AuditLog.tenant_id == tenant_id)
    total = db.scalar(count_q) or 0
    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()
    return AuditLogResponse(
        entries=[
            AuditLogItem(
                id=e.id, tenant_id=e.tenant_id, diagnosis_id=e.diagnosis_id,
                action=e.action, actor_subject=e.actor_subject,
                metadata_json=e.metadata_json, created_at=e.created_at,
            )
            for e in rows
        ],
        total=total,
    )


# ─── Platform LLM Usage (self-observability) ──────────────────────────────────


class PlatformLlmUsageItem(BaseModel):
    id: str
    purpose: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float | None
    tenant_id: str | None
    diagnosis_id: str | None
    created_at: datetime


class PlatformLlmUsageSummaryResponse(BaseModel):
    total_calls: int
    total_cost_usd: float
    total_tokens: int
    avg_latency_ms: float
    by_purpose: dict[str, dict[str, Any]]
    by_model: dict[str, dict[str, Any]]
    recent: list[PlatformLlmUsageItem]


@router.get("/platform-llm-usage", response_model=PlatformLlmUsageSummaryResponse)
def owner_platform_llm_usage(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = 100,
) -> PlatformLlmUsageSummaryResponse:
    """Summarize ZROKY's own LLM usage (fix generation, assistant, analytics, etc.)."""
    total_calls = db.scalar(select(func.count()).select_from(PlatformLlmUsage)) or 0
    total_cost = db.scalar(select(func.sum(PlatformLlmUsage.cost_usd))) or 0.0
    total_tokens = db.scalar(select(func.sum(PlatformLlmUsage.total_tokens))) or 0
    avg_latency = db.scalar(select(func.avg(PlatformLlmUsage.latency_ms))) or 0.0

    # Purpose breakdown
    by_purpose: dict[str, dict[str, Any]] = {}
    purpose_rows = db.execute(
        select(PlatformLlmUsage.purpose, func.count(), func.sum(PlatformLlmUsage.cost_usd), func.sum(PlatformLlmUsage.total_tokens))
        .group_by(PlatformLlmUsage.purpose)
    ).all()
    for purpose, calls, cost, tokens in purpose_rows:
        by_purpose[purpose] = {
            "calls": int(calls or 0),
            "cost_usd": float(cost or 0.0),
            "tokens": int(tokens or 0),
        }

    # Model breakdown
    by_model: dict[str, dict[str, Any]] = {}
    model_rows = db.execute(
        select(PlatformLlmUsage.model, func.count(), func.sum(PlatformLlmUsage.cost_usd), func.sum(PlatformLlmUsage.total_tokens))
        .group_by(PlatformLlmUsage.model)
    ).all()
    for model, calls, cost, tokens in model_rows:
        by_model[model or "unknown"] = {
            "calls": int(calls or 0),
            "cost_usd": float(cost or 0.0),
            "tokens": int(tokens or 0),
        }

    recent_rows = db.execute(
        select(PlatformLlmUsage).order_by(PlatformLlmUsage.created_at.desc()).limit(limit)
    ).scalars().all()

    return PlatformLlmUsageSummaryResponse(
        total_calls=int(total_calls),
        total_cost_usd=float(total_cost),
        total_tokens=int(total_tokens),
        avg_latency_ms=float(avg_latency),
        by_purpose=by_purpose,
        by_model=by_model,
        recent=[
            PlatformLlmUsageItem(
                id=r.id,
                purpose=r.purpose,
                provider=r.provider,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                cost_usd=float(r.cost_usd),
                latency_ms=r.latency_ms,
                tenant_id=r.tenant_id,
                diagnosis_id=r.diagnosis_id,
                created_at=r.created_at,
            )
            for r in recent_rows
        ],
    )


# ─── Support Tickets (Owner View) ────────────────────────────────────────────


class OwnerSupportTicketUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None


class OwnerSupportReplyRequest(BaseModel):
    body: str
    is_internal: bool = False


@router.get("/support/tickets")
def owner_list_support_tickets(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    ticket_status: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    q = select(SupportTicket).order_by(SupportTicket.created_at.desc())
    count_q = select(func.count()).select_from(SupportTicket)
    if ticket_status:
        q = q.where(SupportTicket.status == ticket_status)
        count_q = count_q.where(SupportTicket.status == ticket_status)
    if priority:
        q = q.where(SupportTicket.priority == priority)
        count_q = count_q.where(SupportTicket.priority == priority)
    if tenant_id:
        q = q.where(SupportTicket.tenant_id == tenant_id)
        count_q = count_q.where(SupportTicket.tenant_id == tenant_id)
    if assigned_to:
        q = q.where(SupportTicket.assigned_to == assigned_to)
        count_q = count_q.where(SupportTicket.assigned_to == assigned_to)
    total = db.scalar(count_q) or 0
    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "ticket_id": t.id, "tenant_id": t.tenant_id, "title": t.title,
                "category": t.category, "priority": t.priority, "status": t.status,
                "assigned_to": t.assigned_to, "created_at": t.created_at,
                "updated_at": t.updated_at, "message_count": len(t.messages),
            }
            for t in rows
        ],
    }


@router.patch("/support/tickets/{ticket_id}")
@limiter.limit("20/minute")
def owner_update_support_ticket(
    request: Request,
    ticket_id: str,
    body: OwnerSupportTicketUpdateRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    ticket = db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id))
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if body.status is not None:
        ticket.status = body.status
        if body.status == "resolved" and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(UTC)
    if body.priority is not None:
        ticket.priority = body.priority
    if body.assigned_to is not None:
        ticket.assigned_to = body.assigned_to
    _owner_audit(db, action="owner.support.ticket.update", actor=_resolve_actor(request),
                 target_id=ticket_id, metadata={"status": body.status, "assigned_to": body.assigned_to})
    db.commit()
    return {"ok": True, "ticket_id": ticket_id, "status": ticket.status}


@router.post("/support/tickets/{ticket_id}/reply", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def owner_reply_support_ticket(
    request: Request,
    ticket_id: str,
    body: OwnerSupportReplyRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    ticket = db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id))
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    msg = SupportMessage(
        ticket_id=ticket_id,
        sender_type="owner",
        sender_subject=_resolve_actor(request),
        body=body.body,
        is_internal=body.is_internal,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "message_id": msg.id, "ticket_id": ticket_id}


# ─── Billing Platform Summary ──────────────────────────────────────────────────


@router.get("/billing/summary")
def owner_billing_summary(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    plan_rows = db.execute(
        select(
            SubscriptionPlan.name,
            SubscriptionPlan.slug,
            func.count(TenantSubscription.id).label("tenant_count"),
        )
        .outerjoin(TenantSubscription, TenantSubscription.plan_id == SubscriptionPlan.id)
        .where(SubscriptionPlan.is_active.is_(True))
        .group_by(SubscriptionPlan.name, SubscriptionPlan.slug)
        .order_by(SubscriptionPlan.slug)
    ).all()

    status_rows = db.execute(
        select(TenantSubscription.status, func.count().label("count"))
        .group_by(TenantSubscription.status)
    ).all()

    total_subscriptions = db.scalar(select(func.count()).select_from(TenantSubscription)) or 0
    overdue = db.scalar(
        select(func.count()).select_from(TenantSubscription)
        .where(TenantSubscription.status == "past_due")
    ) or 0
    canceled = db.scalar(
        select(func.count()).select_from(TenantSubscription)
        .where(TenantSubscription.status == "canceled")
    ) or 0

    return {
        "total_subscriptions": total_subscriptions,
        "overdue": overdue,
        "canceled": canceled,
        "by_plan": [
            {"plan": name, "slug": slug, "tenant_count": int(count)}
            for name, slug, count in plan_rows
        ],
        "by_status": [
            {"status": s, "count": int(c)} for s, c in status_rows
        ],
    }


# ─── Per-Tenant Rate Limit Overrides ─────────────────────────────────────────

_TENANT_RATE_LIMIT_KEY = "zroky:tenant:rate_limit:{project_id}"


class TenantRateLimitRequest(BaseModel):
    ingest_soft_limit_rpm: int | None = None
    ingest_burst_limit_rpm: int | None = None
    ingest_enforce_rate_limit: bool | None = None


@router.get("/projects/{project_id}/rate-limit")
def owner_get_tenant_rate_limit(
    project_id: str,
    _: None = Depends(require_provisioning_access),
) -> dict:
    key = _TENANT_RATE_LIMIT_KEY.format(project_id=project_id)
    overrides: dict = {}
    if _redis_ok():
        try:
            raw = get_redis_client().get(key)
            if raw:
                overrides = json.loads(raw)
        except Exception:
            pass
    return {"project_id": project_id, "overrides": overrides, "has_override": bool(overrides)}


@router.put("/projects/{project_id}/rate-limit")
@limiter.limit("10/minute")
def owner_set_tenant_rate_limit(
    request: Request,
    project_id: str,
    body: TenantRateLimitRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    overrides = {k: v for k, v in body.model_dump().items() if v is not None}
    key = _TENANT_RATE_LIMIT_KEY.format(project_id=project_id)
    get_redis_client().set(key, json.dumps(overrides))
    _owner_audit(db, action="owner.tenant.rate_limit.set", actor=_resolve_actor(request),
                 target_id=project_id, metadata={"overrides": overrides})
    db.commit()
    return {"ok": True, "project_id": project_id, "overrides": overrides}


@router.delete("/projects/{project_id}/rate-limit")
@limiter.limit("10/minute")
def owner_clear_tenant_rate_limit(
    request: Request,
    project_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if _redis_ok():
        get_redis_client().delete(_TENANT_RATE_LIMIT_KEY.format(project_id=project_id))
    _owner_audit(db, action="owner.tenant.rate_limit.clear", actor=_resolve_actor(request),
                 target_id=project_id, metadata={})
    db.commit()
    return {"ok": True, "project_id": project_id}


# ─── GDPR / User Data Management ──────────────────────────────────────────────


@router.post("/users/{user_id}/anonymize")
@limiter.limit("10/minute")
def owner_anonymize_user(
    request: Request,
    user_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    u.email = None  # type: ignore[assignment]
    u.email_hash = None  # type: ignore[assignment]
    u.display_name = "Deleted User"  # type: ignore[assignment]
    u.github_id = None  # type: ignore[assignment]
    u.google_id = None  # type: ignore[assignment]
    u.github_login = None  # type: ignore[assignment]
    u.github_token_encrypted = None  # type: ignore[assignment]
    u.github_token_scopes = None  # type: ignore[assignment]
    u.github_token_connected_at = None  # type: ignore[assignment]
    u.github_token_updated_at = None  # type: ignore[assignment]
    u.is_active = False  # type: ignore[assignment]
    _owner_audit(db, action="owner.user.anonymize", actor=_resolve_actor(request),
                 target_id=user_id, metadata={})
    db.commit()
    return {"ok": True, "user_id": user_id, "action": "anonymized"}


@router.delete("/users/{user_id}")
@limiter.limit("5/minute")
def owner_delete_user(
    request: Request,
    user_id: str,
    confirm: str = Query(..., description="Must be 'DELETE_CONFIRMED'"),
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if confirm != "DELETE_CONFIRMED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass ?confirm=DELETE_CONFIRMED to hard-delete a user.",
        )
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _owner_audit(db, action="owner.user.delete", actor=_resolve_actor(request),
                 target_id=user_id, metadata={"subject": u.subject})
    db.flush()
    db.delete(u)
    db.commit()
    return {"ok": True, "user_id": user_id, "action": "deleted"}


# ─── Celery Task Management ───────────────────────────────────────────────────

_ALLOWED_QUEUES = {"diagnosis_fast", "diagnosis_pattern", "celery"}


class RevokeTaskRequest(BaseModel):
    terminate: bool = False


@router.delete("/queues/{queue_name}/purge")
@limiter.limit("5/minute")
def owner_purge_queue(
    request: Request,
    queue_name: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if queue_name not in _ALLOWED_QUEUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown queue. Allowed: {sorted(_ALLOWED_QUEUES)}",
        )
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    deleted = get_redis_client().delete(queue_name)
    _owner_audit(db, action="owner.queue.purge", actor=_resolve_actor(request),
                 target_id=queue_name, metadata={"deleted_keys": deleted})
    db.commit()
    return {"ok": True, "queue": queue_name, "deleted_keys": int(deleted)}


@router.post("/tasks/{task_id}/revoke")
@limiter.limit("20/minute")
def owner_revoke_task(
    request: Request,
    task_id: str,
    body: RevokeTaskRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        celery_app.control.revoke(
            task_id,
            terminate=body.terminate,
            signal="SIGKILL" if body.terminate else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Celery revoke failed: {exc}") from exc
    _owner_audit(db, action="owner.task.revoke", actor=_resolve_actor(request),
                 target_id=task_id, metadata={"terminate": body.terminate})
    db.commit()
    return {"ok": True, "task_id": task_id, "terminate": body.terminate}


# ─── Broadcast Notifications ──────────────────────────────────────────────────


class BroadcastRequest(BaseModel):
    title: str
    body: str | None = None
    category: str = "announcement"
    action_url: str | None = None
    tenant_ids: list[str] | None = None


@router.post("/broadcast", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def owner_broadcast(
    request: Request,
    body: BroadcastRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if body.tenant_ids:
        user_ids = list(db.scalars(
            select(ProjectMembership.user_id)
            .where(ProjectMembership.project_id.in_(body.tenant_ids))
            .where(ProjectMembership.is_active.is_(True))
            .distinct()
        ).all())
    else:
        user_ids = list(db.scalars(
            select(User.id).where(User.is_active.is_(True))
        ).all())

    for uid in user_ids:
        db.add(Notification(
            user_id=uid,
            title=body.title,
            body=body.body,
            category=body.category,
            action_url=body.action_url,
            is_read=False,
        ))
    _owner_audit(db, action="owner.broadcast", actor=_resolve_actor(request),
                 target_id="all" if not body.tenant_ids else ",".join(body.tenant_ids),
                 metadata={"title": body.title, "recipient_count": len(user_ids),
                            "tenant_ids": body.tenant_ids})
    db.commit()
    return {"ok": True, "sent_to": len(user_ids), "title": body.title}


# ─── Data Retention Config ────────────────────────────────────────────────────


@router.get("/retention")
def owner_retention_config(
    _: None = Depends(require_provisioning_access),
) -> dict:
    s = get_settings()
    return {
        "call_retention_days": getattr(s, "CALL_RETENTION_DAYS", None),
        "diagnosis_retention_days": getattr(s, "DIAGNOSIS_RETENTION_DAYS", None),
        "audit_log_retention_days": getattr(s, "AUDIT_LOG_RETENTION_DAYS", None),
        "notification_retention_days": getattr(s, "NOTIFICATION_RETENTION_DAYS", None),
        "note": "Retention is enforced by scheduled purge tasks. Contact infrastructure team to modify.",
    }
