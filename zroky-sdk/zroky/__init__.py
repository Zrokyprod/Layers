"""
ZROKY Python SDK
Production AI diagnosis engine — capture, diagnose, fix.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any

from zroky._internal import validation as _validation
from zroky._internal.config import SDKConfig, load_config
from zroky._internal.loop_signals import (
    normalize_retry_metadata,
    output_signal,
    summarize_tool_lifecycle,
)
from zroky._internal.metrics import (
    notify_error as _notify_error,
    notify_event as _notify_event,
    register_error_callback,
    register_event_callback,
    register_flush_callback,
    unregister_error_callback,
    unregister_event_callback,
    unregister_flush_callback,
)
from zroky._internal.models import CallEvent, CallType, ErrorCode
from zroky._internal.pii import mask_error_message, mask_messages, mask_text, mask_value
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint
from zroky._internal.queue import EventQueue
from zroky._internal.retry import RetryOutcome, RetryPolicy, retry_async, retry_sync
from zroky._internal.fallback import (
    FallbackChain,
    FallbackExecutor,
    FallbackOutcome,
    ModelHealthRegistry,
    build_chain,
    resolve_provider_from_model,
)
from zroky._internal.failure_reason import build_failure_reason, extract_status_code
from zroky._internal.rate_limiter import RateLimiter, rate_limit_key
from zroky._internal.budget import BudgetTracker, BudgetExceededError
from zroky._internal.cost import calculate_cost
from zroky._internal.loop_guard import LoopGuard, LoopDetectedError
from zroky._internal.timeout_manager import (
    TimeoutManager,
    _timed_async_iter,
    _timed_sync_iter,
)
from zroky._internal.cache import (
    CacheEntry,
    CachedResponse,
    ResponseCache,
    build_cache_key,
    cached_stream_iter,
    cached_stream_iter_async,
)

_ASYNC_AVAILABLE = True  # asyncio is in stdlib; flag kept for optional-dep gating

_config: SDKConfig | None = None
_queue: EventQueue | None = None
_lock = threading.Lock()
_recent_preflight_calls: deque[float] = deque()
_preflight_lock = threading.Lock()
_logger = logging.getLogger(__name__)

# Per-model health tracker for adaptive fallback ordering
_model_health_registry = ModelHealthRegistry()
_rate_limiter = RateLimiter()
_response_cache: ResponseCache | None = None
_budget_tracker: BudgetTracker | None = None
_loop_guard: LoopGuard | None = None
_timeout_manager: TimeoutManager | None = None
_payload_guard_logged_call_ids: set[str] = set()
_payload_guard_log_order: deque[str] = deque()
_payload_guard_log_lock = threading.Lock()

_PREFLIGHT_RECENT_CALLS_WINDOW_SECONDS = 60.0
_PROVIDER_PAYLOAD_KWARG_KEYS = frozenset({"messages", "tools", "stream"})
_SDK_TELEMETRY_KWARG_KEYS = frozenset({"_zroky_retry_metadata", "_zroky_tool_lifecycle"})
_PAYLOAD_GUARD_LOG_DEDUPE_LIMIT = 1024

# Thread-local agent context
_local = threading.local()


class ZrokyPreflightError(RuntimeError):
    """Raised when configured preflight blocking warnings are present."""

    def __init__(self, warnings: list[dict[str, Any]]) -> None:
        self.warnings = warnings
        self.warning_types = [
            str(warning.get("type", "UNKNOWN")).strip().upper()
            for warning in warnings
        ]
        self.error_code = self._error_code_from_warning_types(self.warning_types)
        warning_types = ", ".join(
            warning_type or "UNKNOWN" for warning_type in self.warning_types
        )
        super().__init__(
            "[ZROKY] Preflight blocked provider call due to: "
            f"{warning_types or 'UNKNOWN'}"
        )

    @staticmethod
    def _error_code_from_warning_types(warning_types: list[str]) -> str:
        if "AUTH_RISK" in warning_types:
            return ErrorCode.AUTH_FAILURE
        if "TOKEN_OVERFLOW" in warning_types:
            return ErrorCode.TOKEN_OVERFLOW
        if "RATE_LIMIT_RISK" in warning_types:
            return ErrorCode.RATE_LIMIT
        return ErrorCode.UNKNOWN_ERROR


def _build_synthetic_response(content: str, provider: str, model: str) -> Any:
    """Build a minimal OpenAI-style response dict for loop guard return_cached."""
    return {
        "id": "zroky-loop-guard-synthetic",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _get_agent() -> str | None:
    """Try to discover the current agent name from the call stack."""
    return getattr(_local, "agent_name", None)


def _copy_provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy original request messages before any telemetry-only transformation."""
    return deepcopy(messages)


def _copy_provider_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Copy original request tools before any telemetry-only transformation."""
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


def _build_retry_policy(cfg: SDKConfig, max_retries: int | None = None) -> RetryPolicy:
    """Construct retry policy from config with optional per-call override."""
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
    """Merge retry outcome into event telemetry when retries occurred."""
    meta = outcome.to_retry_metadata()
    if meta is not None:
        event.retry_metadata = meta


def _private_tool_lifecycle(kwargs: dict[str, Any]) -> list[dict[str, Any]] | None:
    value = kwargs.get("_zroky_tool_lifecycle")
    if isinstance(value, list):
        return summarize_tool_lifecycle(mask_value(value))
    return None


def _record_tool_lifecycle(request: dict[str, Any]) -> list[dict[str, Any]] | None:
    value = request.get("tool_lifecycle") or request.get("tool_lifecycle_summary")
    return mask_value(value) if isinstance(value, list) else None


def _estimate_prompt_tokens_for_telemetry(
    *,
    model: str,
    messages: list[dict[str, Any]],
) -> int | None:
    try:
        estimate = _validation.estimate_tokens(
            {
                "model": model,
                "messages": deepcopy(messages),
            }
        )
    except Exception:
        return None
    return estimate if estimate >= 0 else None


def _model_context_limit_for_telemetry(model: str) -> int | None:
    try:
        return _validation.known_model_context_limit(model)
    except Exception:
        return None


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
        "model_context_limit_catalog_stale_after_days": (
            resolution.get("catalog_stale_after_days")
        ),
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


def _log_provider_payload_guard(
    *,
    reason: str,
    model: str,
    call_id: str,
    mode: str,
) -> None:
    if not _should_log_provider_payload_guard(call_id):
        return

    _logger.warning(
        "[ZROKY] Internal payload separation guard recovered provider payload: "
        "%s. model=%s call_id=%s mode=%s. Provider calls must use the original "
        "unmasked request payload.",
        reason,
        model,
        call_id,
        mode,
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
            model=model,
            call_id=call_id,
            mode=mode,
        )
        provider_messages = _copy_provider_messages(original_messages)
    if provider_tools is not None and provider_tools is telemetry_tools:
        _log_provider_payload_guard(
            reason="provider tools share the telemetry tools object",
            model=model,
            call_id=call_id,
            mode=mode,
        )
        provider_tools = _copy_provider_tools(original_tools)
    if provider_messages is original_messages:
        _log_provider_payload_guard(
            reason="provider messages were not defensively copied",
            model=model,
            call_id=call_id,
            mode=mode,
        )
        provider_messages = _copy_provider_messages(original_messages)
    if provider_tools is not None and provider_tools is original_tools:
        _log_provider_payload_guard(
            reason="provider tools were not defensively copied",
            model=model,
            call_id=call_id,
            mode=mode,
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
    sdk_telemetry_keys = [
        key for key in sorted(_SDK_TELEMETRY_KWARG_KEYS) if key in provider_kwargs
    ]
    for key in sdk_telemetry_keys:
        provider_kwargs.pop(key, None)

    removed_keys = [key for key in sorted(_PROVIDER_PAYLOAD_KWARG_KEYS) if key in provider_kwargs]
    for key in removed_keys:
        provider_kwargs.pop(key, None)

    if removed_keys:
        _logger.error(
            "[ZROKY] Removed duplicate provider payload kwargs before provider call: "
            "keys=%s model=%s call_id=%s mode=%s. Explicit original payload values "
            "will be used.",
            ",".join(removed_keys),
            model,
            call_id,
            mode,
        )

    return provider_kwargs


# ---------------------------------------------------------------------------
# Public: pre-execution validation
# ---------------------------------------------------------------------------

def estimate_tokens(payload: dict[str, Any]) -> int:
    """Estimate token usage using a lightweight heuristic (~4 chars/token)."""
    return _validation.estimate_tokens(payload)


def check_token_overflow(
    payload: dict[str, Any],
    *,
    estimated_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Check whether payload is near model context limit."""
    return _validation.check_token_overflow(payload, estimated_tokens=estimated_tokens)


