"""FastAPI ingress for MCP interception — ``POST /v1/mcp/{project_id}``.

Production-dark by default: the route is registered but *inert* (404) unless
``Settings.MCP_INTERCEPTION_ENABLED`` is true, so shipping it changes no
behaviour until an operator opts a deployment in.

Auth: ``require_tenant_context`` resolves the caller's authorized tenant from
the bearer token / tenant header. The ``{project_id}`` in the path is then
checked against that authorized tenant — it is *validated, never trusted* —
so a caller cannot proxy MCP traffic for a project they do not belong to.

This ingress owns path + auth + kernel decision + upstream forwarding. When
an allowed call reaches upstream, ``McpPostExecutionProcessor`` records the
execution attempt, reconciles supplied SOR evidence, and generates a signed
receipt without changing the production-dark rollout posture.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.mcp.gate import McpSession
from app.mcp.kernel_adapter import DbKernelAdapter
from app.mcp.post_execution import McpPostExecutionProcessor
from app.mcp.persistence import DbEventSink, load_project_bindings
from app.mcp.proxy import UpstreamTransport, handle_message
from app.mcp.upstream import HttpMcpUpstream

router = APIRouter()
logger = logging.getLogger(__name__)


def get_mcp_upstream(settings: Settings = Depends(get_settings)) -> UpstreamTransport:
    """Deployment-wide upstream MCP server. Overridden in tests with a fake."""
    return HttpMcpUpstream(
        settings.MCP_UPSTREAM_URL, timeout_seconds=settings.MCP_UPSTREAM_TIMEOUT_SECONDS
    )


@router.post("/v1/mcp/{project_id}")
def mcp_ingress(
    project_id: str,
    message: dict[str, Any] = Body(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
    upstream: UpstreamTransport = Depends(get_mcp_upstream),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not settings.MCP_INTERCEPTION_ENABLED:
        # Inert until explicitly enabled — indistinguishable from "not mounted".
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    # The path project must be the caller's authorized tenant, not trusted input.
    if project_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for the requested project.",
        )

    mcp_request_id = str(uuid.uuid4())
    method = message.get("method")

    # JSON-RPC notifications (no id) get no response body.
    if message.get("id") is None and isinstance(method, str) and method.startswith("notifications/"):
        return {}

    session = McpSession(
        project_id=project_id,
        environment="production",
        agent_id=None,
        principal=({"type": "user", "id": context.subject} if context.subject else None),
        idempotency_key=_resolve_idempotency_key(idempotency_key, message),
    )

    response = handle_message(
        message,
        session=session,
        kernel=DbKernelAdapter(db),
        upstream=upstream,
        bindings=load_project_bindings(db, project_id),
        event_sink=DbEventSink(
            db, project_id=project_id, mcp_request_id=mcp_request_id, method=method or "unknown"
        ),
        post_execution=McpPostExecutionProcessor(
            db,
            actor=context.subject or "mcp-proxy",
        ),
    )

    _log_correlation(mcp_request_id, project_id, method, message, response)
    return response


def _resolve_idempotency_key(caller_token: str | None, message: dict[str, Any]) -> str | None:
    """Dedupe ONLY on an explicit caller-supplied token.

    We deliberately do NOT fall back to (MCP session id + JSON-RPC id): many
    clients reuse ``id: 1`` across requests, so keying on it would silently
    collapse two legitimate identical calls into one — the worst failure on a
    money rail. Absent an explicit token we return None → the adapter mints a
    fresh unique key → every call is a distinct action. Dedupe is opt-in.
    """
    if caller_token and caller_token.strip():
        return caller_token.strip()
    params_meta = (message.get("params") or {}).get("_meta") or {}
    meta_token = params_meta.get("idempotencyKey")
    if isinstance(meta_token, str) and meta_token.strip():
        return meta_token.strip()
    return None


def _log_correlation(
    mcp_request_id: str,
    project_id: str,
    method: str | None,
    message: dict[str, Any],
    response: dict[str, Any],
) -> None:
    """Structured line for every intercepted call (the observability spine)."""
    tool_name = (message.get("params") or {}).get("name") if method == "tools/call" else None
    meta = ((response.get("result") or {}).get("_meta") or {}).get("zroky") or {}
    logger.info(
        "mcp.ingress request_id=%s project=%s method=%s tool=%s decision=%s intent=%s fail=%s",
        mcp_request_id,
        project_id,
        method,
        tool_name,
        meta.get("decision"),
        meta.get("intent_id"),
        meta.get("fail"),
    )
