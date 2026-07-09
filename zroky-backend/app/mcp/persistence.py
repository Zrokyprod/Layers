"""DB adapters for MCP interception: bindings load + event sink.

Bridges the pure proxy/gate to the two Slice-1.5 tables. Kept separate from
``routes.py`` so the persistence shape is testable on its own.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import McpInterceptionEvent, McpToolBinding
from app.mcp.proxy import InterceptionEvent
from app.mcp.tool_binding import ToolBinding


def load_project_bindings(db: Session, project_id: str) -> list[ToolBinding]:
    """Active durable tool bindings for a project, as classifier bindings."""
    rows = db.execute(
        select(McpToolBinding).where(
            McpToolBinding.project_id == project_id,
            McpToolBinding.status == "active",
        )
    ).scalars().all()
    return [
        ToolBinding(
            match=row.tool_name,
            action_type=row.action_type,
            operation_kind=row.operation_kind or "custom",
            connector_family=row.connector_family or "unknown",
            is_regex=row.is_regex,
            contract_key=row.contract_key,
            contract_version=row.contract_version,
            fail_posture=row.fail_posture,
            protected_override=row.protected,
        )
        for row in rows
    ]


class DbEventSink:
    """Writes one durable audit row per intercepted tools/call.

    Uses a SEPARATE session on the same engine as the request — so the audit
    commit is independent of the request/kernel transaction (a rolled-back
    request cannot silently drop its audit, and vice-versa). ``record`` raises
    on failure so the proxy can fail-closed for protected actions; the outcome
    update is best-effort.
    """

    def __init__(self, db: Session, *, project_id: str, mcp_request_id: str, method: str) -> None:
        self._bind = db.get_bind()
        self._project_id = project_id
        self._mcp_request_id = mcp_request_id
        self._method = method

    def record(self, event: InterceptionEvent) -> str:
        event_id = str(uuid.uuid4())
        with Session(bind=self._bind) as session:
            session.add(
                McpInterceptionEvent(
                    id=event_id,
                    project_id=self._project_id,
                    mcp_request_id=self._mcp_request_id,
                    method=self._method,
                    tool_name=event.tool_name,
                    action_type=event.action_type,
                    protected=event.protected,
                    binding_source=event.binding_source,
                    decision=event.decision,
                    intent_id=event.intent_id,
                    forward_attempted=False,
                    forward_succeeded=False,
                    execution_state="not_attempted",
                    upstream_error=None,  # decision record is pre-forward; set via update_outcome
                    fail_posture=event.fail_posture,
                )
            )
            session.commit()
        return event_id

    def update_outcome(
        self,
        event_id: str | None,
        *,
        forward_attempted: bool,
        forward_succeeded: bool,
        execution_state: str,
        upstream_error: str | None,
        action_receipt_id: str | None = None,
        receipt_digest: str | None = None,
        proof_status: str | None = None,
    ) -> None:
        if event_id is None:
            return
        with Session(bind=self._bind) as session:
            row = session.get(McpInterceptionEvent, event_id)
            if row is None:
                return
            row.forward_attempted = forward_attempted
            row.forward_succeeded = forward_succeeded
            row.execution_state = execution_state
            row.upstream_error = upstream_error
            row.action_receipt_id = action_receipt_id
            row.receipt_digest = receipt_digest
            row.proof_status = proof_status
            session.commit()
