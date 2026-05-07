import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import require_provisioning_access
from app.core.config import get_settings
from app.db.models import Call, Project, ProjectMembership, User
from app.db.session import get_db_session
from app.services.currency import get_exchange_rate_debug_snapshot

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


@router.get("/exchange-rate", include_in_schema=False)
def internal_exchange_rate(
    _: None = Depends(require_internal_debug_access),
) -> dict[str, object]:
    return get_exchange_rate_debug_snapshot()
