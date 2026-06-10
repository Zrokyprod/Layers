# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Internal telemetry helpers: payload building, PII masking, error classification,
provider resolution, event finalization, and payload-guard deduplication.

All helpers here are pure (stateless) or carry only non-test-reset state
(_local, _payload_guard_*).  The test fixture in conftest.py calls .clear()
on the deque/set names re-exported from zroky.__init__, which works because
they reference the same underlying objects defined here.
"""
from __future__ import annotations

import threading
from inspect import isawaitable
from collections import deque
from copy import deepcopy
from typing import Any

from zroky._internal import validation as _validation
from zroky._internal.config import SDKConfig
from zroky._internal.loop_signals import (
    normalize_retry_metadata,
    output_signal,
    summarize_tool_lifecycle,
)
from zroky._internal.models import CallEvent, ErrorCode
from zroky._internal.pii import mask_error_message, mask_text, mask_messages, mask_value
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint  # noqa: F401 (re-export)
from zroky._internal.failure_reason import build_failure_reason, extract_status_code
from zroky._internal.retry import RetryOutcome, RetryPolicy
from zroky._internal.queue import EventQueue
from zroky._internal.metrics import notify_error as _notify_error, notify_event as _notify_event

# ---------------------------------------------------------------------------
# Thread-local agent context (shared by agent() context manager in __init__)
# ---------------------------------------------------------------------------

_local = threading.local()

# ---------------------------------------------------------------------------
# Payload-guard dedup state (cleared by conftest via zroky.__init__ aliases)
# ---------------------------------------------------------------------------

_PAYLOAD_GUARD_LOG_DEDUPE_LIMIT = 1024
_PROVIDER_PAYLOAD_KWARG_KEYS = frozenset({"messages", "tools", "stream"})
_SDK_TELEMETRY_KWARG_KEYS = frozenset({"_zroky_retry_metadata", "_zroky_tool_lifecycle"})

_payload_guard_logged_call_ids: set[str] = set()
_payload_guard_log_order: deque[str] = deque()
_payload_guard_log_lock = threading.Lock()

import logging  # noqa: E402
_logger = logging.getLogger("zroky")


# ---------------------------------------------------------------------------
# Agent context
# ---------------------------------------------------------------------------

def _get_agent() -> str | None:
    return getattr(_local, "agent_name", None)


# ---------------------------------------------------------------------------
# Payload copying
# ---------------------------------------------------------------------------

def _copy_provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return deepcopy(messages)


def _copy_provider_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    return deepcopy(tools)


def _build_telemetry_messages(
    messages: list[dict[str, Any]],
    *,
    mask_pii: bool,
) -> list[dict[str, Any]]:
    return mask_messages(messages) if mask_pii else mask_value(messages)


def _mask_telemetry_value(value: Any) -> Any:
    return mask_value(value)


def _build_telemetry_tools(
    tools: list[dict[str, Any]] | None,
    *,
    mask_pii: bool,
) -> list[dict[str, Any]] | None:
    if tools is None:
        return None
    return _mask_telemetry_value(tools)


# ---------------------------------------------------------------------------
# Loop / tool lifecycle telemetry
# ---------------------------------------------------------------------------

def _apply_loop_telemetry_from_output(event: CallEvent, output_content: Any) -> None:
    signal = output_signal(output_content)
    event.normalized_output = signal.get("normalized_output")
    event.output_fingerprint = signal.get("output_fingerprint")


def _apply_tool_lifecycle_telemetry(event: CallEvent) -> None:
    summary = summarize_tool_lifecycle(event.tool_calls_made)
    if summary is not None:
        event.tool_lifecycle_summary = summary


def _private_retry_metadata(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    return normalize_retry_metadata(kwargs.get("_zroky_retry_metadata"))


def _private_tool_lifecycle(kwargs: dict[str, Any]) -> list[dict[str, Any]] | None:
    value = kwargs.get("_zroky_tool_lifecycle")
    if isinstance(value, list):
        return summarize_tool_lifecycle(mask_value(value))
    return None


def _record_tool_lifecycle(request: dict[str, Any]) -> list[dict[str, Any]] | None:
    value = request.get("tool_lifecycle") or request.get("tool_lifecycle_summary")
    return mask_value(value) if isinstance(value, list) else None


# ---------------------------------------------------------------------------
# Token / context telemetry
# ---------------------------------------------------------------------------

def _estimate_prompt_tokens_for_telemetry(
    *,
    model: str,
    messages: list[dict[str, Any]],
) -> int | None:
    try:
        estimate = _validation.estimate_tokens({"model": model, "messages": deepcopy(messages)})
    except Exception:
        return None
    return estimate if estimate >= 0 else None


def _model_context_limit_telemetry_for_model(model: str) -> dict[str, Any]:
    try:
        resolution = _validation.model_context_limit_resolution(model)
    except Exception:
        resolution = {}
    return {
        "model_context_limit": resolution.get("limit"),
        "model_context_limit_source": resolution.get("source"),
        "model_context_limit_source_detail": resolution.get("source_detail"),
        "model_context_limit_confidence": resolution.get("confidence"),
        "model_context_limit_catalog_version": resolution.get("catalog_version"),
        "model_context_limit_catalog_updated_at": resolution.get("catalog_updated_at"),
        "model_context_limit_catalog_stale": resolution.get("catalog_stale"),
        "model_context_limit_catalog_stale_after_days": resolution.get("catalog_stale_after_days"),
    }


def _token_estimator_version_for_telemetry(estimated_prompt_tokens: int | None) -> str | None:
    if estimated_prompt_tokens is None:
        return None
    try:
        return _validation.token_estimator_version()
    except Exception:
        return None


def _token_rules_version_for_telemetry() -> str | None:
    try:
        return _validation.token_rules_version()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Retry / fallback helpers
# ---------------------------------------------------------------------------

def _build_retry_policy(cfg: SDKConfig, max_retries: int | None = None) -> RetryPolicy:
    retries = max_retries if max_retries is not None else cfg.retry_max_retries
    return RetryPolicy(
        max_retries=retries,
        base_backoff_seconds=cfg.retry_base_backoff_seconds,
        max_backoff_seconds=cfg.retry_max_backoff_seconds,
    )


def _effective_fallback_models(
    cfg: SDKConfig,
    fallback: list[str] | None,
) -> list[str] | None:
    if fallback is not None:
        return fallback
    if cfg.fallback_models:
        return list(cfg.fallback_models)
    return None


def _merge_retry_metadata(event: CallEvent, outcome: RetryOutcome) -> None:
    meta = outcome.to_retry_metadata()
    if meta is not None:
        event.retry_metadata = meta


# ---------------------------------------------------------------------------
# Provider payload isolation guard
# ---------------------------------------------------------------------------

def _log_provider_payload_guard(*, reason: str, model: str, call_id: str, mode: str) -> None:
    if not _should_log_provider_payload_guard(call_id):
        return
    _logger.warning(
        "[ZROKY] Internal payload separation guard recovered provider payload: "
        "%s. model=%s call_id=%s mode=%s. Provider calls must use the original "
        "unmasked request payload.",
        reason, model, call_id, mode,
    )


def _should_log_provider_payload_guard(call_id: str) -> bool:
    with _payload_guard_log_lock:
        if call_id in _payload_guard_logged_call_ids:
            return False
        if len(_payload_guard_log_order) >= _PAYLOAD_GUARD_LOG_DEDUPE_LIMIT:
            oldest_call_id = _payload_guard_log_order.popleft()
            _payload_guard_logged_call_ids.discard(oldest_call_id)
        _payload_guard_log_order.append(call_id)
        _payload_guard_logged_call_ids.add(call_id)
        return True


def _ensure_provider_payload_is_isolated(
    *,
    original_messages: list[dict[str, Any]],
    provider_messages: list[dict[str, Any]],
    telemetry_messages: list[dict[str, Any]],
    original_tools: list[dict[str, Any]] | None,
    provider_tools: list[dict[str, Any]] | None,
    telemetry_tools: list[dict[str, Any]] | None,
    model: str,
    call_id: str,
    mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    if provider_messages is telemetry_messages:
        _log_provider_payload_guard(
            reason="provider messages share the telemetry messages object",
            model=model, call_id=call_id, mode=mode,
        )
        provider_messages = _copy_provider_messages(original_messages)
    if provider_tools is not None and provider_tools is telemetry_tools:
        _log_provider_payload_guard(
            reason="provider tools share the telemetry tools object",
            model=model, call_id=call_id, mode=mode,
        )
        provider_tools = _copy_provider_tools(original_tools)
    if provider_messages is original_messages:
        _log_provider_payload_guard(
            reason="provider messages were not defensively copied",
            model=model, call_id=call_id, mode=mode,
        )
        provider_messages = _copy_provider_messages(original_messages)
    if provider_tools is not None and provider_tools is original_tools:
        _log_provider_payload_guard(
            reason="provider tools were not defensively copied",
            model=model, call_id=call_id, mode=mode,
        )
        provider_tools = _copy_provider_tools(original_tools)
    return provider_messages, provider_tools


def _build_provider_kwargs(
    kwargs: dict[str, Any],
    *,
    model: str,
    call_id: str,
    mode: str,
) -> dict[str, Any]:
    provider_kwargs = dict(kwargs)
    sdk_telemetry_keys = [k for k in sorted(_SDK_TELEMETRY_KWARG_KEYS) if k in provider_kwargs]
    for key in sdk_telemetry_keys:
        provider_kwargs.pop(key, None)
    removed_keys = [k for k in sorted(_PROVIDER_PAYLOAD_KWARG_KEYS) if k in provider_kwargs]
    for key in removed_keys:
        provider_kwargs.pop(key, None)
    if removed_keys:
        _logger.error(
            "[ZROKY] Removed duplicate provider payload kwargs before provider call: "
            "keys=%s model=%s call_id=%s mode=%s.",
            ",".join(removed_keys), model, call_id, mode,
        )
    return provider_kwargs


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------

def _resolve_provider_fn(provider: str, kwargs: dict[str, Any]) -> Any:
    client = kwargs.pop("_client", None)
    if client is not None:
        return client.chat.completions.create
    if provider in ("openai", "azure_openai"):
        try:
            import openai  # noqa: PLC0415
            return openai.chat.completions.create
        except ImportError:
            pass
    if provider == "anthropic":
        try:
            import anthropic  # noqa: PLC0415
            _anthropic_client = anthropic.Anthropic()
            return _anthropic_client.messages.create
        except ImportError:
            pass
    raise RuntimeError(
        f"[ZROKY] Cannot resolve provider '{provider}'. "
        "Pass `_client=your_client` or install the provider library."
    )


# ---------------------------------------------------------------------------
# Response metadata extraction
# ---------------------------------------------------------------------------

def _extract_response_metadata(event: CallEvent, response: Any) -> None:
    usage = getattr(response, "usage", None)
    if usage:
        event.prompt_tokens = getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0)
        event.completion_tokens = getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0)
        event.reasoning_tokens = getattr(
            getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0
        ) or 0
        event.cache_creation_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0
        event.cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
    choices = getattr(response, "choices", [])
    if choices:
        message = getattr(choices[0], "message", None)
        if message:
            tc_list = getattr(message, "tool_calls", None)
            if tc_list:
                event.tool_calls_made = mask_value([
                    {
                        "id": getattr(tc, "id", None),
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": getattr(tc.function, "name", None) if hasattr(tc, "function") else None,
                            "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
                        },
                    }
                    for tc in tc_list
                ])
                _apply_tool_lifecycle_telemetry(event)
            event.output_content = mask_value(getattr(message, "content", None))
            event.final_answer = event.final_answer or event.output_content
            _apply_loop_telemetry_from_output(event, event.output_content)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def _classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    status_code = extract_status_code(exc)
    provider_code = str(getattr(exc, "code", "") or "").lower()
    provider_type = str(getattr(exc, "type", "") or "").lower()
    combined = " ".join(
        item for item in (msg, exc_type, provider_code, provider_type, str(status_code or "")) if item
    )
    if _validation.is_token_overflow_error_message(combined):
        return ErrorCode.TOKEN_OVERFLOW
    rate_limit_patterns = [
        "429", "rate limit", "rate_limit", "too many requests", "throttling",
        "quota exceeded", "capacity", "over quota", "limit exceeded",
        "requests per minute", "rpm limit", "tpm limit",
    ]
    if status_code == 429 or any(p in combined for p in rate_limit_patterns):
        return ErrorCode.RATE_LIMIT
    auth_patterns = [
        "401", "403", "invalid_api_key", "invalid api key", "authentication",
        "unauthorized", "access denied", "permission denied", "not authenticated",
        "invalid token", "expired token", "api key not found",
    ]
    auth_exception_types = ["authenticationerror", "permissionerror", "unauthorizederror"]
    if (
        status_code in {401, 403}
        or any(p in combined for p in auth_patterns)
        or any(t in exc_type for t in auth_exception_types)
    ):
        return ErrorCode.AUTH_FAILURE
    timeout_patterns = [
        "timeout", "timed out", "deadline exceeded", "read timeout",
        "connect timeout", "request timeout", "connection timeout",
    ]
    if (
        status_code in {408, 504}
        or any(p in combined for p in timeout_patterns)
        or any(t in exc_type for t in ["timeouterror", "timeoutexception"])
    ):
        return ErrorCode.TIMEOUT
    connection_patterns = [
        "connection error", "connecterror", "network error", "unreachable",
        "refused", "reset by peer", "broken pipe", "dns", "name resolution",
    ]
    if any(p in combined for p in connection_patterns):
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# Event finalization helpers (take queue/cfg as args, no module state needed)
# ---------------------------------------------------------------------------

def _build_synthetic_response(content: str, provider: str, model: str) -> Any:
    return {
        "id": "zroky-loop-guard-synthetic",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _apply_preflight_block_event(event: CallEvent, exc: Any) -> None:
    event.status = "blocked"
    event.latency_ms = 0.0
    event.error_code = exc.error_code
    event.error_message = mask_error_message(exc)
    event.failure_reason = mask_value({
        "schema_version": "zroky.preflight_block.v1",
        "classification": exc.error_code,
        "message": str(exc),
        "preflight_warning_types": exc.warning_types,
        "preflight_warnings": exc.warnings,
    })


def _finalize_call(
    event: CallEvent,
    response: Any,
    latency_ms: float,
    queue: EventQueue,
    cfg: SDKConfig,
) -> None:
    event.status = "success"
    event.latency_ms = latency_ms
    _extract_response_metadata(event, response)
    queue.enqueue(event)
    _notify_event(event)
    if cfg.verbose:
        print(
            f"[ZROKY] Call captured: {event.provider}/{event.model}"
            f" — {latency_ms:.0f}ms — fp={event.prompt_fingerprint}"
        )


def _finalize_call_error(
    event: CallEvent,
    exc: Exception,
    latency_ms: float,
    queue: EventQueue,
    cfg: SDKConfig,
) -> None:
    event.status = "failed"
    event.latency_ms = latency_ms
    event.error_code = _classify_error(exc)
    event.error_message = mask_error_message(exc)
    event.failure_reason = build_failure_reason(exc, error_code=event.error_code)
    queue.enqueue(event)
    _notify_event(event)
    _notify_error(event, exc)
    if cfg.verbose:
        print(
            f"[ZROKY] {event.error_code} detected in your last call. "
            f"fp={event.prompt_fingerprint}. Open dashboard for fix."
        )


def _finalize_preflight_blocked(
    event: CallEvent,
    exc: Any,
    queue: EventQueue,
    cfg: SDKConfig,
) -> None:
    _apply_preflight_block_event(event, exc)
    queue.enqueue(event)
    _notify_event(event)
    _notify_error(event, exc)
    if cfg.verbose:
        print(
            f"[ZROKY] {event.error_code} blocked before provider call. "
            f"fp={event.prompt_fingerprint}."
        )


async def _enqueue_event_async(queue: Any, event: CallEvent) -> None:
    """Enqueue from async paths while tolerating synchronous test doubles."""
    result = queue.enqueue(event)
    if isawaitable(result):
        await result


async def _finalize_call_async(
    event: CallEvent,
    response: Any,
    latency_ms: float,
    queue: Any,
    cfg: SDKConfig,
) -> None:
    event.status = "success"
    event.latency_ms = latency_ms
    _extract_response_metadata(event, response)
    await _enqueue_event_async(queue, event)
    _notify_event(event)
    if cfg.verbose:
        print(
            f"[ZROKY] Call captured: {event.provider}/{event.model}"
            f" — {latency_ms:.0f}ms — fp={event.prompt_fingerprint}"
        )


async def _finalize_call_error_async(
    event: CallEvent,
    exc: Exception,
    latency_ms: float,
    queue: Any,
    cfg: SDKConfig,
) -> None:
    event.status = "failed"
    event.latency_ms = latency_ms
    event.error_code = _classify_error(exc)
    event.error_message = mask_error_message(exc)
    event.failure_reason = build_failure_reason(exc, error_code=event.error_code)
    await _enqueue_event_async(queue, event)
    _notify_event(event)
    _notify_error(event, exc)
    if cfg.verbose:
        print(
            f"[ZROKY] {event.error_code} detected in your last call. "
            f"fp={event.prompt_fingerprint}. Open dashboard for fix."
        )


async def _finalize_preflight_blocked_async(
    event: CallEvent,
    exc: Any,
    queue: Any,
    cfg: SDKConfig,
) -> None:
    _apply_preflight_block_event(event, exc)
    await _enqueue_event_async(queue, event)
    _notify_event(event)
    _notify_error(event, exc)
    if cfg.verbose:
        print(
            f"[ZROKY] {event.error_code} blocked before provider call. "
            f"fp={event.prompt_fingerprint}."
        )
