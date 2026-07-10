"""Bounded Streamable-HTTP transport for an upstream MCP server.

The gateway deliberately owns upstream authentication and session headers.
Inbound client headers are never replayed to an upstream server.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

import httpx


class UpstreamNotConfigured(RuntimeError):
    """No active project binding or enabled compatibility fallback exists."""


class McpUpstreamError(RuntimeError):
    """A safe, non-secret-bearing upstream failure."""


class McpUpstreamProtocolError(McpUpstreamError):
    """The upstream response was not a supported MCP JSON-RPC response."""


@dataclass(frozen=True)
class McpUpstreamTarget:
    """Resolved runtime target; bearer token exists only for this request."""

    endpoint_url: str
    protocol_version: str = "2025-06-18"
    bearer_token: str | None = None
    allowed_tools: frozenset[str] | None = None
    binding_id: str | None = None
    binding_version: int | None = None


@dataclass(frozen=True)
class McpInitializeResponse:
    result: dict[str, Any]
    upstream_session_id: str | None


class HttpMcpUpstream:
    """One project- and session-scoped upstream MCP client.

    The ingress is currently synchronous, so this client runs in FastAPI's
    sync worker pool with strict timeouts. The constructor accepts a target
    rather than arbitrary headers to keep auth ownership inside the gateway.
    """

    def __init__(
        self,
        target: McpUpstreamTarget | str | None,
        *,
        timeout_seconds: float = 30.0,
        upstream_session_id: str | None = None,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        if isinstance(target, str):
            target = McpUpstreamTarget(endpoint_url=target)
        self._target = target
        self._timeout = timeout_seconds
        self._upstream_session_id = upstream_session_id
        self._client_factory = client_factory

    @property
    def allowed_tools(self) -> frozenset[str] | None:
        return self._target.allowed_tools if self._target is not None else None

    @property
    def binding_id(self) -> str | None:
        return self._target.binding_id if self._target is not None else None

    @property
    def binding_version(self) -> int | None:
        return self._target.binding_version if self._target is not None else None

    def with_session(self, upstream_session_id: str | None) -> "HttpMcpUpstream":
        return HttpMcpUpstream(
            self._target,
            timeout_seconds=self._timeout,
            upstream_session_id=upstream_session_id,
            client_factory=self._client_factory,
        )

    def initialize(self, params: dict[str, Any], *, request_id: Any) -> McpInitializeResponse:
        result, headers = self._rpc("initialize", params, request_id=request_id)
        return McpInitializeResponse(
            result=result,
            upstream_session_id=headers.get("mcp-session-id"),
        )

    def list_tools(self, *, request_id: Any | None = None) -> list[dict[str, Any]]:
        result, _ = self._rpc("tools/list", {}, request_id=self._request_id(request_id))
        tools = result.get("tools")
        return list(tools) if isinstance(tools, list) else []

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        request_id: Any | None = None,
    ) -> dict[str, Any]:
        result, _ = self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
            request_id=self._request_id(request_id),
        )
        return result

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Forward an MCP notification without manufacturing a JSON-RPC id."""
        target = self._require_target()
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            with self._new_client() as client:
                response = client.post(target.endpoint_url, json=payload, headers=self._headers())
                if response.status_code != 202:
                    response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise McpUpstreamError("upstream_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise McpUpstreamError("upstream_http_error") from exc
        except httpx.HTTPError as exc:
            raise McpUpstreamError("upstream_unreachable") from exc

    def close_session(self) -> None:
        """Best-effort MCP session termination for the gateway DELETE path."""
        if not self._upstream_session_id:
            return
        target = self._require_target()
        try:
            with self._new_client() as client:
                response = client.delete(target.endpoint_url, headers=self._headers())
                if response.status_code not in (202, 204, 405):
                    response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise McpUpstreamError("upstream_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise McpUpstreamError("upstream_http_error") from exc
        except httpx.HTTPError as exc:
            raise McpUpstreamError("upstream_unreachable") from exc

    def _request_id(self, request_id: Any | None) -> Any:
        return request_id if request_id is not None else f"zroky-{uuid4()}"

    def _require_target(self) -> McpUpstreamTarget:
        if self._target is None or not self._target.endpoint_url:
            raise UpstreamNotConfigured("No project MCP upstream is configured")
        return self._target

    def _headers(self) -> dict[str, str]:
        target = self._require_target()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": target.protocol_version,
        }
        if self._upstream_session_id:
            headers["Mcp-Session-Id"] = self._upstream_session_id
        if target.bearer_token:
            headers["Authorization"] = f"Bearer {target.bearer_token}"
        return headers

    def _rpc(
        self,
        method: str,
        params: dict[str, Any],
        *,
        request_id: Any,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        target = self._require_target()
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            with self._new_client() as client:
                with client.stream("POST", target.endpoint_url, json=payload, headers=self._headers()) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type.startswith("text/event-stream"):
                        body = self._read_sse_response(response, request_id=request_id)
                    else:
                        try:
                            body = json.loads(response.read())
                        except ValueError as exc:
                            raise McpUpstreamProtocolError("upstream_invalid_json") from exc
                    headers = {key.lower(): value for key, value in response.headers.items()}
        except httpx.TimeoutException as exc:
            raise McpUpstreamError("upstream_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise McpUpstreamError("upstream_http_error") from exc
        except httpx.HTTPError as exc:
            raise McpUpstreamError("upstream_unreachable") from exc

        if not isinstance(body, dict):
            raise McpUpstreamProtocolError("upstream_invalid_jsonrpc")
        if body.get("id") != request_id:
            raise McpUpstreamProtocolError("upstream_request_id_mismatch")
        if body.get("error"):
            raise McpUpstreamError("upstream_mcp_error")
        result = body.get("result")
        if not isinstance(result, dict):
            raise McpUpstreamProtocolError("upstream_missing_result")
        return result, headers

    def _read_sse_response(self, response: httpx.Response, *, request_id: Any) -> dict[str, Any]:
        """Consume an upstream SSE response until our JSON-RPC response arrives.

        The gateway returns a normal JSON-RPC response to its caller, while the
        upstream may use Streamable HTTP's SSE response form. Progress events
        and notifications are ignored; unrelated server requests are rejected
        because the proxy cannot safely execute them on a tenant's behalf.
        If the stream ends before the matching response, the caller receives an
        upstream error and the action rail records an honest unknown outcome.
        """
        data_lines: list[str] = []
        for line in response.iter_lines():
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
                continue
            if line:
                continue
            message = self._decode_sse_message(data_lines)
            data_lines = []
            if message is None:
                continue
            if message.get("id") == request_id:
                return message
            if isinstance(message.get("method"), str):
                raise McpUpstreamProtocolError("upstream_server_request_unsupported")

        message = self._decode_sse_message(data_lines)
        if message is not None and message.get("id") == request_id:
            return message
        raise McpUpstreamProtocolError("upstream_stream_interrupted")

    @staticmethod
    def _decode_sse_message(data_lines: list[str]) -> dict[str, Any] | None:
        if not data_lines:
            return None
        try:
            message = json.loads("\n".join(data_lines))
        except (TypeError, ValueError) as exc:
            raise McpUpstreamProtocolError("upstream_invalid_sse_json") from exc
        if not isinstance(message, dict):
            raise McpUpstreamProtocolError("upstream_invalid_sse_message")
        return message

    def _new_client(self) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(
            timeout=httpx.Timeout(self._timeout, connect=min(5.0, self._timeout)),
            follow_redirects=False,
        )
