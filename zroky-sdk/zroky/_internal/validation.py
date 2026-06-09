# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Pre-execution payload validation for upcoming LLM calls.

This module is advisory-only and never mutates input payloads.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Any

from zroky._internal import token_rules

MODEL_CONTEXT_LIMITS = token_rules.MODEL_CONTEXT_LIMITS
MODEL_CONTEXT_LIMIT_PREFIXES = token_rules.MODEL_CONTEXT_LIMIT_PREFIXES
TOKEN_ESTIMATOR_VERSION = token_rules.TOKEN_ESTIMATOR_VERSION
TOKEN_RULES_VERSION = token_rules.TOKEN_RULES_VERSION
TOKEN_OVERFLOW_ERROR_PATTERNS = token_rules.TOKEN_OVERFLOW_ERROR_PATTERNS
DEFAULT_MODEL_CONTEXT_LIMIT = 4096
TOKEN_OVERFLOW_THRESHOLD_RATIO = 0.90
RATE_LIMIT_LARGE_REQUEST_RATIO = 0.85
RATE_LIMIT_RECENT_CALLS_THRESHOLD = 20
PRINT_WARNING_SUPPRESSION_WINDOW_SECONDS = 30.0
PRINT_WARNING_MAX_EMISSIONS_PER_WINDOW = 2

