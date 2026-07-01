from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import Project
from app.db.session import get_db_session, get_db_session_read
from app.schemas.agents import (
    AgentProfileCreateRequest,
    AgentProfileListResponse,
    AgentProfileResponse,
    AgentProfileUpdateRequest,
)
from app.services.agent_profiles import (
    AgentProfileConflict,
    AgentProfileLimitExceeded,
    AgentProfileMandateError,
    AgentProfileNotFound,
    AgentProfileValidationError,
    agent_profile_to_dict,
    apply_agent_setup_mandate,
    count_active_agent_profiles,
    create_agent_profile,
    deactivate_agent_profile,
    get_agent_profile,
    list_agent_profiles,
    resolve_agent_profile_limit,
    update_agent_profile,
)


router = APIRouter(prefix="/v1/agents")


def _require_role(context: TenantContext, minimum: str) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK[minimum]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant role '{context.role}' does not allow this action.",
        )


def _require_project(db: Session, project_id: str) -> None:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _response(row) -> AgentProfileResponse:
    return AgentProfileResponse(**agent_profile_to_dict(row))


@router.get("", response_model=AgentProfileListResponse)
@limiter.limit("120/minute")
def list_agents_route(
    request: Request,
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session_read),
) -> AgentProfileListResponse:
    _require_role(context, "viewer")
    _require_project(db, context.tenant_id)
    rows, total = list_agent_profiles(
        db,
        project_id=context.tenant_id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    active_count = count_active_agent_profiles(db, project_id=context.tenant_id)
    max_active_agents = resolve_agent_profile_limit(db, project_id=context.tenant_id)
    return AgentProfileListResponse(
        items=[_response(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        active_count=active_count,
        max_active_agents=max_active_agents,
        limit_reached=max_active_agents != -1 and active_count >= max_active_agents,
    )


@router.post("", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_agent_route(
    request: Request,
    body: AgentProfileCreateRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentProfileResponse:
    _require_role(context, "admin")
    _require_project(db, context.tenant_id)
    try:
        row = create_agent_profile(
            db,
            project_id=context.tenant_id,
            payload=body.model_dump(mode="json"),
            actor_subject=context.subject,
        )
    except AgentProfileConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AgentProfileLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc
    except AgentProfileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _response(row)


@router.post("/{agent_id}/enforce", response_model=AgentProfileResponse)
@limiter.limit("20/minute")
def enforce_agent_route(
    request: Request,
    agent_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentProfileResponse:
    _require_role(context, "admin")
    _require_project(db, context.tenant_id)
    try:
        row = apply_agent_setup_mandate(
            db,
            project_id=context.tenant_id,
            agent_id=agent_id,
            actor_subject=context.subject,
        )
    except AgentProfileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (AgentProfileMandateError, AgentProfileValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _response(row)


@router.get("/{agent_id}", response_model=AgentProfileResponse)
@limiter.limit("120/minute")
def get_agent_route(
    request: Request,
    agent_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session_read),
) -> AgentProfileResponse:
    _require_role(context, "viewer")
    _require_project(db, context.tenant_id)
    row = get_agent_profile(db, project_id=context.tenant_id, agent_id=agent_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent profile not found")
    return _response(row)


@router.patch("/{agent_id}", response_model=AgentProfileResponse)
@limiter.limit("30/minute")
def update_agent_route(
    request: Request,
    agent_id: str,
    body: AgentProfileUpdateRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentProfileResponse:
    _require_role(context, "admin")
    _require_project(db, context.tenant_id)
    try:
        row = update_agent_profile(
            db,
            project_id=context.tenant_id,
            agent_id=agent_id,
            payload=body.model_dump(mode="json", exclude_unset=True),
            actor_subject=context.subject,
        )
    except AgentProfileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentProfileConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AgentProfileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _response(row)


@router.delete("/{agent_id}", response_model=AgentProfileResponse)
@limiter.limit("20/minute")
def delete_agent_route(
    request: Request,
    agent_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> AgentProfileResponse:
    _require_role(context, "admin")
    _require_project(db, context.tenant_id)
    try:
        row = deactivate_agent_profile(
            db,
            project_id=context.tenant_id,
            agent_id=agent_id,
            actor_subject=context.subject,
        )
    except AgentProfileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response(row)
