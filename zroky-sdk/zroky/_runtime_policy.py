# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Runtime policy gate client.

Agents call this before executing risky tools or external actions. The helper
fails closed: if the control plane cannot return an explicit allow decision,
the caller gets an exception instead of silently continuing.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from zroky._errors import ZrokyRuntimePolicyBlocked, ZrokyRuntimePolicyError
from zroky._internal.pii import mask_value

_REQUEST_TIMEOUT_S = 8.0


def _runtime_policy_url(ingest_url: str) -> str:
    parsed = urlsplit(ingest_url)
    if not parsed.scheme or not parsed.netloc:
        return ingest_url.rstrip("/") + "/v1/runtime-policy/check"

    path = parsed.path.rstrip("/")
    for suffix in ("/api/v1/ingest", "/v1/ingest", "/ingest"):
        if path.endswith(suffix):
            base_path = path[: -len(suffix)].rstrip("/")
            runtime_path = f"{base_path}/v1/runtime-policy/check"
            return urlunsplit((parsed.scheme, parsed.netloc, runtime_path, "", ""))

    return urlunsplit((parsed.scheme, parsed.netloc, "/v1/runtime-policy/check", "", ""))


def check_runtime_policy(
    *,
    action_type: str,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | list[Any] | str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    call_id: str | None = None,
    agent_name: str | None = None,
    role: str | None = None,
    tool_call_count: int | None = None,
    retry_count: int | None = None,
    estimated_cost_usd: float | None = None,
    input_text: str | None = None,
    user_input: str | None = None,
    output_text: str | None = None,
    external_action: bool | None = None,
    prompt_injection_detected: bool | None = None,
    pii_detected: bool | None = None,
    approval_id: str | None = None,
    business_impact: dict[str, Any] | str | None = None,
    business_impact_summary: str | None = None,
    impact_usd: float | None = None,
    customer_id: str | None = None,
    account_id: str | None = None,
    order_id: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    raise_on_block: bool = True,
) -> dict[str, Any]:
    """Return the backend runtime policy decision for a pending agent action.

    When ``raise_on_block`` is true, any non-allow decision raises
    ``ZrokyRuntimePolicyBlocked``. Transport errors and non-2xx responses raise
    ``ZrokyRuntimePolicyError`` so callers fail closed.
    """
    import zroky as _z  # lazy import keeps global config in sync

    if _z._config is None:
        _z.init()
    cfg = _z._config
    if cfg is None:
        raise ZrokyRuntimePolicyError("[ZROKY] Runtime policy gate is not initialized.")

    pii_hit = False

    def _masked(value: Any) -> Any:
        nonlocal pii_hit
        if not cfg.mask_pii:
            return value
        masked = mask_value(value)
        if masked != value:
            pii_hit = True
        return masked

    masked_tool_args = _masked(tool_args)
    masked_input_text = _masked(input_text)
    masked_user_input = _masked(user_input)
    masked_output_text = _masked(output_text)
    masked_business_impact = _masked(business_impact)
    masked_metadata = _masked(metadata)

    payload: dict[str, Any] = {
        "action_type": action_type,
        "tool_name": tool_name,
        "tool_args": masked_tool_args,
        "trace_id": trace_id,
        "span_id": span_id,
        "call_id": call_id,
        "agent_name": agent_name or _z._get_agent() or cfg.default_agent,
        "role": role,
        "tool_call_count": tool_call_count,
        "retry_count": retry_count,
        "estimated_cost_usd": estimated_cost_usd,
        "input_text": masked_input_text,
        "user_input": masked_user_input,
        "output_text": masked_output_text,
        "external_action": external_action,
        "prompt_injection_detected": prompt_injection_detected,
        "pii_detected": pii_detected if pii_detected is not None else (pii_hit or None),
        "approval_id": approval_id,
        "business_impact": masked_business_impact,
        "business_impact_summary": _masked(business_impact_summary),
        "impact_usd": impact_usd,
        "customer_id": _masked(customer_id),
        "account_id": _masked(account_id),
        "order_id": _masked(order_id),
        "resource_id": _masked(resource_id),
        "metadata": masked_metadata,
    }
    payload = {key: value for key, value in payload.items() if value is not None}

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["x-api-key"] = cfg.api_key
    if cfg.project:
        headers["x-project-id"] = cfg.project

    try:
        response = httpx.post(
            _runtime_policy_url(cfg.ingest_url),
            headers=headers,
            json=payload,
            timeout=_REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise ZrokyRuntimePolicyError(
            f"[ZROKY] Runtime policy gate unavailable: {exc}",
        ) from exc

    if response.status_code >= 300:
        raise ZrokyRuntimePolicyError(
            f"[ZROKY] Runtime policy gate failed with HTTP {response.status_code}.",
        )

    decision = response.json()
    allowed = bool(decision.get("allowed"))
    if not allowed and raise_on_block:
        reasons = decision.get("reasons") if isinstance(decision.get("reasons"), list) else []
        reason_text = ", ".join(str(item) for item in reasons) or "runtime policy blocked action"
        raise ZrokyRuntimePolicyBlocked(
            f"[ZROKY] Runtime policy blocked action: {reason_text}",
            decision=decision,
        )

    return decision
