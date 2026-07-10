"""Tenant-scoped MCP upstream gateway configuration and session state."""
from __future__ import annotations

from app.db._internal.model_shared import *  # noqa: F401,F403


class McpUpstreamBinding(Base):
    """The approved MCP upstream for one project.

    The public ingress has a project path rather than an upstream identifier, so
    one project has one active default binding. Updating it increments
    ``version``; gateway sessions pin that version and must re-initialize
    rather than silently moving an in-flight agent to a new server.
    """

    __tablename__ = "mcp_upstream_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    protocol_version: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'2025-06-18'")
    )
    bearer_credential_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connector_credentials.id", ondelete="RESTRICT"), nullable=True
    )
    allowed_tools_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    test_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'not_tested'")
    )
    tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", name="ux_mcp_upstream_bindings_project"),
        CheckConstraint("status IN ('draft','active','disabled')", name="ck_mcp_upstream_bindings_status"),
        CheckConstraint(
            "test_status IN ('not_tested','succeeded','failed')",
            name="ck_mcp_upstream_bindings_test_status",
        ),
        CheckConstraint("version >= 1", name="ck_mcp_upstream_bindings_version"),
        Index("ix_mcp_upstream_bindings_project_status", "project_id", "status"),
    )


class McpGatewaySession(Base):
    """Gateway session mapped to the upstream's opaque session identifier."""

    __tablename__ = "mcp_gateway_sessions"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mcp_upstream_bindings.id", ondelete="CASCADE"), nullable=False
    )
    binding_version: Mapped[int] = mapped_column(Integer, nullable=False)
    principal_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upstream_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_mcp_gateway_sessions_project_expiry", "project_id", "expires_at"),
        Index("ix_mcp_gateway_sessions_binding", "binding_id", "binding_version"),
    )
