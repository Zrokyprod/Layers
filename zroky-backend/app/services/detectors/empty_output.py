"""EMPTY_OUTPUT fast-rule detector.

Fires when the model returned a null / empty / whitespace-only response
on a call that did NOT otherwise fail at the transport layer.

This catches a common silent-failure mode where providers return HTTP 200
with no usable content — typically due to:

  - Content filter / safety system blocked the response.
  - Streaming connection dropped after headers.
  - Model hit `stop` immediately (bad system prompt).
  - Tool-only response with no text and caller expected text.

Skip rules — never fires when the call already failed for other reasons:
  - status in {failed, error, timeout, cancelled}
  - HTTP status code >= 400
  - Status is partial/streaming/incomplete (handled by other detectors)
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_int,
    _as_str,
    _estimate_detection_allowed,
    _pick,
)

_RULE_CONFIDENCE_EMPTY_OUTPUT = 0.99
_OUTPUT_PATHS: tuple[tuple[str, ...], ...] = (
    ("output_text",),
    ("response_text",),
    ("completion_text",),
    ("response", "content"),
    ("response", "text"),
    ("response", "output_text"),
    ("completion",),
    ("output",),
)


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_empty_output(payload)


def _extract_output_text(payload: Mapping[str, Any]) -> str | None:
    """Return the first present output-text field, or None if no field is set.

    Distinguishes "no output field present in payload" (return None — can't
    judge) from "field present but empty" (return "" — fire detector).
    """
    for path in _OUTPUT_PATHS:
        value = _pick(payload, path)
        if value is None:
            continue
        if isinstance(value, str):
            return value
        # Non-string truthy value (e.g. JSON object) means there IS output.
        return None
    return None


def _detect_empty_output(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    # Skip if the call was clearly a transport-layer failure — other
    # detectors (auth_failure, rate_limit, provider_error, token_overflow)
    # will own those signals.
    status = _as_str(_pick(payload, ("status",), ("call_status",))).lower()
    if status in {"failed", "error", "timeout", "cancelled", "canceled"}:
        return None

    status_code = _as_int(
        _pick(
            payload,
            ("status_code",),
            ("response", "status_code"),
        ),
    )
    if status_code and status_code >= 400:
        return None

    # If the call status is success/complete-ish but output is missing,
    # `_estimate_detection_allowed` returns False — flip the gate: we
    # SHOULD detect on success states. Skip non-terminal states.
    if status in {"partial", "partial_success", "incomplete", "streaming"}:
        return None

    output = _extract_output_text(payload)
    if output is None:
        return None  # No output field present — caller didn't ship one
    if output.strip():
        return None  # Has visible content

    completion_tokens = _as_int(
        _pick(
            payload,
            ("completion_tokens",),
            ("usage", "completion_tokens"),
            ("output_tokens",),
            ("usage", "output_tokens"),
        ),
    )
    finish_reason = _as_str(
        _pick(
            payload,
            ("finish_reason",),
            ("response", "finish_reason"),
            ("stop_reason",),
            ("response", "stop_reason"),
        ),
    ).lower() or None

    # Heuristic root-cause refinement.
    if finish_reason in {"content_filter", "safety", "blocked"}:
        root_cause = (
            "Provider returned an empty response because the safety / content "
            "filter blocked the completion."
        )
        primary_fix = (
            "Inspect and adjust the system prompt or input to avoid the "
            "safety trigger; consider switching to a less restrictive model "
            "or adding a fallback."
        )
    elif completion_tokens == 0 and finish_reason in {"stop", None}:
        root_cause = (
            "Model returned an empty completion (0 output tokens) despite a "
            "successful HTTP response — likely an over-restrictive stop "
            "sequence or bad system prompt."
        )
        primary_fix = (
            "Review stop sequences and system prompt; ensure the prompt does "
            "not coerce the model into immediate termination."
        )
    else:
        root_cause = (
            "Model call succeeded at the transport layer but returned a "
            f"blank response (finish_reason={finish_reason or 'unknown'})."
        )
        primary_fix = (
            "Add an output-length guardrail in the SDK to retry once on "
            "empty completions, and surface the retry attempt to the caller."
        )

    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")

    return {
        "category": "EMPTY_OUTPUT",
        "speed_class": "fast",
        "confidence": _RULE_CONFIDENCE_EMPTY_OUTPUT,
        "root_cause": root_cause,
        "fix": {
            "primary": primary_fix,
            "code": (
                "if not (response.output_text or '').strip():\n"
                "    metrics.increment('empty_output')\n"
                "    return retry_with_fallback_model()"
            ),
            "alternative": (
                "Cache last successful response and serve as fallback when "
                "downstream calls return empty content."
            ),
        },
        "evidence": {
            "provider": provider,
            "model": model,
            "completion_tokens": completion_tokens,
            "finish_reason": finish_reason,
            "status_code": status_code or None,
            "trigger_rule": "successful_call_with_blank_output_text",
        },
    }
