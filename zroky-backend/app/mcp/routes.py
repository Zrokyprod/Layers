"""FastAPI ingress for MCP interception — ``POST /v1/mcp/{project_id}``.

Production-dark by default: the route is registered but *inert* (404) unless
``Settings.MCP_INTERCEPTION_ENABLED`` is true, so shipping it changes no
behaviour until an operator opts a deployment in.

Auth: ``require_tenant_context`` resolves the caller's authorized tenant from
the bearer token / tenant header. The ``{project_id}`` in the path is then
checked against that authorized tenant — it is *validated, never trusted* —
so a caller cannot proxy MCP traffic for a project they do not belong to.

This ingress owns path + auth + inline kernel decision + upstream forwarding.
When an allowed call reaches upstream, ``McpPostExecutionProcessor`` records
the execution attempt and queues verification/receipt work for the existing
worker. The request path gates before damage; proof is async.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.mcp.gate import McpSession
from app.mcp.gateway import (
    DbMcpUpstreamResolver,
    McpBindingError,
    McpGatewaySessionError,
    McpUpstreamResolution,
)
from app.mcp.kernel_adapter import DbKernelAdapter
from app.mcp.post_execution import McpPostExecutionProcessor
from app.mcp.persistence import DbEventSink, load_project_bindings
from app.mcp.proxy import handle_message
from app.mcp.upstream import UpstreamNotConfigured

router = APIRouter()
logger = logging.getLogger(__name__)


def get_mcp_upstream(settings: Settings = Depends(get_settings)) -> DbMcpUpstreamResolver:
    """Resolve a tenant's active binding or the explicit legacy fallback."""
    return DbMcpUpstreamResolver(settings)


@router.post("/v1/mcp/{project_id}", response_model=None)
def mcp_ingress(
    project_id: str,
    message: dict[str, Any] = Body(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    origin: str | None = Header(default=None, alias="Origin"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
    upstream_resolver: DbMcpUpstreamResolver = Depends(get_mcp_upstream),
    settings: Settings = Depends(get_settings),
) -> Any:
    if not settings.MCP_INTERCEPTION_ENABLED:
        # Inert until explicitly enabled — indistinguishable from "not mounted".
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    # The path project must be the caller's authorized tenant, not trusted input.
    if project_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for the requested project.",
        )

    _validate_origin(settings, origin)

    allowed_projects = _mcp_project_allowlist(settings)
    if allowed_projects is not None and project_id not in allowed_projects:
        # Keep non-canary tenants indistinguishable from disabled MCP.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    mcp_request_id = str(uuid.uuid4())
    method = message.get("method")

    try:
        resolution = _resolve_upstream(
            upstream_resolver,
            db=db,
            project_id=project_id,
            method=method,
            mcp_session_id=mcp_session_id,
            principal_subject=context.subject,
        )
    except UpstreamNotConfigured:
        return _gateway_error(
            message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=-32003,
            detail="No active MCP upstream is configured for this project.",
        )
    except McpGatewaySessionError as exc:
        return _gateway_error(
            message,
            status_code=status.HTTP_409_CONFLICT,
            code=-32001,
            detail=str(exc),
        )
    except McpBindingError:
        logger.exception("mcp.upstream_binding_unavailable project=%s", project_id)
        return _gateway_error(
            message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=-32003,
            detail="MCP upstream binding is unavailable.",
        )

    if method == "initialize":
        try:
            initialized = resolution.upstream.initialize(
                message.get("params") or {}, request_id=message.get("id")
            )
        except Exception:
            logger.exception("mcp.upstream_initialize_failed project=%s", project_id)
            return _gateway_error(
                message,
                status_code=status.HTTP_502_BAD_GATEWAY,
                code=-32002,
                detail="MCP upstream initialization failed.",
            )
        response = _initialize_response(message.get("id"), initialized.result)
        if resolution.requires_gateway_session:
            gateway_session = upstream_resolver.create_gateway_session(
                db,
                resolution=resolution,
                project_id=project_id,
                principal_subject=context.subject,
                upstream_session_id=initialized.upstream_session_id,
            )
            return JSONResponse(
                content=response,
                headers={"Mcp-Session-Id": gateway_session.id},
            )
        return response

    # MCP notifications have no JSON-RPC response, but initialized must still
    # reach the upstream server so its session becomes usable there too.
    if message.get("id") is None and isinstance(method, str) and method.startswith("notifications/"):
        try:
            resolution.upstream.notify(method, message.get("params") or {})
        except Exception:
            logger.exception("mcp.upstream_notification_failed project=%s method=%s", project_id, method)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MCP upstream notification failed.",
            ) from None
        return Response(status_code=status.HTTP_202_ACCEPTED)

    session = _gate_session(project_id, context.subject, idempotency_key, message)

    response = handle_message(
        message,
        session=session,
        kernel=DbKernelAdapter(db),
        upstream=resolution.upstream,
        bindings=load_project_bindings(db, project_id),
        event_sink=DbEventSink(
            db, project_id=project_id, mcp_request_id=mcp_request_id, method=method or "unknown"
        ),
        post_execution=McpPostExecutionProcessor(
            db,
            actor=context.subject or "mcp-proxy",
        ),
    )

    _log_correlation(
        mcp_request_id,
        project_id,
        method,
        message,
        response,
        upstream_source=resolution.source,
        binding_id=resolution.binding_id,
    )
    return response