def check_rate_limit_risk(
    payload: dict[str, Any],
    *,
    estimated_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Check burst/heavy-request risk before executing provider call."""
    return _validation.check_rate_limit_risk(payload, estimated_tokens=estimated_tokens)


def model_context_limit_resolution(model: str | None) -> dict[str, Any]:
    """Resolve context limit with source/confidence metadata for a model."""
    return _validation.model_context_limit_resolution(model)


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze an upcoming LLM call payload and return structured warnings."""
    return _validation.validate(payload)


def print_validation(result: dict[str, Any]) -> None:
    """Print validation result with developer-friendly warnings."""
    _validation.print_validation(result)


# ---------------------------------------------------------------------------
# Public: init
# ---------------------------------------------------------------------------

def init(
    *,
    api_key: str | None = None,
    project: str | None = None,
    mode: str | None = None,
    mask_pii: bool | None = None,
    ingest_url: str | None = None,
    validate_preflight: bool | None = None,
    validate_preflight_sample_rate: float | None = None,
    preflight_blocking_warning_types: list[str] | tuple[str, ...] | None = None,
    circuit_breaker_failure_threshold: int | None = None,
    circuit_breaker_reset_timeout_seconds: float | None = None,
    retry_max_retries: int | None = None,
    retry_base_backoff_seconds: float | None = None,
    retry_max_backoff_seconds: float | None = None,
    fallback_models: list[str] | tuple[str, ...] | None = None,
    fallback_max: int | None = None,
    fallback_adaptive: bool | None = None,
    rate_limits: dict[str, dict[str, int]] | None = None,
    rate_limit_enabled: bool | None = None,
    cache_enabled: bool | None = None,
    cache_default_ttl: float | None = None,
    cache_max_memory: int | None = None,
    cache_db_path: str | None = None,
    cache_ttl_overrides: dict[str, float] | None = None,
    budget_enabled: bool | None = None,
    budget_db_path: str | None = None,
    budget_default_rate: float | None = None,
    budget_rules: dict[str, dict[str, dict[str, dict[str, Any]]]] | None = None,
    loop_guard_enabled: bool | None = None,
    loop_guard_max_calls_per_trace: int | None = None,
    loop_guard_max_repeated_outputs: int | None = None,
    loop_guard_max_cost_per_trace_usd: float | None = None,
    loop_guard_action: str | None = None,
    timeout_enabled: bool | None = None,
    timeout_stream_chunk_seconds: float | None = None,
    default_timeout: float | None = None,
) -> None:
    """
    Initialize the ZROKY SDK.
    Call once at application startup before any tracked calls.
    """
    global _config, _queue, _response_cache, _budget_tracker, _loop_guard, _timeout_manager

    with _lock:
        cfg = load_config(
            api_key=api_key,
            project=project,
            mode=mode,
            mask_pii=mask_pii,
            ingest_url=ingest_url,
            validate_preflight=validate_preflight,
            validate_preflight_sample_rate=validate_preflight_sample_rate,
            preflight_blocking_warning_types=preflight_blocking_warning_types,
            circuit_breaker_failure_threshold=circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout_seconds=circuit_breaker_reset_timeout_seconds,
            retry_max_retries=retry_max_retries,
            retry_base_backoff_seconds=retry_base_backoff_seconds,
            retry_max_backoff_seconds=retry_max_backoff_seconds,
            fallback_models=fallback_models,
            fallback_max=fallback_max,
            fallback_adaptive=fallback_adaptive,
            rate_limits=rate_limits,
            rate_limit_enabled=rate_limit_enabled,
            cache_enabled=cache_enabled,
            cache_default_ttl=cache_default_ttl,
            cache_max_memory=cache_max_memory,
            cache_db_path=cache_db_path,
            cache_ttl_overrides=cache_ttl_overrides,
            budget_enabled=budget_enabled,
            budget_db_path=budget_db_path,
            budget_default_rate=budget_default_rate,
            budget_rules=budget_rules,
            loop_guard_enabled=loop_guard_enabled,
            loop_guard_max_calls_per_trace=loop_guard_max_calls_per_trace,
            loop_guard_max_repeated_outputs=loop_guard_max_repeated_outputs,
            loop_guard_max_cost_per_trace_usd=loop_guard_max_cost_per_trace_usd,
            loop_guard_action=loop_guard_action,
            timeout_enabled=timeout_enabled,
            timeout_stream_chunk_seconds=timeout_stream_chunk_seconds,
            default_timeout=default_timeout,
        )
        _config = cfg

        from zroky._internal.queue import EventQueue  # noqa: PLC0415
        q = EventQueue(config=cfg)
        q.start()
        _queue = q

    # Configure rate limiter from explicit limits
    if cfg.rate_limit_enabled and cfg.rate_limits:
        _rate_limiter.configure_all(cfg.rate_limits)

    # Configure response cache
    if cfg.cache_enabled:
        _response_cache = ResponseCache(
            max_memory=cfg.cache_max_memory,
            default_ttl=cfg.cache_default_ttl,
            db_path=cfg.cache_db_path,
            ttl_overrides=cfg.cache_ttl_overrides,
        )
    else:
        _response_cache = None

    # Configure budget tracker
    global _budget_tracker
    if cfg.budget_enabled:
        _budget_tracker = BudgetTracker(
            db_path=cfg.budget_db_path,
            default_rate_per_1m_tokens=cfg.budget_default_rate,
            rules=cfg.budget_rules,
        )
    else:
        _budget_tracker = None

    # Configure loop guard
    global _loop_guard
    if cfg.loop_guard_enabled:
        _loop_guard = LoopGuard(
            max_calls_per_trace=cfg.loop_guard_max_calls_per_trace,
            max_repeated_outputs=cfg.loop_guard_max_repeated_outputs,
            max_cost_per_trace_usd=cfg.loop_guard_max_cost_per_trace_usd,
            default_action=cfg.loop_guard_action,
        )
    else:
        _loop_guard = None

    # Configure timeout manager
    global _timeout_manager
    if cfg.timeout_enabled:
        _timeout_manager = TimeoutManager(
            stream_chunk_timeout=cfg.timeout_stream_chunk_seconds,
            default_timeout=cfg.default_timeout,
        )
    else:
        _timeout_manager = None

    _print_init_banner(cfg)


def _print_init_banner(cfg: SDKConfig) -> None:
    project_label = cfg.project or ("configured-key" if cfg.api_key else "unknown")
    print(f"[ZROKY] Connected to project: {project_label}")
    print(f"[ZROKY] PII masking: {'active' if cfg.mask_pii else 'inactive'}")
    print(
        "[ZROKY] Circuit breaker: armed "
        f"(threshold={cfg.circuit_breaker_failure_threshold}, "
        f"reset={cfg.circuit_breaker_reset_timeout_seconds:.0f}s)"
    )
    retry_label = f"enabled (max {cfg.retry_max_retries})" if cfg.retry_max_retries > 0 else "disabled"
    print(f"[ZROKY] Auto-retry: {retry_label}")
    fallback_label = (
        f"enabled ({len(cfg.fallback_models)} backup model(s))"
        if cfg.fallback_models
        else "disabled"
    )
    print(f"[ZROKY] Fallback policy: {fallback_label}")
    rl_label = "enabled" if cfg.rate_limit_enabled else "disabled"
    if cfg.rate_limit_enabled and cfg.rate_limits:
        rl_label += f" ({len(cfg.rate_limits)} key(s) configured)"
    print(f"[ZROKY] Rate limiter: {rl_label}")
    cache_label = "enabled" if cfg.cache_enabled else "disabled"
    if cfg.cache_enabled:
        disk_part = f", disk: {cfg.cache_db_path}" if cfg.cache_db_path else ""
        cache_label += f" (memory: {cfg.cache_max_memory}, TTL: {cfg.cache_default_ttl:.0f}s{disk_part})"
    print(f"[ZROKY] Cache: {cache_label}")
    budget_label = "enabled" if cfg.budget_enabled else "disabled"
    if cfg.budget_enabled:
        budget_label += f" (default_rate=${cfg.budget_default_rate}/1M tokens)"
    print(f"[ZROKY] Budget: {budget_label}")
    loop_guard_label = "enabled" if cfg.loop_guard_enabled else "disabled"
    if cfg.loop_guard_enabled:
        loop_guard_label += (
            f" (max_calls={cfg.loop_guard_max_calls_per_trace}, "
            f"max_repeated={cfg.loop_guard_max_repeated_outputs}, "
            f"action={cfg.loop_guard_action})"
        )
    print(f"[ZROKY] Loop guard: {loop_guard_label}")
    timeout_label = "enabled" if cfg.timeout_enabled else "disabled"
    if cfg.timeout_enabled:
        timeout_label += f" (chunk_timeout={cfg.timeout_stream_chunk_seconds:.0f}s)"
    print(f"[ZROKY] Timeout control: {timeout_label}")
    print(f"[ZROKY] Preflight validation: {'enabled' if cfg.validate_preflight else 'disabled'}")
    if cfg.validate_preflight:
        print(f"[ZROKY] Preflight sample rate: {cfg.validate_preflight_sample_rate:.2f}")
    if cfg.preflight_blocking_warning_types:
        print(
            "[ZROKY] Preflight blocking warnings: "
            f"{', '.join(cfg.preflight_blocking_warning_types)}"
        )
    print("[ZROKY] Ready. First call should appear in dashboard within 5 seconds.")


def _ensure_init() -> tuple[SDKConfig, EventQueue]:
    if _config is None or _queue is None:
        # Auto-init from environment if not explicitly initialized
        init()
    return _config, _queue  # type: ignore[return-value]


def _recent_calls_for_preflight(now: float | None = None) -> int:
    current_time = now if now is not None else time.monotonic()
    cutoff = current_time - _PREFLIGHT_RECENT_CALLS_WINDOW_SECONDS

    with _preflight_lock:
        _recent_preflight_calls.append(current_time)
        while _recent_preflight_calls and _recent_preflight_calls[0] < cutoff:
            _recent_preflight_calls.popleft()
        return len(_recent_preflight_calls)


def _provider_api_key_hint(*, provider: str, kwargs: dict[str, Any]) -> str | None:
    explicit_key = kwargs.get("api_key")
    if isinstance(explicit_key, str) and explicit_key.strip():
        return explicit_key

    if kwargs.get("_client") is not None:
        return "client-configured"

    provider_key_env_map: dict[str, tuple[str, ...]] = {
        "openai": ("OPENAI_API_KEY",),
        "azure_openai": ("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "anthropic": ("ANTHROPIC_API_KEY",),
    }

    for env_name in provider_key_env_map.get(provider, ()):
        env_value = os.environ.get(env_name)
        if isinstance(env_value, str) and env_value.strip():
            return "env-configured"

    return None


def _is_preflight_sampled_in(*, sample_rate: float, sample_key: str) -> bool:
    if sample_rate <= 0.0:
        return False
    if sample_rate >= 1.0:
        return True

    digest = hashlib.sha256(sample_key.encode("utf-8")).digest()
    bucket_value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    normalized_bucket = bucket_value / float(1 << 64)
    return normalized_bucket < sample_rate


def _run_preflight_validation(
    *,
    cfg: SDKConfig,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    sample_key: str,
    kwargs: dict[str, Any],
) -> None:
    blocking_types = {
        warning_type.strip().upper()
        for warning_type in cfg.preflight_blocking_warning_types
        if warning_type.strip()
    }
    if not cfg.validate_preflight and not blocking_types:
        return

    if cfg.validate_preflight and not _is_preflight_sampled_in(
        sample_rate=cfg.validate_preflight_sample_rate,
        sample_key=sample_key,
    ) and not blocking_types:
        return

    try:
        payload: dict[str, Any] = {
            "provider": provider,
            "model": model,
            "messages": messages,
            "tools": tools,
            "meta": {
                "recent_calls": _recent_calls_for_preflight(),
            },
        }
        api_key_hint = _provider_api_key_hint(provider=provider, kwargs=kwargs)
        if api_key_hint:
            payload["api_key"] = api_key_hint

        validation_result = _validation.validate(payload)
        warnings = (
            validation_result.get("warnings")
            if isinstance(validation_result, dict)
            else None
        )
        if isinstance(warnings, list) and warnings:
            _validation.print_validation(validation_result)
            blocking_warnings = [
                warning
                for warning in warnings
                if str(warning.get("type", "")).strip().upper() in blocking_types
            ]
            if blocking_warnings:
                raise ZrokyPreflightError(blocking_warnings)
    except ZrokyPreflightError:
        raise
    except Exception:
        # Validation is advisory-only and must never break provider execution path.
        if cfg.verbose:
            print("[ZROKY] Preflight validation unavailable; continuing call.")


# ---------------------------------------------------------------------------
# Public: call
# ---------------------------------------------------------------------------

def call(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    user_id: str | None = None,
    max_retries: int | None = None,
    fallback: list[str] | None = None,
    no_cache: bool = False,
    timeout: float | None = None,
    stream_chunk_timeout: float | None = None,
    # Pass-through kwargs forwarded to provider
    **kwargs: Any,
) -> Any:
    """
    Make a tracked provider call.
    This wraps openai.chat.completions.create / anthropic equivalent
    and captures request/response metadata for ZROKY.

    For actual provider call to happen the developer must also have
    the provider client installed and pass `_client` kwarg, or set up
    the provider library to be called through @zroky.trace / zroky.agent().

    In capture-only mode: call zroky.record() directly after your own
    provider call (see record()).
    """
    cfg, queue = _ensure_init()

    original_messages = _copy_provider_messages(messages)
    original_tools = _copy_provider_tools(tools)
    provider_messages = _copy_provider_messages(original_messages)
    provider_tools = _copy_provider_tools(original_tools)
    telemetry_messages = _build_telemetry_messages(original_messages, mask_pii=cfg.mask_pii)
    telemetry_tools = _build_telemetry_tools(original_tools, mask_pii=cfg.mask_pii)

    call_type = CallType.TOOL_CALL if tools else CallType.CHAT
    prompt_fingerprint = generate_prompt_fingerprint(
        messages=original_messages,
        tools=original_tools,
        model=model,
    )
    estimated_prompt_tokens = _estimate_prompt_tokens_for_telemetry(
        model=model,
        messages=original_messages,
    )
    model_context_telemetry = _model_context_limit_telemetry_for_model(model)
    model_context_limit = model_context_telemetry["model_context_limit"]
    token_estimator_version = _token_estimator_version_for_telemetry(
        estimated_prompt_tokens,
    )
    token_rules_version = _token_rules_version_for_telemetry()

    event = CallEvent(
        provider=provider,
        model=model,
        messages=telemetry_messages,
        tools=telemetry_tools,
        estimated_prompt_tokens=estimated_prompt_tokens,
        model_context_limit=model_context_limit,
        model_context_limit_source=(
            model_context_telemetry["model_context_limit_source"]
        ),
        model_context_limit_source_detail=(
            model_context_telemetry["model_context_limit_source_detail"]
        ),
        model_context_limit_confidence=(
            model_context_telemetry["model_context_limit_confidence"]
        ),
        model_context_limit_catalog_version=(
            model_context_telemetry["model_context_limit_catalog_version"]
        ),
        model_context_limit_catalog_updated_at=(
            model_context_telemetry["model_context_limit_catalog_updated_at"]
        ),
        model_context_limit_catalog_stale=(
            model_context_telemetry["model_context_limit_catalog_stale"]
        ),
        model_context_limit_catalog_stale_after_days=(
            model_context_telemetry["model_context_limit_catalog_stale_after_days"]
        ),
        token_estimator_version=token_estimator_version,
        token_rules_version=token_rules_version,
        call_type=call_type,
        trace_id=trace_id,
        parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        prompt_fingerprint=prompt_fingerprint,
        user_id=user_id,
        retry_metadata=_private_retry_metadata(kwargs),
        tool_lifecycle_summary=_private_tool_lifecycle(kwargs),
    )

    # --- Cache check (before preflight, retry, fallback, rate-limit) ---
    _cache_key: str | None = None
    if _response_cache is not None and not no_cache:
        _cache_key = build_cache_key(prompt_fingerprint)
        cached_entry = _response_cache.get(_cache_key)
        if cached_entry is not None:
            event.cache_hit = True
            event.status = "success"
            event.latency_ms = 0.0
            if cached_entry.usage:
                event.prompt_tokens = cached_entry.usage.get("prompt_tokens", 0)
                event.completion_tokens = cached_entry.usage.get("completion_tokens", 0)
            event.output_content = mask_text(cached_entry.content) if cached_entry.content else None
            _apply_loop_telemetry_from_output(event, event.output_content)
            if cached_entry.tool_calls:
                event.tool_calls_made = mask_value(cached_entry.tool_calls)
                _apply_tool_lifecycle_telemetry(event)
            queue.enqueue(event)
            _notify_event(event)
            if cfg.verbose:
                print(f"[ZROKY] Cache HIT: {provider}/{model} — fp={prompt_fingerprint[:12]}")
            if stream:
                return cached_stream_iter(cached_entry)
            return CachedResponse(cached_entry)

    # --- Budget check (after cache, before preflight / rate-limit) ---
    _budget_result = None
    if _budget_tracker is not None:
        _budget_result = _budget_tracker.check(
            project=cfg.project,
            agent=_get_agent() or cfg.default_agent,
            user=user_id,
            model=model,
            prompt_tokens=estimated_prompt_tokens or 0,
        )
        event.estimated_cost_usd = _budget_result.estimated_cost_usd
        event.budget_remaining_usd = _budget_result.remaining_usd
        event.budget_action_taken = _budget_result.action
        if _budget_result.action == "hard_block":
            raise BudgetExceededError(_budget_result.message)
        if _budget_result.action in ("warn", "soft_block"):
            _logger.warning("%s", _budget_result.message)

    # Loop guard: pre-call check
    _loop_result_pre = None
    if _loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_pre = _loop_guard.check_pre_call(
            trace_id=event.trace_id,
            estimated_cost_usd=event.estimated_cost_usd or 0.0,
        )
        if _loop_result_pre.action == "raise":
            raise LoopDetectedError(_loop_result_pre.message, _loop_result_pre.loop_type)
        if _loop_result_pre.action == "warn":
            _logger.warning("%s", _loop_result_pre.message)
        if _loop_result_pre.action == "return_cached":
            cached = _loop_guard.get_last_good_response(event.trace_id)
            if cached is not None:
                event.status = "loop_guarded"
                event.output_content = cached
                event.loop_action_taken = "return_cached"
                queue.enqueue(event)
                _notify_event(event)
                return _build_synthetic_response(cached, provider, model)

    try:
        _run_preflight_validation(
            cfg=cfg,
            provider=provider,
            model=model,
            messages=deepcopy(original_messages),
            tools=deepcopy(original_tools),
            sample_key=f"{provider}|{model}|{prompt_fingerprint}",
            kwargs=kwargs,
        )
    except ZrokyPreflightError as exc:
        _finalize_preflight_blocked(event, exc, queue, cfg)
        raise

    provider_fn_kwargs = dict(kwargs)
    provider_fn = _resolve_provider_fn(provider, provider_fn_kwargs)
    call_mode = "stream" if stream else "non-stream"
    provider_kwargs = _build_provider_kwargs(
        provider_fn_kwargs,
        model=model,
        call_id=event.call_id,
        mode=call_mode,
    )
    start_ns = time.perf_counter_ns()

    retry_policy = _build_retry_policy(cfg, max_retries)
    effective_fallback = _effective_fallback_models(cfg, fallback)
    fallback_chain = build_chain(
        primary_provider=provider,
        primary_model=model,
        fallback=effective_fallback,
        adaptive=cfg.fallback_adaptive,
        max_fallbacks=cfg.fallback_max,
    )
    event.fallback_chain = fallback_chain.models() if fallback_chain else None

    if stream:
        return _wrapped_stream(
            provider_fn,
            event,
            queue,
            cfg,
            start_ns,
            original_messages=original_messages,
            provider_messages=provider_messages,
            telemetry_messages=telemetry_messages,
            original_tools=original_tools,
            provider_tools=provider_tools,
            telemetry_tools=telemetry_tools,
            provider_kwargs=provider_kwargs,
            retry_policy=retry_policy,
            fallback_chain=fallback_chain,
            kwargs=kwargs,
            estimated_prompt_tokens=estimated_prompt_tokens or 0,
            cache_key=_cache_key,
            budget_result=_budget_result,
            timeout=timeout,
            stream_chunk_timeout=stream_chunk_timeout,
        )

    # Non-stream: try each model in chain (primary + fallbacks)
    _fallback_executor = FallbackExecutor(
        chain=fallback_chain,
        registry=_model_health_registry,
        verbose=cfg.verbose,
        circuit_breaker_failure_threshold=cfg.circuit_breaker_failure_threshold,
        circuit_breaker_reset_timeout_seconds=cfg.circuit_breaker_reset_timeout_seconds,
    )

    _last_retry_outcome: list[RetryOutcome] = []

    def _make_call(try_model: str, try_provider: str, _idx: int = 0) -> Any:
        retry_outcome = RetryOutcome()
        _last_retry_outcome[:] = [retry_outcome]
        try_fn_kwargs = dict(kwargs)
        try_provider_fn = _resolve_provider_fn(try_provider, try_fn_kwargs)
        try_provider_kwargs = _build_provider_kwargs(
            try_fn_kwargs, model=try_model, call_id=event.call_id, mode=call_mode,
        )

        # Inject timeout per model (user override or intelligent default)
        if _timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout

        # Rate limiter: wait for capacity before sending
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            _rate_limiter.acquire(
                rl_key,
                estimated_tokens=estimated_prompt_tokens or 0,
                verbose=cfg.verbose,
            )

        def _inner_call(
            target_model: str = try_model,
            target_fn: Any = try_provider_fn,
            target_kwargs: dict[str, Any] = try_provider_kwargs,
        ) -> Any:
            pm, pt = _ensure_provider_payload_is_isolated(
                original_messages=original_messages,
                provider_messages=_copy_provider_messages(original_messages),
                telemetry_messages=telemetry_messages,
                original_tools=original_tools,
                provider_tools=_copy_provider_tools(original_tools),
                telemetry_tools=telemetry_tools,
                model=target_model,
                call_id=event.call_id,
                mode=call_mode,
            )
            return target_fn(model=target_model, messages=pm, tools=pt, **target_kwargs)

        return retry_sync(
            _inner_call,
            policy=retry_policy,
            classify_error=_classify_error,
            verbose=cfg.verbose,
            call_kwargs={},
            outcome=retry_outcome,
        )

    try:
        response, fallback_outcome = _fallback_executor.execute_sync(
            primary_model=model,
            primary_provider=provider,
            call_fn=_make_call,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        _finalize_call_error(event, exc, latency_ms, queue, cfg)
        raise

    latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
    fallback_outcome.merge_into_event(event)
    if _last_retry_outcome:
        _merge_retry_metadata(event, _last_retry_outcome[0])
    _finalize_call(event, response, latency_ms, queue, cfg)
    _model_health_registry.record(
        fallback_outcome.resolved_model or model, latency_ms, success=True,
    )
    # Adaptive timeout: feed observed latency (sync non-stream)
    if _timeout_manager is not None and cfg.timeout_enabled:
        _timeout_manager.record_latency(
            fallback_outcome.resolved_model or model, latency_ms / 1000.0,
        )
    # Rate limiter: learn from response headers & actual usage
    if cfg.rate_limit_enabled:
        rl_key = rate_limit_key(
            fallback_outcome.resolved_provider or provider,
            fallback_outcome.resolved_model or model,
        )
        actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
        _rate_limiter.update_from_response(
            rl_key, response,
            actual_tokens=actual_tokens,
            estimated_tokens=estimated_prompt_tokens or 0,
        )
    # Budget record on success (sync non-stream)
    if _budget_tracker is not None and _budget_result is not None:
        cost_breakdown = calculate_cost(
            model=event.resolved_model or event.model,
            prompt_tokens=event.prompt_tokens or 0,
            completion_tokens=event.completion_tokens or 0,
            reasoning_tokens=event.reasoning_tokens or 0,
            cache_creation_tokens=event.cache_creation_tokens or 0,
            cache_read_tokens=event.cache_read_tokens or 0,
            status="success",
        )
        event.actual_cost_usd = cost_breakdown["total_cost_usd"]
        _budget_tracker.record_spend(
            project=cfg.project,
            agent=event.agent_name or cfg.default_agent,
            user=event.user_id,
            cost_usd=cost_breakdown["total_cost_usd"],
            window_keys=_budget_result.window_keys,
        )
    # Loop guard: post-call check
    if _loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_post = _loop_guard.check_post_call(
            trace_id=event.trace_id,
            output_content=event.output_content,
            provider=event.provider,
            model=event.resolved_model or event.model,
            actual_cost_usd=event.actual_cost_usd or 0.0,
            estimated_cost_usd=event.estimated_cost_usd or 0.0,
        )
        event.loop_action_taken = _loop_result_post.action
        _trace_state = _loop_guard._traces.get(event.trace_id) if event.trace_id else None
        event.loop_cumulative_cost_usd = _trace_state.cumulative_cost_usd if _trace_state is not None else None
        if _loop_result_post.action == "raise":
            raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
        if _loop_result_post.action == "warn":
            _logger.warning("%s", _loop_result_post.message)
    # Cache store on success (sync non-stream)
    if _cache_key is not None and _response_cache is not None:
        _response_cache.put(_cache_key, CacheEntry(
            content=event.output_content,
            tool_calls=event.tool_calls_made,
            usage={"prompt_tokens": event.prompt_tokens or 0,
                   "completion_tokens": event.completion_tokens or 0,
                   "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0)},
            model=fallback_outcome.resolved_model or model,
            provider=fallback_outcome.resolved_provider or provider,
            ttl=_response_cache.ttl_for(fallback_outcome.resolved_model or model),
        ))
    return response


def _wrapped_stream(
    provider_fn: Any,
    event: CallEvent,
    queue: EventQueue,
    cfg: SDKConfig,
    start_ns: int,
    *,
    original_messages: list[dict[str, Any]],
    provider_messages: list[dict[str, Any]],
    telemetry_messages: list[dict[str, Any]],
    original_tools: list[dict[str, Any]] | None,
    provider_tools: list[dict[str, Any]] | None,
    telemetry_tools: list[dict[str, Any]] | None,
    provider_kwargs: dict[str, Any],
    retry_policy: RetryPolicy,
    fallback_chain: FallbackChain | None = None,
    kwargs: dict[str, Any] | None = None,
    estimated_prompt_tokens: int = 0,
    cache_key: str | None = None,
    budget_result: Any = None,
    timeout: float | None = None,
    stream_chunk_timeout: float | None = None,
) -> Iterator[Any]:
    """Yield stream chunks while capturing all events."""
    accumulated_content = ""
    accumulated_tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None
    _last_retry_outcome_stream: list[RetryOutcome] = []

    _fallback_executor_stream = FallbackExecutor(
        chain=fallback_chain,
        registry=_model_health_registry,
        verbose=cfg.verbose,
        circuit_breaker_failure_threshold=cfg.circuit_breaker_failure_threshold,
        circuit_breaker_reset_timeout_seconds=cfg.circuit_breaker_reset_timeout_seconds,
    )

    def _create_stream(try_model: str, try_provider: str, _idx: int = 0) -> Any:
        retry_outcome = RetryOutcome()
        _last_retry_outcome_stream[:] = [retry_outcome]
        try_fn_kwargs = dict(kwargs) if kwargs else {}
        try_provider_fn = _resolve_provider_fn(try_provider, try_fn_kwargs)
        try_provider_kwargs = _build_provider_kwargs(
            try_fn_kwargs, model=try_model, call_id=event.call_id, mode="stream",
        )

        # Inject timeout per model (user override or intelligent default)
        if _timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout

        # Rate limiter: wait for capacity before stream creation
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            _rate_limiter.acquire(
                rl_key,
                estimated_tokens=estimated_prompt_tokens,
                verbose=cfg.verbose,
            )

        def _inner_stream(
            _fn=try_provider_fn,
            _kw=try_provider_kwargs,
            _model=try_model,
        ) -> Any:
            pm, pt = _ensure_provider_payload_is_isolated(
                original_messages=original_messages,
                provider_messages=_copy_provider_messages(original_messages),
                telemetry_messages=telemetry_messages,
                original_tools=original_tools,
                provider_tools=_copy_provider_tools(original_tools),
                telemetry_tools=telemetry_tools,
                model=_model,
                call_id=event.call_id,
                mode="stream",
            )
            return _fn(
                model=_model, messages=pm, tools=pt,
                stream=True, **_kw,
            )

        stream_iter = retry_sync(
            _inner_stream,
            policy=retry_policy,
            classify_error=_classify_error,
            verbose=cfg.verbose,
            call_kwargs={},
            outcome=retry_outcome,
        )
        # Wrap with per-chunk timeout if configured
        if stream_chunk_timeout is not None and stream_chunk_timeout > 0:
            stream_iter = _timed_sync_iter(stream_iter, stream_chunk_timeout, TimeoutError("stream chunk timeout"))
        elif _timeout_manager is not None and cfg.timeout_enabled:
            chunk_t = _timeout_manager.stream_chunk_timeout
            if chunk_t > 0:
                stream_iter = _timed_sync_iter(stream_iter, chunk_t, TimeoutError("stream chunk timeout"))
        return stream_iter

    try:
        stream_iter, fallback_outcome = _fallback_executor_stream.execute_sync(
            primary_model=event.model,
            primary_provider=event.provider,
            call_fn=_create_stream,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        _finalize_call_error(event, exc, latency_ms, queue, cfg)
        raise

    fallback_outcome.merge_into_event(event)

    try:
        for chunk in stream_iter:
            # Accumulate content / tool calls from streamed chunks
            if hasattr(chunk, "choices"):
                for choice in chunk.choices:
                    delta = getattr(choice, "delta", None)
                    if delta:
                        if getattr(delta, "content", None):
                            accumulated_content += delta.content
                        if getattr(delta, "tool_calls", None):
                            for tc in delta.tool_calls:
                                accumulated_tool_calls.append(
                                    {
                                        "id": getattr(tc, "id", None),
                                        "type": getattr(tc, "type", "function"),
                                        "function": {
                                            "name": getattr(tc.function, "name", None)
                                            if hasattr(tc, "function")
                                            else None,
                                            "arguments": getattr(tc.function, "arguments", "")
                                            if hasattr(tc, "function")
                                            else "",
                                        },
                                    }
                                )
            # Capture usage if present in chunk (some providers send it in last chunk)
            if hasattr(chunk, "usage") and chunk.usage:
                usage = {
                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                    "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                }
            yield chunk

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        event.status = "success"
        event.latency_ms = latency_ms
        event.output_content = mask_text(accumulated_content) if accumulated_content else None
        _apply_loop_telemetry_from_output(event, event.output_content)
        event.tool_calls_made = (
            mask_value(accumulated_tool_calls) if accumulated_tool_calls else None
        )
        _apply_tool_lifecycle_telemetry(event)
        if usage:
            event.prompt_tokens = usage.get("prompt_tokens", 0)
            event.completion_tokens = usage.get("completion_tokens", 0)
        if _last_retry_outcome_stream:
            _merge_retry_metadata(event, _last_retry_outcome_stream[0])
        resolved = event.resolved_model or event.model
        _model_health_registry.record(resolved, latency_ms, success=True)
        # Adaptive timeout: feed observed latency (sync stream)
        if _timeout_manager is not None and cfg.timeout_enabled:
            _timeout_manager.record_latency(resolved, latency_ms / 1000.0)
        queue.enqueue(event)
        # Rate limiter: adjust token debt from actual stream usage (no headers available)
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(
                fallback_outcome.resolved_provider or event.provider,
                fallback_outcome.resolved_model or event.model,
            )
            actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            _rate_limiter.update_from_response(
                rl_key, None,
                actual_tokens=actual_tokens,
                estimated_tokens=estimated_prompt_tokens,
            )
        # Budget record after stream completes
        if _budget_tracker is not None and budget_result is not None:
            cost_breakdown = calculate_cost(
                model=event.resolved_model or event.model,
                prompt_tokens=event.prompt_tokens or 0,
                completion_tokens=event.completion_tokens or 0,
                reasoning_tokens=event.reasoning_tokens or 0,
                cache_creation_tokens=event.cache_creation_tokens or 0,
                cache_read_tokens=event.cache_read_tokens or 0,
                status="success",
            )
            event.actual_cost_usd = cost_breakdown["total_cost_usd"]
            _budget_tracker.record_spend(
                project=cfg.project,
                agent=event.agent_name,
                user=event.user_id,
                cost_usd=cost_breakdown["total_cost_usd"],
                window_keys=budget_result.window_keys,
            )
        # Loop guard: post-call check after stream completes
        if _loop_guard is not None and cfg.loop_guard_enabled:
            _loop_result_post = _loop_guard.check_post_call(
                trace_id=event.trace_id,
                output_content=event.output_content,
                provider=event.provider,
                model=event.resolved_model or event.model,
                actual_cost_usd=event.actual_cost_usd or 0.0,
                estimated_cost_usd=event.estimated_cost_usd or 0.0,
            )
            event.loop_action_taken = _loop_result_post.action
            if _loop_result_post.action == "raise":
                raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
            if _loop_result_post.action == "warn":
                _logger.warning("%s", _loop_result_post.message)
        # Cache store after stream completes
        if cache_key is not None and _response_cache is not None:
            _response_cache.put(cache_key, CacheEntry(
                content=event.output_content,
                tool_calls=event.tool_calls_made,
                usage={"prompt_tokens": event.prompt_tokens or 0,
                       "completion_tokens": event.completion_tokens or 0,
                       "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0)},
                model=event.resolved_model or event.model,
                provider=event.provider,
                ttl=_response_cache.ttl_for(event.resolved_model or event.model),
            ))

    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        if _last_retry_outcome_stream:
            _merge_retry_metadata(event, _last_retry_outcome_stream[0])
        if _classify_error(exc) == ErrorCode.TIMEOUT:
            event.timeout_triggered = True
        _finalize_call_error(event, exc, latency_ms, queue, cfg)
        raise


def _resolve_provider_fn(provider: str, kwargs: dict[str, Any]) -> Any:
    """
    Resolve the actual provider callable from kwargs or installed library.
    Accepts `_client` kwarg to use a pre-initialized provider client.
    """
    client = kwargs.pop("_client", None)
    if client is not None:
        # Assume OpenAI-compatible interface
        return client.chat.completions.create

    # Try to resolve from installed provider libraries
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
    await queue.enqueue(event)
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
    await queue.enqueue(event)
    _notify_event(event)
    _notify_error(event, exc)
    if cfg.verbose:
        print(
            f"[ZROKY] {event.error_code} detected in your last call. "
            f"fp={event.prompt_fingerprint}. Open dashboard for fix."
        )


def _apply_preflight_block_event(event: CallEvent, exc: ZrokyPreflightError) -> None:
    event.status = "blocked"
    event.latency_ms = 0.0
    event.error_code = exc.error_code
    event.error_message = mask_error_message(exc)
    event.failure_reason = mask_value(
        {
            "schema_version": "zroky.preflight_block.v1",
            "classification": exc.error_code,
            "message": str(exc),
            "preflight_warning_types": exc.warning_types,
            "preflight_warnings": exc.warnings,
        }
    )


def _finalize_preflight_blocked(
    event: CallEvent,
    exc: ZrokyPreflightError,
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


async def _finalize_preflight_blocked_async(
    event: CallEvent,
    exc: ZrokyPreflightError,
    queue: Any,
    cfg: SDKConfig,
) -> None:
    _apply_preflight_block_event(event, exc)
    await queue.enqueue(event)
    _notify_event(event)
    _notify_error(event, exc)
    if cfg.verbose:
        print(
            f"[ZROKY] {event.error_code} blocked before provider call. "
            f"fp={event.prompt_fingerprint}."
        )


def _extract_response_metadata(event: CallEvent, response: Any) -> None:
    """Extract token usage and tool calls from provider response object."""
    usage = getattr(response, "usage", None)
    if usage:
        event.prompt_tokens = getattr(usage, "prompt_tokens", 0) or getattr(
            usage, "input_tokens", 0
        )
        event.completion_tokens = getattr(usage, "completion_tokens", 0) or getattr(
            usage, "output_tokens", 0
        )
        # Reasoning tokens (o3 and similar)
        event.reasoning_tokens = getattr(
            getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0
        ) or 0
        # Cache tokens (Anthropic)
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        event.cache_creation_tokens = cache_creation
        event.cache_read_tokens = cache_read

    # Tool calls in response
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
                            "name": getattr(tc.function, "name", None)
                            if hasattr(tc, "function")
                            else None,
                            "arguments": getattr(tc.function, "arguments", "")
                            if hasattr(tc, "function")
                            else "",
                        },
                    }
                    for tc in tc_list
                ])
                _apply_tool_lifecycle_telemetry(event)
            event.output_content = mask_value(getattr(message, "content", None))
            _apply_loop_telemetry_from_output(event, event.output_content)


def _classify_error(exc: Exception) -> str:
    """Classify provider errors into standard error codes."""
    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    status_code = extract_status_code(exc)
    provider_code = str(getattr(exc, "code", "") or "").lower()
    provider_type = str(getattr(exc, "type", "") or "").lower()
    combined = " ".join(
        item
        for item in (
            msg,
            exc_type,
            provider_code,
            provider_type,
            str(status_code or ""),
        )
        if item
    )

    # Token overflow patterns
    if _validation.is_token_overflow_error_message(combined):
        return ErrorCode.TOKEN_OVERFLOW

    # Rate limit patterns (comprehensive)
    rate_limit_patterns = [
        "429",
        "rate limit",
        "rate_limit",
        "too many requests",
        "throttling",
        "quota exceeded",
        "capacity",
        "over quota",
        "limit exceeded",
        "requests per minute",
        "rpm limit",
        "tpm limit",
    ]
    if status_code == 429 or any(pattern in combined for pattern in rate_limit_patterns):
        return ErrorCode.RATE_LIMIT

    # Auth failure patterns (comprehensive)
    auth_patterns = [
        "401",
        "403",
        "invalid_api_key",
        "invalid api key",
        "authentication",
        "unauthorized",
        "access denied",
        "permission denied",
        "not authenticated",
        "invalid token",
        "expired token",
        "api key not found",
    ]
    auth_exception_types = ["authenticationerror", "permissionerror", "unauthorizederror"]
    if (
        status_code in {401, 403}
        or any(pattern in combined for pattern in auth_patterns)
        or any(t in exc_type for t in auth_exception_types)
    ):
        return ErrorCode.AUTH_FAILURE

    # Timeout patterns
    timeout_patterns = [
        "timeout",
        "timed out",
        "deadline exceeded",
        "read timeout",
        "connect timeout",
        "request timeout",
        "connection timeout",
    ]
    timeout_exception_types = ["timeouterror", "timeoutexception"]
    if (
        status_code in {408, 504}
        or any(pattern in combined for pattern in timeout_patterns)
        or any(t in exc_type for t in timeout_exception_types)
    ):
        return ErrorCode.TIMEOUT

    # Connection errors
    connection_patterns = [
        "connection error",
        "connecterror",
        "network error",
        "unreachable",
        "refused",
        "reset by peer",
        "broken pipe",
        "dns",
        "name resolution",
    ]
    if any(pattern in combined for pattern in connection_patterns):
        return ErrorCode.NETWORK_ERROR

    return ErrorCode.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# Public: record (manual capture path)
# ---------------------------------------------------------------------------

def record(
    *,
    provider: str,
    model: str,
    request: dict[str, Any],
    response: Any | None = None,
    error: Exception | None = None,
    latency_ms: float | None = None,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """
    Manually record a provider call that was made outside of zroky.call().
    Use when you have your own provider client and want to capture metadata.
    """
    cfg, queue = _ensure_init()

    messages = _copy_provider_messages(request.get("messages", []))
    tools = _copy_provider_tools(request.get("tools"))
    telemetry_messages = _build_telemetry_messages(messages, mask_pii=cfg.mask_pii)
    telemetry_tools = _build_telemetry_tools(tools, mask_pii=cfg.mask_pii)
    prompt_fingerprint = generate_prompt_fingerprint(
        messages=messages,
        tools=tools,
        model=model,
    )
    estimated_prompt_tokens = _estimate_prompt_tokens_for_telemetry(
        model=model,
        messages=messages,
    )
    model_context_telemetry = _model_context_limit_telemetry_for_model(model)
    model_context_limit = model_context_telemetry["model_context_limit"]
    token_estimator_version = _token_estimator_version_for_telemetry(
        estimated_prompt_tokens,
    )
    token_rules_version = _token_rules_version_for_telemetry()

    event = CallEvent(
        provider=provider,
        model=model,
        messages=telemetry_messages,
        tools=telemetry_tools,
        estimated_prompt_tokens=estimated_prompt_tokens,
        model_context_limit=model_context_limit,
        model_context_limit_source=(
            model_context_telemetry["model_context_limit_source"]
        ),
        model_context_limit_source_detail=(
            model_context_telemetry["model_context_limit_source_detail"]
        ),
        model_context_limit_confidence=(
            model_context_telemetry["model_context_limit_confidence"]
        ),
        model_context_limit_catalog_version=(
            model_context_telemetry["model_context_limit_catalog_version"]
        ),
        model_context_limit_catalog_updated_at=(
            model_context_telemetry["model_context_limit_catalog_updated_at"]
        ),
        model_context_limit_catalog_stale=(
            model_context_telemetry["model_context_limit_catalog_stale"]
        ),
        model_context_limit_catalog_stale_after_days=(
            model_context_telemetry["model_context_limit_catalog_stale_after_days"]
        ),
        token_estimator_version=token_estimator_version,
        token_rules_version=token_rules_version,
        call_type=CallType.TOOL_CALL if tools else CallType.CHAT,
        trace_id=trace_id,
        parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        prompt_fingerprint=prompt_fingerprint,
        user_id=user_id,
        latency_ms=latency_ms,
        retry_metadata=normalize_retry_metadata(request.get("retry_metadata")),
        tool_lifecycle_summary=summarize_tool_lifecycle(_record_tool_lifecycle(request)),
    )

    if error is not None:
        event.status = "failed"
        event.error_code = _classify_error(error)
        event.error_message = mask_error_message(error)
        event.failure_reason = build_failure_reason(error, error_code=event.error_code)
    elif response is not None:
        event.status = "success"
        _extract_response_metadata(event, response)
    else:
        event.status = "success"

    queue.enqueue(event)
    _notify_event(event)
    if error is not None:
        _notify_error(event, error)


# ---------------------------------------------------------------------------
# Public: trace decorator
# ---------------------------------------------------------------------------

def trace(_fn: Any = None, *, name: str | None = None) -> Any:
    """
    Decorator to capture any function that makes AI provider calls.

    @zroky.trace
    def ask_ai(prompt: str):
        return client.chat.completions.create(...)
    """
    def decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cfg, queue = _ensure_init()
            fn_name = name or fn.__name__
            start_ns = time.perf_counter_ns()
            exc_to_raise: Exception | None = None
            result: Any = None

            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:
                exc_to_raise = exc
                raise
            finally:
                latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
                event = CallEvent(
                    provider="unknown",
                    model="unknown",
                    messages=[],
                    call_type=CallType.CHAT,
                    agent_name=_get_agent() or cfg.default_agent or fn_name,
                    latency_ms=latency_ms,
                    status="failed" if exc_to_raise else "success",
                )
                if exc_to_raise:
                    event.error_code = _classify_error(exc_to_raise)
                    event.error_message = mask_error_message(exc_to_raise)
                    event.failure_reason = build_failure_reason(
                        exc_to_raise,
                        error_code=event.error_code,
                    )
                elif result is not None:
                    _extract_response_metadata(event, result)
                queue.enqueue(event)

        return wrapper

    if _fn is not None:
        return decorator(_fn)
    return decorator


# ---------------------------------------------------------------------------
# Public: agent context manager
# ---------------------------------------------------------------------------

@contextmanager
def agent(name: str) -> Generator[None, None, None]:
    """
    Context manager that tags all ZROKY-captured calls within the block
    with the given agent name.

    with zroky.agent("research-agent"):
        out = client.chat.completions.create(...)
    """
    previous = getattr(_local, "agent_name", None)
    _local.agent_name = name
    try:
        yield
    finally:
        _local.agent_name = previous


# ---------------------------------------------------------------------------
# Public: flush / shutdown
# ---------------------------------------------------------------------------

def flush() -> None:
    """Force flush all pending events to the ingest API. Blocks until done."""
    if _queue is not None:
        _queue.flush(timeout=10.0)


def shutdown() -> None:
    """Flush and stop the background queue worker. Call at process exit."""
    global _response_cache, _budget_tracker, _loop_guard, _timeout_manager
    if _queue is not None:
        _queue.shutdown()
    if _response_cache is not None:
        _response_cache.close()
        _response_cache = None
    if _budget_tracker is not None:
        _budget_tracker.close()
        _budget_tracker = None
    if _loop_guard is not None:
        _loop_guard = None
    if _timeout_manager is not None:
        _timeout_manager = None


# ---------------------------------------------------------------------------
# Public: metrics callbacks
# ---------------------------------------------------------------------------

def on_event(callback: Callable[["CallEvent"], None]) -> None:
    """
    Register a callback to be called for every captured event.

    Example:
        def my_handler(event):
            print(f"Captured: {event.provider}/{event.model}")

        zroky.on_event(my_handler)
    """
    register_event_callback(callback)


def on_error(callback: Callable[["CallEvent", Exception], None]) -> None:
    """
    Register a callback to be called when an error is captured.

    Example:
        def my_handler(event, exc):
            if event.error_code == "RATE_LIMIT":
                alert_ops_team("Rate limit hit!")

        zroky.on_error(my_handler)
    """
    register_error_callback(callback)


def on_flush(callback: Callable[[int, int], None]) -> None:
    """
    Register a callback to be called after batch flush.

    The callback receives (success_count, fail_count).

    Example:
        def my_handler(success, fail):
            metrics.gauge("zroky.flush.success", success)

        zroky.on_flush(my_handler)
    """
    register_flush_callback(callback)


# ---------------------------------------------------------------------------
# Async support
# ---------------------------------------------------------------------------

_async_queue: "AsyncEventQueue | None" = None
_async_lock = threading.Lock()


async def ainit(
    *,
    api_key: str | None = None,
    project: str | None = None,
    mode: str | None = None,
    mask_pii: bool | None = None,
    ingest_url: str | None = None,
    validate_preflight: bool | None = None,
    validate_preflight_sample_rate: float | None = None,
    preflight_blocking_warning_types: list[str] | tuple[str, ...] | None = None,
    retry_max_retries: int | None = None,
    retry_base_backoff_seconds: float | None = None,
    retry_max_backoff_seconds: float | None = None,
    fallback_models: list[str] | tuple[str, ...] | None = None,
    fallback_max: int | None = None,
    fallback_adaptive: bool | None = None,
    circuit_breaker_failure_threshold: int | None = None,
    circuit_breaker_reset_timeout_seconds: float | None = None,
    rate_limits: dict[str, dict[str, int]] | None = None,
    rate_limit_enabled: bool | None = None,
    cache_enabled: bool | None = None,
    cache_default_ttl: float | None = None,
    cache_max_memory: int | None = None,
    cache_db_path: str | None = None,
    cache_ttl_overrides: dict[str, float] | None = None,
    budget_enabled: bool | None = None,
    budget_db_path: str | None = None,
    budget_default_rate: float | None = None,
    budget_rules: dict[str, dict[str, dict[str, dict[str, Any]]]] | None = None,
    loop_guard_enabled: bool | None = None,
    loop_guard_max_calls_per_trace: int | None = None,
    loop_guard_max_repeated_outputs: int | None = None,
    loop_guard_max_cost_per_trace_usd: float | None = None,
    loop_guard_action: str | None = None,
    timeout_enabled: bool | None = None,
    timeout_stream_chunk_seconds: float | None = None,
    default_timeout: float | None = None,
) -> None:
    """
    Async version of init(). Initialize the ZROKY SDK for asyncio applications.

    Use this instead of init() when working with async/await code.
    """
    global _async_queue, _config

    if not _ASYNC_AVAILABLE:
        raise RuntimeError(
            "Async support requires asyncio. "
            "Install with: pip install zroky[async]"
        )

    with _async_lock:
        cfg = load_config(
            api_key=api_key,
            project=project,
            mode=mode,
            mask_pii=mask_pii,
            ingest_url=ingest_url,
            validate_preflight=validate_preflight,
            validate_preflight_sample_rate=validate_preflight_sample_rate,
            preflight_blocking_warning_types=preflight_blocking_warning_types,
            retry_max_retries=retry_max_retries,
            retry_base_backoff_seconds=retry_base_backoff_seconds,
            retry_max_backoff_seconds=retry_max_backoff_seconds,
            fallback_models=fallback_models,
            fallback_max=fallback_max,
            fallback_adaptive=fallback_adaptive,
            circuit_breaker_failure_threshold=circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout_seconds=circuit_breaker_reset_timeout_seconds,
            rate_limits=rate_limits,
            rate_limit_enabled=rate_limit_enabled,
            cache_enabled=cache_enabled,
            cache_default_ttl=cache_default_ttl,
            cache_max_memory=cache_max_memory,
            cache_db_path=cache_db_path,
            cache_ttl_overrides=cache_ttl_overrides,
            budget_enabled=budget_enabled,
            budget_db_path=budget_db_path,
            budget_default_rate=budget_default_rate,
            budget_rules=budget_rules,
            loop_guard_enabled=loop_guard_enabled,
            loop_guard_max_calls_per_trace=loop_guard_max_calls_per_trace,
            loop_guard_max_repeated_outputs=loop_guard_max_repeated_outputs,
            loop_guard_max_cost_per_trace_usd=loop_guard_max_cost_per_trace_usd,
            loop_guard_action=loop_guard_action,
            timeout_enabled=timeout_enabled,
            timeout_stream_chunk_seconds=timeout_stream_chunk_seconds,
            default_timeout=default_timeout,
        )

        from zroky._internal.async_queue import AsyncEventQueue  # noqa: PLC0415
        q = AsyncEventQueue(config=cfg)
        await q.start()
        _async_queue = q
        _config = cfg

    # Configure rate limiter from explicit limits
    if cfg.rate_limit_enabled and cfg.rate_limits:
        _rate_limiter.configure_all(cfg.rate_limits)

    # Configure response cache
    if cfg.cache_enabled:
        global _response_cache
        _response_cache = ResponseCache(
            max_memory=cfg.cache_max_memory,
            default_ttl=cfg.cache_default_ttl,
            db_path=cfg.cache_db_path,
            ttl_overrides=cfg.cache_ttl_overrides,
        )
    else:
        _response_cache = None

    # Configure budget tracker
    global _budget_tracker
    if cfg.budget_enabled:
        _budget_tracker = BudgetTracker(
            db_path=cfg.budget_db_path,
            default_rate_per_1m_tokens=cfg.budget_default_rate,
            rules=cfg.budget_rules,
        )
    else:
        _budget_tracker = None

    # Configure loop guard
    global _loop_guard
    if cfg.loop_guard_enabled:
        _loop_guard = LoopGuard(
            max_calls_per_trace=cfg.loop_guard_max_calls_per_trace,
            max_repeated_outputs=cfg.loop_guard_max_repeated_outputs,
            max_cost_per_trace_usd=cfg.loop_guard_max_cost_per_trace_usd,
            default_action=cfg.loop_guard_action,
        )
    else:
        _loop_guard = None

    # Configure timeout manager
    global _timeout_manager
    if cfg.timeout_enabled:
        _timeout_manager = TimeoutManager(
            stream_chunk_timeout=cfg.timeout_stream_chunk_seconds,
            default_timeout=cfg.default_timeout,
        )
    else:
        _timeout_manager = None

    _print_init_banner(cfg)


async def acall(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    user_id: str | None = None,
    max_retries: int | None = None,
    fallback: list[str] | None = None,
    no_cache: bool = False,
    timeout: float | None = None,
    stream_chunk_timeout: float | None = None,
    # Pass-through kwargs forwarded to provider
    **kwargs: Any,
) -> Any:
    """
    Async version of call(). Make a tracked provider call in async context.

    This is the async equivalent of zroky.call() for use with async providers
    or in async applications.
    """
    if _async_queue is None:
        # Auto-init from environment
        await ainit()

    cfg = _config or load_config()
    queue = _async_queue  # type: ignore[union-attr]

    original_messages = _copy_provider_messages(messages)
    original_tools = _copy_provider_tools(tools)
    provider_messages = _copy_provider_messages(original_messages)
    provider_tools = _copy_provider_tools(original_tools)
    telemetry_messages = _build_telemetry_messages(original_messages, mask_pii=cfg.mask_pii)
    telemetry_tools = _build_telemetry_tools(original_tools, mask_pii=cfg.mask_pii)

    call_type = CallType.TOOL_CALL if tools else CallType.CHAT
    prompt_fingerprint = generate_prompt_fingerprint(
        messages=original_messages,
        tools=original_tools,
        model=model,
    )
    estimated_prompt_tokens = _estimate_prompt_tokens_for_telemetry(
        model=model,
        messages=original_messages,
    )
    model_context_telemetry = _model_context_limit_telemetry_for_model(model)
    model_context_limit = model_context_telemetry["model_context_limit"]
    token_estimator_version = _token_estimator_version_for_telemetry(
        estimated_prompt_tokens,
    )
    token_rules_version = _token_rules_version_for_telemetry()

    event = CallEvent(
        provider=provider,
        model=model,
        messages=telemetry_messages,
        tools=telemetry_tools,
        estimated_prompt_tokens=estimated_prompt_tokens,
        model_context_limit=model_context_limit,
        model_context_limit_source=(
            model_context_telemetry["model_context_limit_source"]
        ),
        model_context_limit_source_detail=(
            model_context_telemetry["model_context_limit_source_detail"]
        ),
        model_context_limit_confidence=(
            model_context_telemetry["model_context_limit_confidence"]
        ),
        model_context_limit_catalog_version=(
            model_context_telemetry["model_context_limit_catalog_version"]
        ),
        model_context_limit_catalog_updated_at=(
            model_context_telemetry["model_context_limit_catalog_updated_at"]
        ),
        model_context_limit_catalog_stale=(
            model_context_telemetry["model_context_limit_catalog_stale"]
        ),
        model_context_limit_catalog_stale_after_days=(
            model_context_telemetry["model_context_limit_catalog_stale_after_days"]
        ),
        token_estimator_version=token_estimator_version,
        token_rules_version=token_rules_version,
        call_type=call_type,
        trace_id=trace_id,
        parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        prompt_fingerprint=prompt_fingerprint,
        user_id=user_id,
        retry_metadata=_private_retry_metadata(kwargs),
        tool_lifecycle_summary=_private_tool_lifecycle(kwargs),
    )

    # --- Cache check (before preflight, retry, fallback, rate-limit) ---
    _cache_key: str | None = None
    if _response_cache is not None and not no_cache:
        _cache_key = build_cache_key(prompt_fingerprint)
        cached_entry = _response_cache.get(_cache_key)
        if cached_entry is not None:
            event.cache_hit = True
            event.status = "success"
            event.latency_ms = 0.0
            if cached_entry.usage:
                event.prompt_tokens = cached_entry.usage.get("prompt_tokens", 0)
                event.completion_tokens = cached_entry.usage.get("completion_tokens", 0)
            event.output_content = mask_text(cached_entry.content) if cached_entry.content else None
            _apply_loop_telemetry_from_output(event, event.output_content)
            if cached_entry.tool_calls:
                event.tool_calls_made = mask_value(cached_entry.tool_calls)
                _apply_tool_lifecycle_telemetry(event)
            await queue.enqueue(event)
            _notify_event(event)
            if cfg.verbose:
                print(f"[ZROKY] Cache HIT: {provider}/{model} — fp={prompt_fingerprint[:12]}")
            if stream:
                return cached_stream_iter_async(cached_entry)
            return CachedResponse(cached_entry)

    # --- Budget check (after cache, before preflight / rate-limit) ---
    _budget_result = None
    if _budget_tracker is not None:
        _budget_result = _budget_tracker.check(
            project=cfg.project,
            agent=_get_agent() or cfg.default_agent,
            user=user_id,
            model=model,
            prompt_tokens=estimated_prompt_tokens or 0,
        )
        event.estimated_cost_usd = _budget_result.estimated_cost_usd
        event.budget_remaining_usd = _budget_result.remaining_usd
        event.budget_action_taken = _budget_result.action
        if _budget_result.action == "hard_block":
            raise BudgetExceededError(_budget_result.message)
        if _budget_result.action in ("warn", "soft_block"):
            _logger.warning("%s", _budget_result.message)

    # Loop guard: pre-call check
    _loop_result_pre = None
    if _loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_pre = _loop_guard.check_pre_call(
            trace_id=event.trace_id,
            estimated_cost_usd=event.estimated_cost_usd or 0.0,
        )
        if _loop_result_pre.action == "raise":
            raise LoopDetectedError(_loop_result_pre.message, _loop_result_pre.loop_type)
        if _loop_result_pre.action == "warn":
            _logger.warning("%s", _loop_result_pre.message)
        if _loop_result_pre.action == "return_cached":
            cached = _loop_guard.get_last_good_response(event.trace_id)
            if cached is not None:
                event.status = "loop_guarded"
                event.output_content = cached
                event.loop_action_taken = "return_cached"
                await queue.enqueue(event)
                _notify_event(event)
                return _build_synthetic_response(cached, provider, model)

    try:
        _run_preflight_validation(
            cfg=cfg,
            provider=provider,
            model=model,
            messages=deepcopy(original_messages),
            tools=deepcopy(original_tools),
            sample_key=f"{provider}|{model}|{prompt_fingerprint}",
            kwargs=kwargs,
        )
    except ZrokyPreflightError as exc:
        await _finalize_preflight_blocked_async(event, exc, queue, cfg)
        raise

    provider_fn_kwargs = dict(kwargs)
    provider_fn = _resolve_provider_fn(provider, provider_fn_kwargs)
    call_mode = "stream" if stream else "non-stream"
    provider_kwargs = _build_provider_kwargs(
        provider_fn_kwargs,
        model=model,
        call_id=event.call_id,
        mode=call_mode,
    )
    start_ns = time.perf_counter_ns()

    retry_policy = _build_retry_policy(cfg, max_retries)
    effective_fallback = _effective_fallback_models(cfg, fallback)
    fallback_chain = build_chain(
        primary_provider=provider,
        primary_model=model,
        fallback=effective_fallback,
        adaptive=cfg.fallback_adaptive,
        max_fallbacks=cfg.fallback_max,
    )
    event.fallback_chain = fallback_chain.models() if fallback_chain else None

    if stream:
        return _wrapped_stream_async(
            provider_fn,
            event,
            queue,
            cfg,
            start_ns,
            original_messages=original_messages,
            provider_messages=provider_messages,
            telemetry_messages=telemetry_messages,
            original_tools=original_tools,
            provider_tools=provider_tools,
            telemetry_tools=telemetry_tools,
            provider_kwargs=provider_kwargs,
            retry_policy=retry_policy,
            fallback_chain=fallback_chain,
            kwargs=kwargs,
            estimated_prompt_tokens=estimated_prompt_tokens or 0,
            budget_result=_budget_result,
            cache_key=_cache_key,
            timeout=timeout,
            stream_chunk_timeout=stream_chunk_timeout,
        )

    _fallback_executor_async = FallbackExecutor(
        chain=fallback_chain,
        registry=_model_health_registry,
        verbose=cfg.verbose,
        circuit_breaker_failure_threshold=cfg.circuit_breaker_failure_threshold,
        circuit_breaker_reset_timeout_seconds=cfg.circuit_breaker_reset_timeout_seconds,
    )

    _last_retry_outcome_async: list[RetryOutcome] = []

    async def _make_async_call(try_model: str, try_provider: str, _idx: int = 0) -> Any:
        retry_outcome = RetryOutcome()
        _last_retry_outcome_async[:] = [retry_outcome]
        try_fn_kwargs = dict(kwargs)
        try_provider_fn = _resolve_provider_fn(try_provider, try_fn_kwargs)
        try_provider_kwargs = _build_provider_kwargs(
            try_fn_kwargs, model=try_model, call_id=event.call_id, mode=call_mode,
        )

        # Inject timeout per model (user override or intelligent default)
        if _timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout

        # Rate limiter: async wait for capacity
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            await _rate_limiter.acquire_async(
                rl_key,
                estimated_tokens=estimated_prompt_tokens or 0,
                verbose=cfg.verbose,
            )

        async def _inner_async_call(
            target_model: str = try_model,
            target_fn: Any = try_provider_fn,
            target_kwargs: dict[str, Any] = try_provider_kwargs,
        ) -> Any:
            pm, pt = _ensure_provider_payload_is_isolated(
                original_messages=original_messages,
                provider_messages=_copy_provider_messages(original_messages),
                telemetry_messages=telemetry_messages,
                original_tools=original_tools,
                provider_tools=_copy_provider_tools(original_tools),
                telemetry_tools=telemetry_tools,
                model=target_model,
                call_id=event.call_id,
                mode=call_mode,
            )
            if asyncio.iscoroutinefunction(target_fn):
                return await target_fn(
                    model=target_model, messages=pm, tools=pt, **target_kwargs,
                )
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: target_fn(
                    model=target_model, messages=pm, tools=pt, **target_kwargs,
                )
            )

        return await retry_async(
            _inner_async_call,
            policy=retry_policy,
            classify_error=_classify_error,
            verbose=cfg.verbose,
            call_kwargs={},
            outcome=retry_outcome,
        )

    try:
        response, fallback_outcome = await _fallback_executor_async.execute_async(
            primary_model=model,
            primary_provider=provider,
            call_fn=_make_async_call,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        await _finalize_call_error_async(event, exc, latency_ms, queue, cfg)
        raise

    latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
    fallback_outcome.merge_into_event(event)
    if _last_retry_outcome_async:
        _merge_retry_metadata(event, _last_retry_outcome_async[0])
    await _finalize_call_async(event, response, latency_ms, queue, cfg)
    _model_health_registry.record(
        fallback_outcome.resolved_model or model, latency_ms, success=True,
    )
    # Adaptive timeout: feed observed latency (async non-stream)
    if _timeout_manager is not None and cfg.timeout_enabled:
        _timeout_manager.record_latency(
            fallback_outcome.resolved_model or model, latency_ms / 1000.0,
        )
    # Rate limiter: learn from response headers & actual usage
    if cfg.rate_limit_enabled:
        rl_key = rate_limit_key(
            fallback_outcome.resolved_provider or provider,
            fallback_outcome.resolved_model or model,
        )
        actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
        _rate_limiter.update_from_response(
            rl_key, response,
            actual_tokens=actual_tokens,
            estimated_tokens=estimated_prompt_tokens or 0,
        )
    # Budget record on success (async non-stream)
    if _budget_tracker is not None and _budget_result is not None:
        cost_breakdown = calculate_cost(
            model=event.resolved_model or event.model,
            prompt_tokens=event.prompt_tokens or 0,
            completion_tokens=event.completion_tokens or 0,
            reasoning_tokens=event.reasoning_tokens or 0,
            cache_creation_tokens=event.cache_creation_tokens or 0,
            cache_read_tokens=event.cache_read_tokens or 0,
            status="success",
        )
        event.actual_cost_usd = cost_breakdown["total_cost_usd"]
        _budget_tracker.record_spend(
            project=cfg.project,
            agent=event.agent_name or cfg.default_agent,
            user=event.user_id,
            cost_usd=cost_breakdown["total_cost_usd"],
            window_keys=_budget_result.window_keys,
        )
    # Loop guard: post-call check
    if _loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_post = _loop_guard.check_post_call(
            trace_id=event.trace_id,
            output_content=event.output_content,
            provider=event.provider,
            model=event.resolved_model or event.model,
            actual_cost_usd=event.actual_cost_usd or 0.0,
            estimated_cost_usd=event.estimated_cost_usd or 0.0,
        )
        event.loop_action_taken = _loop_result_post.action
        if _loop_result_post.action == "raise":
            raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
        if _loop_result_post.action == "warn":
            _logger.warning("%s", _loop_result_post.message)
    # Cache store on success (async non-stream)
    if _cache_key is not None and _response_cache is not None:
        _response_cache.put(_cache_key, CacheEntry(
            content=event.output_content,
            tool_calls=event.tool_calls_made,
            usage={"prompt_tokens": event.prompt_tokens or 0,
                   "completion_tokens": event.completion_tokens or 0,
                   "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0)},
            model=fallback_outcome.resolved_model or model,
            provider=fallback_outcome.resolved_provider or provider,
            ttl=_response_cache.ttl_for(fallback_outcome.resolved_model or model),
        ))
    return response


async def _wrapped_stream_async(
    provider_fn: Any,
    event: CallEvent,
    queue: "AsyncEventQueue",
    cfg: SDKConfig,
    start_ns: int,
    *,
    original_messages: list[dict[str, Any]],
    provider_messages: list[dict[str, Any]],
    telemetry_messages: list[dict[str, Any]],
    original_tools: list[dict[str, Any]] | None,
    provider_tools: list[dict[str, Any]] | None,
    telemetry_tools: list[dict[str, Any]] | None,
    provider_kwargs: dict[str, Any],
    retry_policy: RetryPolicy,
    fallback_chain: FallbackChain | None = None,
    kwargs: dict[str, Any] | None = None,
    estimated_prompt_tokens: int = 0,
    cache_key: str | None = None,
    budget_result: Any = None,
    timeout: float | None = None,
    stream_chunk_timeout: float | None = None,
) -> Any:
    """Async version of stream wrapper."""
    accumulated_content = ""
    accumulated_tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None

    _fallback_executor_stream_async = FallbackExecutor(
        chain=fallback_chain,
        registry=_model_health_registry,
        verbose=cfg.verbose,
        circuit_breaker_failure_threshold=cfg.circuit_breaker_failure_threshold,
        circuit_breaker_reset_timeout_seconds=cfg.circuit_breaker_reset_timeout_seconds,
    )

    _last_retry_outcome_stream_async: list[RetryOutcome] = []

    async def _create_stream_async(try_model: str, try_provider: str, _idx: int = 0) -> Any:
        retry_outcome = RetryOutcome()
        _last_retry_outcome_stream_async[:] = [retry_outcome]
        try_fn_kwargs = dict(kwargs) if kwargs else {}
        try_provider_fn = _resolve_provider_fn(try_provider, try_fn_kwargs)
        try_provider_kwargs = _build_provider_kwargs(
            try_fn_kwargs, model=try_model, call_id=event.call_id, mode="stream",
        )

        # Inject timeout per model (user override or intelligent default)
        if _timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout

        # Rate limiter: async wait for capacity before stream creation
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            await _rate_limiter.acquire_async(
                rl_key,
                estimated_tokens=estimated_prompt_tokens,
                verbose=cfg.verbose,
            )

        async def _inner_stream(
            _fn=try_provider_fn,
            _kw=try_provider_kwargs,
            _model=try_model,
        ) -> Any:
            pm, pt = _ensure_provider_payload_is_isolated(
                original_messages=original_messages,
                provider_messages=_copy_provider_messages(original_messages),
                telemetry_messages=telemetry_messages,
                original_tools=original_tools,
                provider_tools=_copy_provider_tools(original_tools),
                telemetry_tools=telemetry_tools,
                model=_model,
                call_id=event.call_id,
                mode="stream",
            )
            if asyncio.iscoroutinefunction(_fn):
                return await _fn(
                    model=_model, messages=pm, tools=pt,
                    stream=True, **_kw,
                )
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: _fn(
                    model=_model, messages=pm, tools=pt,
                    stream=True, **_kw,
                )
            )

        stream_iter = await retry_async(
            _inner_stream,
            policy=retry_policy,
            classify_error=_classify_error,
            verbose=cfg.verbose,
            call_kwargs={},
            outcome=retry_outcome,
        )
        # Wrap with per-chunk timeout if configured
        if stream_chunk_timeout is not None and stream_chunk_timeout > 0:
            stream_iter = _timed_async_iter(stream_iter, stream_chunk_timeout, TimeoutError("stream chunk timeout"))
        elif _timeout_manager is not None and cfg.timeout_enabled:
            chunk_t = _timeout_manager.stream_chunk_timeout
            if chunk_t > 0:
                stream_iter = _timed_async_iter(stream_iter, chunk_t, TimeoutError("stream chunk timeout"))
        return stream_iter

    try:
        stream_iter, fallback_outcome = await _fallback_executor_stream_async.execute_async(
            primary_model=event.model,
            primary_provider=event.provider,
            call_fn=_create_stream_async,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        await _finalize_call_error_async(event, exc, latency_ms, queue, cfg)
        raise

    fallback_outcome.merge_into_event(event)

    try:
        async for chunk in _async_iterable(stream_iter):
            # Accumulate content / tool calls from streamed chunks
            if hasattr(chunk, "choices"):
                for choice in chunk.choices:
                    delta = getattr(choice, "delta", None)
                    if delta:
                        if getattr(delta, "content", None):
                            accumulated_content += delta.content
                        if getattr(delta, "tool_calls", None):
                            for tc in delta.tool_calls:
                                accumulated_tool_calls.append(
                                    {
                                        "id": getattr(tc, "id", None),
                                        "type": getattr(tc, "type", "function"),
                                        "function": {
                                            "name": getattr(tc.function, "name", None)
                                            if hasattr(tc, "function")
                                            else None,
                                            "arguments": getattr(tc.function, "arguments", "")
                                            if hasattr(tc, "function")
                                            else "",
                                        },
                                    }
                                )
            # Capture usage if present in chunk
            if hasattr(chunk, "usage") and chunk.usage:
                usage = {
                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                    "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                }
            yield chunk

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        event.status = "success"
        event.latency_ms = latency_ms
        event.output_content = mask_text(accumulated_content) if accumulated_content else None
        _apply_loop_telemetry_from_output(event, event.output_content)
        event.tool_calls_made = (
            mask_value(accumulated_tool_calls) if accumulated_tool_calls else None
        )
        _apply_tool_lifecycle_telemetry(event)
        if usage:
            event.prompt_tokens = usage.get("prompt_tokens", 0)
            event.completion_tokens = usage.get("completion_tokens", 0)
        if _last_retry_outcome_stream_async:
            _merge_retry_metadata(event, _last_retry_outcome_stream_async[0])
        resolved = event.resolved_model or event.model
        _model_health_registry.record(resolved, latency_ms, success=True)
        # Adaptive timeout: feed observed latency (async stream)
        if _timeout_manager is not None and cfg.timeout_enabled:
            _timeout_manager.record_latency(resolved, latency_ms / 1000.0)
        await queue.enqueue(event)
        # Rate limiter: adjust token debt from actual stream usage (no headers available)
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(
                fallback_outcome.resolved_provider or event.provider,
                fallback_outcome.resolved_model or event.model,
            )
            actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            _rate_limiter.update_from_response(
                rl_key, None,
                actual_tokens=actual_tokens,
                estimated_tokens=estimated_prompt_tokens,
            )
        # Budget record after async stream completes
        if _budget_tracker is not None and budget_result is not None:
            cost_breakdown = calculate_cost(
                model=event.resolved_model or event.model,
                prompt_tokens=event.prompt_tokens or 0,
                completion_tokens=event.completion_tokens or 0,
                reasoning_tokens=event.reasoning_tokens or 0,
                cache_creation_tokens=event.cache_creation_tokens or 0,
                cache_read_tokens=event.cache_read_tokens or 0,
                status="success",
            )
            event.actual_cost_usd = cost_breakdown["total_cost_usd"]
            _budget_tracker.record_spend(
                project=cfg.project,
                agent=event.agent_name,
                user=event.user_id,
                cost_usd=cost_breakdown["total_cost_usd"],
                window_keys=budget_result.window_keys,
            )
        # Loop guard: post-call check after stream completes
        if _loop_guard is not None and cfg.loop_guard_enabled:
            _loop_result_post = _loop_guard.check_post_call(
                trace_id=event.trace_id,
                output_content=event.output_content,
                provider=event.provider,
                model=event.resolved_model or event.model,
                actual_cost_usd=event.actual_cost_usd or 0.0,
                estimated_cost_usd=event.estimated_cost_usd or 0.0,
            )
            event.loop_action_taken = _loop_result_post.action
            if _loop_result_post.action == "raise":
                raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
            if _loop_result_post.action == "warn":
                _logger.warning("%s", _loop_result_post.message)
        # Cache store after stream completes
        if cache_key is not None and _response_cache is not None:
            _response_cache.put(cache_key, CacheEntry(
                content=event.output_content,
                tool_calls=event.tool_calls_made,
                usage={"prompt_tokens": event.prompt_tokens or 0,
                       "completion_tokens": event.completion_tokens or 0,
                       "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0)},
                model=event.resolved_model or event.model,
                provider=event.provider,
                ttl=_response_cache.ttl_for(event.resolved_model or event.model),
            ))

    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        if _last_retry_outcome_stream_async:
            _merge_retry_metadata(event, _last_retry_outcome_stream_async[0])
        if _classify_error(exc) == ErrorCode.TIMEOUT:
            event.timeout_triggered = True
        await _finalize_call_error_async(event, exc, latency_ms, queue, cfg)
        raise


async def _async_iterable(iterable: Any) -> Any:
    """Convert sync iterable to async iterable."""
    if hasattr(iterable, '__aiter__'):
        async for item in iterable:
            yield item
    else:
        for item in iterable:
            yield item


async def aflush() -> None:
    """Async version of flush()."""
    if _async_queue is not None:
        await _async_queue.flush(timeout=10.0)


async def ashutdown() -> None:
    """Async version of shutdown()."""
    global _async_queue, _response_cache, _budget_tracker, _loop_guard, _timeout_manager
    if _async_queue is not None:
        await _async_queue.shutdown()
        _async_queue = None
    if _response_cache is not None:
        _response_cache.close()
        _response_cache = None
    if _budget_tracker is not None:
        _budget_tracker.close()
        _budget_tracker = None
    if _loop_guard is not None:
        _loop_guard = None
    if _timeout_manager is not None:
        _timeout_manager = None
