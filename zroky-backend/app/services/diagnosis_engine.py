from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.services.loop_signals import DEFAULT_LOOP_WINDOW_SIZE
from app.services.provider_status import resolve_provider_status_context
from app.services.privacy import mask_text
from app.services.token_overflow_rules import (
    match_token_overflow_error_pattern,
    resolve_model_context_limit,
    token_rules_version,
)


_COST_SPIKE_HARD_FLOOR_USD = 25.0

RULE_CONFIDENCE: dict[str, float] = {
    "TOKEN_OVERFLOW": 0.98,
    "RATE_LIMIT": 0.95,
    "AUTH_FAILURE": 0.99,
    "PROVIDER_ERROR": 0.82,
    "LOOP_DETECTED": 0.92,
    "COST_SPIKE": 0.90,
}

FAST_RULE_CATEGORIES = ("TOKEN_OVERFLOW", "RATE_LIMIT", "AUTH_FAILURE", "PROVIDER_ERROR")
PATTERN_RULE_CATEGORIES = ("LOOP_DETECTED", "COST_SPIKE")
TOKEN_OVERFLOW_ESTIMATE_THRESHOLD_RATIO = 0.90


def evaluate_fast_rules(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    diagnoses: list[dict[str, Any]] = []

    token_overflow = _detect_token_overflow(payload)
    if token_overflow is not None:
        diagnoses.append(token_overflow)

    rate_limit = _detect_rate_limit(payload)
    if rate_limit is not None:
        diagnoses.append(rate_limit)

    auth_failure = _detect_auth_failure(payload)
    if auth_failure is not None:
        diagnoses.append(auth_failure)

    if not diagnoses:
        provider_error = _detect_provider_error(payload)
        if provider_error is not None:
            diagnoses.append(provider_error)

    return diagnoses


def evaluate_pattern_rules(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_time = now or datetime.now(timezone.utc)

    diagnoses: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []

    loop_detected = _detect_loop(payload, current_time)
    if loop_detected is not None:
        diagnoses.append(loop_detected)

    cost_spike, cost_info = _detect_cost_spike(payload)
    if cost_spike is not None:
        diagnoses.append(cost_spike)
    if cost_info is not None:
        informational.append(cost_info)

    return diagnoses, informational


def build_diagnosis_result(
    *,
    payload: Mapping[str, Any],
    fast_diagnoses: list[dict[str, Any]],
    pattern_diagnoses: list[dict[str, Any]],
    informational: list[dict[str, Any]],
) -> dict[str, Any]:
    combined = [*fast_diagnoses, *pattern_diagnoses]
    result: dict[str, Any] = {
        "diagnosis_contract_version": "v1",
        "diagnoses": combined,
        "diagnosis_count": len(combined),
        "speed_classes": {
            "fast": list(FAST_RULE_CATEGORIES),
            "pattern": list(PATTERN_RULE_CATEGORIES),
            "targets": {
                "fast_p95_seconds": 5,
                "pattern_p95_seconds": 30,
            },
        },
    }

    if informational:
        result["informational"] = informational

    blast_radius = _build_blast_radius(payload)
    if blast_radius is not None:
        result["blast_radius"] = blast_radius

    return result


def evaluate_diagnosis_payload(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    fast_diagnoses = evaluate_fast_rules(payload)
    pattern_diagnoses, informational = evaluate_pattern_rules(payload, now=now)
    return build_diagnosis_result(
        payload=payload,
        fast_diagnoses=fast_diagnoses,
        pattern_diagnoses=pattern_diagnoses,
        informational=informational,
    )


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
        and estimated_prompt_tokens / max(model_limit, 1)
        > TOKEN_OVERFLOW_ESTIMATE_THRESHOLD_RATIO
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
        confidence = RULE_CONFIDENCE["TOKEN_OVERFLOW"]
    elif "token_estimate" in detection_signals:
        detected_by = "token_estimate"
        signal_tokens = estimated_prompt_tokens
        confidence = _token_estimate_confidence(
            estimated_tokens=estimated_prompt_tokens,
            model_limit=model_limit,
        )
    else:
        return None

    overflow_by = (
        signal_tokens - model_limit
        if model_limit > 0 and signal_tokens > 0
        else 0
    )

    conversation_turns = _as_int(
        _pick(payload, ("conversation_turns",), ("conversation", "turns")),
        fallback=1,
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
        fix_alternative = "Route this path to a larger context model when strict truncation is not acceptable."
    else:
        fix_primary = "Summarize or trim rolling conversation history before appending new turns."
        fix_code = (
            "if conversation_tokens(history) > 2500:\n"
            "    history = summarize_history(history, max_tokens=1200)"
        )
        fix_alternative = "Introduce a turn cap with semantic memory extraction for long-running sessions."

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
            "model_context_limit_source_detail": model_limit_details.get(
                "source_detail"
            ),
            "model_context_limit_confidence": model_limit_details.get("confidence"),
            "model_context_limit_catalog_version": model_limit_details.get(
                "catalog_version"
            ),
            "model_context_limit_catalog_updated_at": (
                model_limit_details.get("catalog_updated_at")
            ),
            "model_context_limit_catalog_stale": model_limit_details.get(
                "catalog_stale"
            ),
            "model_context_limit_catalog_stale_after_days": (
                model_limit_details.get("catalog_stale_after_days")
            ),
            "token_estimator_version": _as_str(
                _pick(payload, ("token_estimator_version",)),
            ) or None,
            "token_rules_version": _as_str(
                _pick(payload, ("token_rules_version",)),
            ) or token_rules_version(),
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


def _normalize_error_code(value: str) -> str:
    return value.strip().upper().replace("-", "_")


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


def _resolve_model_context_limit(payload: Mapping[str, Any]) -> int:
    return _as_int(_resolve_model_context_limit_details(payload).get("limit"))


def _resolve_model_context_limit_details(payload: Mapping[str, Any]) -> dict[str, Any]:
    model = _as_str(_pick(payload, ("model",), ("request", "model")))

    explicit_limit = _as_int(
        _pick(
            payload,
            ("model_limit_tokens",),
            ("usage", "model_limit_tokens"),
        ),
    )
    if explicit_limit > 0:
        return _payload_model_context_limit_resolution(
            payload,
            model=model,
            limit=explicit_limit,
            source="payload_explicit",
            source_detail="model_limit_tokens",
            confidence=1.0,
        )

    sdk_limit = _as_int(_pick(payload, ("model_context_limit",)))
    if sdk_limit > 0:
        source = _as_str(
            _pick(payload, ("model_context_limit_source",)),
            fallback="sdk_payload",
        )
        source_detail = _as_str(
            _pick(payload, ("model_context_limit_source_detail",)),
            fallback="model_context_limit",
        )
        confidence = _as_float(
            _pick(payload, ("model_context_limit_confidence",)),
            fallback=0.88,
        )
        return _payload_model_context_limit_resolution(
            payload,
            model=model,
            limit=sdk_limit,
            source=source,
            source_detail=source_detail,
            confidence=confidence,
        )

    return resolve_model_context_limit(model).to_dict()


def _payload_model_context_limit_resolution(
    payload: Mapping[str, Any],
    *,
    model: str,
    limit: int,
    source: str,
    source_detail: str,
    confidence: float,
) -> dict[str, Any]:
    fallback = resolve_model_context_limit(model).to_dict()
    normalized_model = _as_str(fallback.get("normalized_model")) or model.strip().lower()
    return {
        "model": model or None,
        "normalized_model": normalized_model,
        "limit": limit,
        "source": source,
        "source_detail": source_detail,
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "catalog_version": _as_str(
            _pick(payload, ("model_context_limit_catalog_version",)),
            fallback=_as_str(fallback.get("catalog_version")),
        ),
        "catalog_updated_at": _as_str(
            _pick(payload, ("model_context_limit_catalog_updated_at",)),
            fallback=_as_str(fallback.get("catalog_updated_at")),
        ),
        "catalog_stale": False
        if source == "payload_explicit"
        else _as_bool(
            _pick(payload, ("model_context_limit_catalog_stale",)),
            fallback=bool(fallback.get("catalog_stale", False)),
        ),
        "catalog_stale_after_days": _as_int(
            _pick(payload, ("model_context_limit_catalog_stale_after_days",)),
            fallback=_as_int(fallback.get("catalog_stale_after_days"), fallback=180),
        ),
    }


def _estimate_detection_allowed(payload: Mapping[str, Any]) -> bool:
    status = _as_str(_pick(payload, ("status",), ("call_status",))).strip().lower()
    if status in {
        "partial",
        "partial_success",
        "incomplete",
        "streaming",
        "cancelled",
        "canceled",
    }:
        return False
    if status in {"success", "completed", "complete", "ok", "succeeded"}:
        return False
    return True


def _token_estimate_confidence(*, estimated_tokens: int, model_limit: int) -> float:
    ratio = estimated_tokens / max(model_limit, 1)
    if ratio >= 1.0:
        return 0.85
    if ratio >= 0.98:
        return 0.82
    if ratio >= 0.95:
        return 0.78
    return 0.72


def _error_snippet(error_message: str) -> str | None:
    text = error_message.strip()
    if not text:
        return None
    return mask_text(text)[:240]


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


def _failure_reason(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _pick(payload, ("failure_reason",))
    return dict(value) if isinstance(value, Mapping) else {}


def _error_message_from_payload(payload: Mapping[str, Any]) -> str:
    return _as_str(
        _pick(
            payload,
            ("error_message",),
            ("error", "message"),
            ("failure_reason", "message"),
            ("failure_reason", "provider_error", "message"),
            ("failure_reason", "provider_error_body", "message"),
        )
    )


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
    retry_after_seconds = _as_float(_pick(payload, ("failure_reason", "retry_after_seconds")), fallback=0.0)
    provider_request_id = _as_str(_pick(payload, ("failure_reason", "provider_request_id"))) or None

    is_rate_limit = status_code == 429 or any(
        signal in error_code or signal in error_message
        for signal in ("rate_limit", "too_many_requests", "quota")
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
    status_fallback_used = _as_bool(provider_status_context.get("status_fallback_used"), fallback=True)

    return {
        "category": "RATE_LIMIT",
        "speed_class": "fast",
        "confidence": RULE_CONFIDENCE["RATE_LIMIT"],
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
        "invalid_api_key",
        "invalid_key",
        "invalid_token",
        "expired_key",
        "expired_token",
        "unauthorized",
        "forbidden",
        "auth",
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
        "confidence": RULE_CONFIDENCE["AUTH_FAILURE"],
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
    failure_reason = _failure_reason(payload)

    has_failure_signal = (
        status in {"failed", "failure", "error", "errored", "timeout", "dead_lettered"}
        or status_code >= 400
        or bool(error_code)
        or bool(error_message)
        or bool(failure_reason)
    )
    if not has_failure_signal:
        return None

    # Known high-confidence rules should own these categories.
    if error_code in {"TOKEN_OVERFLOW", "RATE_LIMIT", "AUTH_FAILURE"}:
        return None
    if status_code in {401, 403, 429}:
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
            status_code=status_code,
            has_failure_reason=bool(failure_reason),
        ),
        "detected_by": "structured_failure_reason" if failure_reason else "failed_call_metadata",
        "root_cause": _provider_error_root_cause(
            provider=provider,
            model=model,
            status_code=status_code,
            error_class=error_class,
            provider_error_code=provider_error_code,
            provider_error_type=provider_error_type,
            provider_error_param=provider_error_param,
            provider_request_id=provider_request_id,
            error_message=error_message,
        ),
        "fix": _provider_error_fix(
            subtype=subtype,
            provider=provider,
            provider_error_param=provider_error_param,
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
            "failure_reason": failure_reason or None,
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
        for item in (
            error_code,
            provider_error_code or "",
            provider_error_type or "",
            error_message,
        )
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
        return RULE_CONFIDENCE["PROVIDER_ERROR"]
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
        param_hint = (
            f" around `{provider_error_param}`" if provider_error_param else ""
        )
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
            "primary": (
                "Set a bounded timeout with retry/backoff and fallback for transient "
                "provider latency."
            ),
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
            "primary": (
                "Handle provider safety refusals as a typed application state instead "
                "of a generic failure."
            ),
            "code": "if provider_error == 'content_filter': return safe_refusal_response()",
            "alternative": (
                "Route policy-sensitive requests through a moderation/rewrite step "
                "before generation."
            ),
        }
    if subtype == "provider_5xx":
        return {
            "primary": (
                f"Treat {provider} 5xx as transient: retry with jitter, fallback, "
                "and provider-status alerting."
            ),
            "code": "retry_with_jitter(max_attempts=3, retry_on={500, 502, 503, 504})",
            "alternative": (
                "Temporarily shift traffic to a fallback provider while incident "
                "rate is elevated."
            ),
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


def _detect_loop(payload: Mapping[str, Any], now: datetime) -> dict[str, Any] | None:
    agent_name = _as_str(_pick(payload, ("agent_name",), ("loop", "agent_name")), fallback="unknown")
    signature = _as_str(
        _pick(payload, ("prompt_fingerprint",), ("loop", "prompt_fingerprint")),
        fallback="unknown",
    )

    repeat_count = _as_int(
        _pick(payload, ("loop", "repeat_count"), ("repeat_count",)),
    )
    repeat_window_seconds = _as_int(
        _pick(payload, ("loop", "window_seconds"), ("repeat_window_seconds",)),
        fallback=90,
    )
    tool_chain_cycles = _as_int(
        _pick(payload, ("loop", "tool_chain_repeat_cycles"), ("tool_chain_repeat_cycles",)),
    )
    tool_window_seconds = _as_int(
        _pick(payload, ("loop", "tool_window_seconds"), ("tool_window_seconds",)),
        fallback=120,
    )
    no_progress = _as_bool(
        _pick(payload, ("loop", "no_progress"), ("no_progress",)),
        fallback=False,
    )
    loop_window_size = _as_int(
        _pick(payload, ("loop", "loop_window_size"), ("loop_window_size",)),
        fallback=DEFAULT_LOOP_WINDOW_SIZE,
    )
    loop_resolved = _as_bool(
        _pick(payload, ("loop", "loop_resolved"), ("loop_resolved",)),
        fallback=False,
    )
    if loop_resolved:
        return None

    guard_reason = _loop_false_positive_guard(payload, now)
    if guard_reason is not None:
        return None

    no_progress_reasons_raw = _pick(payload, ("loop", "no_progress_reasons"))
    no_progress_reasons = [
        _as_str(reason)
        for reason in no_progress_reasons_raw
        if _as_str(reason)
    ] if isinstance(no_progress_reasons_raw, list) else []

    sample_timestamps_raw = _pick(payload, ("loop", "sample_timestamps"))
    sample_timestamps = [
        _as_str(value)
        for value in sample_timestamps_raw
        if _as_str(value)
    ] if isinstance(sample_timestamps_raw, list) else []

    error_pattern_raw = _pick(payload, ("loop", "error_pattern"))
    error_pattern = error_pattern_raw if isinstance(error_pattern_raw, Mapping) else {}
    output_pattern_raw = _pick(payload, ("loop", "output_pattern"))
    output_pattern = output_pattern_raw if isinstance(output_pattern_raw, Mapping) else {}
    tool_cycle_raw = _pick(payload, ("loop", "tool_cycle"))
    tool_cycle = tool_cycle_raw if isinstance(tool_cycle_raw, Mapping) else {}
    retry_pattern_raw = _pick(payload, ("loop", "retry_pattern"))
    retry_pattern = retry_pattern_raw if isinstance(retry_pattern_raw, Mapping) else {}
    retry_metadata_raw = _pick(payload, ("retry_metadata",), ("retry",))
    retry_metadata = retry_metadata_raw if isinstance(retry_metadata_raw, Mapping) else {}

    output_repeat_count = _as_int(
        output_pattern.get("repeat_count") or _pick(payload, ("output_repeat_count",)),
    )
    output_fingerprint = _as_str(
        output_pattern.get("output_fingerprint") or _pick(payload, ("output_fingerprint",)),
    )
    output_similarity = _as_float(output_pattern.get("output_similarity_score"))
    near_repeated_output = _as_bool(
        output_pattern.get("near_repeated_output"),
        fallback=output_similarity >= 0.72,
    )
    tool_cycle_repeat_count = _as_int(
        tool_cycle.get("repeat_count") or tool_chain_cycles,
    )
    tool_state_changed = _as_bool(tool_cycle.get("state_changed"), fallback=False)
    retry_count = _as_int(
        retry_pattern.get("retry_count")
        or retry_metadata.get("retry_count")
        or _pick(payload, ("retry_count",)),
    )
    repeated_retry_reason_count = _as_int(
        retry_pattern.get("dominant_retry_reason_count"),
    )
    max_steps_reached = _as_bool(
        retry_metadata.get("max_steps_reached") or _pick(payload, ("max_steps_reached",)),
        fallback=False,
    )
    retry_suppression_applied = _as_bool(
        _pick(payload, ("loop", "retry_suppression_applied")),
        fallback=False,
    )
    exact_output_repeat = bool(
        output_fingerprint and output_repeat_count >= 3 and repeat_count >= 3,
    )
    similar_output_repeat = bool(
        near_repeated_output and output_similarity >= 0.72 and repeat_count >= 3,
    )
    output_signal = (
        "output_fingerprint"
        if exact_output_repeat
        else "output_similarity"
        if similar_output_repeat
        else None
    )

    # Tool cycle detection: require at least 3 repeats within a reasonable window
    # and no state change to indicate a loop
    tool_cycle_detected = (
        tool_cycle_repeat_count >= 3
        and tool_window_seconds > 0  # Ensure window is valid
        and not tool_state_changed
    )

    score_result = _loop_score(
        prompt_repeat=repeat_count >= 5 and repeat_window_seconds <= 90 and no_progress,
        output_signal=output_signal,
        tool_cycle_repeat=tool_cycle_detected,
        retry_pattern=retry_count >= 3 and (repeated_retry_reason_count >= 3 or max_steps_reached),
        no_progress=no_progress,
    )
    loop_score = score_result["score"]
    detected_by = score_result["detected_by"]
    score_breakdown = score_result["breakdown"]
    if loop_score < 0.65 or not detected_by:
        return None

    confidence_level = _loop_confidence_level(loop_score)
    dominant_pattern = _loop_dominant_pattern(
        detected_by=detected_by,
        output_fingerprint=output_fingerprint,
        tool_cycle=tool_cycle,
        retry_pattern=retry_pattern,
        repeat_count=repeat_count,
    )
    return {
        "category": "LOOP_DETECTED",
        "speed_class": "pattern",
        "confidence": loop_score,
        "confidence_level": confidence_level,
        "detected_by": detected_by[0],
        "root_cause": (
            "Multi-signal loop detected"
            f" for agent {agent_name} with signature {signature}"
            f" (score={loop_score:.2f}, signals={','.join(detected_by)})."
        ),
        "fix": {
            "primary": "Add a no-progress guard using input, output, tool, and retry signatures.",
            "code": (
                "if loop_score(input_sig, output_sig, tool_sig, retry_sig) >= 0.65:\n"
                "    break_loop_and_emit_guardrail()"
            ),
            "alternative": "Add max-step limits and require state-change proof before repeating tools.",
        },
        "evidence": {
            "detected_by": detected_by,
            "loop_score": loop_score,
            "loop_score_breakdown": score_breakdown,
            "confidence": loop_score,
            "confidence_level": confidence_level,
            "dominant_pattern": dominant_pattern,
            "loop_window_size": loop_window_size,
            "loop_resolved": False,
            "agent_name": agent_name,
            "prompt_fingerprint": signature,
            "repeat_count": repeat_count,
            "repeat_window_seconds": repeat_window_seconds,
            "output_fingerprint": output_fingerprint or None,
            "output_repeat_count": output_repeat_count,
            "output_similarity_score": output_similarity,
            "near_repeated_output": near_repeated_output,
            "tool_chain_repeat_cycles": tool_cycle_repeat_count,
            "tool_window_seconds": tool_window_seconds,
            "tool_name": _tool_name_from_pattern(tool_cycle),
            "retry_count": retry_count,
            "retry_reason": _as_str(
                retry_pattern.get("dominant_retry_reason") or retry_metadata.get("retry_reason"),
            ) or None,
            "max_steps_reached": max_steps_reached,
            "no_progress": no_progress,
            "no_progress_reasons": no_progress_reasons,
            "retry_suppression_applied": retry_suppression_applied,
            "sample_timestamps": sample_timestamps,
            "output_pattern": {
                "output_fingerprint": output_fingerprint or None,
                "repeat_count": output_repeat_count,
                "stagnant_output": _as_bool(output_pattern.get("stagnant_output"), fallback=False),
                "output_similarity_score": output_similarity,
                "near_repeated_output": near_repeated_output,
            },
            "tool_cycle": {
                "dominant_pattern": _as_str(tool_cycle.get("dominant_pattern")) or None,
                "pattern_type": _as_str(tool_cycle.get("pattern_type")) or None,
                "repeat_count": tool_cycle_repeat_count,
                "tool_sequence": tool_cycle.get("tool_sequence") if isinstance(tool_cycle.get("tool_sequence"), list) else [],
                "state_changed": tool_state_changed,
                "state_change_count": _as_int(tool_cycle.get("state_change_count")),
                "no_state_change_count": _as_int(tool_cycle.get("no_state_change_count")),
            },
            "retry_pattern": {
                "retry_count": retry_count,
                "dominant_retry_reason": _as_str(retry_pattern.get("dominant_retry_reason")) or None,
                "dominant_retry_reason_count": repeated_retry_reason_count,
            },
            "error_pattern": {
                "dominant_error": _error_snippet(_as_str(error_pattern.get("dominant_error"), fallback="")),
                "dominant_error_count": _as_int(error_pattern.get("dominant_error_count")),
                "failure_count": _as_int(error_pattern.get("failure_count")),
                "useless_output_count": _as_int(error_pattern.get("useless_output_count")),
                "stagnant_output": _as_bool(error_pattern.get("stagnant_output"), fallback=False),
            },
            "cooldown_seconds": 600,
            "threshold_agent_repeat_count": 5,
            "threshold_agent_window_seconds": 90,
            "threshold_tool_chain_cycles": 3,
            "threshold_tool_window_seconds": 120,
            "threshold_output_similarity_score": 0.72,
        },
    }


def _loop_false_positive_guard(payload: Mapping[str, Any], now: datetime) -> str | None:
    if _as_bool(_pick(payload, ("loop", "user_driven_repetition"), ("user_driven_repetition",)), fallback=False):
        return "user_driven_repetition"
    if _as_bool(_pick(payload, ("loop", "legitimate_repeated_output"), ("legitimate_repeated_output",)), fallback=False):
        return "legitimate_repeated_output"
    if _as_bool(_pick(payload, ("loop", "idempotent_retry"), ("idempotent_retry",)), fallback=False):
        return "idempotent_retry"

    retry_attempts = _as_int(
        _pick(payload, ("retry", "sdk_attempts"), ("sdk_retry_attempts",), ("retry_attempt",)),
    )
    backoff_attempts = _as_int(
        _pick(payload, ("retry", "backoff_attempts"), ("backoff_attempts",)),
    )
    known_sdk_retry = _as_bool(
        _pick(payload, ("retry", "is_sdk_retry"), ("is_sdk_retry",)),
        fallback=False,
    )
    if known_sdk_retry:
        return "known_sdk_retry"

    last_fired_raw = _pick(payload, ("loop", "last_fired_at"), ("last_loop_detected_at",))
    last_fired_at = _parse_datetime(last_fired_raw)
    if last_fired_at and now - last_fired_at < timedelta(minutes=10):
        return "cooldown_active"
    return None


def _loop_score(
    *,
    prompt_repeat: bool,
    output_signal: str | None,
    tool_cycle_repeat: bool,
    retry_pattern: bool,
    no_progress: bool,
) -> dict[str, Any]:
    # Weights normalized to sum to 1.0 (0.20 + 0.35 + 0.30 + 0.15 = 1.0)
    weights = {
        "prompt_repeat": 0.20,
        "output_fingerprint": 0.35,
        "tool_cycle": 0.30,
        "retry_pattern": 0.15,
    }
    detected_by: list[str] = []
    breakdown = {
        "prompt_repeat": 0.0,
        "output": 0.0,
        "tool_cycle": 0.0,
        "retry_pattern": 0.0,
        "no_progress_bonus": 0.0,
    }
    score = 0.0
    if prompt_repeat:
        breakdown["prompt_repeat"] = weights["prompt_repeat"]
        score += breakdown["prompt_repeat"]
        detected_by.append("prompt_repeat")
    if output_signal:
        breakdown["output"] = weights["output_fingerprint"]
        score += breakdown["output"]
        detected_by.append(output_signal)
    if tool_cycle_repeat:
        breakdown["tool_cycle"] = weights["tool_cycle"]
        score += breakdown["tool_cycle"]
        detected_by.append("tool_cycle")
    if retry_pattern:
        breakdown["retry_pattern"] = weights["retry_pattern"]
        score += breakdown["retry_pattern"]
        detected_by.append("retry_pattern")
    if no_progress and len(detected_by) >= 2:
        breakdown["no_progress_bonus"] = 0.10
        score += breakdown["no_progress_bonus"]
    return {
        "score": round(min(score, 0.97), 2),
        "detected_by": detected_by,
        "breakdown": {key: round(value, 2) for key, value in breakdown.items()},
    }


def _loop_confidence_level(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _loop_dominant_pattern(
    *,
    detected_by: list[str],
    output_fingerprint: str,
    tool_cycle: Mapping[str, Any],
    retry_pattern: Mapping[str, Any],
    repeat_count: int,
) -> str:
    if "tool_cycle" in detected_by:
        pattern = _as_str(tool_cycle.get("dominant_pattern"))
        return pattern or "repeated tool cycle"
    if "output_fingerprint" in detected_by:
        return f"repeated output_fingerprint:{output_fingerprint[:12]}"
    if "output_similarity" in detected_by:
        return "near-repeated output content"
    if "retry_pattern" in detected_by:
        reason = _as_str(retry_pattern.get("dominant_retry_reason"), fallback="same outcome")
        return f"retry loop:{reason}"
    return f"prompt_repeat:{repeat_count}"


def _tool_name_from_pattern(tool_cycle: Mapping[str, Any]) -> str | None:
    pattern = _as_str(tool_cycle.get("dominant_pattern"))
    if not pattern:
        sequence = tool_cycle.get("tool_sequence")
        if isinstance(sequence, list) and sequence:
            return _as_str(sequence[-1]) or None
        return None
    return pattern.split(":", 1)[0].split("->", 1)[0] or None


def _detect_cost_spike(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_spend = _as_float(
        _pick(
            payload,
            ("cost", "current_15m_spend_usd"),
            ("current_15m_spend_usd",),
            ("spend", "current_15m"),
        ),
    )
    baseline_spend = _as_float(
        _pick(
            payload,
            ("cost", "baseline_15m_spend_usd"),
            ("baseline_15m_spend_usd",),
            ("spend", "baseline_15m"),
        ),
    )
    history_days = _as_float(_pick(payload, ("cost", "history_days"), ("history_days",)))
    history_calls = _as_int(_pick(payload, ("cost", "history_calls"), ("history_calls",)))
    baseline_window_days = _as_int(
        _pick(payload, ("cost", "baseline_window_days"), ("baseline_window_days",)),
        fallback=14,
    )
    spend_bucket_minutes = _as_int(
        _pick(payload, ("cost", "spend_bucket_minutes"), ("spend_bucket_minutes",)),
        fallback=15,
    )
    model_coefficient = _as_float(
        _pick(payload, ("cost", "model_spend_coefficient"), ("model_spend_coefficient",)),
        fallback=1.0,
    )
    model_coefficient = max(model_coefficient, 1.0)

    if current_spend <= 0 and baseline_spend <= 0:
        return None, None

    warmup_ready = history_days >= 3 and history_calls >= 200
    effective_baseline = baseline_spend * model_coefficient
    hard_threshold = max(3 * effective_baseline, effective_baseline + _COST_SPIKE_HARD_FLOOR_USD)

    if not warmup_ready:
        informational_threshold = max(2 * max(effective_baseline, 0.01), effective_baseline + 10)
        if current_spend > informational_threshold:
            return None, {
                "type": "COST_SURGE_WARNING",
                "message": "Spend surge observed before baseline warm-up gate was met.",
                "evidence": {
                    "current_15m_spend_usd": current_spend,
                    "baseline_15m_spend_usd": baseline_spend,
                    "effective_baseline_15m_spend_usd": effective_baseline,
                    "history_days": history_days,
                    "history_calls": history_calls,
                    "warmup_required_days": 3,
                    "warmup_required_calls": 200,
                    "baseline_window_days": baseline_window_days,
                    "spend_bucket_minutes": spend_bucket_minutes,
                    "model_spend_coefficient": model_coefficient,
                },
            }
        return None, None

    if current_spend <= hard_threshold:
        return None, None

    return {
        "category": "COST_SPIKE",
        "speed_class": "pattern",
        "confidence": RULE_CONFIDENCE["COST_SPIKE"],
        "root_cause": (
            "Current 15-minute spend exceeded project baseline threshold: "
            f"{current_spend:.2f} USD vs threshold {hard_threshold:.2f} USD."
        ),
        "fix": {
            "primary": "Throttle high-cost routes and enforce budget-aware model routing immediately.",
            "code": (
                "if current_15m_spend_usd > cost_threshold:\n"
                "    route_to_lower_cost_model(); enable_budget_guardrails()"
            ),
            "alternative": "Apply per-model spend caps and temporary traffic shaping for top spenders.",
        },
        "evidence": {
            "current_15m_spend_usd": current_spend,
            "baseline_15m_spend_usd": baseline_spend,
            "effective_baseline_15m_spend_usd": effective_baseline,
            "hard_threshold_15m_spend_usd": hard_threshold,
            "trigger_rule": "current_15m_spend > max(3*baseline, baseline+25)",
            "history_days": history_days,
            "history_calls": history_calls,
            "warmup_gate_met": warmup_ready,
            "warmup_required_days": 3,
            "warmup_required_calls": 200,
            "baseline_window_days": baseline_window_days,
            "spend_bucket_minutes": spend_bucket_minutes,
            "model_spend_coefficient": model_coefficient,
        },
    }, None


def _build_blast_radius(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    trace_id = _as_str(_pick(payload, ("trace_id",)), fallback="")
    if not trace_id:
        return None

    downstream_calls_any = _pick(payload, ("downstream_calls",), ("blast_radius", "downstream_calls"))
    downstream_calls = (
        downstream_calls_any if isinstance(downstream_calls_any, list) else []
    )

    affected_count = _as_int(_pick(payload, ("blast_radius", "downstream_affected_calls")))
    if affected_count <= 0:
        affected_count = len(downstream_calls)

    wasted_cost_usd = _as_float(_pick(payload, ("blast_radius", "wasted_cost_usd")))
    if wasted_cost_usd <= 0:
        wasted_cost_usd = sum(
            _as_float(item.get("wasted_cost_usd"))
            for item in downstream_calls
            if isinstance(item, Mapping)
        )

    if affected_count <= 0 and wasted_cost_usd <= 0:
        return None

    failed_agent = _as_str(
        _pick(payload, ("blast_radius", "failed_agent"), ("agent_name",)),
        fallback="unknown-agent",
    )

    return {
        "trace_id": trace_id,
        "failed_agent": failed_agent,
        "downstream_affected_calls": affected_count,
        "wasted_cost_usd": round(wasted_cost_usd, 6),
        "summary": (
            f"{failed_agent} failure impacted {affected_count} downstream calls"
            f" with estimated wasted cost ${wasted_cost_usd:.2f}."
        ),
    }


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


def _as_int(value: Any, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return int(float(text))
        except ValueError:
            return fallback
    return fallback


def _as_float(value: Any, *, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return float(text)
        except ValueError:
            return fallback
    return fallback


def _as_str(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _as_bool(value: Any, *, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
