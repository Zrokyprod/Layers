"""PROVIDER_ERROR fast-rule detector."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.token_overflow_rules import match_token_overflow_error_pattern
from app.services.detectors._payload import (
    _as_float,
    _as_int,
    _as_str,
    _error_message_from_payload,
    _error_snippet,
    _failure_reason,
    _normalize_error_code,
    _pick,
)

_RULE_CONFIDENCE_PROVIDER_ERROR = 0.82


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return _detect_provider_error(payload)


def _detect_provider_error(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    status = _as_str(_pick(payload, ("status",), ("call_status",))).strip().lower()
    status_code = _as_int(
        _pick(
            payload,
            ("status_code",),
            ("response", "status_code"),
            ("error", "status_code"),
            ("failure_reason", "http_status"),
        ),
    )
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
        )
    )
    error_message = _error_message_from_payload(payload)
    failure_reason_data = _failure_reason(payload)

    has_failure_signal = (
        status in {"failed", "failure", "error", "errored", "timeout", "dead_lettered"}
        or status_code >= 400
        or bool(error_code)
        or bool(error_message)
        or bool(failure_reason_data)
    )
    if not has_failure_signal:
        return None

    if error_code in {"TOKEN_OVERFLOW", "RATE_LIMIT", "AUTH_FAILURE"}:
        return None
    if status_code in {401, 403, 429}:
        return None
    if 400 <= status_code < 500 and not failure_reason_data:
        return None
    if match_token_overflow_error_pattern(error_message) is not None:
        return None

    provider = _as_str(_pick(payload, ("provider",)), fallback="unknown")
    model = _as_str(_pick(payload, ("model",), ("request", "model")), fallback="unknown")
    provider_error_code = _as_str(_pick(payload, ("failure_reason", "provider_error_code"))) or None
    provider_error_type = _as_str(_pick(payload, ("failure_reason", "provider_error_type"))) or None
    provider_error_param = _as_str(_pick(payload, ("failure_reason", "provider_error_param"))) or None
    provider_request_id = _as_str(_pick(payload, ("failure_reason", "provider_request_id"))) or None
    error_class = _as_str(_pick(payload, ("failure_reason", "error_class"))) or None
    retry_after_seconds = _as_float(_pick(payload, ("failure_reason", "retry_after_seconds")), fallback=0.0)
    subtype = _provider_error_subtype(
        status_code=status_code,
        error_code=error_code,
        provider_error_code=provider_error_code,
        provider_error_type=provider_error_type,
        error_message=error_message,
    )

    return {
        "category": "PROVIDER_ERROR",
        "subtype": subtype,
        "speed_class": "fast",
        "confidence": _provider_error_confidence(
            status_code=status_code, has_failure_reason=bool(failure_reason_data),
        ),
        "detected_by": "structured_failure_reason" if failure_reason_data else "failed_call_metadata",
        "root_cause": _provider_error_root_cause(
            provider=provider, model=model, status_code=status_code,
            error_class=error_class, provider_error_code=provider_error_code,
            provider_error_type=provider_error_type, provider_error_param=provider_error_param,
            provider_request_id=provider_request_id, error_message=error_message,
        ),
        "fix": _provider_error_fix(
            subtype=subtype, provider=provider, provider_error_param=provider_error_param,
        ),
        "evidence": {
            "provider": provider,
            "model": model,
            "status": status or None,
            "status_code": status_code or None,
            "error_code": error_code or None,
            "error_class": error_class,
            "provider_error_code": provider_error_code,
            "provider_error_type": provider_error_type,
            "provider_error_param": provider_error_param,
            "provider_request_id": provider_request_id,
            "retry_after_seconds": retry_after_seconds or None,
            "error_snippet": _error_snippet(error_message),
            "failure_reason": failure_reason_data or None,
        },
    }


def _provider_error_subtype(
    *,
    status_code: int,
    error_code: str,
    provider_error_code: str | None,
    provider_error_type: str | None,
    error_message: str,
) -> str:
    combined = " ".join(
        item.lower()
        for item in (error_code, provider_error_code or "", provider_error_type or "", error_message)
        if item
    )
    if status_code in {408, 504} or "TIMEOUT" in error_code or "timeout" in combined:
        return "timeout"
    if "NETWORK_ERROR" in error_code or any(
        marker in combined
        for marker in ("network", "dns", "connection", "unreachable", "reset by peer")
    ):
        return "network"
    if "content_filter" in combined or "safety" in combined or "policy" in combined:
        return "safety_filter"
    if status_code == 400 or "invalid_request" in combined or "bad_request" in combined:
        return "bad_request"
    if status_code == 404 or "model_not_found" in combined or "not_found" in combined:
        return "model_or_endpoint_not_found"
    if status_code == 402 or "billing" in combined:
        return "billing_or_quota"
    if status_code >= 500:
        return "provider_5xx"
    return "provider_unknown"


def _provider_error_confidence(*, status_code: int, has_failure_reason: bool) -> float:
    if status_code >= 400 and has_failure_reason:
        return _RULE_CONFIDENCE_PROVIDER_ERROR
    if status_code >= 400:
        return 0.74
    if has_failure_reason:
        return 0.70
    return 0.62


def _provider_error_root_cause(
    *,
    provider: str,
    model: str,
    status_code: int,
    error_class: str | None,
    provider_error_code: str | None,
    provider_error_type: str | None,
    provider_error_param: str | None,
    provider_request_id: str | None,
    error_message: str,
) -> str:
    details: list[str] = []
    if error_class:
        details.append(error_class)
    if status_code:
        details.append(f"HTTP {status_code}")
    if provider_error_code:
        details.append(f"code {provider_error_code}")
    if provider_error_type:
        details.append(f"type {provider_error_type}")
    if provider_error_param:
        details.append(f"param {provider_error_param}")
    if provider_request_id:
        details.append(f"request {provider_request_id}")
    detail_text = f" ({', '.join(details)})" if details else ""
    snippet = _error_snippet(error_message)
    suffix = f" Provider message: {snippet}" if snippet else ""
    return f"Provider {provider} failed for model {model}{detail_text}.{suffix}"


def _provider_error_fix(
    *,
    subtype: str,
    provider: str,
    provider_error_param: str | None,
) -> dict[str, str]:
    if subtype == "bad_request":
        param_hint = f" around `{provider_error_param}`" if provider_error_param else ""
        return {
            "primary": f"Validate provider request schema and model parameters{param_hint} before sending.",
            "code": "validate_provider_payload(messages, model, tools, kwargs)",
            "alternative": "Capture the provider request id and replay the same payload in a staging probe.",
        }
    if subtype == "model_or_endpoint_not_found":
        return {
            "primary": "Verify the model name, deployment id, region, and account access for this provider.",
            "code": "assert model in allowed_models_for_provider(provider)",
            "alternative": "Route this path to a known-good fallback model until access is restored.",
        }
    if subtype == "timeout":
        return {
            "primary": "Set a bounded timeout with retry/backoff and fallback for transient provider latency.",
            "code": "response = call_provider(timeout=30, max_retries=2)",
            "alternative": "Use streaming or a smaller model for latency-sensitive paths.",
        }
    if subtype == "network":
        return {
            "primary": "Check egress, DNS, proxy, and provider endpoint reachability from the runtime.",
            "code": "verify_provider_network(provider_endpoint)",
            "alternative": "Fail over to another provider/region when network checks fail.",
        }
    if subtype == "safety_filter":
        return {
            "primary": "Handle provider safety refusals as a typed application state instead of a generic failure.",
            "code": "if provider_error == 'content_filter': return safe_refusal_response()",
            "alternative": "Route policy-sensitive requests through a moderation/rewrite step before generation.",
        }
    if subtype == "provider_5xx":
        return {
            "primary": (
                f"Treat {provider} 5xx as transient: retry with jitter, fallback, "
                "and provider-status alerting."
            ),
            "code": "retry_with_jitter(max_attempts=3, retry_on={500, 502, 503, 504})",
            "alternative": "Temporarily shift traffic to a fallback provider while incident rate is elevated.",
        }
    if subtype == "billing_or_quota":
        return {
            "primary": "Check provider billing status, quota limits, and active payment method.",
            "code": "verify_provider_billing_and_quota(provider)",
            "alternative": "Route traffic to a fallback provider while billing is resolved.",
        }
    return {
        "primary": "Use the structured provider error fields to map this failure to a typed handler.",
        "code": "raise ProviderCallError(status, provider_code, request_id)",
        "alternative": "Add a provider-specific classifier once this error repeats.",
    }
