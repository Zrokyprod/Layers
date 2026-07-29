# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

import httpx

from zroky._errors import (
    ZrokyRuntimePolicyApprovalRequired,
    ZrokyRuntimePolicyBlocked,
    ZrokyRuntimePolicyError,
)
from zroky._verified_action import _api_url, _ensure_config, _headers

_REQUEST_TIMEOUT_S = 8.0


def pre_execution_guard(
    *,
    intent: Mapping[str, Any],
    environment: str = "production",
    agent_ref: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create a trusted intent and enforce final policy before side effects."""
    cfg = _ensure_config()
    key = idempotency_key or f"intent-{uuid4()}"
    try:
        intent_response = httpx.post(
            _api_url(cfg.ingest_url, "/v1/intents"),
            headers=_headers(cfg, idempotency_key=key),
            json={"environment": environment, "agent_ref": agent_ref, "intent": dict(intent)},
            timeout=_REQUEST_TIMEOUT_S,
        )
        intent_response.raise_for_status()
        created_intent = intent_response.json()

        policy_response = httpx.post(
            _api_url(cfg.ingest_url, "/v1/policy/check"),
            headers=_headers(cfg),
            json={"intent_id": created_intent["id"]},
            timeout=_REQUEST_TIMEOUT_S,
        )
        policy_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ZrokyRuntimePolicyError(f"[ZROKY] Pre-execution guard unavailable: {exc}") from exc

    decision = policy_response.json()
    if decision.get("decision") == "allow":
        return {"intent": created_intent, "policy": decision}
    if decision.get("decision") == "approval_required":
        raise ZrokyRuntimePolicyApprovalRequired("[ZROKY] Pre-execution guard requires approval.", decision=decision)
    raise ZrokyRuntimePolicyBlocked("[ZROKY] Pre-execution guard did not allow action.", decision=decision)
