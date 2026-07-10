"""Project-scoped MCP upstream bindings, preflight, and session resolution."""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import McpGatewaySession, McpUpstreamBinding
from app.mcp.upstream import HttpMcpUpstream, McpUpstreamTarget, UpstreamNotConfigured
from app.services.connector_credentials import (
    CredentialUnavailableError,
    RemoteCredentialResolutionRequired,
    resolve_managed_bearer_credential,
)


DEFAULT_PROTOCOL_VERSION = "2025-06-18"
# The proxy currently implements the 2025-06 JSON request/response surface.
# A newer protocol is added only with an explicit transport conformance suite.
SUPPORTED_PROTOCOL_VERSIONS = frozenset({DEFAULT_PROTOCOL_VERSION})
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,255}$")
_GATEWAY_CREDENTIAL_SCOPE = "mcp_upstream"


class McpBindingError(ValueError):
    """Base error for safe binding lifecycle failures."""


class McpBindingNotFound(McpBindingError):
    pass


class McpBindingConflict(McpBindingError):
    pass


class McpGatewaySessionError(McpBindingError):
    pass


class McpGatewaySessionExpired(McpGatewaySessionError):
    pass


class McpGatewaySessionStale(McpGatewaySessionError):
    pass


class McpGatewaySessionUnauthorized(McpGatewaySessionError):
    pass


@dataclass(frozen=True)
class McpUpstreamResolution:
    upstream: HttpMcpUpstream
    source: str
    binding_id: str | None
    binding_version: int | None
    requires_gateway_session: bool


class McpBindingTester(Protocol):
    def test(self, target: McpUpstreamTarget) -> list[str]: ...


