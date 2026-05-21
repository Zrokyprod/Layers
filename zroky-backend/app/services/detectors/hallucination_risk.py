"""HALLUCINATION_RISK pattern-rule detector (Layer 3 wiring).

Bridges the LLM-as-judge engine output (specifically
``ReferenceFreeEvaluator``'s ``groundedness`` dimension) into the diagnosis
surface. When the judge has graded an agent response and the groundedness
score is below the hallucination-risk threshold, this detector emits a
``HALLUCINATION_RISK`` diagnosis that flows through the same orchestrator
output as deterministic detectors like ``TOKEN_OVERFLOW`` and ``COST_SPIKE``.

The `anomalies.py` module already reserves ``HALLUCINATION_RISK`` as a
valid anomaly detector (plan §6.1), but until this module nothing was
producing it — the slot was unwired. This closes that gap.

Expected payload shape (populated by judge_engine + replay_executor or
upstream judge runner):

  {
    "judge": {
      "model": "anthropic/claude-haiku-4",
      "verdict": "fail" | "pass" | "inconclusive",
      "confidence": 0.0..1.0,
      "dimensions": {
        "groundedness": {"score": 0.0..1.0, "reason": "..."},
        "relevance":    {"score": 0.0..1.0, "reason": "..."},
        ...
      },
      "overall_score": 0.0..1.0
    },
    "agent_name": "...",
    "trace_id": "..."
  }

Trigger:
  - judge.dimensions.groundedness.score is present AND < _GROUNDEDNESS_FLOOR (0.35)
  - mirrors the threshold documented in ``ReferenceFreeEvaluator``'s
    system prompt: "fail when groundedness < 0.35".

Skip rules:
  - Judge dimensions absent or no ``groundedness`` key → silent no-op.
    (Replay runs that used a single-verdict-only evaluator have no dims.)
  - Judge verdict was ``inconclusive`` AND confidence is below 0.5 →
    skip. The judge itself signalled low certainty; firing a hallucination
    diagnosis on top of low-confidence judge output would amplify noise.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_HALLUCINATION_RISK = 0.90
_GROUNDEDNESS_FLOOR = 0.35
_JUDGE_CONFIDENCE_MIN_WHEN_INCONCLUSIVE = 0.5


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    return _detect(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect(payload)


def _extract_dimension_score(
    payload: Mapping[str, Any], dim_name: str
) -> tuple[float | None, str]:
    """Pull `judge.dimensions.<dim_name>.score` + reason, or (None, "").

    Tolerant: the dimension entry may be a dict ``{"score": x, "reason": y}``
    or — when callers flattened the payload — a raw float. Both are accepted.
    """
    dim_obj = _pick(
        payload,
        ("judge", "dimensions", dim_name),
        ("dimensions", dim_name),
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
    groundedness_score, groundedness_reason = _extract_dimension_score(
        payload, "groundedness"
    )
    if groundedness_score is None:
        return None  # No judge dim data — silent no-op
    if groundedness_score >= _GROUNDEDNESS_FLOOR:
        return None  # Above the hallucination-risk floor

    # Respect judge self-uncertainty.
    judge_verdict = _as_str(_pick(payload, ("judge", "verdict"))).lower()
    judge_confidence = _as_float(_pick(payload, ("judge", "confidence")))
    if judge_verdict == "inconclusive" and judge_confidence < _JUDGE_CONFIDENCE_MIN_WHEN_INCONCLUSIVE:
        return None

    judge_model = _as_str(_pick(payload, ("judge", "model")), fallback="unknown")
    overall_score = _as_float(_pick(payload, ("judge", "overall_score")))
    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")

    # Best-effort context for the dashboard "why" panel.
    other_dims: dict[str, float] = {}
    for dim in ("relevance", "coherence", "completeness", "accuracy", "faithfulness"):
        score, _ = _extract_dimension_score(payload, dim)
        if score is not None:
            other_dims[dim] = round(score, 3)

    return {
        "category": "HALLUCINATION_RISK",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_HALLUCINATION_RISK,
        "root_cause": (
            f"Judge {judge_model} scored groundedness at "
            f"{groundedness_score:.2f} (below {_GROUNDEDNESS_FLOOR} floor) "
            f"for agent {agent_name} on {provider}/{model}. The response "
            "contains unverifiable confident claims — classic hallucination "
            "signature. "
            + (f"Judge said: {groundedness_reason}" if groundedness_reason else "")
        ),
        "fix": {
            "primary": (
                "Force the agent to cite its sources for every factual claim. "
                "Add a system-prompt instruction: 'If you don't have a source "
                "in the retrieved context, say so explicitly rather than guess.'"
            ),
            "code": (
                "system_prompt += (\n"
                "    '\\nFor every fact, cite the source chunk inline. '\n"
                "    'If you cannot ground a claim, write \"I do not have '\n"
                "    'enough information to answer that.\"'\n"
                ")"
            ),
            "alternative": (
                "Add a post-generation verification step: re-run with a "
                "second judge call asking 'is every factual claim above "
                "supported by the retrieved context?'. Block / regenerate "
                "if it returns no."
            ),
        },
        "evidence": {
            "judge_model": judge_model,
            "judge_verdict": judge_verdict or None,
            "judge_confidence": judge_confidence or None,
            "groundedness_score": round(groundedness_score, 4),
            "groundedness_floor": _GROUNDEDNESS_FLOOR,
            "groundedness_reason": groundedness_reason or None,
            "judge_overall_score": (
                round(overall_score, 4) if overall_score > 0 else None
            ),
            "other_dimensions": other_dims or None,
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "trigger_rule": "judge.dimensions.groundedness.score < 0.35",
        },
    }
