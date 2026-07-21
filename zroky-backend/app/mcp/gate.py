"""The interception gate — classify → policy → allow/deny/hold/observe.

This module is intentionally pure and side-effect-free at its core: it
orchestrates a :class:`KernelPort` (a thin adapter over the existing
``action_kernel``) and returns a :class:`GateOutcome`. The FastAPI proxy
(:mod:`app.mcp.proxy`) supplies the real adapter; tests supply a fake.
That keeps the decision logic unit-testable without a DB, a tenant, or a
live upstream MCP server.

Outcome → MCP mapping (see proxy):
  OBSERVE → forward upstream, emit a lightweight receipt (fail-OPEN)
  ALLOW   → forward upstream, verify against SOR, sign receipt
  DENY    → JSON-RPC error with structured ``reasons`` (agent self-corrects)
  HOLD    → typed "pending approval" result carrying ``approval_ref``
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.mcp.tool_binding import (
    ActionClassification,
    ToolBinding,
    classify_tool,
)


class IdempotencyConflict(Exception):
    """The idempotency key was already used for a DIFFERENT payload.

    Raised by the kernel adapter so the proxy can surface a distinct
    ``idempotency_conflict`` reason rather than a generic gate failure.
    """


class GateDecision(str, Enum):
    OBSERVE = "observe"  # unprotected — passthrough + light receipt
    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"  # requires human approval


@dataclass(frozen=True)
class McpSession:
    """Auth/tenant context extracted from the MCP connection."""

    project_id: str
    environment: str
    agent_id: str | None = None
    principal: dict | None = None
    # Effective idempotency key for this call, resolved by the route:
    # caller-supplied token > (MCP session id + JSON-RPC id) > None. When
    # None the adapter mints a fresh unique key so NO dedupe happens — a
    # money rail must never silently collapse two legitimate identical calls.
    idempotency_key: str | None = None


@dataclass(frozen=True)
class KernelDecision:
    allowed: bool
    requires_approval: bool
    reasons: list[str]
    intent_id: str | None = None


class KernelPort(Protocol):
    """Adapter surface over ``action_kernel`` (open intent, run policy).

    The real adapter calls ``create_action_intent`` then
    ``decide_action_intent`` inside one DB transaction and maps the
    resulting ``ActionIntentDecision`` onto :class:`KernelDecision`.
    """

    def open_and_decide(
        self,
        *,
        session: McpSession,
        tool_name: str,
        classification: ActionClassification,
        arguments: dict,
    ) -> KernelDecision: ...


@dataclass(frozen=True)
class GateOutcome:
    decision: GateDecision
    classification: ActionClassification
    reasons: list[str]
    intent_id: str | None = None
    approval_ref: str | None = None

    @property
    def forwards_upstream(self) -> bool:
        """Whether the proxy should actually call the upstream tool."""
        return self.decision in (GateDecision.OBSERVE, GateDecision.ALLOW)


def evaluate(
    *,
    session: McpSession,
    tool_name: str,
    arguments: dict | None,
    kernel: KernelPort,
    bindings: list[ToolBinding] | None = None,
) -> GateOutcome:
    """Classify a tool call and, if protected, run it through the kernel."""
    args = dict(arguments or {})
    classification = classify_tool(tool_name, args, bindings)

    if not classification.protected:
        return GateOutcome(
            decision=GateDecision.OBSERVE,
            classification=classification,
            reasons=[
                f"'{tool_name}' classified as "
                f"{classification.action_type} ({classification.binding_source}); "
                "unprotected — observe-only passthrough"
            ],
        )

    decision = kernel.open_and_decide(
        session=session,
        tool_name=tool_name,
        classification=classification,
        arguments=args,
    )

    if decision.allowed:
        gate = GateDecision.ALLOW
        approval_ref = None
    elif decision.requires_approval:
        gate = GateDecision.HOLD
        approval_ref = decision.intent_id
    else:
        gate = GateDecision.DENY
        approval_ref = None

    return GateOutcome(
        decision=gate,
        classification=classification,
        reasons=list(decision.reasons),
        intent_id=decision.intent_id,
        approval_ref=approval_ref,
    )
