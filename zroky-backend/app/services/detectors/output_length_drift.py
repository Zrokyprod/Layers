"""OUTPUT_LENGTH_DRIFT pattern-rule detector.

Fires when the *completion length* of an agent's response deviates
significantly from its rolling baseline. The classic failure mode it
catches:

  - Agent suddenly verbose: a prompt change made the model repeat itself
    or dump a long chain-of-thought. Output that should be ~240 tokens
    is now 1500 tokens. Cost goes up, response quality often goes down.
  - Cache / fallback regression: a code path that should emit short
    structured output is emitting raw text or boilerplate.

This detector is the *behavioural* counterpart to OUTPUT_TRUNCATED
(Layer 1), which fires only when the model hit `finish_reason=length`.
OUTPUT_LENGTH_DRIFT detects suspicious lengths *under* the cap.

Inputs (payload-injected upstream by analytics service):
  - completion_tokens                        — current call
  - length.baseline_completion_tokens_p50    — rolling baseline
  - length.baseline_completion_tokens_p95
  - length.history_calls / history_days      — warmup gate

Skip rules:
  - history_days < 3 OR history_calls < 200  (warmup unmet)
  - completion_tokens < _ABSOLUTE_FLOOR_TOKENS (200)
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_OUTPUT_LENGTH_DRIFT = 0.88
_DRIFT_MULTIPLIER = 2.5
_ABSOLUTE_FLOOR_TOKENS = 200
_WARMUP_DAYS = 3
_WARMUP_CALLS = 200


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    return _detect(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect(payload)


def _detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    completion_tokens = _as_int(
        _pick(
            payload,
            ("completion_tokens",),
            ("usage", "completion_tokens"),
            ("output_tokens",),
            ("usage", "output_tokens"),
        ),
    )
    if completion_tokens < _ABSOLUTE_FLOOR_TOKENS:
        return None

    baseline_p50 = _as_float(
        _pick(
            payload,
            ("length", "baseline_completion_tokens_p50"),
            ("baseline_completion_tokens_p50",),
        ),
    )
    baseline_p95 = _as_float(
        _pick(
            payload,
            ("length", "baseline_completion_tokens_p95"),
            ("baseline_completion_tokens_p95",),
        ),
    )
    history_calls = _as_int(
        _pick(payload, ("length", "history_calls"), ("history_calls",))
    )
    history_days = _as_float(
        _pick(payload, ("length", "history_days"), ("history_days",))
    )

    if baseline_p95 <= 0:
        return None  # No baseline to compare against
    if history_days < _WARMUP_DAYS or history_calls < _WARMUP_CALLS:
        return None  # Warmup gate not met

    threshold = baseline_p95 * _DRIFT_MULTIPLIER
    if completion_tokens <= threshold:
        return None

    overshoot_ratio = round(completion_tokens / max(baseline_p95, 1.0), 2)
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")
    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")

    return {
        "category": "OUTPUT_LENGTH_DRIFT",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_OUTPUT_LENGTH_DRIFT,
        "root_cause": (
            f"Agent {agent_name} on {provider}/{model} emitted "
            f"{completion_tokens} completion tokens — {overshoot_ratio}× the "
            f"P95 baseline of {baseline_p95:.0f}. This is the classic "
            "signature of a prompt change causing verbose drift or a "
            "fallback path returning unbounded text."
        ),
        "fix": {
            "primary": (
                "Diff the recent prompt versions and revert any change that "
                "removed length-bounding instructions ('respond in <= N "
                "sentences', 'be concise', etc.). Add a max_tokens cap as a "
                "safety floor."
            ),
            "code": (
                "system_prompt += "
                "'\\nLimit responses to 3 short paragraphs unless asked.'\n"
                "request.max_tokens = min(request.max_tokens or 4096, 800)"
            ),
            "alternative": (
                "Add a length-budget guardrail in the SDK that re-prompts "
                "with 'be more concise' when output exceeds 2x P95."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "completion_tokens": completion_tokens,
            "baseline_completion_tokens_p50": baseline_p50 or None,
            "baseline_completion_tokens_p95": baseline_p95,
            "drift_threshold_tokens": int(threshold),
            "drift_multiplier": _DRIFT_MULTIPLIER,
            "overshoot_ratio": overshoot_ratio,
            "history_calls": history_calls,
            "history_days": history_days,
            "warmup_required_days": _WARMUP_DAYS,
            "warmup_required_calls": _WARMUP_CALLS,
            "absolute_floor_tokens": _ABSOLUTE_FLOOR_TOKENS,
            "trigger_rule": "completion_tokens > p95 * 2.5",
        },
    }
