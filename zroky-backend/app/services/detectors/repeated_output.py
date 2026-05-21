"""REPEATED_OUTPUT pattern-rule detector.

Fires when the *same* response text was delivered to the user 3 or more
times within a single session.

This complements LOOP_DETECTED (loop.py) which focuses on agent reasoning
loops with `no_progress` semantics. This detector targets a different
failure mode: the agent emitted distinct turns, but the *user-visible
output* was identical — typically a sign of:

  - A degenerate fallback path always returning the same canned answer.
  - A cached / memoized response served stale across distinct queries.
  - A system prompt that coerces the model into the same opening.

To avoid double-firing, this detector is *only* invoked when LOOP_DETECTED
did NOT fire (orchestrated by diagnosis_engine.evaluate_pattern_rules).

Activation requires the SDK to ship a `session_outputs` (or
`recent_outputs`) array — a list of recent agent text outputs in the
current session/conversation. Each entry may be a string or an object
with `text`/`content` field.
"""
from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_REPEATED_OUTPUT = 0.92
_MIN_REPEAT_COUNT = 3
_MIN_TEXT_LENGTH = 8  # Ignore trivially short outputs ("ok", "yes", etc.)


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    """Plugin-protocol entry point."""
    return _detect_repeated_output(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_repeated_output(payload)


def _normalize_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    if isinstance(value, MappingABC):
        for key in ("text", "content", "output_text", "response"):
            inner = value.get(key)
            if isinstance(inner, str):
                return " ".join(inner.strip().lower().split())
    return ""


def _extract_session_outputs(payload: Mapping[str, Any]) -> list[str]:
    raw = _pick(
        payload,
        ("session_outputs",),
        ("recent_outputs",),
        ("trace", "session_outputs"),
        ("trace", "recent_outputs"),
    )
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = _normalize_text(item)
        if len(text) >= _MIN_TEXT_LENGTH:
            out.append(text)
    return out


def _detect_repeated_output(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    outputs = _extract_session_outputs(payload)
    if len(outputs) < _MIN_REPEAT_COUNT:
        return None

    # Count occurrences; the most-common entry must repeat >= threshold
    # AND there must be at least 2 distinct queries (otherwise this is
    # just one query repeated by the caller, not a degenerate response).
    counts: dict[str, int] = {}
    for text in outputs:
        counts[text] = counts.get(text, 0) + 1

    top_text, top_count = max(counts.items(), key=lambda kv: kv[1])
    if top_count < _MIN_REPEAT_COUNT:
        return None

    # Distinct-query gate: customer must opt in by shipping `session_inputs`
    # to confirm the inputs were *different*. If absent, assume distinct
    # (we err toward firing — false-positive cost is low because LOOP
    # already filtered the obvious agent-loop cases).
    session_inputs = _pick(payload, ("session_inputs",), ("recent_inputs",))
    distinct_inputs = None
    if isinstance(session_inputs, list):
        normalized = {
            _normalize_text(i)
            for i in session_inputs
            if _normalize_text(i)
        }
        distinct_inputs = len(normalized)
        if distinct_inputs < 2:
            return None  # Same input repeated — not a degenerate-output signal

    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")
    repeat_window_size = _as_int(
        _pick(payload, ("session_window_size",), ("session_outputs_window_size",))
    )

    snippet = top_text[:160]

    return {
        "category": "REPEATED_OUTPUT",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_REPEATED_OUTPUT,
        "root_cause": (
            f"Agent {agent_name} returned the same response {top_count} times "
            f"across at least {distinct_inputs or 'multiple'} distinct user "
            f"inputs in the current session — likely a degenerate fallback "
            f"or stale cache."
        ),
        "fix": {
            "primary": (
                "Add a uniqueness guardrail: hash recent outputs and force "
                "a regeneration with raised temperature when the new output "
                "matches the previous one for a different input."
            ),
            "code": (
                "if hash(new_output) in recent_output_hashes:\n"
                "    new_output = regenerate(temperature=0.7, seed=None)"
            ),
            "alternative": (
                "Audit fallback / cache code paths — confirm the cache key "
                "incorporates the user query and that fallback responses "
                "are clearly labeled as such."
            ),
        },
        "evidence": {
            "agent_name": agent_name,
            "repeat_count": top_count,
            "session_outputs_observed": len(outputs),
            "distinct_outputs": len(counts),
            "distinct_inputs_observed": distinct_inputs,
            "repeat_window_size": repeat_window_size or None,
            "repeated_output_snippet": snippet,
            "trigger_rule": "same_normalized_output_count_ge_3_with_distinct_inputs",
        },
    }
