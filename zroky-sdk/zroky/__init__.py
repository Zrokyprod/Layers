# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
ZROKY Python SDK
Production AI diagnosis engine — capture, diagnose, fix.

This file is the thin public surface of the SDK.  Heavy implementation is
split across:
  _telemetry.py  — pure helpers, PII masking, event finalization
  preflight.py   — pre-execution validation
  _call.py       — call(), record(), trace(), agent()
  _streaming.py  — _wrapped_stream() for sync streaming
  _async.py      — ainit(), acall(), aflush(), ashutdown()
  _globals.py    — stub (see module docstring)
  _errors.py     — ZrokyPreflightError
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from zroky._internal.config import SDKConfig, load_config
from zroky._internal.budget import BudgetTracker
from zroky._internal.cache import ResponseCache
from zroky._internal.fallback import ModelHealthRegistry
from zroky._internal.loop_guard import LoopGuard
from zroky._internal.metrics import (
    register_error_callback,
    register_event_callback,
    register_flush_callback,
    unregister_error_callback,
    unregister_event_callback,
    unregister_flush_callback,
)
from zroky._internal.models import CallEvent
from zroky._internal.queue import EventQueue
from zroky._internal.rate_limiter import RateLimiter
from zroky._internal.timeout_manager import TimeoutManager
from zroky._internal import validation as _validation  # noqa: F401

# Re-export errors so callers can do: from zroky import ZrokyPreflightError
from zroky._errors import (  # noqa: F401
    ZrokyPreflightError,
    ZrokyRuntimePolicyBlocked,
    ZrokyRuntimePolicyError,
)

# Re-export call-surface from _call.py
from zroky._call import (  # noqa: F401
    agent,
    call,
    capture_handoff,
    capture_memory,
    capture_policy_decision,
    capture_retrieval,
    capture_tool_call,
    record,
    trace,
    trace_run,
)

from zroky._runtime_policy import check_runtime_policy  # noqa: F401

# Re-export outcome() — Cost-of-Failure Attribution
from zroky._outcome import outcome  # noqa: F401

# Re-export async surface from _async.py
from zroky._async import acall, aflush, ainit, ashutdown  # noqa: F401

# Re-export preflight public API from preflight.py
from zroky.preflight import (  # noqa: F401
    _is_preflight_sampled_in,
    check_rate_limit_risk,
    check_token_overflow,
    estimate_tokens,
    model_context_limit_resolution,
    print_validation,
    validate,
)

# Re-export internal exception types
from zroky._internal.budget import BudgetExceededError  # noqa: F401
from zroky._internal.loop_guard import LoopDetectedError  # noqa: F401
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint  # noqa: F401

# ---------------------------------------------------------------------------
# Backward-compat aliases for mutable test-fixture state
# (test conftest calls .clear() on these — they are the SAME objects as in
#  the submodules, so clear() propagates correctly)
# ---------------------------------------------------------------------------
from zroky._telemetry import (  # noqa: F401
    _classify_error,
    _build_provider_kwargs,
    _ensure_provider_payload_is_isolated,
    _get_agent,
    _local,
    _payload_guard_logged_call_ids,
    _payload_guard_log_order,
)
from zroky.preflight import _recent_preflight_calls  # noqa: F401

_ASYNC_AVAILABLE = True

# ---------------------------------------------------------------------------
# Module-level mutable state
# All submodules access these via lazy `import zroky as _z` to stay in sync
# when tests replace them directly (e.g. zroky._model_health_registry = ...)
# ---------------------------------------------------------------------------

_config: SDKConfig | None = None
_queue: EventQueue | None = None
_lock = threading.Lock()
_async_queue: Any = None
_async_lock = threading.Lock()

_model_health_registry: ModelHealthRegistry = ModelHealthRegistry()
_rate_limiter: RateLimiter = RateLimiter()

