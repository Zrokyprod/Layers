"""Upstream MCP transport — forwards allowed calls to the real MCP server.

Slice-1 forwarding speaks MCP over Streamable HTTP (a JSON-RPC POST to the
configured ``MCP_UPSTREAM_URL``). Per-project upstream routing is a later
slice; this is the deployment-wide default target.

The transport is injected into the route as a FastAPI dependency so tests
substitute a fake without a network, while production wires the real HTTP
client.
"""
from __future__ import annotations

from typing import Any

import httpx


class UpstreamNotConfigured(RuntimeError):
    """MCP interception is on but no upstream MCP server URL is configured."""


class HttpMcpUpstream:
    """Forwards ``tools/list`` / ``tools/call`` to an upstream MCP server."""

    def __init__(self, base_url: str | None, *, timeout_seconds: float = 30.0) -> None:
        # base_url may be None at construction (keeps dependency injection
        # simple); the missing-config error is raised only if a forward is
        # actually attempted, so read-only/observe paths still fail cleanly.
        self._base_url = base_url
        self._timeout = timeout_seconds

    def _require_url(self) -> str:
        if not self._base_url:
            raise UpstreamNotConfigured("MCP_UPSTREAM_URL is not set")
        return self._base_url

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list", {})
        tools = result.get("tools")
        return list(tools) if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        base_url = self._require_url()
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                base_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            response.raise_for_status()
            body = response.json()
        if "error" in body and body["error"]:
            raise httpx.HTTPError(f"upstream MCP error: {body['error']}")
        result = body.get("result")
        return result if isinstance(result, dict) else {}
