"""TOKEN_OVERFLOW fast-rule detector."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.token_overflow_rules import (
    match_token_overflow_error_pattern,
    token_rules_version,
)
from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _error_message_from_payload,
    _error_snippet,
    _estimate_detection_allowed,
    _normalize_error_code,
    _pick,
    _resolve_model_context_limit_details,
)

TOKEN_OVERFLOW_ESTIMATE_THRESHOLD_RATIO = 0.90
_RULE_CONFIDENCE_TOKEN_OVERFLOW = 0.98


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_token_overflow(payload)


def _detect_token_overflow(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    prompt_tokens = _as_int(
        _pick(
            payload,
            ("prompt_tokens",),
            ("usage", "prompt_tokens"),
            ("token_usage", "prompt_tokens"),
        ),
    )
    estimated_prompt_tokens = _as_int(
        _pick(
            payload,
            ("estimated_prompt_tokens",),
            ("usage", "estimated_prompt_tokens"),
            ("token_usage", "estimated_prompt_tokens"),
        ),
    )
    system_prompt_tokens = _as_int(
        _pick(payload, ("system_prompt_tokens",), ("usage", "system_prompt_tokens")),
    )
    user_message_tokens = _as_int(
        _pick(payload, ("user_message_tokens",), ("usage", "user_message_tokens")),
    )
    model_limit_details = _resolve_model_context_limit_details(payload)
    model_limit = _as_int(model_limit_details.get("limit"))
    error_code = _normalize_error_code(
        _as_str(
            _pick(
                payload,
                ("error_code",),
                ("error", "code"),
                ("error", "type"),
                ("failure_reason", "classification"),
                ("failure_reason", "provider_error_code"),
                ("failure_reason", "provider_error_type"),
            )
        ),
    )
    error_message = _error_message_from_payload(payload)
    matched_error_pattern = match_token_overflow_error_pattern(error_message)

    if prompt_tokens <= 0 and (system_prompt_tokens > 0 or user_message_tokens > 0):
        prompt_tokens = system_prompt_tokens + user_message_tokens

    signal_tokens = estimated_prompt_tokens or prompt_tokens
    usage_over_limit = model_limit > 0 and prompt_tokens > model_limit
    estimate_near_limit = (
        model_limit > 0
        and estimated_prompt_tokens > 0
        and estimated_prompt_tokens / max(model_limit, 1) > TOKEN_OVERFLOW_ESTIMATE_THRESHOLD_RATIO
        and _estimate_detection_allowed(payload)
    )
    detection_signals = _token_overflow_detection_signals(
        error_code=error_code,
        matched_error_pattern=matched_error_pattern,
        usage_over_limit=usage_over_limit,
        estimate_near_limit=estimate_near_limit,
    )

    if "error_code" in detection_signals:
        detected_by = "error_code"
        confidence = 0.97
    elif "error_message_pattern" in detection_signals:
        detected_by = "error_message_pattern"
        confidence = 0.80
    elif "usage_over_limit" in detection_signals:
        detected_by = "token_estimate"
        signal_tokens = prompt_tokens
        confidence = _RULE_CONFIDENCE_TOKEN_OVERFLOW
    elif "token_estimate" in detection_signals:
        detected_by = "token_estimate"
        signal_tokens = estimated_prompt_tokens
        confidence = _token_estimate_confidence(
            estimated_tokens=estimated_prompt_tokens, model_limit=model_limit,
        )
    else:
        return None

    overflow_by = (
        signal_tokens - model_limit if model_limit > 0 and signal_tokens > 0 else 0
    )

    conversation_turns = _as_int(
        _pick(payload, ("conversation_turns",), ("conversation", "turns")), fallback=1,
    )
    history_tokens = _as_int(
        _pick(payload, ("history_tokens",), ("conversation", "history_tokens")),
    )
    subtype = (
        "conversation_accumulation"
        if conversation_turns > 1 or history_tokens > 0
        else "single_call_overflow"
    )

    if subtype == "single_call_overflow":
        fix_primary = "Validate and truncate the current request payload before provider call."
        fix_code = (
            "if count_tokens(user_message) > 2000:\n"
            "    user_message = truncate(user_message, 2000)"
        )
        fix_alternative = (
            "Route this path to a larger context model when strict truncation is not acceptable."
        )
    else:
        fix_primary = "Summarize or trim rolling conversation history before appending new turns."
        fix_code = (
            "if conversation_tokens(history) > 2500:\n"
            "    history = summarize_history(history, max_tokens=1200)"
        )
        fix_alternative = (
            "Introduce a turn cap with semantic memory extraction for long-running sessions."
        )

    return {
        "category": "TOKEN_OVERFLOW",
        "subtype": subtype,
        "speed_class": "fast",
        "confidence": confidence,
        "detected_by": detected_by,
        "root_cause": _token_overflow_root_cause(
            detected_by=detected_by,
            signal_tokens=signal_tokens,
            model_limit=model_limit,
            overflow_by=overflow_by,
        ),
        "fix": {
            "primary": fix_primary,
            "code": fix_code,
            "alternative": fix_alternative,
        },
        "evidence": {
            "detected_by": detected_by,
            "detection_signals": detection_signals,
            "estimated_tokens": signal_tokens or None,
            "model_limit": model_limit or None,
            "model_context_limit_source": model_limit_details.get("source"),
            "model_context_limit_source_detail": model_limit_details.get("source_detail"),
            "model_context_limit_confidence": model_limit_details.get("confidence"),
            "model_context_limit_catalog_version": model_limit_details.get("catalog_version"),
            "model_context_limit_catalog_updated_at": model_limit_details.get("catalog_updated_at"),
            "model_context_limit_catalog_stale": model_limit_details.get("catalog_stale"),
            "model_context_limit_catalog_stale_after_days": model_limit_details.get("catalog_stale_after_days"),
            "token_estimator_version": _as_str(_pick(payload, ("token_estimator_version",))) or None,
            "token_rules_version": _as_str(_pick(payload, ("token_rules_version",))) or token_rules_version(),
            "error_snippet": _error_snippet(error_message),
            "matched_error_pattern": matched_error_pattern,
            "error_code": error_code or None,
            "prompt_tokens": prompt_tokens,
            "estimated_prompt_tokens": estimated_prompt_tokens or None,
            "overflow_by": overflow_by,
            "system_prompt_tokens": system_prompt_tokens,
            "user_message_tokens": user_message_tokens,
            "conversation_turns": conversation_turns,
            "history_tokens": history_tokens,
            "threshold_prompt_tokens_gt_model_limit": usage_over_limit,
            "threshold_estimated_prompt_tokens_gt_90pct_model_limit": estimate_near_limit,
        },
    }


def _token_overflow_detection_signals(
    *,
    error_code: str,
    matched_error_pattern: str | None,
    usage_over_limit: bool,
    estimate_near_limit: bool,
) -> list[str]:
    signals: list[str] = []
    if error_code == "TOKEN_OVERFLOW":
        signals.append("error_code")
    if matched_error_pattern is not None:
        signals.append("error_message_pattern")
    if usage_over_limit:
        signals.append("usage_over_limit")
    if estimate_near_limit:
        signals.append("token_estimate")
    return signals


def _token_estimate_confidence(*, estimated_tokens: int, model_limit: int) -> float:
    ratio = estimated_tokens / max(model_limit, 1)
    if ratio >= 1.0:
        return 0.85
    if ratio >= 0.98:
        return 0.82
    if ratio >= 0.95:
        return 0.78
    return 0.72


def _token_overflow_root_cause(
    *,
    detected_by: str,
    signal_tokens: int,
    model_limit: int,
    overflow_by: int,
) -> str:
    if detected_by == "error_code":
        return "Provider or SDK classified this failed call as TOKEN_OVERFLOW."
    if detected_by == "error_message_pattern":
        return "Provider error message contains a context/token limit overflow signal."
    if model_limit > 0 and signal_tokens > 0:
        if overflow_by > 0:
            return (
                "Prompt token usage exceeded model context limit: "
                f"{signal_tokens} vs {model_limit} (overflow {overflow_by})."
            )
        return (
            "Estimated prompt size is above 90% of the model context limit: "
            f"{signal_tokens} vs {model_limit}."
        )
    return "Token overflow detected from available telemetry signals."
