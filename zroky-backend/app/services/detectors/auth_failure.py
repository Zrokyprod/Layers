"""AUTH_FAILURE fast-rule detector."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.detectors._payload import (
    _as_int,
    _as_str,
    _error_message_from_payload,
    _pick,
)

_RULE_CONFIDENCE_AUTH_FAILURE = 0.99


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_auth_failure(payload)


def _detect_auth_failure(payload: Mapping[str, Any]) -> dict[str, Any] | None:
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
    provider_request_id = _as_str(_pick(payload, ("failure_reason", "provider_request_id"))) or None

    auth_signals = (
        "invalid_api_key", "invalid_key", "invalid_token",
        "expired_key", "expired_token", "unauthorized", "forbidden", "auth",
    )
    is_auth_failure = status_code in {401, 403} or any(
        signal in error_code or signal in error_message for signal in auth_signals
    )
    if not is_auth_failure:
        return None

    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    return {
        "category": "AUTH_FAILURE",
        "speed_class": "fast",
        "confidence": _RULE_CONFIDENCE_AUTH_FAILURE,
        "root_cause": (
            f"Authentication failed for provider {provider}"
            f" (status {status_code or 'unknown'}, code {error_code or 'n/a'})."
        ),
        "fix": {
            "primary": "Rotate provider credentials and verify environment binding for the active project.",
            "code": "if not provider_key or provider_key.is_expired(): raise AuthConfigError()",
            "alternative": "Add startup credential verification and alerting before serving traffic.",
        },
        "evidence": {
            "status_code": status_code,
            "error_code": error_code or None,
            "provider": provider,
            "provider_request_id": provider_request_id,
            "threshold_auth_status_codes": [401, 403],
        },
    }
