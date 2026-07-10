"""Safe, deterministic next actions for MCP policy outcomes.

This is an agent-facing contract, not a policy explanation. It intentionally
uses a small allowlist of stable reason codes and action types. Detailed
runtime-policy reasons remain inside the kernel and durable audit trail so the
MCP proxy does not become a policy-discovery or bypass oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Remediation:
    """A machine-readable, safe next step after a non-allow outcome."""

    reason_code: str
    retryable: bool
    next_actions: tuple[dict[str, str], ...]
    retry_after_seconds: int | None = None

    def to_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "reason_code": self.reason_code,
            "retryable": self.retryable,
            "next_actions": [dict(action) for action in self.next_actions],
        }
        if self.retry_after_seconds is not None:
            meta["retry_after_seconds"] = self.retry_after_seconds
        return meta


def for_hold(*, approval_ref: str | None) -> Remediation:
    action: dict[str, str] = {"type": "await_approval"}
    if approval_ref:
        action["approval_ref"] = approval_ref
    return Remediation(
        reason_code="approval_required",
        retryable=False,
        next_actions=(action,),
    )


def for_policy_deny(reasons: list[str]) -> Remediation:
    """Map only known lifecycle states; all policy rules stay opaque."""
    normalized = {" ".join(reason.lower().split()) for reason in reasons}
    if "linked approval was rejected" in normalized:
        return Remediation(
            reason_code="approval_rejected",
            retryable=False,
            next_actions=({"type": "escalate_to_human"},),
        )
    if "linked approval expired" in normalized:
        return Remediation(
            reason_code="approval_expired",
            retryable=False,
            next_actions=({"type": "request_new_approval"},),
        )
    return Remediation(
        reason_code="policy_denied",
        retryable=False,
        next_actions=({"type": "escalate_to_human"},),
    )


def for_idempotency_conflict() -> Remediation:
    return Remediation(
        reason_code="idempotency_conflict",
        retryable=False,
        next_actions=({"type": "review_idempotency_key"},),
    )


def for_service_unavailable(reason_code: str) -> Remediation:
    if reason_code not in {"audit_unavailable", "gate_unavailable"}:
        raise ValueError("unsupported service-unavailable reason code")
    return Remediation(
        reason_code=reason_code,
        retryable=True,
        retry_after_seconds=30,
        next_actions=({"type": "retry_later"},),
    )


def for_execution_unknown(*, intent_id: str | None) -> Remediation:
    action: dict[str, str] = {"type": "check_execution_status"}
    if intent_id:
        action["intent_id"] = intent_id
    return Remediation(
        reason_code="execution_unknown",
        retryable=False,
        next_actions=(action,),
    )
