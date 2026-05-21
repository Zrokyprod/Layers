"""ACCURACY_REGRESSION pattern-rule detector (Layer 3 wiring).

Bridges the multi-dimensional judge engine (``MultiDimEvaluator``'s
``accuracy`` dimension) into the diagnosis surface. Fires when the judge's
accuracy score for the current call deviates below a rolling baseline OR
falls under an absolute hard floor — whichever is more conservative.

Distinct from ``HALLUCINATION_RISK`` (groundedness-based, single-call) and
from ``SCHEMA_VIOLATION`` (structural mismatch). Accuracy is the
*semantic* match against the golden expected output. A regression here
indicates that the agent answers in a fluent, grounded, schema-valid way
but the answers are *wrong* — typically caused by a model swap, a prompt
edit, or RAG-index corruption.

Two trigger modes (both must pass the accuracy floor first to fire):

  1. Hard floor:    accuracy.score < _ABSOLUTE_FLOOR (0.40)
  2. Baseline drift: accuracy.score < (baseline_accuracy * (1 - _DRIFT_DELTA))
     where baseline_accuracy is the rolling mean over the calibration
     window and _DRIFT_DELTA = 0.15 (a 15% relative drop).

The baseline-drift path requires warmup gating (history_calls / history_days)
matching the Layer 2 cost/latency/error-rate drift detectors.

Expected payload shape:

  {
    "judge": {
      "dimensions": {
        "accuracy": {"score": 0.0..1.0, "reason": "..."},
        ...
      },
      "overall_score": 0.0..1.0
    },
    "accuracy": {
      "baseline_mean": 0.85,   # rolling mean over history window
      "history_days": 7,
      "history_calls": 800
    }
  }
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_ACCURACY_REGRESSION = 0.90
_ABSOLUTE_FLOOR = 0.40
_DRIFT_DELTA = 0.15  # 15% relative drop below baseline triggers
_WARMUP_DAYS = 3
_WARMUP_CALLS = 200


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    return _detect(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect(payload)


def _extract_accuracy_score(
    payload: Mapping[str, Any],
) -> tuple[float | None, str]:
    """Pull `judge.dimensions.accuracy.{score,reason}` defensively."""
    dim_obj = _pick(
        payload,
        ("judge", "dimensions", "accuracy"),
        ("dimensions", "accuracy"),
    )
    if dim_obj is None:
        return None, ""
    if isinstance(dim_obj, Mapping):
        try:
            score = float(dim_obj.get("score"))
        except (TypeError, ValueError):
            return None, ""
        reason = str(dim_obj.get("reason") or "").strip()
        return score, reason
    try:
        return float(dim_obj), ""
    except (TypeError, ValueError):
        return None, ""


def _detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    accuracy_score, accuracy_reason = _extract_accuracy_score(payload)
    if accuracy_score is None:
        return None  # No judge dim data — silent no-op

    # Pull baseline + warmup stats.
    baseline_mean = _as_float(
        _pick(
            payload,
            ("accuracy", "baseline_mean"),
            ("accuracy", "baseline_accuracy"),
            ("baseline_accuracy_mean",),
        ),
    )
    history_days = _as_float(
        _pick(payload, ("accuracy", "history_days"), ("history_days",))
    )
    history_calls = _as_int(
        _pick(payload, ("accuracy", "history_calls"), ("history_calls",))
    )

    # Decide which path applies.
    hard_floor_breach = accuracy_score < _ABSOLUTE_FLOOR
    drift_breach = False
    drift_threshold: float | None = None
    if baseline_mean > 0 and history_days >= _WARMUP_DAYS and history_calls >= _WARMUP_CALLS:
        drift_threshold = baseline_mean * (1.0 - _DRIFT_DELTA)
        drift_breach = accuracy_score < drift_threshold

    if not (hard_floor_breach or drift_breach):
        return None

    trigger_basis = "hard_floor" if hard_floor_breach else "baseline_drift"

    judge_model = _as_str(_pick(payload, ("judge", "model")), fallback="unknown")
    overall_score = _as_float(_pick(payload, ("judge", "overall_score")))
    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")

    if trigger_basis == "hard_floor":
        root_cause = (
            f"Judge {judge_model} scored accuracy at {accuracy_score:.2f} "
            f"(below {_ABSOLUTE_FLOOR} hard floor) for agent {agent_name} "
            f"on {provider}/{model}. The response is semantically wrong vs "
            "the expected output."
        )
    else:
        delta_pct = (
            (baseline_mean - accuracy_score) / max(baseline_mean, 0.01) * 100
        )
        root_cause = (
            f"Judge {judge_model} scored accuracy at {accuracy_score:.2f} — "
            f"{delta_pct:.0f}% below rolling baseline of {baseline_mean:.2f}. "
            f"Agent {agent_name} on {provider}/{model} answered in a "
            "plausible-looking way but the content is wrong relative to "
            "what passed yesterday."
        )

    return {
        "category": "ACCURACY_REGRESSION",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_ACCURACY_REGRESSION,
        "root_cause": root_cause
        + (f" Judge said: {accuracy_reason}" if accuracy_reason else ""),
        "fix": {
            "primary": (
                "Diff the agent's prompt + model + retrieval config against "
                "the last known-good replay run. Accuracy regressions almost "
                "always trace to (a) model swap, (b) prompt edit, or "
                "(c) RAG index reindex with wrong embedding model."
            ),
            "code": (
                "# 1) Pin the model version explicitly\n"
                "request.model = 'anthropic/claude-sonnet-4-20260301'\n"
                "# 2) Replay the failing trace against the previous deploy\n"
                "zroky replay-run --trace-id {trace_id} --against=last_known_good"
            ),
            "alternative": (
                "Roll back the most recent deploy and re-run the affected "
                "golden set; promote the rollback only when accuracy returns "
                "to baseline."
            ),
        },
        "evidence": {
            "judge_model": judge_model,
            "accuracy_score": round(accuracy_score, 4),
            "absolute_floor": _ABSOLUTE_FLOOR,
            "baseline_mean": round(baseline_mean, 4) if baseline_mean > 0 else None,
            "drift_threshold": round(drift_threshold, 4) if drift_threshold is not None else None,
            "drift_delta": _DRIFT_DELTA,
            "trigger_basis": trigger_basis,
            "accuracy_reason": accuracy_reason or None,
            "judge_overall_score": (
                round(overall_score, 4) if overall_score > 0 else None
            ),
            "history_calls": history_calls or None,
            "history_days": history_days or None,
            "warmup_required_days": _WARMUP_DAYS,
            "warmup_required_calls": _WARMUP_CALLS,
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "trigger_rule": (
                "accuracy < 0.40 (hard floor) OR "
                "accuracy < baseline_mean * (1 - 0.15) with warmup met"
            ),
        },
    }
