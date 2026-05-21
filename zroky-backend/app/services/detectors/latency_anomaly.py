"""LATENCY_ANOMALY fast-rule detector.

Fires when a single LLM/agent call exceeded an absolute latency ceiling.

Threshold resolution order (first non-zero wins):
  1. payload.latency_threshold_ms        (per-call override)
  2. payload.contract.latency_budget_ms  (contract-level cap)
  3. _DEFAULT_LATENCY_THRESHOLD_MS       (60_000ms = 60s)

This is intentionally a *fast* rule — no rolling baseline required.
For statistical drift (e.g. p95 trending upward), use the Layer-2
baseline-drift detectors (separate module).

We avoid double-firing when the call already failed for a transport
reason — TIMEOUT-class failures are owned by provider_error.py.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_LATENCY_ANOMALY = 0.90
_DEFAULT_LATENCY_THRESHOLD_MS = 60_000.0
_MIN_LATENCY_THRESHOLD_MS = 1_000.0  # Reject obviously-bogus thresholds < 1s


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_latency_anomaly(payload)


def _resolve_threshold_ms(payload: Mapping[str, Any]) -> tuple[float, str]:
    explicit = _as_float(
        _pick(
            payload,
            ("latency_threshold_ms",),
            ("contract", "latency_threshold_ms"),
        ),
    )
    if explicit >= _MIN_LATENCY_THRESHOLD_MS:
        return explicit, "payload_explicit"

    contract_budget = _as_float(
        _pick(
            payload,
            ("contract", "latency_budget_ms"),
            ("latency_budget_ms",),
        ),
    )
    if contract_budget >= _MIN_LATENCY_THRESHOLD_MS:
        return contract_budget, "contract_budget"

    return _DEFAULT_LATENCY_THRESHOLD_MS, "default"


def _detect_latency_anomaly(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    latency_ms = _as_float(
        _pick(
            payload,
            ("latency_ms",),
            ("response", "latency_ms"),
            ("call_latency_ms",),
            ("timing", "latency_ms"),
        ),
    )
    if latency_ms <= 0:
        return None

    threshold_ms, threshold_source = _resolve_threshold_ms(payload)
    if latency_ms <= threshold_ms:
        return None

    # Skip if this was a timeout-class failure — provider_error owns those.
    error_code = _as_str(
        _pick(
            payload,
            ("error_code",),
            ("error", "code"),
            ("failure_reason", "classification"),
        ),
    ).lower()
    if "timeout" in error_code:
        return None

    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")
    prompt_tokens = _as_int(
        _pick(payload, ("prompt_tokens",), ("usage", "prompt_tokens"))
    )
    completion_tokens = _as_int(
        _pick(payload, ("completion_tokens",), ("usage", "completion_tokens"))
    )

    overshoot_ms = latency_ms - threshold_ms
    overshoot_ratio = round(latency_ms / threshold_ms, 2) if threshold_ms > 0 else None

    return {
        "category": "LATENCY_ANOMALY",
        "speed_class": "fast",
        "confidence": _RULE_CONFIDENCE_LATENCY_ANOMALY,
        "root_cause": (
            f"Call to {provider}/{model} took {latency_ms:.0f}ms, exceeding "
            f"the {threshold_source} threshold of {threshold_ms:.0f}ms by "
            f"{overshoot_ms:.0f}ms."
        ),
        "fix": {
            "primary": (
                "Add a hard request-side timeout below the threshold and "
                "route overflow traffic to a faster model or cached response."
            ),
            "code": (
                "with timeout(ms=client_timeout_budget):\n"
                "    response = await client.chat_completions(...)"
            ),
            "alternative": (
                "Reduce prompt size or completion length; long prompts and "
                "long completions are the dominant latency drivers — split "
                "the task into smaller stages."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "latency_ms": int(latency_ms),
            "threshold_ms": int(threshold_ms),
            "threshold_source": threshold_source,
            "overshoot_ms": int(overshoot_ms),
            "overshoot_ratio": overshoot_ratio,
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "trigger_rule": "latency_ms_gt_threshold",
        },
    }
