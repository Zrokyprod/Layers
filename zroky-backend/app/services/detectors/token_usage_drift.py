"""TOKEN_USAGE_DRIFT pattern-rule detector.

Fires when the *prompt token count* deviates significantly from its
rolling baseline — i.e. prompts are getting bloated. Classic causes:

  - RAG retrieved-chunk top-k was bumped (e.g. 5 → 20) silently
  - System prompt grew with new instructions / examples
  - Conversation history being passed in full instead of summarized
  - A tool's response is being injected raw into the next prompt

This catches cost / latency regressions *before* they manifest as
COST_SPIKE or LATENCY_DRIFT downstream.

Distinct from TOKEN_OVERFLOW (Layer 1 fast rule), which fires only when
the prompt would exceed the model's context window. TOKEN_USAGE_DRIFT
fires *under* the window when prompts have grown but still fit.

Inputs:
  - prompt_tokens                              — current call
  - tokens.baseline_prompt_tokens_p50          — rolling baseline
  - tokens.baseline_prompt_tokens_p95
  - tokens.history_calls / history_days

Skip rules:
  - TOKEN_OVERFLOW already fires (model-context exceeded → harder signal)
  - prompt_tokens < _ABSOLUTE_FLOOR_TOKENS (1000)
  - history_days < 3 OR history_calls < 200  (warmup unmet)
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _pick,
    _resolve_model_context_limit,
)

_RULE_CONFIDENCE_TOKEN_USAGE_DRIFT = 0.88
_DRIFT_MULTIPLIER = 1.5
_ABSOLUTE_FLOOR_TOKENS = 1000
_WARMUP_DAYS = 3
_WARMUP_CALLS = 200


def detect_entry(payload: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
    return _detect(payload)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect(payload)


def _is_token_overflow_imminent(payload: Mapping[str, Any], prompt_tokens: int) -> bool:
    """Suppress drift when prompt is already crowding the model context limit.

    TOKEN_OVERFLOW will own that surface — drift would be redundant noise.
    """
    limit = _resolve_model_context_limit(payload)
    if limit <= 0:
        return False
    return prompt_tokens >= int(limit * 0.9)


def _detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    prompt_tokens = _as_int(
        _pick(
            payload,
            ("prompt_tokens",),
            ("usage", "prompt_tokens"),
            ("input_tokens",),
            ("usage", "input_tokens"),
        ),
    )
    if prompt_tokens < _ABSOLUTE_FLOOR_TOKENS:
        return None
    if _is_token_overflow_imminent(payload, prompt_tokens):
        return None  # TOKEN_OVERFLOW will fire instead

    baseline_p50 = _as_float(
        _pick(
            payload,
            ("tokens", "baseline_prompt_tokens_p50"),
            ("baseline_prompt_tokens_p50",),
        ),
    )
    baseline_p95 = _as_float(
        _pick(
            payload,
            ("tokens", "baseline_prompt_tokens_p95"),
            ("baseline_prompt_tokens_p95",),
        ),
    )
    history_calls = _as_int(
        _pick(payload, ("tokens", "history_calls"), ("history_calls",))
    )
    history_days = _as_float(
        _pick(payload, ("tokens", "history_days"), ("history_days",))
    )

    if baseline_p95 <= 0:
        return None
    if history_days < _WARMUP_DAYS or history_calls < _WARMUP_CALLS:
        return None

    threshold = baseline_p95 * _DRIFT_MULTIPLIER
    if prompt_tokens <= threshold:
        return None

    overshoot_ratio = round(prompt_tokens / max(baseline_p95, 1.0), 2)
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")
    agent_name = _as_str(_pick(payload, ("agent_name",)), fallback="unknown")

    return {
        "category": "TOKEN_USAGE_DRIFT",
        "speed_class": "pattern",
        "confidence": _RULE_CONFIDENCE_TOKEN_USAGE_DRIFT,
        "root_cause": (
            f"Agent {agent_name} on {provider}/{model} sent "
            f"{prompt_tokens} prompt tokens — {overshoot_ratio}× the rolling "
            f"P95 baseline of {baseline_p95:.0f}. Prompt bloat detected."
        ),
        "fix": {
            "primary": (
                "Audit the prompt-build pipeline: check RAG top-k, system "
                "prompt size, conversation-history truncation policy, and "
                "tool-result inlining. The biggest wins usually come from "
                "tightening retrieval to top-3 or top-5 chunks."
            ),
            "code": (
                "context_chunks = retrieve(query, top_k=5, max_chunk_tokens=300)\n"
                "history = summarize_if_over_tokens(history, budget=2000)"
            ),
            "alternative": (
                "Move static instructions / few-shot examples into the "
                "model's system-prompt cache (Anthropic prompt caching, "
                "OpenAI prefix-caching) to amortise token cost."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "prompt_tokens": prompt_tokens,
            "baseline_prompt_tokens_p50": (
                int(baseline_p50) if baseline_p50 > 0 else None
            ),
            "baseline_prompt_tokens_p95": int(baseline_p95),
            "drift_threshold_tokens": int(threshold),
            "drift_multiplier": _DRIFT_MULTIPLIER,
            "overshoot_ratio": overshoot_ratio,
            "history_calls": history_calls,
            "history_days": history_days,
            "warmup_required_days": _WARMUP_DAYS,
            "warmup_required_calls": _WARMUP_CALLS,
            "absolute_floor_tokens": _ABSOLUTE_FLOOR_TOKENS,
            "trigger_rule": "prompt_tokens > p95 * 1.5",
        },
    }
