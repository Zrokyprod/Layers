"""OUTPUT_TRUNCATED fast-rule detector.

Fires when the provider terminated generation because the max-output-tokens
limit was reached (i.e. the response was cut off mid-stream).

Trigger signals (any one is sufficient):
  - OpenAI / OpenRouter:    finish_reason == "length"
  - Anthropic:              stop_reason   == "max_tokens"
  - Google Gemini:          finish_reason == "MAX_TOKENS"
  - Generic SDK normalized: finish_reason in {"length", "max_tokens", "truncated"}

Distinct from TOKEN_OVERFLOW which fires when the *prompt* is too large.
This detector fires when the *response* hit the configured cap.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_int,
    _as_str,
    _pick,
)

_RULE_CONFIDENCE_OUTPUT_TRUNCATED = 0.98
_TRUNCATION_FINISH_REASONS = frozenset(
    {
        "length",
        "max_tokens",
        "max_output_tokens",
        "max-tokens",
        "max_token",
        "truncated",
        "truncation",
    }
)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_output_truncated(payload)


def _normalize_finish_reason(value: Any) -> str:
    return _as_str(value).lower().replace(" ", "_")


def _detect_output_truncated(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    finish_reason = _normalize_finish_reason(
        _pick(
            payload,
            ("finish_reason",),
            ("response", "finish_reason"),
            ("stop_reason",),
            ("response", "stop_reason"),
        ),
    )
    if not finish_reason:
        return None
    if finish_reason not in _TRUNCATION_FINISH_REASONS:
        return None

    completion_tokens = _as_int(
        _pick(
            payload,
            ("completion_tokens",),
            ("usage", "completion_tokens"),
            ("output_tokens",),
            ("usage", "output_tokens"),
        ),
    )
    requested_max_tokens = _as_int(
        _pick(
            payload,
            ("max_tokens",),
            ("request", "max_tokens"),
            ("max_output_tokens",),
            ("request", "max_output_tokens"),
        ),
    )
    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")

    suggested_max_tokens: int | None = None
    if requested_max_tokens > 0:
        # Default suggestion: 2x current cap, rounded up to nearest 256.
        bumped = max(requested_max_tokens * 2, requested_max_tokens + 256)
        suggested_max_tokens = ((bumped + 255) // 256) * 256

    return {
        "category": "OUTPUT_TRUNCATED",
        "speed_class": "fast",
        "confidence": _RULE_CONFIDENCE_OUTPUT_TRUNCATED,
        "root_cause": (
            f"Provider {provider} truncated the response on model {model} "
            f"because the configured max-output-tokens cap was reached "
            f"(finish_reason={finish_reason})."
        ),
        "fix": {
            "primary": (
                "Increase the max_tokens / max_output_tokens parameter for "
                "this call type, or split the task into smaller stages."
            ),
            "code": (
                "request.max_tokens = "
                f"{suggested_max_tokens if suggested_max_tokens else 'max(current * 2, 1024)'}"
            ),
            "alternative": (
                "Stream the response with a continuation strategy: detect "
                "finish_reason=length and re-invoke with the partial output "
                "as a prefix until the model emits a natural stop."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "finish_reason": finish_reason,
            "completion_tokens": completion_tokens or None,
            "requested_max_tokens": requested_max_tokens or None,
            "suggested_max_tokens": suggested_max_tokens,
            "trigger_rule": "finish_reason in {length, max_tokens, truncated}",
        },
    }