_print_state_lock = threading.Lock()
_print_warning_state: dict[str, tuple[float, int]] = {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value

    try:
        return str(value)
    except Exception:
        return ""


def _as_payload(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    return {}


def _as_messages(payload: Mapping[str, Any]) -> list[Any]:
    messages = payload.get("messages")
    if isinstance(messages, list):
        return messages
    return []


def _model_limit_resolution(payload: Mapping[str, Any]) -> token_rules.ModelContextLimitResolution:
    model = _as_text(payload.get("model")).strip().lower()
    return token_rules.resolve_model_context_limit(model)


def _model_limit(payload: Mapping[str, Any]) -> int | None:
    return _model_limit_resolution(payload).limit


def known_model_context_limit(model: str | None) -> int | None:
    return token_rules.known_model_context_limit(model)


def resolve_model_context_limit(model: str | None) -> token_rules.ModelContextLimitResolution:
    return token_rules.resolve_model_context_limit(model)


def model_context_limit_resolution(model: str | None) -> dict[str, Any]:
    return token_rules.resolve_model_context_limit(model).to_dict()


def token_estimator_version() -> str:
    return token_rules.token_estimator_version()


def token_rules_version() -> str:
    return token_rules.token_rules_version()


def match_token_overflow_error_pattern(error_message: Any) -> str | None:
    return token_rules.match_token_overflow_error_pattern(error_message)


def is_token_overflow_error_message(error_message: Any) -> bool:
    return token_rules.is_token_overflow_error_message(error_message)


def estimate_tokens(payload: Mapping[str, Any]) -> int:
    """Estimate token count using a simple ~4 chars/token heuristic."""
    try:
        total_chars = 0
        for message in _as_messages(payload):
            if isinstance(message, Mapping):
                role_text = _as_text(message.get("role"))
                content_text = _as_text(message.get("content"))
            else:
                role_text = ""
                content_text = _as_text(message)

            total_chars += len(role_text)
            total_chars += len(content_text)

        # Round up so tiny payloads are not estimated as zero tokens.
        return max(0, (total_chars + 3) // 4)
    except Exception:
        return 0


def check_token_overflow(
    payload: Mapping[str, Any],
    *,
    estimated_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Return TOKEN_OVERFLOW warning when payload is near model context limit."""
    try:
        estimate = estimated_tokens if estimated_tokens is not None else estimate_tokens(payload)
        resolution = _model_limit_resolution(payload)
        limit = resolution.limit
        if limit is None:
            threshold = int(DEFAULT_MODEL_CONTEXT_LIMIT * TOKEN_OVERFLOW_THRESHOLD_RATIO)
            if estimate < threshold:
                return None
            return {
                "type": "TOKEN_CONTEXT_LIMIT_UNKNOWN",
                "confidence": 0.42,
                "message": (
                    f"Estimated prompt size is {estimate} tokens, but model context "
                    f"limit for '{_as_text(payload.get('model')) or 'unknown'}' is unknown."
                ),
                "suggested_fix": (
                    "Set ZROKY_MODEL_CONTEXT_LIMITS for this model or update the "
                    "built-in token rules catalog before relying on overflow diagnosis."
                ),
                "estimated_tokens": estimate,
                "model_context_limit": None,
                "model_context_limit_source": resolution.source,
                "model_context_limit_source_detail": resolution.source_detail,
                "model_context_limit_confidence": resolution.confidence,
                "model_context_limit_catalog_version": resolution.catalog_version,
                "model_context_limit_catalog_updated_at": resolution.catalog_updated_at,
                "model_context_limit_catalog_stale": resolution.catalog_stale,
                "model_context_limit_catalog_stale_after_days": (
                    resolution.catalog_stale_after_days
                ),
            }
        threshold = int(limit * TOKEN_OVERFLOW_THRESHOLD_RATIO)

        if estimate < threshold:
            return None

        ratio = estimate / max(limit, 1)
        confidence = 0.92 if ratio <= 1.0 else 0.97

        return {
            "type": "TOKEN_OVERFLOW",
            "confidence": round(confidence, 2),
            "message": (
                f"Estimated prompt size is {estimate} tokens, near/over model limit {limit}. "
                f"Alert threshold is {threshold} tokens (90%)."
            ),
            "suggested_fix": (
                "Truncate input, summarize conversation history, and switch to a larger "
                "context model when needed."
            ),
            "estimated_tokens": estimate,
            "model_context_limit": limit,
            "model_context_limit_source": resolution.source,
            "model_context_limit_source_detail": resolution.source_detail,
            "model_context_limit_confidence": resolution.confidence,
            "model_context_limit_catalog_version": resolution.catalog_version,
            "model_context_limit_catalog_updated_at": resolution.catalog_updated_at,
            "model_context_limit_catalog_stale": resolution.catalog_stale,
            "model_context_limit_catalog_stale_after_days": (
                resolution.catalog_stale_after_days
            ),
        }
    except Exception:
        return None


def _safe_recent_calls(payload: Mapping[str, Any]) -> int:
    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        return 0

    try:
        return max(0, int(meta.get("recent_calls", 0)))
    except (TypeError, ValueError):
        return 0


def check_rate_limit_risk(
    payload: Mapping[str, Any],
    *,
    estimated_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Return RATE_LIMIT_RISK warning for burst-like or heavy request patterns."""
    try:
        estimate = estimated_tokens if estimated_tokens is not None else estimate_tokens(payload)
        limit = _model_limit(payload)
        recent_calls = _safe_recent_calls(payload)

        burst_risk = recent_calls >= RATE_LIMIT_RECENT_CALLS_THRESHOLD
        large_request_risk = (
            limit is not None
            and estimate >= int(limit * RATE_LIMIT_LARGE_REQUEST_RATIO)
        )

        if not burst_risk and not large_request_risk:
            return None

        reasons: list[str] = []
        if burst_risk:
            reasons.append(f"recent_calls={recent_calls}")
        if large_request_risk:
            reasons.append(f"estimated_tokens={estimate}")

        confidence = 0.76 if burst_risk and large_request_risk else 0.68

        return {
            "type": "RATE_LIMIT_RISK",
            "confidence": round(confidence, 2),
            "message": (
                "Potential rate-limit risk due to burst/heavy request pattern "
                f"({', '.join(reasons)})."
            ),
            "suggested_fix": (
                "Add retry with exponential backoff, reduce request size, and queue requests."
            ),
        }
    except Exception:
        return None


def _is_valid_api_key_format(value: str) -> bool:
    candidate = value.strip()
    if len(candidate) < 12:
        return False
    if any(char.isspace() for char in candidate):
        return False
    return True


def _warning_signature(warning: Mapping[str, Any]) -> str:
    warning_type = _as_text(warning.get("type")).strip().upper()
    message = _as_text(warning.get("message")).strip()
    suggested_fix = _as_text(warning.get("suggested_fix")).strip()
    return f"{warning_type}|{message}|{suggested_fix}"


def _should_emit_warning(signature: str, now: float | None = None) -> bool:
    """Allow up to N emissions per warning signature within suppression window."""
    current_time = now if now is not None else time.monotonic()

    with _print_state_lock:
        existing = _print_warning_state.get(signature)
        if existing is None:
            _print_warning_state[signature] = (current_time, 1)
            return True

        window_start, count = existing
        if current_time - window_start > PRINT_WARNING_SUPPRESSION_WINDOW_SECONDS:
            _print_warning_state[signature] = (current_time, 1)
            return True

        if count >= PRINT_WARNING_MAX_EMISSIONS_PER_WINDOW:
            return False

        _print_warning_state[signature] = (window_start, count + 1)
        return True


def _check_auth_risk(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        raw_key = payload.get("api_key")
        if raw_key is None:
            return {
                "type": "AUTH_RISK",
                "confidence": 0.45,
                "message": "api_key is missing from payload; authentication may fail.",
                "suggested_fix": "Pass a valid API key string before executing the request.",
            }

        api_key = _as_text(raw_key)
        if not _is_valid_api_key_format(api_key):
            return {
                "type": "AUTH_RISK",
                "confidence": 0.4,
                "message": "api_key format looks invalid or incomplete.",
                "suggested_fix": (
                    "Verify API key format and ensure full key is loaded from secure config."
                ),
            }

        return None
    except Exception:
        return {
            "type": "AUTH_RISK",
            "confidence": 0.35,
            "message": "Unable to verify api_key format safely.",
            "suggested_fix": "Ensure api_key is present and loaded correctly.",
        }


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze payload before provider execution and return advisory warnings."""
    try:
        safe_payload = _as_payload(payload)
        estimate = estimate_tokens(safe_payload)

        warnings: list[dict[str, Any]] = []
        token_warning = check_token_overflow(safe_payload, estimated_tokens=estimate)
        if token_warning:
            warnings.append(token_warning)

        rate_warning = check_rate_limit_risk(safe_payload, estimated_tokens=estimate)
        if rate_warning:
            warnings.append(rate_warning)

        auth_warning = _check_auth_risk(safe_payload)
        if auth_warning:
            warnings.append(auth_warning)

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
        }
    except Exception:
        return {
            "valid": True,
            "warnings": [],
        }


def print_validation(result: dict[str, Any]) -> None:
    """Print validation summary in a developer-friendly format."""
    try:
        warnings = []
        if isinstance(result, Mapping):
            raw_warnings = result.get("warnings")
            if isinstance(raw_warnings, list):
                warnings = raw_warnings

        if not warnings:
            print("[ZROKY] ✅ Payload looks safe")
            return

        for warning in warnings:
            if not isinstance(warning, Mapping):
                continue

            signature = _warning_signature(warning)
            if not _should_emit_warning(signature):
                continue

            warning_type = _as_text(warning.get("type")) or "UNKNOWN"
            confidence_value = warning.get("confidence", 0.0)
            try:
                confidence = float(confidence_value)
            except (TypeError, ValueError):
                confidence = 0.0

            print(f"[ZROKY] ⚠️ {warning_type} risk detected (confidence: {confidence:.2f})")
            suggested_fix = _as_text(warning.get("suggested_fix")).strip()
            if suggested_fix:
                print(f"Suggested fix: {suggested_fix}")
    except Exception:
        print("[ZROKY] ⚠️ Validation output unavailable")


if __name__ == "__main__":
    # 1) Very long input -> TOKEN_OVERFLOW warning.
    long_payload = {
        "model": "gpt-3.5-turbo",
        "api_key": "__PROVIDER_API_KEY__",
        "messages": [{"role": "user", "content": "x" * 16000}],
    }
    print(validate(long_payload))

    # 2) Normal input -> no warnings.
    normal_payload = {
        "model": "gpt-4o",
        "api_key": "__PROVIDER_API_KEY__",
        "messages": [{"role": "user", "content": "Summarize this short note."}],
    }
    print(validate(normal_payload))

    # 3) Missing api_key -> AUTH_RISK warning.
    missing_auth_payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    print(validate(missing_auth_payload))
