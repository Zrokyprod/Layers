# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Saved connector outcome verification helpers."""
from __future__ import annotations

from typing import Any, Literal

import httpx

from zroky._errors import ZrokyOutcomeVerificationError

_REQUEST_TIMEOUT_S = 15.0

SavedVerificationConnector = Literal["generic_rest", "ledger_refund", "crm_record"]


def _outcome_reconciliation_url(ingest_url: str, connector: SavedVerificationConnector) -> str:
    paths = {
        "generic_rest": "/v1/outcomes/reconciliation/generic-rest/saved",
        "ledger_refund": "/v1/outcomes/reconciliation/ledger-refund/saved",
        "crm_record": "/v1/outcomes/reconciliation/customer-record/saved",
    }
    return ingest_url.rstrip("/") + paths[connector]


def _connector_payload(
    *,
    connector: SavedVerificationConnector,
    record_ref: str | None,
    refund_id: str | None,
    customer_id: str | None,
) -> dict[str, Any]:
    if connector == "generic_rest":
        cleaned_record_ref = (record_ref or "").strip()
        if not cleaned_record_ref:
            raise ZrokyOutcomeVerificationError(
                "[ZROKY] Generic REST outcome verification requires record_ref."
            )
        return {"record_ref": cleaned_record_ref}
    if connector == "ledger_refund":
        return {"refund_id": refund_id} if refund_id else {}
    if connector == "crm_record":
        return {"customer_id": customer_id} if customer_id else {}
    raise ZrokyOutcomeVerificationError(
        f"[ZROKY] Unsupported verification connector: {connector!r}."
    )


def verify_outcome(
    *,
    connector: SavedVerificationConnector,
    claimed: dict[str, Any],
    record_ref: str | None = None,
    refund_id: str | None = None,
    customer_id: str | None = None,
    call_id: str | None = None,
    trace_id: str | None = None,
    runtime_policy_decision_id: str | None = None,
    action_type: str | None = None,
    system_ref: str | None = None,
    match_fields: list[str] | tuple[str, ...] | None = None,
    amount_usd: float | None = None,
    currency: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify an agent's claimed post-action outcome through a saved connector.

    The SDK sends only the record reference and claimed result. Customer-owned
    connector credentials remain stored server-side in Zroky.
    """
    import zroky as _z

    if _z._config is None:
        _z.init()
    cfg = _z._config
    if cfg is None:
        raise ZrokyOutcomeVerificationError("[ZROKY] Outcome verification is not initialized.")
    if not cfg.api_key or not cfg.project:
        raise ZrokyOutcomeVerificationError(
            "[ZROKY] Outcome verification requires api_key and project."
        )

    payload: dict[str, Any] = {
        **_connector_payload(
            connector=connector,
            record_ref=record_ref,
            refund_id=refund_id,
            customer_id=customer_id,
        ),
        "call_id": call_id,
        "trace_id": trace_id,
        "runtime_policy_decision_id": runtime_policy_decision_id,
        "action_type": action_type,
        "system_ref": system_ref,
        "claimed": claimed,
        "match_fields": list(match_fields) if match_fields else None,
        "amount_usd": amount_usd,
        "currency": currency,
        "idempotency_key": idempotency_key,
        "metadata": metadata,
    }
    payload = {key: value for key, value in payload.items() if value is not None}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
        "x-api-key": cfg.api_key,
        "x-project-id": cfg.project,
    }

    try:
        response = httpx.post(
            _outcome_reconciliation_url(cfg.ingest_url, connector),
            headers=headers,
            json=payload,
            timeout=_REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise ZrokyOutcomeVerificationError(
            f"[ZROKY] Outcome verification unavailable: {exc}",
        ) from exc

    if response.status_code >= 300:
        raise ZrokyOutcomeVerificationError(
            f"[ZROKY] Outcome verification failed with HTTP {response.status_code}."
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise ZrokyOutcomeVerificationError(
            f"[ZROKY] Outcome verification returned invalid JSON: {exc}",
        ) from exc
    if not isinstance(result, dict):
        raise ZrokyOutcomeVerificationError(
            "[ZROKY] Outcome verification returned an invalid response shape."
        )
    return result
