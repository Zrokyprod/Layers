# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Verified action client for backend-owned execution, verification, and receipt."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx

from zroky._errors import (
    ZrokyVerifiedActionApprovalRequired,
    ZrokyVerifiedActionBlocked,
    ZrokyVerifiedActionError,
)

_REQUEST_TIMEOUT_S = 8.0
_TERMINAL_PROOF_STATUSES = {"matched", "mismatched", "not_verified"}
_TERMINAL_RECEIPT_STATUSES = {"generated", "failed"}

_EXECUTION_REQUEST_FORBIDDEN_KEYS = {
    "runner_id",
    "runner",
    "credential_ref",
    "credential_reference",
    "protected_credential_ref",
}
_EXECUTION_REQUEST_RAW_SECRET_KEYS = {
    "authorization",
    "bearer_token",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
}
_EXECUTION_REQUEST_RAW_SECRET_VALUES = (
    "bearer ",
    "sk_live_",
    "sk_test_",
    "xoxb-",
    "xoxp-",
    "ghp_",
    "gho_",
    "github_pat_",
    "-----begin private key-----",
)


def _api_base(ingest_url: str) -> str:
    parsed = urlsplit(ingest_url)
    if not parsed.scheme or not parsed.netloc:
        return ingest_url.rstrip("/")

    path = parsed.path.rstrip("/")
    for suffix in ("/api/v1/ingest", "/v1/ingest", "/ingest"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _api_url(ingest_url: str, path: str) -> str:
    return f"{_api_base(ingest_url)}{path}"


def _execution_request_violation(value: Any, *, key_path: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).strip().lower()
            if key_text in _EXECUTION_REQUEST_FORBIDDEN_KEYS:
                return ".".join((*key_path, str(key)))
            if any(marker in key_text for marker in _EXECUTION_REQUEST_RAW_SECRET_KEYS):
                return ".".join((*key_path, str(key)))
            found = _execution_request_violation(nested, key_path=(*key_path, str(key)))
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            found = _execution_request_violation(nested, key_path=(*key_path, str(index)))
            if found is not None:
                return found
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if any(marker in lowered for marker in _EXECUTION_REQUEST_RAW_SECRET_VALUES):
            return ".".join(key_path) or "execution_request"
    return None


def _validate_execution_request(execution_request: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if execution_request is None:
        return None
    if not isinstance(execution_request, Mapping):
        raise ZrokyVerifiedActionError("[ZROKY] execution_request must be an object.")
    execution_plan = execution_request.get("execution_plan")
    if not isinstance(execution_plan, Mapping) or not execution_plan:
        raise ZrokyVerifiedActionError("[ZROKY] execution_request.execution_plan must be a non-empty object.")
    credential_pointer = execution_request.get("credential_pointer")
    if isinstance(credential_pointer, str) and "://" in credential_pointer:
        raise ZrokyVerifiedActionError("[ZROKY] execution_request.credential_pointer must be a non-secret alias.")
    credential = execution_request.get("credential")
    if isinstance(credential, Mapping):
        nested_pointer = credential.get("pointer")
        if isinstance(nested_pointer, str) and "://" in nested_pointer:
            raise ZrokyVerifiedActionError("[ZROKY] execution_request.credential.pointer must be a non-secret alias.")
    violation = _execution_request_violation(execution_request)
    if violation is not None:
        raise ZrokyVerifiedActionError(
            "[ZROKY] execution_request must not include runner pins, protected "
            f"credential refs, or raw secret material at {violation}."
        )
    return dict(execution_request)


def _ensure_config():
    import zroky as _z  # lazy import keeps global config in sync

    if _z._config is None:
        _z.init()
    cfg = _z._config
    if cfg is None or not cfg.api_key or not cfg.project:
        raise ZrokyVerifiedActionError("[ZROKY] verified_action requires api_key and project.")
    return cfg


def _headers(cfg: Any, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.api_key,
        "x-project-id": cfg.project,
        "Authorization": f"Bearer {cfg.api_key}",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _request_json(
    method: str,
    path: str,
    *,
    json_payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    timeout: float = _REQUEST_TIMEOUT_S,
) -> dict[str, Any]:
    cfg = _ensure_config()
    try:
        response = httpx.request(
            method,
            _api_url(cfg.ingest_url, path),
            headers=_headers(cfg, idempotency_key=idempotency_key),
            json=json_payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ZrokyVerifiedActionError(f"[ZROKY] verified action API unavailable: {exc}") from exc

    if response.status_code >= 300:
        raise ZrokyVerifiedActionError(
            f"[ZROKY] verified action API failed with HTTP {response.status_code}: {response.text[:240]}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ZrokyVerifiedActionError("[ZROKY] verified action API returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise ZrokyVerifiedActionError("[ZROKY] verified action API returned a non-object response.")
    return data


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _iso_or_value(value: datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _requires_approval(decision: dict[str, Any]) -> bool:
    return bool(decision.get("requires_approval")) or decision.get("status") == "approval_pending"


def _blocked(decision: dict[str, Any]) -> bool:
    return bool(decision.get("allowed")) is False and not _requires_approval(decision)


def verified_action(
    *,
    agent_id: str | None = None,
    contract_version: str,
    action_type: str,
    operation_kind: str,
    environment: str = "production",
    principal: dict[str, Any] | None = None,
    actor_chain: list[dict[str, Any]] | None = None,
    purpose: dict[str, Any] | None = None,
    resource: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    execution_request: Mapping[str, Any] | None = None,
    verification_profile: str | None = None,
    deadline: datetime | str | None = None,
    trace_context: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    raise_on_approval: bool = True,
) -> dict[str, Any]:
    """Create and authorize a backend-owned verified action.

    The agent supplies only intent plus an execution_request. It must not name a
    runner or protected credential ref; the backend resolves those from runner
    configuration, then workers execute and verify independently.
    """

    checked_execution_request = _validate_execution_request(execution_request)
    effective_idempotency_key = idempotency_key or f"zroky-sdk:{uuid4()}"
    cfg = _ensure_config()
    payload = _without_none(
        {
            "agent_id": agent_id or cfg.default_agent_id,
            "contract_version": contract_version,
            "action_type": action_type,
            "operation_kind": operation_kind,
            "environment": environment,
            "principal": principal or {},
            "actor_chain": actor_chain or [],
            "purpose": purpose or {},
            "resource": resource or {},
            "parameters": parameters or {},
            "execution_request": checked_execution_request,
            "verification_profile": verification_profile,
            "deadline": _iso_or_value(deadline),
            "trace_context": trace_context,
        }
    )

    action = _request_json(
        "POST",
        "/v1/action-intents",
        json_payload=payload,
        idempotency_key=effective_idempotency_key,
    )
    action_id = str(action.get("action_id") or "")
    if not action_id:
        raise ZrokyVerifiedActionError("[ZROKY] verified action create response did not include action_id.")

    decision = _request_json("POST", f"/v1/action-intents/{action_id}/decide", json_payload={})
    if _requires_approval(decision):
        if raise_on_approval:
            raise ZrokyVerifiedActionApprovalRequired(
                "[ZROKY] verified action requires approval before execution.",
                action=action,
                decision=decision,
            )
        return decision
    if _blocked(decision):
        raise ZrokyVerifiedActionBlocked(
            "[ZROKY] verified action was blocked by policy.",
            action=action,
            decision=decision,
        )
    return decision


def await_action_proof(
    action_id: str,
    *,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Poll until backend verification and receipt generation reach a terminal state."""

    deadline = time.monotonic() + max(0.1, timeout_seconds)
    last_action: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        action = _request_json("GET", f"/v1/action-intents/{action_id}")
        last_action = action
        proof_status = str(action.get("proof_status") or "")
        receipt_status = str(action.get("receipt_status") or "")
        if proof_status in _TERMINAL_PROOF_STATUSES and receipt_status in _TERMINAL_RECEIPT_STATUSES:
            receipt: dict[str, Any] | None = None
            if receipt_status == "generated":
                receipt = _request_json("GET", f"/v1/action-intents/{action_id}/receipt")
            return {
                "action_id": action_id,
                "action": action,
                "receipt": receipt,
                "proof_status": proof_status,
                "receipt_status": receipt_status,
                "signature_valid": receipt.get("signature_valid") if receipt else None,
                "evidence_id": receipt.get("receipt_id") if receipt else None,
            }
        time.sleep(max(0.05, poll_interval_seconds))

    raise ZrokyVerifiedActionError(
        "[ZROKY] timed out waiting for verified action proof.",
        action=last_action,
    )
