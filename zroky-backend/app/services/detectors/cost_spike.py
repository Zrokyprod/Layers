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
    per_call_cost = _as_float(
        _pick(
            payload,
            ("cost_usd",),
            ("cost_total",),
            ("total_cost",),
            ("cost", "usd"),
            ("cost", "total"),
            ("usage", "cost_usd"),
        ),
    )
    per_session_cost = _as_float(
        _pick(payload, ("per_session_cost_usd",), ("session", "cost_usd")),
    )
    if per_call_cost >= 1.0 or per_session_cost >= 10.0:
        return _cost_spike_result(
            current_spend=max(per_call_cost, per_session_cost),
            baseline_spend=0.0,
            effective_baseline=0.0,
            hard_threshold=1.0 if per_call_cost >= 1.0 else 10.0,
            history_days=0.0,
            history_calls=0,
            baseline_window_days=0,
            spend_bucket_minutes=0,
            model_coefficient=1.0,
            trigger_rule="per-call or per-session spend exceeded launch guardrail",
        ), None

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

    return _cost_spike_result(
        current_spend=current_spend,
        baseline_spend=baseline_spend,
        effective_baseline=effective_baseline,
        hard_threshold=hard_threshold,
        history_days=history_days,
        history_calls=history_calls,
        baseline_window_days=baseline_window_days,
        spend_bucket_minutes=spend_bucket_minutes,
        model_coefficient=model_coefficient,
        trigger_rule="current_15m_spend > max(3*baseline, baseline+25)",
    ), None


def _cost_spike_result(
    *,
    current_spend: float,
    baseline_spend: float,
    effective_baseline: float,
    hard_threshold: float,
    history_days: float,
    history_calls: int,
    baseline_window_days: int,
    spend_bucket_minutes: int,
    model_coefficient: float,
    trigger_rule: str,
) -> dict[str, Any]:
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
            "trigger_rule": trigger_rule,
            "history_days": history_days,
            "history_calls": history_calls,
            "warmup_gate_met": history_days >= 3 and history_calls >= 200,
            "warmup_required_days": 3,
            "warmup_required_calls": 200,
            "baseline_window_days": baseline_window_days,
            "spend_bucket_minutes": spend_bucket_minutes,
            "model_spend_coefficient": model_coefficient,
        },
    }
