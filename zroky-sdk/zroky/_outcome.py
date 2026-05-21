# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""outcome() — attach a business cost to a Zroky call.

Usage:
    import zroky
    zroky.init(api_key="...", project="proj_xxx")

    # After your AI call:
    result = zroky.call(client.chat.completions.create, ...)
    call_id = result._zroky_call_id

    # When a downstream business event occurs:
    zroky.outcome(
        call_id=call_id,
        type="refund_issued",
        amount_usd=49.00,
        metadata={"order_id": "ORD-9182", "customer_tier": "premium"},
    )

Fire-and-forget: the HTTP POST runs in a daemon thread and never blocks the
caller.  Retries once on transient network error; permanent errors are logged
at DEBUG level and dropped — outcome data is best-effort.
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

_logger = logging.getLogger("zroky.outcome")

_OUTCOME_PATH = "/v1/outcomes"
_TIMEOUT_S = 5.0
_MAX_RETRIES = 2


def _post_outcome(
    ingest_url: str,
    api_key: str,
    payload: dict[str, Any],
) -> None:
    """Fire the HTTP POST with simple retry.  Runs in a daemon thread."""
    body = json.dumps(payload, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = ingest_url.rstrip("/") + _OUTCOME_PATH
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                if resp.status < 300:
                    _logger.debug(
                        "zroky.outcome sent call_id=%s type=%s attempt=%d",
                        payload.get("call_id"),
                        payload.get("outcome_type"),
                        attempt,
                    )
                    return
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                _logger.debug(
                    "zroky.outcome permanent error %d call_id=%s",
                    exc.code,
                    payload.get("call_id"),
                )
                return
            _logger.debug(
                "zroky.outcome server error %d attempt=%d", exc.code, attempt
            )
        except Exception as exc:  # noqa: BLE001
            _logger.debug(
                "zroky.outcome network error attempt=%d: %s", attempt, exc
            )
        if attempt == _MAX_RETRIES:
            _logger.debug(
                "zroky.outcome dropped after %d attempts call_id=%s",
                _MAX_RETRIES,
                payload.get("call_id"),
            )


def outcome(
    call_id: str,
    *,
    type: str,  # noqa: A002  (shadows built-in, matches user-facing API)
    amount_usd: float = 0.0,
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Attach a business-outcome cost to a Zroky call.

    Parameters
    ----------
    call_id:
        The ``_zroky_call_id`` returned on the response object of a
        ``zroky.call()`` / ``zroky.record()`` invocation.
    type:
        Outcome category.  Well-known values: ``refund_issued``,
        ``ticket_escalated``, ``human_handoff``, ``churn``,
        ``compliance_fine``, ``retry_cost``, ``custom``.
    amount_usd:
        Monetary cost of this outcome in USD (default 0).
    occurred_at:
        When the business event happened (defaults to now).
    idempotency_key:
        Stable key for dedup — same key always returns the same server row.
        Defaults to ``"{call_id}:{type}"`` so SDK retries never double-count.
    metadata:
        Arbitrary JSON-serialisable dict (order_id, customer_id, …).
    """
    import zroky as _z

    cfg = _z._config
    if cfg is None:
        _logger.debug("zroky.outcome called before zroky.init() — dropping")
        return

    api_key = cfg.api_key
    ingest_url = cfg.ingest_url or "https://api.zroky.ai"
    if not api_key:
        _logger.debug("zroky.outcome: no api_key configured — dropping")
        return

    key = idempotency_key or f"{call_id}:{type}"
    payload: dict[str, Any] = {
        "call_id": call_id,
        "outcome_type": type,
        "amount_usd": float(amount_usd),
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
        "idempotency_key": key,
        "source": "sdk",
    }
    if metadata:
        payload["metadata"] = metadata

    t = threading.Thread(
        target=_post_outcome,
        args=(ingest_url, api_key, payload),
        daemon=True,
        name="zroky-outcome",
    )
    t.start()
