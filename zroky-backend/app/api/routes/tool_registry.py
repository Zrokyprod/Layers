from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.core.limiter import limiter
from app.db.models import Project
from app.db.session import get_db_session_read
from app.schemas.tool_registry import ToolRegistryResponse
from app.services.agent_profiles import get_agent_profile
from app.services.tool_registry import build_tool_registry


router = APIRouter(prefix="/v1/tools")


@router.get("/registry", response_model=ToolRegistryResponse)
@limiter.limit("120/minute")
def get_tool_registry(
    request: Request,
    agent_id: str | None = Query(default=None, max_length=36),
    action_type: str | None = Query(default=None, max_length=64),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> ToolRegistryResponse:
    if db.get(Project, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    agent = None
    if agent_id:
        agent = get_agent_profile(db, project_id=tenant_id, agent_id=agent_id)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent profile not found")

    payload = build_tool_registry(
        agent,
        requested_action_type=action_type.strip().lower() if action_type else None,
    )
    return ToolRegistryResponse(project_id=tenant_id, **payload)
