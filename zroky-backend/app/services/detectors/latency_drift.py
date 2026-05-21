"""LATENCY_DRIFT pattern-rule detector.

Fires when call latency *drifts* significantly from its rolling baseline,
even when the absolute value is below the LATENCY_ANOMALY hard threshold
(60s). This is the *behavioural* counterpart:

  - LATENCY_ANOMALY (Layer 1, fast rule):  latency_ms > absolute threshold
  - LATENCY_DRIFT   (Layer 2, pattern):    latency_ms > k × rolling P95

Use case: provider has degraded silently — was 2s P95, now 8s P95 —
still well under the SLO ceiling but worth surfacing because:
  * Prompt bloat dragging context size up
  * Provider regional outage / failover to slower DC
  * New tools added to agent loop that re-call the model

Inputs:
  - latency_ms                          — current call
  - latency.baseline_p50_ms             — rolling baseline
  - latency.baseline_p95_ms
  - latency.baseline_p99_ms             (optional, tighter trigger)
  - latency.history_calls / history_days

Skip rules:
  - history_days < 3 OR history_calls < 200  (warmup unmet)
  - latency_ms < _ABSOLUTE_FLOOR_MS (2000ms — too noisy on tiny calls)
  - latency_ms >= _ABSOLUTE_CEILING_MS (60_000ms — owned by LATENCY_ANOMALY)
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_LATENCY_DRIFT = 0.88
_P95_DRIFT_MULTIPLIER = 2.0
_P99_DRIFT_MULTIPLIER = 1.5
_ABSOLUTE_FLOOR_MS = 2_000
_ABSOLUTE_CEILING_MS = 60_000  # >= this → LATENCY_ANOMALY domain
_WARMUP_DAYS = 3
_WARMUP_CALLS = 200


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    return _detect(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect(payload)


def _detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    latency_ms = _as_float(
        _pick(
            payload,
            ("latency_ms",),
            ("response", "latency_ms"),
            ("call_latency_ms",),
            ("timing", "latency_ms"),
        ),
    )
    if latency_ms < _ABSOLUTE_FLOOR_MS:
        return None
    if latency_ms >= _ABSOLUTE_CEILING_MS:
        return None  # Owned by LATENCY_ANOMALY (fast rule)

    baseline_p50 = _as_float(
        _pick(
            payload,
            ("latency", "baseline_p50_ms"),
            ("baseline_latency_p50_ms",),
        ),
    )
    baseline_p95 = _as_float(
        _pick(
            payload,
            ("latency", "baseline_p95_ms"),
            ("baseline_latency_p95_ms",),
        ),
    )
    baseline_p99 = _as_float(
        _pick(
            payload,
            ("latency", "baseline_p99_ms"),
            ("baseline_latency_p99_ms",),
        ),
    )
    history_calls = _as_int(
        _pick(payload, ("latency", "history_calls"), ("history_calls",))
    )
    history_days = _as_float(
        _pick(payload, ("latency", "history_days"), ("history_days",))
    )

    if baseline_p95 <= 0:
        return None
    if history_days < _WARMUP_DAYS or history_calls < _WARMUP_CALLS:
        return None

    p95_threshold = baseline_p95 * _P95_DRIFT_MULTIPLIER
    p99_threshold = (
        baseline_p99 * _P99_DRIFT_MULTIPLIER if baseline_p99 > 0 else float("inf")
    )

    breach_p95 = latency_ms > p95_threshold
    breach_p99 = latency_ms > p99_threshold
    if not (breach_p95 or breach_p99):
        return None

    # Pick the tighter of the two breached thresholds for evidence display.
    if breach_p99 and (not breach_p95 or p99_threshold < p95_threshold):
        triggered_threshold = p99_threshold
        triggered_basis = "p99"
    else:
        triggered_threshold = p95_threshold
        triggered_basis = "p95"

    overshoot_ratio = round(latency_ms / max(baseline_p95, 1.0), 2)
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")
    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")

    return {
        "category": "LATENCY_DRIFT",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_LATENCY_DRIFT,
        "root_cause": (
            f"Call to {provider}/{model} took {latency_ms:.0f}ms — "
            f"{overshoot_ratio}× the rolling P95 of {baseline_p95:.0f}ms. "
            f"Triggered on the {triggered_basis} threshold "
            f"({triggered_threshold:.0f}ms)."
        ),
        "fix": {
            "primary": (
                "Compare prompt size and tool count against the previous "
                "deploy; LLM latency is dominated by input length and "
                "tool-call hops. Trim retrieved context to the top-k "
                "relevant chunks."
            ),
            "code": (
                "context_chunks = top_k(retrieved_chunks, k=5)\n"
                "request.timeout_ms = min(client_budget, p95_baseline * 3)"
            ),
            "alternative": (
                "Failover to a faster model variant when latency exceeds "
                "p95 × 1.5 — many providers offer Haiku/Mini-class fallbacks."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "latency_ms": int(latency_ms),
            "baseline_latency_p50_ms": int(baseline_p50) if baseline_p50 > 0 else None,
            "baseline_latency_p95_ms": int(baseline_p95),
            "baseline_latency_p99_ms": int(baseline_p99) if baseline_p99 > 0 else None,
            "p95_drift_threshold_ms": int(p95_threshold),
            "p99_drift_threshold_ms": (
                int(p99_threshold) if baseline_p99 > 0 else None
            ),
            "triggered_basis": triggered_basis,
            "overshoot_ratio_vs_p95": overshoot_ratio,
            "history_calls": history_calls,
            "history_days": history_days,
            "warmup_required_days": _WARMUP_DAYS,
            "warmup_required_calls": _WARMUP_CALLS,
            "absolute_floor_ms": _ABSOLUTE_FLOOR_MS,
            "absolute_ceiling_ms": _ABSOLUTE_CEILING_MS,
            "trigger_rule": "latency_ms > p95 * 2 OR latency_ms > p99 * 1.5",
        },
    }
