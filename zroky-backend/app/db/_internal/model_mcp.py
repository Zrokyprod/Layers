"""MCP interception persistence.

Two durable tables that harden the MCP ingress and link it to receipts:

  * ``mcp_tool_bindings`` — per-project, operator-declared mapping from an
    exact (or regex) MCP tool name to a Zroky action contract + fail posture.
    Replaces reliance on in-code keyword heuristics for real customers.
  * ``mcp_interception_events`` — an append-only audit row for every
    intercepted ``tools/call``: what was decided, whether it was forwarded,
    and any upstream error. This is the observability spine and the
    compliance log (blocked/held attempts must be durably recorded), and it
    stores the post-execution receipt linkage when an allowed call completes.
"""
from __future__ import annotations

from app.db._internal.model_shared import *  # noqa: F401,F403


class McpToolBinding(Base):
    """Durable project config: MCP tool name → action contract + posture."""

    __tablename__ = "mcp_tool_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    action_type: Mapped[str] = mapped_column(String(160), nullable=False)
    operation_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    connector_family: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Explicit contract to gate against — removes the "latest active by
    # action_type" ambiguity when a project has multiple contracts/versions.
    contract_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contract_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Optional posture override; NULL = derive from protected (closed/open).
    fail_posture: Mapped[str | None] = mapped_column(String(16), nullable=True)
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "tool_name", name="ux_mcp_tool_bindings_project_tool"),
        CheckConstraint(
            "fail_posture IS NULL OR fail_posture IN ('fail_open','fail_closed')",
            name="ck_mcp_tool_bindings_fail_posture",
        ),
        CheckConstraint("status IN ('active','retired')", name="ck_mcp_tool_bindings_status"),
        Index("ix_mcp_tool_bindings_project_status", "project_id", "status"),
    )


class McpInterceptionEvent(Base):
    """Append-only audit of every intercepted tools/call."""

    __tablename__ = "mcp_interception_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mcp_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    binding_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    intent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Forwarding is described honestly: we know whether we *attempted* the
    # upstream call and whether the RESPONSE succeeded, but an upstream error
    # after the request left us cannot prove the side-effect did NOT happen —
    # so execution_state carries 'unknown' rather than a false 'not forwarded'.
    forward_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    forward_succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    execution_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'not_attempted'")
    )
    upstream_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fail_posture: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action_receipt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    receipt_digest: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proof_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "execution_state IN ('not_attempted','succeeded','unknown')",
            name="ck_mcp_interception_events_execution_state",
        ),
        Index("ix_mcp_interception_events_project_created", "project_id", "created_at"),
        Index("ix_mcp_interception_events_request", "mcp_request_id"),
        Index("ix_mcp_interception_events_receipt", "project_id", "action_receipt_id"),
    )