_response_cache: ResponseCache | None = None
_budget_tracker: BudgetTracker | None = None
_loop_guard: LoopGuard | None = None
_timeout_manager: TimeoutManager | None = None


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
    agent_framework: str | None = None,
    session_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    prompt_version: str | None = None,
    environment: str | None = None,
    code_sha: str | None = None,
    deployment_id: str | None = None,
    model_version: str | None = None,
    tool_schema_version: str | None = None,
    rag_version: str | None = None,
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
    global _model_health_registry, _rate_limiter

    with _lock:
        if _queue is not None:
            _queue.shutdown()
            _queue = None
        if _response_cache is not None:
            _response_cache.close()
            _response_cache = None
        if _budget_tracker is not None:
            _budget_tracker.close()
            _budget_tracker = None
        _loop_guard = None
        _timeout_manager = None
        _model_health_registry = ModelHealthRegistry()
        _rate_limiter = RateLimiter()

        cfg = load_config(
            api_key=api_key, project=project, mode=mode, mask_pii=mask_pii,
            ingest_url=ingest_url, agent_framework=agent_framework,
            session_id=session_id, workflow_id=workflow_id,
            workflow_name=workflow_name, prompt_version=prompt_version,
            environment=environment, code_sha=code_sha,
            deployment_id=deployment_id, model_version=model_version,
            tool_schema_version=tool_schema_version, rag_version=rag_version,
            validate_preflight=validate_preflight,
            validate_preflight_sample_rate=validate_preflight_sample_rate,
            preflight_blocking_warning_types=preflight_blocking_warning_types,
            circuit_breaker_failure_threshold=circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout_seconds=circuit_breaker_reset_timeout_seconds,
            retry_max_retries=retry_max_retries,
            retry_base_backoff_seconds=retry_base_backoff_seconds,
            retry_max_backoff_seconds=retry_max_backoff_seconds,
            fallback_models=fallback_models, fallback_max=fallback_max,
            fallback_adaptive=fallback_adaptive,
            rate_limits=rate_limits, rate_limit_enabled=rate_limit_enabled,
            cache_enabled=cache_enabled, cache_default_ttl=cache_default_ttl,
            cache_max_memory=cache_max_memory, cache_db_path=cache_db_path,
            cache_ttl_overrides=cache_ttl_overrides,
            budget_enabled=budget_enabled, budget_db_path=budget_db_path,
            budget_default_rate=budget_default_rate, budget_rules=budget_rules,
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
        q = EventQueue(config=cfg)
        q.start()
        _queue = q

    if cfg.rate_limit_enabled and cfg.rate_limits:
        _rate_limiter.configure_all(cfg.rate_limits)

    _response_cache = (
        ResponseCache(
            max_memory=cfg.cache_max_memory, default_ttl=cfg.cache_default_ttl,
            db_path=cfg.cache_db_path, ttl_overrides=cfg.cache_ttl_overrides,
        ) if cfg.cache_enabled else None
    )

    _budget_tracker = (
        BudgetTracker(
            db_path=cfg.budget_db_path,
            default_rate_per_1m_tokens=cfg.budget_default_rate,
            rules=cfg.budget_rules,
        ) if cfg.budget_enabled else None
    )

    _loop_guard = (
        LoopGuard(
            max_calls_per_trace=cfg.loop_guard_max_calls_per_trace,
            max_repeated_outputs=cfg.loop_guard_max_repeated_outputs,
            max_cost_per_trace_usd=cfg.loop_guard_max_cost_per_trace_usd,
            default_action=cfg.loop_guard_action,
        ) if cfg.loop_guard_enabled else None
    )

    _timeout_manager = (
        TimeoutManager(
            stream_chunk_timeout=cfg.timeout_stream_chunk_seconds,
            default_timeout=cfg.default_timeout,
        ) if cfg.timeout_enabled else None
    )

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
        if cfg.fallback_models else "disabled"
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
        init()
    return _config, _queue  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public: flush / shutdown
# ---------------------------------------------------------------------------

def flush() -> None:
    """Force flush all pending events to the ingest API. Blocks until done."""
    if _queue is not None:
        _queue.flush(timeout=10.0)


def shutdown() -> None:
    """Flush and stop the background queue worker. Call at process exit."""
    global _config, _queue, _response_cache, _budget_tracker, _loop_guard, _timeout_manager
    global _model_health_registry, _rate_limiter
    if _queue is not None:
        _queue.shutdown()
        _queue = None
    if _response_cache is not None:
        _response_cache.close()
        _response_cache = None
    if _budget_tracker is not None:
        _budget_tracker.close()
        _budget_tracker = None
    _config = None
    _loop_guard = None
    _timeout_manager = None
    _model_health_registry = ModelHealthRegistry()
    _rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# Public: metrics callbacks
# ---------------------------------------------------------------------------

def on_event(callback: Callable[["CallEvent"], None]) -> None:
    """Register a callback for every captured event."""
    register_event_callback(callback)


def on_error(callback: Callable[["CallEvent", Exception], None]) -> None:
    """Register a callback when an error is captured."""
    register_error_callback(callback)


def on_flush(callback: Callable[[int, int], None]) -> None:
    """Register a callback after batch flush (success_count, fail_count)."""
    register_flush_callback(callback)


def off_event(callback: Callable[["CallEvent"], None]) -> None:
    """Unregister a previously registered on_event callback."""
    unregister_event_callback(callback)


def off_error(callback: Callable[["CallEvent", Exception], None]) -> None:
    """Unregister a previously registered on_error callback."""
    unregister_error_callback(callback)


def off_flush(callback: Callable[[int, int], None]) -> None:
    """Unregister a previously registered on_flush callback."""
    unregister_flush_callback(callback)
