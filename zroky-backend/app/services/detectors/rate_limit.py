"""RATE_LIMIT fast-rule detector."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.provider_status import resolve_provider_status_context
from app.services.detectors._payload import (
    _as_bool,
    _as_float,
    _as_int,
    _as_str,
    _error_message_from_payload,
    _pick,
)

_RULE_CONFIDENCE_RATE_LIMIT = 0.95


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_rate_limit(payload)


def _detect_rate_limit(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    status_code = _as_int(
        _pick(
            payload,
            ("status_code",),
            ("response", "status_code"),
            ("error", "status_code"),
            ("failure_reason", "http_status"),
        ),
    )
    error_code = _as_str(
        _pick(
            payload,
            ("error_code",),
            ("error", "code"),
            ("error", "type"),
            ("failure_reason", "classification"),
            ("failure_reason", "provider_error_code"),
            ("failure_reason", "provider_error_type"),
        ),
    ).lower()
    error_message = _error_message_from_payload(payload).lower()
    retry_after_seconds = _as_float(
        _pick(payload, ("failure_reason", "retry_after_seconds")), fallback=0.0,
    )
    provider_request_id = _as_str(_pick(payload, ("failure_reason", "provider_request_id"))) or None

    rate_limit_signals = (
        "rate_limit",
        "rate limit",
        "too_many_requests",
        "too many requests",
        "quota",
        "overload_error",
        "requests_per_minute",
        "tokens_per_minute",
        "concurrent_requests",
        "daily_limit",
    )
    is_rate_limit = status_code == 429 or retry_after_seconds > 0 or any(
        signal in error_code or signal in error_message
        for signal in rate_limit_signals
    )
    if not is_rate_limit:
        return None

    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    provider_status_context = resolve_provider_status_context(provider=provider, payload=payload)
    provider_status = _as_str(provider_status_context.get("provider_status"), fallback="unknown")
    p95_latency_ms = _as_int(provider_status_context.get("provider_latency_p95_ms"))
    p99_latency_ms = _as_int(provider_status_context.get("provider_latency_p99_ms"))
    status_fetch_timeout_ms = _as_int(provider_status_context.get("status_fetch_timeout_ms"))
    status_cache_ttl_seconds = _as_int(provider_status_context.get("status_cache_ttl_seconds"))
    status_fallback_used = _as_bool(
        provider_status_context.get("status_fallback_used"), fallback=True,
    )

    return {
        "category": "RATE_LIMIT",
        "speed_class": "fast",
        "confidence": _RULE_CONFIDENCE_RATE_LIMIT,
        "root_cause": (
            f"Provider {provider} returned rate limiting signals"
            f" (status {status_code or 'unknown'}, code {error_code or 'n/a'})."
        ),
        "fix": {
            "primary": "Use exponential backoff with bounded retries and respect Retry-After when present.",
            "code": "retry_delay = min(base_delay * (2 ** attempt), 60)",
            "alternative": "Shift overflow traffic to a fallback model/provider while preserving idempotency.",
        },
        "evidence": {
            "status_code": status_code,
            "error_code": error_code or None,
            "provider": provider,
            "provider_status": provider_status,
            "provider_latency_p95_ms": p95_latency_ms,
            "provider_latency_p99_ms": p99_latency_ms,
            "retry_window_recommendation": "retry in 30-60 seconds with exponential backoff",
            "retry_after_seconds": retry_after_seconds or None,
            "provider_request_id": provider_request_id,
            "status_fetch_timeout_ms": status_fetch_timeout_ms,
            "status_cache_ttl_seconds": status_cache_ttl_seconds,
            "status_fallback_used": status_fallback_used,
        },
    }