class HttpMcpBindingTester:
    """Non-mutating preflight: initialize then inventory tools."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds

    def test(self, target: McpUpstreamTarget) -> list[str]:
        upstream = HttpMcpUpstream(target, timeout_seconds=self._timeout_seconds)
        initialized = upstream.initialize(
            {
                "protocolVersion": target.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "zroky-mcp-preflight", "version": "1.0"},
            },
            request_id="zroky-preflight-initialize",
        )
        tools = upstream.with_session(initialized.upstream_session_id).list_tools(
            request_id="zroky-preflight-tools-list"
        )
        return sorted(
            {
                str(tool.get("name"))
                for tool in tools
                if isinstance(tool, dict) and isinstance(tool.get("name"), str)
            }
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_protocol_version(value: str | None) -> str:
    normalized = str(value or DEFAULT_PROTOCOL_VERSION).strip()
    if normalized not in SUPPORTED_PROTOCOL_VERSIONS:
        raise McpBindingError("unsupported MCP protocol version")
    return normalized


def normalize_endpoint_url(value: str) -> str:
    """Permit only public HTTPS MCP endpoints in the managed gateway.

    VPC-only upstreams belong behind the private runner; allowing arbitrary
    private addresses here would turn the public control plane into an SSRF
    primitive.
    """
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise McpBindingError("MCP endpoint URL is invalid") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise McpBindingError("MCP endpoint must be a public HTTPS URL without credentials or query data")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host == "metadata.google.internal":
        raise McpBindingError("MCP endpoint host is not permitted")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise McpBindingError("MCP endpoint host is not permitted")
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", "", ""))


def normalize_allowed_tools(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    names: set[str] = set()
    for raw in values or []:
        name = str(raw or "").strip()
        if not _TOOL_NAME_RE.fullmatch(name):
            raise McpBindingError("allowed MCP tool names are invalid")
        names.add(name)
    if len(names) > 500:
        raise McpBindingError("an MCP binding may allow at most 500 tools")
    return tuple(sorted(names))


def _allowed_tools(binding: McpUpstreamBinding) -> tuple[str, ...]:
    try:
        raw = json.loads(binding.allowed_tools_json or "[]")
    except (TypeError, ValueError):
        raise McpBindingError("MCP binding tool allowlist is invalid") from None
    if not isinstance(raw, list):
        raise McpBindingError("MCP binding tool allowlist is invalid")
    return normalize_allowed_tools(raw)


def get_project_binding(db: Session, *, project_id: str) -> McpUpstreamBinding | None:
    return db.execute(
        select(McpUpstreamBinding).where(McpUpstreamBinding.project_id == project_id)
    ).scalar_one_or_none()


def upsert_draft_binding(
    db: Session,
    *,
    project_id: str,
    endpoint_url: str,
    protocol_version: str | None,
    bearer_credential_id: str | None,
    allowed_tools: list[str] | tuple[str, ...] | None,
    actor_subject: str | None,
) -> McpUpstreamBinding:
    """Write a new draft and invalidate all sessions pinned to the old version."""
    normalized_url = normalize_endpoint_url(endpoint_url)
    normalized_protocol = _normalize_protocol_version(protocol_version)
    normalized_tools = normalize_allowed_tools(allowed_tools)
    row = get_project_binding(db, project_id=project_id)
    if row is None:
        row = McpUpstreamBinding(
            project_id=project_id,
            endpoint_url=normalized_url,
            protocol_version=normalized_protocol,
            bearer_credential_id=bearer_credential_id,
            allowed_tools_json=json.dumps(normalized_tools, separators=(",", ":")),
            status="draft",
            test_status="not_tested",
            version=1,
            created_by_subject=actor_subject,
            updated_by_subject=actor_subject,
        )
        db.add(row)
    else:
        row.endpoint_url = normalized_url
        row.protocol_version = normalized_protocol
        row.bearer_credential_id = bearer_credential_id
        row.allowed_tools_json = json.dumps(normalized_tools, separators=(",", ":"))
        row.status = "draft"
        row.test_status = "not_tested"
        row.tested_at = None
        row.last_test_error = None
        row.activated_at = None
        row.version += 1
        row.updated_by_subject = actor_subject
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _target_for_binding(db: Session, binding: McpUpstreamBinding) -> McpUpstreamTarget:
    bearer_token: str | None = None
    if binding.bearer_credential_id:
        try:
            bearer_token = resolve_managed_bearer_credential(
                db,
                project_id=binding.project_id,
                credential_id=binding.bearer_credential_id,
                allowed_connector_type=_GATEWAY_CREDENTIAL_SCOPE,
            )
        except (CredentialUnavailableError, RemoteCredentialResolutionRequired) as exc:
            raise McpBindingConflict("MCP upstream credential is unavailable") from exc
    return McpUpstreamTarget(
        endpoint_url=binding.endpoint_url,
        protocol_version=binding.protocol_version,
        bearer_token=bearer_token,
        allowed_tools=frozenset(_allowed_tools(binding)),
        binding_id=binding.id,
        binding_version=binding.version,
    )


def test_binding(
    db: Session,
    *,
    project_id: str,
    tester: McpBindingTester,
) -> tuple[McpUpstreamBinding, list[str]]:
    binding = get_project_binding(db, project_id=project_id)
    if binding is None:
        raise McpBindingNotFound("MCP upstream binding was not found")
    try:
        discovered_tools = tester.test(_target_for_binding(db, binding))
        missing = set(_allowed_tools(binding)).difference(discovered_tools)
        if missing:
            raise McpBindingConflict("configured MCP tools are not present upstream")
    except McpBindingConflict:
        binding.test_status = "failed"
        binding.tested_at = _utc_now()
        binding.last_test_error = "allowed_tool_missing"
        db.add(binding)
        db.commit()
        raise
    except Exception:
        # Do not persist exception strings; an upstream may include sensitive
        # diagnostic data in its response body or URL.
        binding.test_status = "failed"
        binding.tested_at = _utc_now()
        binding.last_test_error = "upstream_unavailable"
        db.add(binding)
        db.commit()
        return binding, []
    binding.test_status = "succeeded"
    binding.tested_at = _utc_now()
    binding.last_test_error = None
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding, discovered_tools


def activate_binding(db: Session, *, project_id: str, actor_subject: str | None) -> McpUpstreamBinding:
    binding = get_project_binding(db, project_id=project_id)
    if binding is None:
        raise McpBindingNotFound("MCP upstream binding was not found")
    if binding.test_status != "succeeded":
        raise McpBindingConflict("MCP upstream must pass preflight before activation")
    if not _allowed_tools(binding):
        raise McpBindingConflict("MCP upstream must declare at least one allowed tool before activation")
    binding.status = "active"
    binding.activated_at = _utc_now()
    binding.updated_by_subject = actor_subject
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def disable_binding(db: Session, *, project_id: str, actor_subject: str | None) -> McpUpstreamBinding:
    binding = get_project_binding(db, project_id=project_id)
    if binding is None:
        raise McpBindingNotFound("MCP upstream binding was not found")
    binding.status = "disabled"
    binding.updated_by_subject = actor_subject
    binding.version += 1
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


class DbMcpUpstreamResolver:
    """Resolve only the active binding belonging to the authorized project."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve_for_initialize(self, db: Session, *, project_id: str) -> McpUpstreamResolution:
        binding = get_project_binding(db, project_id=project_id)
        if binding is not None and binding.status == "active":
            return McpUpstreamResolution(
                upstream=HttpMcpUpstream(
                    _target_for_binding(db, binding),
                    timeout_seconds=self._settings.MCP_UPSTREAM_TIMEOUT_SECONDS,
                ),
                source="binding",
                binding_id=binding.id,
                binding_version=binding.version,
                requires_gateway_session=True,
            )
        return self._legacy_resolution()

    def resolve_for_session(
        self,
        db: Session,
        *,
        project_id: str,
        gateway_session_id: str,
        principal_subject: str | None,
    ) -> McpUpstreamResolution:
        session = db.get(McpGatewaySession, gateway_session_id)
        binding = self._validate_session(
            db,
            session=session,
            project_id=project_id,
            principal_subject=principal_subject,
        )
        session.last_seen_at = _utc_now()
        db.add(session)
        db.commit()
        return McpUpstreamResolution(
            upstream=HttpMcpUpstream(
                _target_for_binding(db, binding),
                timeout_seconds=self._settings.MCP_UPSTREAM_TIMEOUT_SECONDS,
                upstream_session_id=session.upstream_session_id,
            ),
            source="binding",
            binding_id=binding.id,
            binding_version=binding.version,
            requires_gateway_session=True,
        )

    def close_gateway_session(
        self,
        db: Session,
        *,
        project_id: str,
        gateway_session_id: str,
        principal_subject: str | None,
    ) -> None:
        """Terminate the upstream session and remove its gateway mapping.

        Upstream DELETE is best-effort because the server may already have
        expired the opaque session. The gateway mapping is removed either way,
        so a client cannot keep using a stale tenant binding.
        """
        session = db.get(McpGatewaySession, gateway_session_id)
        binding = self._validate_session(
            db,
            session=session,
            project_id=project_id,
            principal_subject=principal_subject,
            allow_expired=True,
        )
        try:
            _target = _target_for_binding(db, binding)
            HttpMcpUpstream(
                _target,
                timeout_seconds=self._settings.MCP_UPSTREAM_TIMEOUT_SECONDS,
                upstream_session_id=session.upstream_session_id if session else None,
            ).close_session()
        except Exception:
            # Session deletion is local security state. Do not retain a usable
            # gateway token merely because the upstream is unavailable.
            pass
        if session is not None:
            db.delete(session)
        db.commit()

    @staticmethod
    def _validate_session(
        db: Session,
        *,
        session: McpGatewaySession | None,
        project_id: str,
        principal_subject: str | None,
        allow_expired: bool = False,
    ) -> McpUpstreamBinding:
        if session is None or session.project_id != project_id:
            raise McpGatewaySessionUnauthorized("MCP session does not belong to this project")
        if session.principal_subject != principal_subject:
            raise McpGatewaySessionUnauthorized("MCP session principal does not match")
        if not allow_expired and session.expires_at <= _utc_now():
            raise McpGatewaySessionExpired("MCP session has expired")
        binding = db.get(McpUpstreamBinding, session.binding_id)
        if (
            binding is None
            or binding.project_id != project_id
            or binding.status != "active"
            or binding.version != session.binding_version
        ):
            raise McpGatewaySessionStale("MCP binding changed; initialize a new session")
        return binding

    def create_gateway_session(
        self,
        db: Session,
        *,
        resolution: McpUpstreamResolution,
        project_id: str,
        principal_subject: str | None,
        upstream_session_id: str | None,
    ) -> McpGatewaySession:
        if not resolution.requires_gateway_session or not resolution.binding_id or not resolution.binding_version:
            raise McpBindingConflict("legacy upstream does not create a gateway session")
        now = _utc_now()
        row = McpGatewaySession(
            id=f"zroky-{uuid4()}",
            project_id=project_id,
            binding_id=resolution.binding_id,
            binding_version=resolution.binding_version,
            principal_subject=principal_subject,
            upstream_session_id=upstream_session_id,
            expires_at=now + timedelta(seconds=self._settings.MCP_GATEWAY_SESSION_TTL_SECONDS),
            last_seen_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _legacy_resolution(self) -> McpUpstreamResolution:
        if not self._settings.MCP_LEGACY_UPSTREAM_FALLBACK_ENABLED:
            raise UpstreamNotConfigured("No active project MCP upstream binding")
        endpoint_url = self._settings.MCP_UPSTREAM_URL
        if not endpoint_url:
            raise UpstreamNotConfigured("No project MCP upstream is configured")
        return McpUpstreamResolution(
            upstream=HttpMcpUpstream(
                endpoint_url,
                timeout_seconds=self._settings.MCP_UPSTREAM_TIMEOUT_SECONDS,
            ),
            source="legacy",
            binding_id=None,
            binding_version=None,
            requires_gateway_session=False,
        )
