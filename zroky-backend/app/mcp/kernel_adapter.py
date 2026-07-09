"""Real :class:`~app.mcp.gate.KernelPort` backed by ``action_kernel``.

Bridges an intercepted MCP tool call onto the existing verified-action
kernel *inside the normal request DB session*:

  1. Resolve the project's bound or active ``ActionContractVersion`` whose
     ``action_type`` matches the tool's classification.
  2. ``create_action_intent`` → ``decide_action_intent`` (one transaction).
  3. Map ``ActionIntentDecision`` → :class:`~app.mcp.gate.KernelDecision`.

A protected tool with no onboarded contract raises
:class:`ContractNotOnboardedError`; the proxy treats that (like any gate
error on a protected action) as **fail-closed** — an action Zroky cannot
govern must not reach the system of record. Explicit per-project
tool→contract bindings remove ambiguity when a tool name needs a precise
contract version.

This adapter intentionally stops at authorization. Post-execution SOR
reconciliation and signed receipt generation run after upstream forwarding,
where the proxy has the upstream result needed to produce honest evidence.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActionContractVersion
from app.mcp.gate import IdempotencyConflict, KernelDecision, McpSession
from app.mcp.tool_binding import ActionClassification
from app.services.action_kernel import (
    ActionIntentConflict,
    create_action_intent,
    decide_action_intent,
)


class ContractNotOnboardedError(RuntimeError):
    """A protected action classified with no active contract for the project."""


class DbKernelAdapter:
    """KernelPort implementation over a live SQLAlchemy session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def open_and_decide(
        self,
        *,
        session: McpSession,
        tool_name: str,
        classification: ActionClassification,
        arguments: dict[str, Any],
    ) -> KernelDecision:
        contract = self._resolve_contract(
            project_id=session.project_id, classification=classification
        )
        if contract is None:
            raise ContractNotOnboardedError(
                f"No active contract for action_type '{classification.action_type}' "
                f"in project '{session.project_id}'"
            )

        idempotency_key = self._idempotency_key(session)

        # Use the CONTRACT's own action_type/operation_kind — the kernel
        # validates the intent against them, and they carry the DB enum casing
        # (CREATE/GRANT/TRANSFER/…) that classification strings do not.
        try:
            created = create_action_intent(
                self._db,
                project_id=session.project_id,
                agent_id=None,
                contract_version=f"{contract.contract_key}/{contract.version}",
                action_type=contract.action_type,
                operation_kind=contract.operation_kind,
                environment=session.environment,
                idempotency_key=idempotency_key,
                principal=session.principal or {"type": "agent", "id": session.agent_id or "mcp"},
                actor_chain=[{"type": "agent", "id": session.agent_id or "mcp-agent", "version": "mcp"}],
                purpose={"code": "mcp_tool_call", "summary": f"MCP tool {tool_name}"},
                resource={"type": classification.connector_family or "mcp", "id": tool_name},
                parameters=dict(arguments),
                verification_profile=None,  # post-exec reconciliation needs the upstream result
            )
        except ActionIntentConflict as exc:
            # Same idempotency key, different payload. Translate the service-layer
            # exception into the neutral port error so the proxy stays decoupled
            # from action_kernel and can surface a distinct conflict reason.
            raise IdempotencyConflict(str(exc)) from exc
        decision = decide_action_intent(
            self._db, project_id=session.project_id, action_id=created.row.id
        )
        self._db.commit()

        return KernelDecision(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reasons=list(decision.reasons),
            intent_id=created.row.id,
        )

    def _resolve_contract(
        self, *, project_id: str, classification: ActionClassification
    ) -> ActionContractVersion | None:
        stmt = select(ActionContractVersion).where(
            ActionContractVersion.project_id == project_id,
            ActionContractVersion.status == "active",
        )
        # Always constrain to the classified action_type — even when a binding
        # pins a contract_key. A misconfigured binding whose contract_key points
        # at a DIFFERENT action_type must NOT resolve (else the audited
        # classification and the executed contract silently diverge); it yields
        # no row → ContractNotOnboardedError → fail-closed for protected actions.
        stmt = stmt.where(ActionContractVersion.action_type == classification.action_type)
        if classification.contract_key:
            stmt = stmt.where(ActionContractVersion.contract_key == classification.contract_key)
            if classification.contract_version:
                stmt = stmt.where(ActionContractVersion.version == classification.contract_version)
        stmt = stmt.order_by(ActionContractVersion.created_at.desc())
        return self._db.execute(stmt).scalars().first()

    @staticmethod
    def _idempotency_key(session: McpSession) -> str:
        # Trust the route-resolved key (caller token / session+id). Absent one,
        # mint a fresh unique key so every call is a distinct intent — false
        # de-dupe (dropping a real action) is worse than a false duplicate.
        if session.idempotency_key:
            return f"mcp:{session.project_id}:{session.idempotency_key}"
        return f"mcp:{session.project_id}:auto:{uuid.uuid4()}"