@router.delete("/v1/mcp/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def mcp_session_delete(
    project_id: str,
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    origin: str | None = Header(default=None, alias="Origin"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
    upstream_resolver: DbMcpUpstreamResolver = Depends(get_mcp_upstream),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Terminate a project-scoped MCP gateway session."""
    _require_ingress_access(project_id, context, settings, origin)
    if not mcp_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mcp-Session-Id is required.")
    try:
        upstream_resolver.close_gateway_session(
            db,
            project_id=project_id,
            gateway_session_id=mcp_session_id,
            principal_subject=context.subject,
        )
    except McpGatewaySessionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/v1/mcp/{project_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
def mcp_stream_not_supported(
    project_id: str,
    origin: str | None = Header(default=None, alias="Origin"),
    context: TenantContext = Depends(require_tenant_context),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Explicitly decline the optional server-to-client SSE channel.

    POST responses support Streamable HTTP's JSON and upstream SSE forms. The
    gateway does not expose an independent GET event stream yet, so returning
    405 is the protocol-defined way to advertise that capability boundary.
    """
    _require_ingress_access(project_id, context, settings, origin)
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST, DELETE"})


def _resolve_upstream(
    resolver: DbMcpUpstreamResolver,
    *,
    db: Session,
    project_id: str,
    method: Any,
    mcp_session_id: str | None,
    principal_subject: str | None,
) -> McpUpstreamResolution:
    if method == "initialize":
        return resolver.resolve_for_initialize(db, project_id=project_id)
    if mcp_session_id:
        return resolver.resolve_for_session(
            db,
            project_id=project_id,
            gateway_session_id=mcp_session_id,
            principal_subject=principal_subject,
        )
    resolution = resolver.resolve_for_initialize(db, project_id=project_id)
    if resolution.requires_gateway_session:
        raise McpGatewaySessionError("MCP session is required; initialize a new session first")
    return resolution


def _require_ingress_access(
    project_id: str,
    context: TenantContext,
    settings: Settings,
    origin: str | None,
) -> None:
    if not settings.MCP_INTERCEPTION_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    if project_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for the requested project.",
        )
    _validate_origin(settings, origin)
    allowed_projects = _mcp_project_allowlist(settings)
    if allowed_projects is not None and project_id not in allowed_projects:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


def _initialize_response(request_id: Any, upstream_result: dict[str, Any]) -> dict[str, Any]:
    """Return only capabilities the gateway actually implements."""
    upstream_capabilities = upstream_result.get("capabilities")
    capabilities: dict[str, dict[str, Any]] = {"tools": {}}
    if isinstance(upstream_capabilities, dict) and isinstance(upstream_capabilities.get("logging"), dict):
        # Logging is safe to advertise only when it is a transparent upstream
        # capability; the gateway does not synthesize log notifications itself.
        capabilities["logging"] = {}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2025-06-18",
            "serverInfo": {"name": "zroky-mcp-proxy", "version": "0.1.0"},
            "capabilities": capabilities,
        },
    }


def _gate_session(
    project_id: str,
    subject: str | None,
    idempotency_key: str | None,
    message: dict[str, Any],
) -> McpSession:
    return McpSession(
        project_id=project_id,
        environment="production",
        agent_id=None,
        principal=({"type": "user", "id": subject} if subject else None),
        idempotency_key=_resolve_idempotency_key(idempotency_key, message),
    )


def _validate_origin(settings: Settings, origin: str | None) -> None:
    if not origin:
        return
    allowed = {item.strip() for item in settings.MCP_ALLOWED_ORIGINS.split(",") if item.strip()}
    if origin not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MCP origin is not allowed.")


def _gateway_error(
    message: dict[str, Any],
    *,
    status_code: int,
    code: int,
    detail: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": code, "message": detail}},
    )


def _mcp_project_allowlist(settings: Settings) -> set[str] | None:
    raw = settings.MCP_INTERCEPTION_PROJECT_ALLOWLIST.strip()
    if not raw:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


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
    *,
    upstream_source: str | None = None,
    binding_id: str | None = None,
) -> None:
    """Structured line for every intercepted call (the observability spine)."""
    tool_name = (message.get("params") or {}).get("name") if method == "tools/call" else None
    meta = ((response.get("result") or {}).get("_meta") or {}).get("zroky") or {}
    logger.info(
        "mcp.ingress request_id=%s project=%s method=%s tool=%s decision=%s intent=%s fail=%s upstream_source=%s binding=%s",
        mcp_request_id,
        project_id,
        method,
        tool_name,
        meta.get("decision"),
        meta.get("intent_id"),
        meta.get("fail"),
        upstream_source,
        binding_id,
    )
