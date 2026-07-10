"""Protocol and boundary tests for the tenant-scoped MCP upstream bridge."""
from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.mcp.gateway import McpBindingError, normalize_endpoint_url
from app.mcp.gateway import (
    DbMcpUpstreamResolver,
    McpGatewaySessionError,
    activate_binding,
    test_binding as _run_binding_test,
    upsert_draft_binding,
)
from app.db.base import Base
from app.mcp.upstream import HttpMcpUpstream, McpUpstreamTarget


def test_endpoint_normalization_rejects_ssrf_primitives() -> None:
    assert normalize_endpoint_url("https://example.com/mcp") == "https://example.com/mcp"
    with pytest.raises(McpBindingError):
        normalize_endpoint_url("http://example.com/mcp")
    with pytest.raises(McpBindingError):
        normalize_endpoint_url("https://user:password@example.com/mcp")
    with pytest.raises(McpBindingError):
        normalize_endpoint_url("https://example.com/mcp?token=secret")
    with pytest.raises(McpBindingError):
        normalize_endpoint_url("https://127.0.0.1/mcp")


def test_upstream_preserves_ids_scopes_headers_and_consumes_sse() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/json",
                    "Mcp-Session-Id": "upstream-session-1",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                    },
                },
            )
        if body.get("method") == "tools/call":
            event = {
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=f"event: message\ndata: {json.dumps(event)}\n\n".encode(),
            )
        if body.get("method", "").startswith("notifications/"):
            assert "id" not in body
            return httpx.Response(202)
        return httpx.Response(404)

    target = McpUpstreamTarget(
        endpoint_url="https://example.com/mcp",
        bearer_token="tenant-token",
        allowed_tools=frozenset({"refund_create"}),
    )
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))
    upstream = HttpMcpUpstream(target, client_factory=factory)

    initialized = upstream.initialize({}, request_id="init-4")
    assert initialized.upstream_session_id == "upstream-session-1"
    result = upstream.with_session(initialized.upstream_session_id).call_tool(
        "refund_create", {"amount": 10}, request_id="call-9"
    )
    assert result["content"][0]["text"] == "ok"

    upstream.with_session(initialized.upstream_session_id).notify("notifications/initialized")
    upstream.with_session(initialized.upstream_session_id).close_session()

    init_body = json.loads(seen[0].content)
    call_body = json.loads(seen[1].content)
    notification_body = json.loads(seen[2].content)
    assert init_body["id"] == "init-4"
    assert call_body["id"] == "call-9"
    assert "id" not in notification_body
    assert seen[1].headers["authorization"] == "Bearer tenant-token"
    assert seen[1].headers["mcp-session-id"] == "upstream-session-1"


class _ToolInventory:
    def test(self, target: McpUpstreamTarget) -> list[str]:
        return ["refund_create"]


def test_binding_session_is_project_scoped_and_pins_binding_version() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            binding = upsert_draft_binding(
                db,
                project_id="project-a",
                endpoint_url="https://example.com/mcp",
                protocol_version="2025-06-18",
                bearer_credential_id=None,
                allowed_tools=["refund_create"],
                actor_subject="owner-a",
            )
            binding, discovered = _run_binding_test(db, project_id="project-a", tester=_ToolInventory())
            assert discovered == ["refund_create"]
            binding = activate_binding(db, project_id="project-a", actor_subject="owner-a")

            settings = type(
                "GatewaySettings",
                (),
                {
                    "MCP_UPSTREAM_TIMEOUT_SECONDS": 5.0,
                    "MCP_GATEWAY_SESSION_TTL_SECONDS": 3600,
                    "MCP_LEGACY_UPSTREAM_FALLBACK_ENABLED": False,
                    "MCP_UPSTREAM_URL": None,
                },
            )()
            resolver = DbMcpUpstreamResolver(settings)
            initial = resolver.resolve_for_initialize(db, project_id="project-a")
            assert initial.binding_id == binding.id
            assert initial.requires_gateway_session is True
            original_version = binding.version
            gateway_session = resolver.create_gateway_session(
                db,
                resolution=initial,
                project_id="project-a",
                principal_subject="agent-a",
                upstream_session_id="upstream-a",
            )
            resolved = resolver.resolve_for_session(
                db,
                project_id="project-a",
                gateway_session_id=gateway_session.id,
                principal_subject="agent-a",
            )
            assert resolved.upstream.binding_id == binding.id

            with pytest.raises(McpGatewaySessionError):
                resolver.resolve_for_session(
                    db,
                    project_id="project-b",
                    gateway_session_id=gateway_session.id,
                    principal_subject="agent-a",
                )

            newer = upsert_draft_binding(
                db,
                project_id="project-a",
                endpoint_url="https://example.org/mcp",
                protocol_version="2025-06-18",
                bearer_credential_id=None,
                allowed_tools=["refund_create"],
                actor_subject="owner-a",
            )
            assert newer.version == original_version + 1
            with pytest.raises(McpGatewaySessionError):
                resolver.resolve_for_session(
                    db,
                    project_id="project-a",
                    gateway_session_id=gateway_session.id,
                    principal_subject="agent-a",
                )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
