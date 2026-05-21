"""ERROR_RATE_DRIFT pattern-rule detector.

Fires when the rolling 15-minute error rate for an agent / project
deviates significantly from its baseline — i.e. something started
breaking in production within the last quarter-hour.

Distinct from the per-call error detectors (PROVIDER_ERROR, AUTH_FAILURE,
RATE_LIMIT) which fire on a single failing call. ERROR_RATE_DRIFT is a
*portfolio* signal: each individual call may not match a known error
pattern, but the overall failure ratio has stepped up.

Inputs (payload-injected upstream by analytics service):
  - error_rate.current_15m              — fraction in [0, 1]
  - error_rate.baseline_15m             — historical fraction in [0, 1]
  - error_rate.history_calls / history_days
  - error_rate.window_calls             — calls observed in current 15m

Trigger:
  current >= max(3 × baseline, baseline + 0.05)

  And gated by absolute floor: current >= 0.02 (don't fire when error
  rate is structurally tiny — e.g. 0.001 → 0.005 is "3× baseline" but
  not actionable).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_ERROR_RATE_DRIFT = 0.92
_DRIFT_MULTIPLIER = 3.0
_ABSOLUTE_DRIFT_DELTA = 0.05  # 5 percentage points
_ABSOLUTE_FLOOR_RATE = 0.02  # 2% — below this, don't surface drift
_WARMUP_DAYS = 3
_WARMUP_CALLS = 200
_MIN_WINDOW_CALLS = 20  # Need at least 20 calls in the 15m window to be statistical


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    return _detect(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect(payload)


def _detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    current_rate = _as_float(
        _pick(
            payload,
            ("error_rate", "current_15m"),
            ("error_rate_current_15m",),
        ),
    )
    baseline_rate = _as_float(
        _pick(
            payload,
            ("error_rate", "baseline_15m"),
            ("error_rate_baseline_15m",),
        ),
    )
    history_calls = _as_int(
        _pick(payload, ("error_rate", "history_calls"), ("history_calls",))
    )
    history_days = _as_float(
        _pick(payload, ("error_rate", "history_days"), ("history_days",))
    )
    window_calls = _as_int(
        _pick(
            payload,
            ("error_rate", "window_calls"),
            ("error_rate_window_calls",),
        ),
    )

    # Validate inputs.
    if current_rate <= 0 or baseline_rate < 0:
        return None
    if not (0.0 <= current_rate <= 1.0):
        return None
    if not (0.0 <= baseline_rate <= 1.0):
        return None

    # Warmup + statistical-significance gates.
    if history_days < _WARMUP_DAYS or history_calls < _WARMUP_CALLS:
        return None
    if window_calls > 0 and window_calls < _MIN_WINDOW_CALLS:
        return None

    # Absolute floor — ignore tiny absolute rates.
    if current_rate < _ABSOLUTE_FLOOR_RATE:
        return None

    multiplicative_threshold = _DRIFT_MULTIPLIER * baseline_rate
    additive_threshold = baseline_rate + _ABSOLUTE_DRIFT_DELTA
    drift_threshold = max(multiplicative_threshold, additive_threshold)

    if current_rate <= drift_threshold:
        return None

    delta = round(current_rate - baseline_rate, 4)
    multiplier = (
        round(current_rate / baseline_rate, 2) if baseline_rate > 0 else None
    )
    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")

    return {
        "category": "ERROR_RATE_DRIFT",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_ERROR_RATE_DRIFT,
        "root_cause": (
            f"Agent {agent_name} 15-minute error rate is "
            f"{current_rate * 100:.2f}% — "
            f"{(multiplier or 'inf')}× the baseline of "
            f"{baseline_rate * 100:.2f}% (delta +{delta * 100:.2f}pp)."
        ),
        "fix": {
            "primary": (
                "Cross-reference the spike with recent deploys, prompt "
                "edits, or provider status pages. The most common driver "
                "is a tool-schema change that breaks downstream parsers."
            ),
            "code": (
                "if recent_deploy_minutes_ago < 60:\n"
                "    rollback_last_deploy()\n"
                "    open_incident(severity='P2')"
            ),
            "alternative": (
                "Increase per-call timeout / retry budgets temporarily and "
                "page on-call for manual triage."
            ),
        },
        "evidence": {
            "agent_name": agent_name,
            "provider": provider,
            "current_15m_error_rate": current_rate,
            "baseline_15m_error_rate": baseline_rate,
            "delta": delta,
            "multiplier_vs_baseline": multiplier,
            "drift_threshold": round(drift_threshold, 4),
            "drift_multiplier": _DRIFT_MULTIPLIER,
            "absolute_drift_delta": _ABSOLUTE_DRIFT_DELTA,
            "absolute_floor_rate": _ABSOLUTE_FLOOR_RATE,
            "history_calls": history_calls,
            "history_days": history_days,
            "window_calls": window_calls or None,
            "min_window_calls": _MIN_WINDOW_CALLS,
            "warmup_required_days": _WARMUP_DAYS,
            "warmup_required_calls": _WARMUP_CALLS,
            "trigger_rule": "current >= max(3*baseline, baseline+0.05) AND current >= 0.02",
        },
    }
