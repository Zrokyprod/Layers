import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import require_provisioning_access
from app.core.config import get_settings
from app.db.models import Call, Project, ProjectMembership, User
from app.db.session import get_db_session, set_db_tenant_context
from app.services.digest_engine import (
    AUDIENCES,
    UnknownAudienceError,
    generate_weekly_digest,
    monday_of,
    serialize_digest,
)
from app.services.discovery.read_model import get_discovery_project_status

router = APIRouter(prefix="/internal")


# ---------------------------------------------------------------------------
# Owner Admin Schemas
# ---------------------------------------------------------------------------


class OwnerStatsResponse(BaseModel):
    total_users: int
    total_projects: int
    total_calls: int
    calls_last_7d: int
    total_cost_usd: float
    cost_last_7d_usd: float
    new_users_last_7d: int


class OwnerUserItem(BaseModel):
    id: str
    email: str | None
    github_login: str | None
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


class OwnerProjectsResponse(BaseModel):
    projects: list[OwnerProjectItem]
    total: int


class DigestGenerateRequest(BaseModel):
    project_id: str | None = None
    week_start: date | None = None
    audience: str | None = None


# ---------------------------------------------------------------------------
# Owner Admin Endpoints (protected by PROVISIONING_TOKEN)
# ---------------------------------------------------------------------------


@router.get("/owner/stats", response_model=OwnerStatsResponse)
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
    total_cost_usd = float(db.scalar(select(func.sum(Call.cost_total)).select_from(Call)) or 0.0)
    cost_last_7d_usd = float(
        db.scalar(select(func.sum(Call.cost_total)).select_from(Call).where(Call.created_at >= cutoff)) or 0.0
    )
    new_users_last_7d = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= cutoff)
    ) or 0

    return OwnerStatsResponse(
        total_users=total_users,
        total_projects=total_projects,
        total_calls=total_calls,
        calls_last_7d=calls_last_7d,
        total_cost_usd=total_cost_usd,
        cost_last_7d_usd=cost_last_7d_usd,
        new_users_last_7d=new_users_last_7d,
    )


@router.get("/owner/users", response_model=OwnerUsersResponse)
def owner_users(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = 100,
    offset: int = 0,
) -> OwnerUsersResponse:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)).scalars().all()

    result: list[OwnerUserItem] = []
    for u in rows:
        pcount = db.scalar(
            select(func.count()).select_from(ProjectMembership).where(ProjectMembership.user_id == u.id)
        ) or 0
        result.append(
            OwnerUserItem(
                id=u.id,
                email=u.email,
                github_login=u.github_login,
                is_active=u.is_active,
                created_at=u.created_at,
                project_count=pcount,
            )
        )

    return OwnerUsersResponse(users=result, total=total)


@router.get("/owner/projects", response_model=OwnerProjectsResponse)
def owner_projects(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = 100,
    offset: int = 0,
) -> OwnerProjectsResponse:
    total = db.scalar(select(func.count()).select_from(Project)) or 0
    rows = db.execute(select(Project).order_by(Project.created_at.desc()).limit(limit).offset(offset)).scalars().all()

    result: list[OwnerProjectItem] = []
    for p in rows:
        call_count = db.scalar(
            select(func.count()).select_from(Call).where(Call.project_id == p.id)
        ) or 0
        total_cost = float(
            db.scalar(select(func.sum(Call.cost_total)).select_from(Call).where(Call.project_id == p.id)) or 0.0
        )
        result.append(
            OwnerProjectItem(
                id=p.id,
                name=p.name,
                owner_ref=p.owner_ref,
                is_active=p.is_active,
                created_at=p.created_at,
                call_count=call_count,
                total_cost_usd=total_cost,
            )
        )

    return OwnerProjectsResponse(projects=result, total=total)


@router.post("/digests/generate", include_in_schema=False)
def generate_digest_internal(
    payload: DigestGenerateRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    week_start = monday_of(payload.week_start or datetime.now(UTC).date())
    audience = payload.audience.strip().lower() if payload.audience else None
    if audience is not None and audience not in AUDIENCES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid audience")

    if payload.project_id:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if not project.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Project is inactive")
        set_db_tenant_context(db, project.id)
        try:
            digest = generate_weekly_digest(
                db,
                project_id=project.id,
                week_start=week_start,
                audience=audience,
            )
        except UnknownAudienceError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "mode": "inline",
            "week_start": week_start.isoformat(),
            "digest": serialize_digest(digest),
        }

    from app.worker import tasks as task_module

    async_result = task_module.generate_weekly_digests.delay(week_start_iso=week_start.isoformat())
    return {
        "mode": "async",
        "week_start": week_start.isoformat(),
        "task_id": async_result.id,
    }


@router.get("/discovery/status", include_in_schema=False)
def discovery_status_internal(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    set_db_tenant_context(db, project_id)
    return get_discovery_project_status(
        db,
        project_id=project_id,
        anomaly_limit=limit,
    )


# ---------------------------------------------------------------------------
# Internal Debug (original endpoint)
# ---------------------------------------------------------------------------


def require_internal_debug_access(request: Request) -> None:
    settings = get_settings()

    if not settings.ENABLE_INTERNAL_DEBUG_ENDPOINT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal debug endpoint is disabled")

    expected_token = (settings.INTERNAL_DEBUG_TOKEN or "").strip()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal debug endpoint is misconfigured",
        )

    provided_token = request.headers.get(settings.INTERNAL_DEBUG_TOKEN_HEADER_NAME)
    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal debug credentials")


