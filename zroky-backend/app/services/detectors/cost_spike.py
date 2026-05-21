"""COST_SPIKE pattern-rule detector."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _pick,
)

_COST_SPIKE_HARD_FLOOR_USD = 25.0
_RULE_CONFIDENCE_COST_SPIKE = 0.90


def detect(payload: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return _detect_cost_spike(payload)


def detect_entry(payload: Mapping[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    """Protocol-compatible shim for importlib.metadata entry-point registration.
    Returns only the primary diagnosis (first tuple element)."""
    primary, _ = _detect_cost_spike(payload)
    return primary


def _detect_cost_spike(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_spend = _as_float(
        _pick(
            payload,
            ("cost", "current_15m_spend_usd"),
            ("current_15m_spend_usd",),
            ("spend", "current_15m"),
        ),
    )
    baseline_spend = _as_float(
        _pick(
            payload,
            ("cost", "baseline_15m_spend_usd"),
            ("baseline_15m_spend_usd",),
            ("spend", "baseline_15m"),
        ),
    )
    history_days = _as_float(_pick(payload, ("cost", "history_days"), ("history_days",)))
    history_calls = _as_int(_pick(payload, ("cost", "history_calls"), ("history_calls",)))
    baseline_window_days = _as_int(
        _pick(payload, ("cost", "baseline_window_days"), ("baseline_window_days",)), fallback=14,
    )
    spend_bucket_minutes = _as_int(
        _pick(payload, ("cost", "spend_bucket_minutes"), ("spend_bucket_minutes",)), fallback=15,
    )
    model_coefficient = _as_float(
        _pick(payload, ("cost", "model_spend_coefficient"), ("model_spend_coefficient",)),
        fallback=1.0,
    )
    model_coefficient = max(model_coefficient, 1.0)

    if current_spend <= 0 and baseline_spend <= 0:
        return None, None

    warmup_ready = history_days >= 3 and history_calls >= 200
    effective_baseline = baseline_spend * model_coefficient
    hard_threshold = max(3 * effective_baseline, effective_baseline + _COST_SPIKE_HARD_FLOOR_USD)

    if not warmup_ready:
        informational_threshold = max(2 * max(effective_baseline, 0.01), effective_baseline + 10)
        if current_spend > informational_threshold:
            return None, {
                "type": "COST_SURGE_WARNING",
                "message": "Spend surge observed before baseline warm-up gate was met.",
                "evidence": {
                    "current_15m_spend_usd": current_spend,
                    "baseline_15m_spend_usd": baseline_spend,
                    "effective_baseline_15m_spend_usd": effective_baseline,
                    "history_days": history_days,
                    "history_calls": history_calls,
                    "warmup_required_days": 3,
                    "warmup_required_calls": 200,
                    "baseline_window_days": baseline_window_days,
                    "spend_bucket_minutes": spend_bucket_minutes,
                    "model_spend_coefficient": model_coefficient,
                },
            }
        return None, None

    if current_spend <= hard_threshold:
        return None, None

    return {
        "category": "COST_SPIKE",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_COST_SPIKE,
        "root_cause": (
            "Current 15-minute spend exceeded project baseline threshold: "
            f"{current_spend:.2f} USD vs threshold {hard_threshold:.2f} USD."
        ),
        "fix": {
            "primary": "Throttle high-cost routes and enforce budget-aware model routing immediately.",
            "code": (
                "if current_15m_spend_usd > cost_threshold:\n"
                "    route_to_lower_cost_model(); enable_budget_guardrails()"
            ),
            "alternative": "Apply per-model spend caps and temporary traffic shaping for top spenders.",
        },
        "evidence": {
            "current_15m_spend_usd": current_spend,
            "baseline_15m_spend_usd": baseline_spend,
            "effective_baseline_15m_spend_usd": effective_baseline,
            "hard_threshold_15m_spend_usd": hard_threshold,
            "trigger_rule": "current_15m_spend > max(3*baseline, baseline+25)",
            "history_days": history_days,
            "history_calls": history_calls,
            "warmup_gate_met": warmup_ready,
            "warmup_required_days": 3,
            "warmup_required_calls": 200,
            "baseline_window_days": baseline_window_days,
            "spend_bucket_minutes": spend_bucket_minutes,
            "model_spend_coefficient": model_coefficient,
        },
    }, None
