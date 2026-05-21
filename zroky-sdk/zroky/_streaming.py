# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Synchronous stream wrapper for the Zroky SDK.

_wrapped_stream() is extracted here to keep zroky/__init__.py under 30 KB.
It accesses shared mutable globals via zroky._globals (imported lazily inside
the function body to avoid circular imports at module load time).
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from zroky._internal.config import SDKConfig
from zroky._internal.fallback import FallbackChain, FallbackExecutor
from zroky._internal.models import CallEvent, ErrorCode
from zroky._internal.queue import EventQueue
from zroky._internal.rate_limiter import rate_limit_key
from zroky._internal.retry import RetryOutcome, RetryPolicy, retry_sync
from zroky._internal.timeout_manager import _timed_sync_iter
from zroky._internal.cost import calculate_cost
from zroky._internal.cache import CacheEntry
from zroky._internal.pii import mask_text, mask_value
from zroky._telemetry import (
    _apply_loop_telemetry_from_output,
    _apply_tool_lifecycle_telemetry,
    _build_provider_kwargs,
    _classify_error,
    _copy_provider_messages,
    _copy_provider_tools,
    _ensure_provider_payload_is_isolated,
    _finalize_call_error,
    _merge_retry_metadata,
    _resolve_provider_fn,
)


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
    """Yield stream chunks while capturing all telemetry events."""
    import zroky as _z  # lazy — avoids circular import

    from zroky._internal.metrics import notify_event as _notify_event

    accumulated_content = ""
    accumulated_tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None
    _last_retry_outcome_stream: list[RetryOutcome] = []

    _fallback_executor_stream = FallbackExecutor(
        chain=fallback_chain,
        registry=_z._model_health_registry,
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
        if _z._timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _z._timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            _z._rate_limiter.acquire(
                rl_key, estimated_tokens=estimated_prompt_tokens, verbose=cfg.verbose,
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
                model=_model, call_id=event.call_id, mode="stream",
            )
            return _fn(model=_model, messages=pm, tools=pt, stream=True, **_kw)

        stream_iter = retry_sync(
            _inner_stream,
            policy=retry_policy,
            classify_error=_classify_error,
            verbose=cfg.verbose,
            call_kwargs={},
            outcome=retry_outcome,
        )
        if stream_chunk_timeout is not None and stream_chunk_timeout > 0:
            stream_iter = _timed_sync_iter(stream_iter, stream_chunk_timeout, TimeoutError("stream chunk timeout"))
        elif _z._timeout_manager is not None and cfg.timeout_enabled:
            chunk_t = _z._timeout_manager.stream_chunk_timeout
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
        if _last_retry_outcome_stream:
            _merge_retry_metadata(event, _last_retry_outcome_stream[0])
        resolved = event.resolved_model or event.model
        _z._model_health_registry.record(resolved, latency_ms, success=True)
        if _z._timeout_manager is not None and cfg.timeout_enabled:
            _z._timeout_manager.record_latency(resolved, latency_ms / 1000.0)
        queue.enqueue(event)
        _notify_event(event)
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(
                fallback_outcome.resolved_provider or event.provider,
                fallback_outcome.resolved_model or event.model,
            )
            actual_tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            _z._rate_limiter.update_from_response(
                rl_key, None,
                actual_tokens=actual_tokens,
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
                project=cfg.project,
                agent=event.agent_name,
                user=event.user_id,
                cost_usd=cost_breakdown["total_cost_usd"],
                window_keys=budget_result.window_keys,
            )
        if _z._loop_guard is not None and cfg.loop_guard_enabled:
            from zroky._internal.loop_guard import LoopDetectedError  # noqa: PLC0415
            _loop_result_post = _z._loop_guard.check_post_call(
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
        if cache_key is not None and _z._response_cache is not None:
            _z._response_cache.put(cache_key, CacheEntry(
                content=event.output_content,
                tool_calls=event.tool_calls_made,
                usage={
                    "prompt_tokens": event.prompt_tokens or 0,
                    "completion_tokens": event.completion_tokens or 0,
                    "total_tokens": (event.prompt_tokens or 0) + (event.completion_tokens or 0),
                },
                model=event.resolved_model or event.model,
                provider=event.provider,
                ttl=_z._response_cache.ttl_for(event.resolved_model or event.model),
            ))

    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        if _last_retry_outcome_stream:
            _merge_retry_metadata(event, _last_retry_outcome_stream[0])
        if _classify_error(exc) == ErrorCode.TIMEOUT:
            event.timeout_triggered = True
        _finalize_call_error(event, exc, latency_ms, queue, cfg)
        raise
