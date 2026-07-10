"""Owner-only lifecycle API for a project's managed MCP upstream."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import Settings, get_settings
from app.core.limiter import limiter
from app.db.models import McpUpstreamBinding
from app.db.session import get_db_session, get_db_session_read
from app.mcp.gateway import (
    HttpMcpBindingTester,
    McpBindingConflict,
    McpBindingError,
    McpBindingNotFound,
    McpBindingTester,
    activate_binding,
    disable_binding,
    get_project_binding,
    test_binding,
    upsert_draft_binding,
)


router = APIRouter(prefix="/v1/mcp-config")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class McpUpstreamDraftRequest(_StrictModel):
    endpoint_url: str = Field(min_length=8, max_length=2048)
    protocol_version: str = Field(default="2025-06-18", max_length=32)
    bearer_credential_id: str | None = Field(default=None, max_length=36)
    allowed_tools: list[str] = Field(default_factory=list, max_length=500)


class McpUpstreamBindingResponse(_StrictModel):
    endpoint_url: str
    protocol_version: str
    credential_configured: bool
    allowed_tools: list[str]
    status: str
    test_status: str
    tested_at: datetime | None
    last_test_error: str | None
    activated_at: datetime | None
    version: int
    created_at: datetime | None
    updated_at: datetime | None


class McpUpstreamPreflightResponse(_StrictModel):
    binding: McpUpstreamBindingResponse
    discovered_tools: list[str]


def get_mcp_binding_tester(settings: Settings = Depends(get_settings)) -> McpBindingTester:
    return HttpMcpBindingTester(timeout_seconds=settings.MCP_UPSTREAM_TIMEOUT_SECONDS)


def _require_owner(context: TenantContext) -> None:
    if context.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant owner role is required for MCP upstream configuration.",
        )


def _response(binding: McpUpstreamBinding) -> McpUpstreamBindingResponse:
    import json

    try:
        allowed_tools = json.loads(binding.allowed_tools_json or "[]")
    except (TypeError, ValueError):
        allowed_tools = []
    return McpUpstreamBindingResponse(
        endpoint_url=binding.endpoint_url,
        protocol_version=binding.protocol_version,
        credential_configured=binding.bearer_credential_id is not None,
        allowed_tools=list(allowed_tools) if isinstance(allowed_tools, list) else [],
        status=binding.status,
        test_status=binding.test_status,
        tested_at=binding.tested_at,
        last_test_error=binding.last_test_error,
        activated_at=binding.activated_at,
        version=binding.version,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _raise_binding_error(exc: Exception) -> None:
    if isinstance(exc, McpBindingNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP upstream binding was not found.") from exc
    if isinstance(exc, McpBindingConflict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, McpBindingError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


@router.get("/upstream", response_model=McpUpstreamBindingResponse)
@limiter.limit("60/minute")
def get_upstream_binding(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session_read),
) -> McpUpstreamBindingResponse:
    _require_owner(context)
    binding = get_project_binding(db, project_id=context.tenant_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP upstream binding was not found.")
    return _response(binding)


@router.put("/upstream", response_model=McpUpstreamBindingResponse)
@limiter.limit("12/minute")
def put_upstream_draft(
    request: Request,
    body: McpUpstreamDraftRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> McpUpstreamBindingResponse:
    _require_owner(context)
    try:
        binding = upsert_draft_binding(
            db,
            project_id=context.tenant_id,
            endpoint_url=body.endpoint_url,
            protocol_version=body.protocol_version,
            bearer_credential_id=body.bearer_credential_id,
            allowed_tools=body.allowed_tools,
            actor_subject=context.subject,
        )
    except Exception as exc:
        _raise_binding_error(exc)
    return _response(binding)


@router.post("/upstream/preflight", response_model=McpUpstreamPreflightResponse)
@limiter.limit("6/minute")
def preflight_upstream(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
    tester: McpBindingTester = Depends(get_mcp_binding_tester),
) -> McpUpstreamPreflightResponse:
    _require_owner(context)
    try:
        binding, discovered_tools = test_binding(
            db, project_id=context.tenant_id, tester=tester
        )
    except Exception as exc:
        _raise_binding_error(exc)
    return McpUpstreamPreflightResponse(binding=_response(binding), discovered_tools=discovered_tools)


@router.post("/upstream/activate", response_model=McpUpstreamBindingResponse)
@limiter.limit("12/minute")
def activate_upstream(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> McpUpstreamBindingResponse:
    _require_owner(context)
    try:
        binding = activate_binding(
            db, project_id=context.tenant_id, actor_subject=context.subject
        )
    except Exception as exc:
        _raise_binding_error(exc)
    return _response(binding)


@router.post("/upstream/disable", response_model=McpUpstreamBindingResponse)
@limiter.limit("12/minute")
def disable_upstream(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> McpUpstreamBindingResponse:
    _require_owner(context)
    try:
        binding = disable_binding(
            db, project_id=context.tenant_id, actor_subject=context.subject
        )
    except Exception as exc:
        _raise_binding_error(exc)
    return _response(binding)
