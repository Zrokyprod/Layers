# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""High-level protected action facade.

``protect`` is the public control-plane primitive: agents submit a real-world
action intent, Zroky applies policy/approval, and the backend-owned runner and
verifier produce proof.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from zroky._errors import ZrokyVerifiedActionError
from zroky._verified_action import await_action_proof, verified_action


def _default_contract_version(action: str) -> str:
    return f"{action}/1.0"


def protect(
    *,
    action: str,
    params: Mapping[str, Any] | None = None,
    operation_kind: str = "EXECUTE",
    contract_version: str | None = None,
    verification_profile: str | None = None,
    execution_request: Mapping[str, Any] | None = None,
    agent_id: str | None = None,
    environment: str = "production",
    principal: dict[str, Any] | None = None,
    actor_chain: list[dict[str, Any]] | None = None,
    purpose: dict[str, Any] | None = None,
    resource: dict[str, Any] | None = None,
    trace_context: dict[str, Any] | None = None,
    deadline: datetime | str | None = None,
    idempotency_key: str | None = None,
    raise_on_approval: bool = True,
    wait_for_receipt: bool = False,
    proof_timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Create a protected action intent and return its policy decision.

    This is intentionally action-first. Use it when an agent is about to touch a
    system of record: money movement, account access, production changes,
    outbound messages, or other side-effecting tools.

    Set ``wait_for_receipt=True`` when the caller should block until source-of-
    record verification and receipt generation reach a terminal state.
    """
    normalized_action = action.strip()
    if not normalized_action:
        raise ZrokyVerifiedActionError("[ZROKY] protect requires a non-empty action.")

    normalized_operation_kind = operation_kind.strip().upper()
    if not normalized_operation_kind:
        raise ZrokyVerifiedActionError("[ZROKY] protect requires a non-empty operation_kind.")

    decision = verified_action(
        agent_id=agent_id,
        contract_version=contract_version or _default_contract_version(normalized_action),
        action_type=normalized_action,
        operation_kind=normalized_operation_kind,
        environment=environment,
        principal=principal,
        actor_chain=actor_chain,
        purpose=purpose,
        resource=resource,
        parameters=dict(params or {}),
        execution_request=execution_request,
        verification_profile=verification_profile,
        deadline=deadline,
        trace_context=trace_context,
        idempotency_key=idempotency_key,
        raise_on_approval=raise_on_approval,
    )

    if not wait_for_receipt:
        return decision

    action_id = str(decision.get("action_id") or "")
    if not action_id:
        raise ZrokyVerifiedActionError("[ZROKY] protect could not wait for receipt without action_id.")

    proof = await_action_proof(
        action_id,
        timeout_seconds=proof_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return {
        "action_id": action_id,
        "decision": decision,
        "proof": proof,
        "receipt": proof.get("receipt"),
        "proof_status": proof.get("proof_status"),
        "receipt_status": proof.get("receipt_status"),
        "signature_valid": proof.get("signature_valid"),
        "evidence_id": proof.get("evidence_id"),
    }
