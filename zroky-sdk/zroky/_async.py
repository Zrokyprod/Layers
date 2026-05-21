# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Async SDK API: ainit, acall, _wrapped_stream_async, aflush, ashutdown.

All functions access the module-level SDK state via lazy imports of
zroky (for _config, _async_queue, _async_lock) and zroky._globals (for the
object singletons that tests don't reset).  This avoids circular imports
at module load time.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from zroky._internal.config import SDKConfig, load_config
from zroky._internal.cost import calculate_cost
from zroky._internal.fallback import FallbackChain, FallbackExecutor
from zroky._internal.loop_guard import LoopDetectedError
from zroky._internal.models import CallEvent, CallType, ErrorCode
from zroky._internal.pii import mask_text, mask_value
from zroky._internal.rate_limiter import rate_limit_key
from zroky._internal.retry import RetryOutcome, RetryPolicy, retry_async
from zroky._internal.timeout_manager import _timed_async_iter
from zroky._internal.cache import CacheEntry
from zroky._internal.metrics import notify_event as _notify_event
from zroky._telemetry import (
    _apply_loop_telemetry_from_output,
    _apply_tool_lifecycle_telemetry,
    _build_provider_kwargs,
    _build_retry_policy,
    _build_telemetry_messages,
    _build_telemetry_tools,
    _build_synthetic_response,
    _classify_error,
    _copy_provider_messages,
    _copy_provider_tools,
    _effective_fallback_models,
    _ensure_provider_payload_is_isolated,
    _estimate_prompt_tokens_for_telemetry,
    _finalize_call_async,
    _finalize_call_error_async,
    _finalize_preflight_blocked_async,
    _get_agent,
    _merge_retry_metadata,
    _model_context_limit_telemetry_for_model,
    _private_retry_metadata,
    _private_tool_lifecycle,
    _resolve_provider_fn,
    _token_estimator_version_for_telemetry,
    _token_rules_version_for_telemetry,
)
from zroky.preflight import _run_preflight_validation

import logging
_logger = logging.getLogger("zroky")

_async_lock = threading.Lock()


# ---------------------------------------------------------------------------
# ainit
# ---------------------------------------------------------------------------

async def ainit(  # noqa: PLR0913
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
    """Async version of init(). Initialize the ZROKY SDK for asyncio applications."""
    import zroky as _z  # lazy
    from zroky._internal.async_queue import AsyncEventQueue  # noqa: PLC0415
    from zroky._internal.cache import ResponseCache
    from zroky._internal.budget import BudgetTracker
    from zroky._internal.loop_guard import LoopGuard
    from zroky._internal.timeout_manager import TimeoutManager

    with _async_lock:
        cfg = load_config(
            api_key=api_key, project=project, mode=mode, mask_pii=mask_pii,
            ingest_url=ingest_url, validate_preflight=validate_preflight,
            validate_preflight_sample_rate=validate_preflight_sample_rate,
            preflight_blocking_warning_types=preflight_blocking_warning_types,
            retry_max_retries=retry_max_retries,
            retry_base_backoff_seconds=retry_base_backoff_seconds,
            retry_max_backoff_seconds=retry_max_backoff_seconds,
            fallback_models=fallback_models, fallback_max=fallback_max,
            fallback_adaptive=fallback_adaptive,
            circuit_breaker_failure_threshold=circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout_seconds=circuit_breaker_reset_timeout_seconds,
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

        q = AsyncEventQueue(config=cfg)
        await q.start()
        _z._async_queue = q
        _z._config = cfg

    if cfg.rate_limit_enabled and cfg.rate_limits:
        _z._rate_limiter.configure_all(cfg.rate_limits)
    _z._response_cache = (
        ResponseCache(
            max_memory=cfg.cache_max_memory, default_ttl=cfg.cache_default_ttl,
            db_path=cfg.cache_db_path, ttl_overrides=cfg.cache_ttl_overrides,
        ) if cfg.cache_enabled else None
    )
    _z._budget_tracker = (
        BudgetTracker(
            db_path=cfg.budget_db_path,
            default_rate_per_1m_tokens=cfg.budget_default_rate,
            rules=cfg.budget_rules,
        ) if cfg.budget_enabled else None
    )
    _z._loop_guard = (
        LoopGuard(
            max_calls_per_trace=cfg.loop_guard_max_calls_per_trace,
            max_repeated_outputs=cfg.loop_guard_max_repeated_outputs,
            max_cost_per_trace_usd=cfg.loop_guard_max_cost_per_trace_usd,
            default_action=cfg.loop_guard_action,
        ) if cfg.loop_guard_enabled else None
    )
    _z._timeout_manager = (
        TimeoutManager(
            stream_chunk_timeout=cfg.timeout_stream_chunk_seconds,
            default_timeout=cfg.default_timeout,
        ) if cfg.timeout_enabled else None
    )
    _print_init_banner_async(cfg)


def _print_init_banner_async(cfg: SDKConfig) -> None:
    project_label = cfg.project or ("configured-key" if cfg.api_key else "unknown")
    print(f"[ZROKY] Connected to project: {project_label}")
    print(f"[ZROKY] PII masking: {'active' if cfg.mask_pii else 'inactive'}")
    print("[ZROKY] Async mode. Ready.")


# ---------------------------------------------------------------------------
# acall
# ---------------------------------------------------------------------------

async def acall(  # noqa: PLR0913
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
    **kwargs: Any,
) -> Any:
    """Async version of call(). Make a tracked provider call in async context."""
    import zroky as _z  # lazy
    from zroky._internal.budget import BudgetExceededError
    from zroky._internal.fallback import build_chain
    from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint

    if _z._async_queue is None:
        await ainit()

    cfg: SDKConfig = _z._config or load_config()
    queue = _z._async_queue

    original_messages = _copy_provider_messages(messages)
    original_tools = _copy_provider_tools(tools)
    telemetry_messages = _build_telemetry_messages(original_messages, mask_pii=cfg.mask_pii)
    telemetry_tools = _build_telemetry_tools(original_tools, mask_pii=cfg.mask_pii)

    call_type = CallType.TOOL_CALL if tools else CallType.CHAT
    prompt_fingerprint = generate_prompt_fingerprint(
        messages=original_messages, tools=original_tools, model=model,
    )
    estimated_prompt_tokens = _estimate_prompt_tokens_for_telemetry(
        model=model, messages=original_messages,
    )
    model_context_telemetry = _model_context_limit_telemetry_for_model(model)
    token_estimator_version = _token_estimator_version_for_telemetry(estimated_prompt_tokens)
    token_rules_version = _token_rules_version_for_telemetry()

    event = CallEvent(
        provider=provider, model=model,
        messages=telemetry_messages, tools=telemetry_tools,
        estimated_prompt_tokens=estimated_prompt_tokens,
        model_context_limit=model_context_telemetry["model_context_limit"],
        model_context_limit_source=model_context_telemetry["model_context_limit_source"],
        model_context_limit_source_detail=model_context_telemetry["model_context_limit_source_detail"],
        model_context_limit_confidence=model_context_telemetry["model_context_limit_confidence"],
        model_context_limit_catalog_version=model_context_telemetry["model_context_limit_catalog_version"],
        model_context_limit_catalog_updated_at=model_context_telemetry["model_context_limit_catalog_updated_at"],
        model_context_limit_catalog_stale=model_context_telemetry["model_context_limit_catalog_stale"],
        model_context_limit_catalog_stale_after_days=model_context_telemetry["model_context_limit_catalog_stale_after_days"],
        token_estimator_version=token_estimator_version,
        token_rules_version=token_rules_version,
        call_type=call_type,
        trace_id=trace_id, parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        prompt_fingerprint=prompt_fingerprint, user_id=user_id,
        retry_metadata=_private_retry_metadata(kwargs),
        tool_lifecycle_summary=_private_tool_lifecycle(kwargs),
    )

    # Cache check
    _cache_key: str | None = None
    if _z._response_cache is not None and not no_cache:
        from zroky._internal.cache import build_cache_key, cached_stream_iter_async, CachedResponse  # noqa: PLC0415
        _cache_key = build_cache_key(prompt_fingerprint)
        cached_entry = _z._response_cache.get(_cache_key)
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
            return cached_stream_iter_async(cached_entry) if stream else CachedResponse(cached_entry)

    # Budget check
    _budget_result = None
    if _z._budget_tracker is not None:
        _budget_result = _z._budget_tracker.check(
            project=cfg.project, agent=_get_agent() or cfg.default_agent,
            user=user_id, model=model, prompt_tokens=estimated_prompt_tokens or 0,
        )
        event.estimated_cost_usd = _budget_result.estimated_cost_usd
        event.budget_remaining_usd = _budget_result.remaining_usd
        event.budget_action_taken = _budget_result.action
        if _budget_result.action == "hard_block":
            raise BudgetExceededError(_budget_result.message)
        if _budget_result.action in ("warn", "soft_block"):
            _logger.warning("%s", _budget_result.message)

    # Loop guard pre-call
    if _z._loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_pre = _z._loop_guard.check_pre_call(
            trace_id=event.trace_id,
            estimated_cost_usd=event.estimated_cost_usd or 0.0,
        )
        if _loop_result_pre.action == "raise":
            raise LoopDetectedError(_loop_result_pre.message, _loop_result_pre.loop_type)
        if _loop_result_pre.action == "warn":
            _logger.warning("%s", _loop_result_pre.message)
        if _loop_result_pre.action == "return_cached":
            cached = _z._loop_guard.get_last_good_response(event.trace_id)
            if cached is not None:
                event.status = "loop_guarded"
                event.output_content = cached
                event.loop_action_taken = "return_cached"
                await queue.enqueue(event)
                _notify_event(event)
                return _build_synthetic_response(cached, provider, model)

    from zroky._errors import ZrokyPreflightError  # noqa: PLC0415
    from copy import deepcopy  # noqa: PLC0415
    try:
        _run_preflight_validation(
            cfg=cfg, provider=provider, model=model,
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
        provider_fn_kwargs, model=model, call_id=event.call_id, mode=call_mode,
    )
    start_ns = time.perf_counter_ns()

    retry_policy = _build_retry_policy(cfg, max_retries)
    effective_fallback = _effective_fallback_models(cfg, fallback)
    fallback_chain = build_chain(
        primary_provider=provider, primary_model=model,
        fallback=effective_fallback, adaptive=cfg.fallback_adaptive,
        max_fallbacks=cfg.fallback_max,
    )
    event.fallback_chain = fallback_chain.models() if fallback_chain else None

    if stream:
        return _wrapped_stream_async(
            provider_fn, event, queue, cfg, start_ns,
            original_messages=original_messages,
            provider_messages=_copy_provider_messages(original_messages),
            telemetry_messages=telemetry_messages,
            original_tools=original_tools,
            provider_tools=_copy_provider_tools(original_tools),
            telemetry_tools=telemetry_tools,
            provider_kwargs=provider_kwargs,
            retry_policy=retry_policy, fallback_chain=fallback_chain,
            kwargs=kwargs, estimated_prompt_tokens=estimated_prompt_tokens or 0,
            budget_result=_budget_result, cache_key=_cache_key,
            timeout=timeout, stream_chunk_timeout=stream_chunk_timeout,
        )

    _fallback_executor_async = FallbackExecutor(
        chain=fallback_chain, registry=_z._model_health_registry, verbose=cfg.verbose,
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
        if _z._timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _z._timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            await _z._rate_limiter.acquire_async(
                rl_key, estimated_tokens=estimated_prompt_tokens or 0, verbose=cfg.verbose,
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
                model=target_model, call_id=event.call_id, mode=call_mode,
            )
            if asyncio.iscoroutinefunction(target_fn):
                return await target_fn(model=target_model, messages=pm, tools=pt, **target_kwargs)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: target_fn(model=target_model, messages=pm, tools=pt, **target_kwargs)
            )

        return await retry_async(
            _inner_async_call, policy=retry_policy, classify_error=_classify_error,
            verbose=cfg.verbose, call_kwargs={}, outcome=retry_outcome,
        )

    try:
        response, fallback_outcome = await _fallback_executor_async.execute_async(
            primary_model=model, primary_provider=provider, call_fn=_make_async_call,
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
    _z._model_health_registry.record(fallback_outcome.resolved_model or model, latency_ms, success=True)
    if _z._timeout_manager is not None and cfg.timeout_enabled:
        _z._timeout_manager.record_latency(fallback_outcome.resolved_model or model, latency_ms / 1000.0)
    if cfg.rate_limit_enabled:
        rl_key = rate_limit_key(
            fallback_outcome.resolved_provider or provider,
            fallback_outcome.resolved_model or model,
        )
        actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
        _z._rate_limiter.update_from_response(
            rl_key, response, actual_tokens=actual_tokens,
            estimated_tokens=estimated_prompt_tokens or 0,
        )
    if _z._budget_tracker is not None and _budget_result is not None:
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
        _z._budget_tracker.record_spend(
            project=cfg.project, agent=event.agent_name or cfg.default_agent,
            user=event.user_id, cost_usd=cost_breakdown["total_cost_usd"],
            window_keys=_budget_result.window_keys,
        )
    if _z._loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_post = _z._loop_guard.check_post_call(
            trace_id=event.trace_id, output_content=event.output_content,
            provider=event.provider, model=event.resolved_model or event.model,
            actual_cost_usd=event.actual_cost_usd or 0.0,
            estimated_cost_usd=event.estimated_cost_usd or 0.0,
        )
        event.loop_action_taken = _loop_result_post.action
        if _loop_result_post.action == "raise":
            raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
    if _cache_key is not None and _z._response_cache is not None:
        _z._response_cache.put(_cache_key, CacheEntry(
            content=event.output_content, tool_calls=event.tool_calls_made,
            usage={
                "prompt_tokens": event.prompt_tokens or 0,
                "completion_tokens": event.completion_tokens or 0,
                "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0),
            },
            model=fallback_outcome.resolved_model or model,
            provider=fallback_outcome.resolved_provider or provider,
            ttl=_z._response_cache.ttl_for(fallback_outcome.resolved_model or model),
        ))
    return response


# ---------------------------------------------------------------------------
# _wrapped_stream_async
# ---------------------------------------------------------------------------

async def _wrapped_stream_async(  # noqa: PLR0912,PLR0915
    provider_fn: Any,
    event: CallEvent,
    queue: Any,
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
    import zroky as _z  # lazy

    accumulated_content = ""
    accumulated_tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None
    _last_retry_outcome_stream_async: list[RetryOutcome] = []

    _fallback_executor_stream_async = FallbackExecutor(
        chain=fallback_chain, registry=_z._model_health_registry, verbose=cfg.verbose,
        circuit_breaker_failure_threshold=cfg.circuit_breaker_failure_threshold,
        circuit_breaker_reset_timeout_seconds=cfg.circuit_breaker_reset_timeout_seconds,
    )

    async def _create_stream_async(try_model: str, try_provider: str, _idx: int = 0) -> Any:
        retry_outcome = RetryOutcome()
        _last_retry_outcome_stream_async[:] = [retry_outcome]
        try_fn_kwargs = dict(kwargs) if kwargs else {}
        try_provider_fn = _resolve_provider_fn(try_provider, try_fn_kwargs)
        try_provider_kwargs = _build_provider_kwargs(
            try_fn_kwargs, model=try_model, call_id=event.call_id, mode="stream",
        )
        if _z._timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _z._timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            await _z._rate_limiter.acquire_async(
                rl_key, estimated_tokens=estimated_prompt_tokens, verbose=cfg.verbose,
            )

        async def _inner_stream(
            _fn=try_provider_fn, _kw=try_provider_kwargs, _model=try_model,
        ) -> Any:
            pm, pt = _ensure_provider_payload_is_isolated(
                original_messages=original_messages,
                provider_messages=_copy_provider_messages(original_messages),
                telemetry_messages=telemetry_messages,
                original_tools=original_tools,
                provider_tools=_copy_provider_tools(original_tools),
                telemetry_tools=telemetry_tools,
                model=_model, call_id=event.call_id, mode="stream",
            )
            if asyncio.iscoroutinefunction(_fn):
                return await _fn(model=_model, messages=pm, tools=pt, stream=True, **_kw)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: _fn(model=_model, messages=pm, tools=pt, stream=True, **_kw)
            )

        stream_iter = await retry_async(
            _inner_stream, policy=retry_policy, classify_error=_classify_error,
            verbose=cfg.verbose, call_kwargs={}, outcome=retry_outcome,
        )
        if stream_chunk_timeout is not None and stream_chunk_timeout > 0:
            stream_iter = _timed_async_iter(stream_iter, stream_chunk_timeout, TimeoutError("stream chunk timeout"))
        elif _z._timeout_manager is not None and cfg.timeout_enabled:
            chunk_t = _z._timeout_manager.stream_chunk_timeout
            if chunk_t > 0:
                stream_iter = _timed_async_iter(stream_iter, chunk_t, TimeoutError("stream chunk timeout"))
        return stream_iter

    try:
        stream_iter, fallback_outcome = await _fallback_executor_stream_async.execute_async(
            primary_model=event.model, primary_provider=event.provider,
            call_fn=_create_stream_async,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        await _finalize_call_error_async(event, exc, latency_ms, queue, cfg)
        raise

    fallback_outcome.merge_into_event(event)

    try:
        async for chunk in _async_iterable(stream_iter):
            if hasattr(chunk, "choices"):
                for choice in chunk.choices:
                    delta = getattr(choice, "delta", None)
                    if delta:
                        if getattr(delta, "content", None):
                            accumulated_content += delta.content
                        if getattr(delta, "tool_calls", None):
                            for tc in delta.tool_calls:
                                accumulated_tool_calls.append({
                                    "id": getattr(tc, "id", None),
                                    "type": getattr(tc, "type", "function"),
                                    "function": {
                                        "name": getattr(tc.function, "name", None) if hasattr(tc, "function") else None,
                                        "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
                                    },
                                })
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
        event.tool_calls_made = mask_value(accumulated_tool_calls) if accumulated_tool_calls else None
        _apply_tool_lifecycle_telemetry(event)
        if usage:
            event.prompt_tokens = usage.get("prompt_tokens", 0)
            event.completion_tokens = usage.get("completion_tokens", 0)
        if _last_retry_outcome_stream_async:
            _merge_retry_metadata(event, _last_retry_outcome_stream_async[0])
        resolved = event.resolved_model or event.model
        _z._model_health_registry.record(resolved, latency_ms, success=True)
        if _z._timeout_manager is not None and cfg.timeout_enabled:
            _z._timeout_manager.record_latency(resolved, latency_ms / 1000.0)
        await queue.enqueue(event)
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(
                fallback_outcome.resolved_provider or event.provider,
                fallback_outcome.resolved_model or event.model,
            )
            actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            _z._rate_limiter.update_from_response(
                rl_key, None, actual_tokens=actual_tokens,
                estimated_tokens=estimated_prompt_tokens,
            )
        if _z._budget_tracker is not None and budget_result is not None:
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
            _z._budget_tracker.record_spend(
                project=cfg.project, agent=event.agent_name, user=event.user_id,
                cost_usd=cost_breakdown["total_cost_usd"],
                window_keys=budget_result.window_keys,
            )
        if _z._loop_guard is not None and cfg.loop_guard_enabled:
            _loop_result_post = _z._loop_guard.check_post_call(
                trace_id=event.trace_id, output_content=event.output_content,
                provider=event.provider, model=event.resolved_model or event.model,
                actual_cost_usd=event.actual_cost_usd or 0.0,
                estimated_cost_usd=event.estimated_cost_usd or 0.0,
            )
            event.loop_action_taken = _loop_result_post.action
            if _loop_result_post.action == "raise":
                raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
        if cache_key is not None and _z._response_cache is not None:
            _z._response_cache.put(cache_key, CacheEntry(
                content=event.output_content, tool_calls=event.tool_calls_made,
                usage={
                    "prompt_tokens": event.prompt_tokens or 0,
                    "completion_tokens": event.completion_tokens or 0,
                    "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0),
                },
                model=event.resolved_model or event.model, provider=event.provider,
                ttl=_z._response_cache.ttl_for(event.resolved_model or event.model),
            ))

    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        if _last_retry_outcome_stream_async:
            _merge_retry_metadata(event, _last_retry_outcome_stream_async[0])
        if _classify_error(exc) == ErrorCode.TIMEOUT:
            event.timeout_triggered = True
        await _finalize_call_error_async(event, exc, latency_ms, queue, cfg)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_iterable(iterable: Any) -> Any:
    if hasattr(iterable, "__aiter__"):
        async for item in iterable:
            yield item
    else:
        for item in iterable:
            yield item


async def aflush() -> None:
    """Async version of flush()."""
    import zroky as _z  # lazy
    if _z._async_queue is not None:
        await _z._async_queue.flush(timeout=10.0)


async def ashutdown() -> None:
    """Async version of shutdown()."""
    import zroky as _z  # lazy
    if _z._async_queue is not None:
        await _z._async_queue.shutdown()
        _z._async_queue = None
    if _z._response_cache is not None:
        _z._response_cache.close()
        _z._response_cache = None
    if _z._budget_tracker is not None:
        _z._budget_tracker.close()
        _z._budget_tracker = None
    _z._loop_guard = None
    _z._timeout_manager = None
