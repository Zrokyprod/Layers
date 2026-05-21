# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Provider failure normalization for telemetry payloads."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from zroky._internal.pii import mask_error_message, mask_value

FAILURE_REASON_SCHEMA_VERSION = "zroky.failure_reason.v1"

_MAX_MESSAGE_LENGTH = 1200
_MAX_BODY_TEXT_LENGTH = 2000
_MAX_FIELD_LENGTH = 256
_SAFE_HEADER_KEYS = {
    "request-id",
    "x-request-id",
    "x-amzn-requestid",
    "x-amzn-trace-id",
    "cf-ray",
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "anthropic-ratelimit-requests-limit",
    "anthropic-ratelimit-requests-remaining",
    "anthropic-ratelimit-requests-reset",
    "anthropic-ratelimit-tokens-limit",
    "anthropic-ratelimit-tokens-remaining",
    "anthropic-ratelimit-tokens-reset",
}


def extract_status_code(exc: Exception) -> int | None:
    """Best-effort HTTP status extraction across provider SDK exception shapes."""
    for value in (
        _read_attr_or_key(exc, "status_code"),
        _read_attr_or_key(exc, "status"),
        _read_attr_or_key(_read_attr_or_key(exc, "response"), "status_code"),
        _read_attr_or_key(_read_attr_or_key(exc, "response"), "status"),
    ):
        parsed = _as_int(value)
        if parsed is not None:
            return parsed
    return None


def build_failure_reason(
    exc: Exception,
    *,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Return a bounded, PII-masked explanation payload for a provider failure."""
    response = _read_attr_or_key(exc, "response")
    body = _extract_provider_body(exc, response)
    headers = _extract_safe_headers(response)

    provider_error = _provider_error_mapping(body)
    provider_code = _first_text(
        _read_attr_or_key(exc, "code"),
        _pick(provider_error, ("code",)),
        _pick(provider_error, ("error", "code")),
    )
    provider_type = _first_text(
        _read_attr_or_key(exc, "type"),
        _pick(provider_error, ("type",)),
        _pick(provider_error, ("error", "type")),
    )
    provider_param = _first_text(
        _read_attr_or_key(exc, "param"),
        _pick(provider_error, ("param",)),
        _pick(provider_error, ("error", "param")),
    )
    provider_request_id = _first_text(
        _read_attr_or_key(exc, "request_id"),
        _read_attr_or_key(exc, "x_request_id"),
        _read_header(headers, "x-request-id"),
        _read_header(headers, "request-id"),
    )
    http_status = extract_status_code(exc) or _as_int(
        _pick(
            provider_error,
            ("status_code",),
            ("status",),
            ("error", "status_code"),
            ("error", "status"),
        )
    )

    message = _first_text(
        _pick(provider_error, ("message",)),
        _pick(provider_error, ("error", "message")),
        mask_error_message(exc, max_length=_MAX_MESSAGE_LENGTH),
    )

    reason: dict[str, Any] = {
        "schema_version": FAILURE_REASON_SCHEMA_VERSION,
        "classification": error_code,
        "error_class": type(exc).__name__,
        "error_module": type(exc).__module__,
        "message": message,
        "http_status": http_status,
        "provider_error_code": provider_code,
        "provider_error_type": provider_type,
        "provider_error_param": provider_param,
        "provider_request_id": provider_request_id,
        "retry_after_seconds": _retry_after_seconds(headers),
    }

    if headers:
        reason["response_headers"] = headers
    if provider_error:
        reason["provider_error"] = provider_error
    elif body is not None:
        reason["provider_error_body"] = body

    return {
        key: value
        for key, value in mask_value(reason).items()
        if value not in (None, "", {}, [])
    }


def _read_attr_or_key(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _extract_provider_body(exc: Exception, response: Any) -> Any:
    for attr in ("body", "error", "response_body", "json_body"):
        value = _read_attr_or_key(exc, attr)
        if value not in (None, ""):
            return _json_safe(value)

    if response is None:
        return None

    json_fn = getattr(response, "json", None)
    if callable(json_fn):
        try:
            parsed = json_fn()
            if parsed not in (None, ""):
                return _json_safe(parsed)
        except Exception:
            pass

    text = _read_attr_or_key(response, "text")
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if isinstance(text, str) and text.strip():
        stripped = " ".join(text.split())
        try:
            return _json_safe(json.loads(stripped))
        except (TypeError, ValueError, json.JSONDecodeError):
            return stripped[:_MAX_BODY_TEXT_LENGTH]
    return None


def _extract_safe_headers(response: Any) -> dict[str, str]:
    headers = _read_attr_or_key(response, "headers")
    if not headers:
        return {}

    safe: dict[str, str] = {}
    for key in _SAFE_HEADER_KEYS:
        value = _read_header(headers, key)
        if value not in (None, ""):
            safe[key] = _truncate(str(value))
    return safe


def _read_header(headers: Any, key: str) -> str | None:
    if headers is None:
        return None
    try:
        value = headers.get(key)
    except Exception:
        value = None
    if value is None and isinstance(headers, Mapping):
        lower_key = key.lower()
        for candidate, candidate_value in headers.items():
            if str(candidate).lower() == lower_key:
                value = candidate_value
                break
    return _truncate(str(value)) if value not in (None, "") else None


def _provider_error_mapping(body: Any) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        return {}
    error = body.get("error")
    if isinstance(error, Mapping):
        return _json_safe(error)
    return _json_safe(body)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
            if item not in (None, "")
        }
    if isinstance(value, list):
        return [_json_safe(item) for item in value[:20]]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value[:20]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            return value[:_MAX_BODY_TEXT_LENGTH]
        return value
    return repr(value)[:_MAX_FIELD_LENGTH]


def _pick(payload: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = payload
        for segment in path:
            if not isinstance(current, Mapping) or segment not in current:
                current = None
                break
            current = current[segment]
        if current is not None:
            return current
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return _truncate(text)
    return None


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    retry_after = _read_header(headers, "retry-after")
    if retry_after is None:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _truncate(value: str) -> str:
    return " ".join(value.split())[:_MAX_FIELD_LENGTH]
