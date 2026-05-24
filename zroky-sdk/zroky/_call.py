# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Synchronous call API: call(), record(), trace(), agent().

All public functions are re-exported from zroky.__init__.
Module-level SDK state (_config, _queue) is accessed via lazy
`import zroky as _z` inside each function body to avoid circular imports.
Shared singleton globals are accessed via `import zroky._globals as _g`.
"""
from __future__ import annotations

import functools
import time
from collections.abc import Generator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable

from zroky._errors import ZrokyPreflightError
from zroky._internal.budget import BudgetExceededError
from zroky._internal.cache import (
    CacheEntry,
    CachedResponse,
    ResponseCache,
    build_cache_key,
    cached_stream_iter,
)
from zroky._internal.config import load_config
from zroky._internal.cost import calculate_cost
from zroky._internal.fallback import FallbackExecutor, build_chain
from zroky._internal.loop_guard import LoopDetectedError
from zroky._internal.models import CallEvent, CallType
from zroky._internal.pii import mask_error_message, mask_text, mask_value
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint
from zroky._internal.rate_limiter import rate_limit_key
from zroky._internal.retry import RetryOutcome, retry_sync
from zroky._internal.failure_reason import build_failure_reason
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
    _extract_response_metadata,
    _finalize_call,
    _finalize_call_error,
    _finalize_preflight_blocked,
    _get_agent,
    _local,
    _merge_retry_metadata,
    _model_context_limit_telemetry_for_model,
    _private_retry_metadata,
    _private_tool_lifecycle,
    _record_tool_lifecycle,
    _resolve_provider_fn,
    _token_estimator_version_for_telemetry,
    _token_rules_version_for_telemetry,
)
from zroky._internal.loop_signals import normalize_retry_metadata, summarize_tool_lifecycle
from zroky._internal.metrics import notify_event as _notify_event
from zroky.preflight import _run_preflight_validation
from zroky._streaming import _wrapped_stream

import logging
_logger = logging.getLogger("zroky")


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
    session_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    prompt_version: str | None = None,
    agent_framework: str | None = None,
    environment: str | None = None,
    step_index: int | None = None,
    metadata: dict[str, Any] | None = None,
    max_retries: int | None = None,
    fallback: list[str] | None = None,
    no_cache: bool = False,
    timeout: float | None = None,
    stream_chunk_timeout: float | None = None,
    **kwargs: Any,
) -> Any:
    """Make a tracked provider call."""
    import zroky as _z  # lazy — avoids circular import at module load

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue

    original_messages = _copy_provider_messages(messages)
    original_tools = _copy_provider_tools(tools)
    provider_messages = _copy_provider_messages(original_messages)
    provider_tools = _copy_provider_tools(original_tools)
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
    model_context_limit = model_context_telemetry["model_context_limit"]
    token_estimator_version = _token_estimator_version_for_telemetry(estimated_prompt_tokens)
    token_rules_version = _token_rules_version_for_telemetry()

    event = CallEvent(
        provider=provider, model=model,
        messages=telemetry_messages, tools=telemetry_tools,
        estimated_prompt_tokens=estimated_prompt_tokens,
        model_context_limit=model_context_limit,
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
        agent_framework=agent_framework or cfg.agent_framework,
        prompt_fingerprint=prompt_fingerprint, user_id=user_id,
        prompt_version=prompt_version or cfg.prompt_version,
        session_id=session_id or cfg.session_id,
        workflow_id=workflow_id or cfg.workflow_id,
        workflow_name=workflow_name or cfg.workflow_name,
        step_index=step_index,
        environment=environment or cfg.environment,
        metadata=metadata,
        retry_metadata=_private_retry_metadata(kwargs),
        tool_lifecycle_summary=_private_tool_lifecycle(kwargs),
    )

    # Cache check
    _cache_key: str | None = None
    if _z._response_cache is not None and not no_cache:
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
            queue.enqueue(event)
            _notify_event(event)
            if cfg.verbose:
                print(f"[ZROKY] Cache HIT: {provider}/{model} — fp={prompt_fingerprint[:12]}")
            if stream:
                return cached_stream_iter(cached_entry)
            return CachedResponse(cached_entry)

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
    _loop_result_pre = None
    if _z._loop_guard is not None and cfg.loop_guard_enabled:
        _loop_result_pre = _z._loop_guard.check_pre_call(
            trace_id=event.trace_id, estimated_cost_usd=event.estimated_cost_usd or 0.0,
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
                queue.enqueue(event)
                _notify_event(event)
                return _build_synthetic_response(cached, provider, model)

    try:
        _run_preflight_validation(
            cfg=cfg, provider=provider, model=model,
            messages=deepcopy(original_messages), tools=deepcopy(original_tools),
            sample_key=f"{provider}|{model}|{prompt_fingerprint}", kwargs=kwargs,
        )
    except ZrokyPreflightError as exc:
        _finalize_preflight_blocked(event, exc, queue, cfg)
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
        return _wrapped_stream(
            provider_fn, event, queue, cfg, start_ns,
            original_messages=original_messages,
            provider_messages=provider_messages,
            telemetry_messages=telemetry_messages,
            original_tools=original_tools,
            provider_tools=provider_tools,
            telemetry_tools=telemetry_tools,
            provider_kwargs=provider_kwargs,
            retry_policy=retry_policy, fallback_chain=fallback_chain,
            kwargs=kwargs, estimated_prompt_tokens=estimated_prompt_tokens or 0,
            cache_key=_cache_key, budget_result=_budget_result,
            timeout=timeout, stream_chunk_timeout=stream_chunk_timeout,
        )

    _fallback_executor = FallbackExecutor(
        chain=fallback_chain, registry=_z._model_health_registry, verbose=cfg.verbose,
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
        if _z._timeout_manager is not None and cfg.timeout_enabled:
            resolved_timeout = _z._timeout_manager.resolve(try_model, user_override=timeout)
            if resolved_timeout is not None:
                try_provider_kwargs["timeout"] = resolved_timeout
        if cfg.rate_limit_enabled:
            rl_key = rate_limit_key(try_provider, try_model)
            _z._rate_limiter.acquire(
                rl_key, estimated_tokens=estimated_prompt_tokens or 0, verbose=cfg.verbose,
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
                model=target_model, call_id=event.call_id, mode=call_mode,
            )
            return target_fn(model=target_model, messages=pm, tools=pt, **target_kwargs)

        return retry_sync(
            _inner_call, policy=retry_policy, classify_error=_classify_error,
            verbose=cfg.verbose, call_kwargs={}, outcome=retry_outcome,
        )

    try:
        response, fallback_outcome = _fallback_executor.execute_sync(
            primary_model=model, primary_provider=provider, call_fn=_make_call,
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
        _trace_state = _z._loop_guard._traces.get(event.trace_id) if event.trace_id else None
        event.loop_cumulative_cost_usd = _trace_state.cumulative_cost_usd if _trace_state is not None else None
        if _loop_result_post.action == "raise":
            raise LoopDetectedError(_loop_result_post.message, _loop_result_post.loop_type)
        if _loop_result_post.action == "warn":
            _logger.warning("%s", _loop_result_post.message)
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
    session_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    prompt_version: str | None = None,
    agent_framework: str | None = None,
    environment: str | None = None,
    step_index: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Manually record a provider call made outside of zroky.call()."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue

    messages = _copy_provider_messages(request.get("messages", []))
    tools = _copy_provider_tools(request.get("tools"))
    telemetry_messages = _build_telemetry_messages(messages, mask_pii=cfg.mask_pii)
    telemetry_tools = _build_telemetry_tools(tools, mask_pii=cfg.mask_pii)
    prompt_fingerprint = generate_prompt_fingerprint(messages=messages, tools=tools, model=model)
    estimated_prompt_tokens = _estimate_prompt_tokens_for_telemetry(model=model, messages=messages)
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
        call_type=CallType.TOOL_CALL if tools else CallType.CHAT,
        trace_id=trace_id, parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=agent_framework or cfg.agent_framework,
        prompt_fingerprint=prompt_fingerprint, user_id=user_id,
        prompt_version=prompt_version or cfg.prompt_version,
        session_id=session_id or cfg.session_id,
        workflow_id=workflow_id or cfg.workflow_id,
        workflow_name=workflow_name or cfg.workflow_name,
        step_index=step_index,
        environment=environment or cfg.environment,
        metadata=metadata,
        latency_ms=latency_ms,
        retry_metadata=normalize_retry_metadata(request.get("retry_metadata")),
        tool_lifecycle_summary=summarize_tool_lifecycle(_record_tool_lifecycle(request)),
    )

    from zroky._internal.metrics import notify_error as _notify_error  # noqa: PLC0415
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


def _compact_documents(documents: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not documents:
        return None
    compacted: list[dict[str, Any]] = []
    for doc in documents[:20]:
        compacted.append(
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "source": doc.get("source"),
                "score": doc.get("score"),
                "metadata": doc.get("metadata"),
                "contentPreview": str(doc.get("contentPreview") or doc.get("content_preview") or "")[:500] or None,
            }
        )
    return compacted


def _document_summary(documents: list[dict[str, Any]] | None) -> str | None:
    if not documents:
        return None
    values: list[str] = []
    for doc in documents[:20]:
        value = doc.get("id") or doc.get("title") or doc.get("source")
        if value:
            values.append(str(value))
    return "\n".join(values)[:4000] or None


def capture_retrieval(
    *,
    query: str,
    index_name: str | None = None,
    retriever_version: str | None = None,
    documents: list[dict[str, Any]] | None = None,
    latency_ms: float | None = None,
    status: str = "success",
    error_code: str | None = None,
    error_message: str | None = None,
    call_id: str | None = None,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    session_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    prompt_version: str | None = None,
    step_index: int | None = None,
    user_id: str | None = None,
    environment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Capture a first-class retrieval/RAG span."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue

    compacted = _compact_documents(mask_value(documents))
    output = _document_summary(compacted)
    event = CallEvent(
        provider="retrieval",
        model=index_name or "unknown",
        messages=[{"role": "user", "content": mask_text(query) if cfg.mask_pii else query}],
        call_type="retrieval",
        call_id=call_id or CallEvent(provider="retrieval", model="unknown", messages=[]).call_id,
        status=status,
        latency_ms=latency_ms,
        prompt_fingerprint=generate_prompt_fingerprint(
            messages=[{"role": "user", "content": query}],
            tools=None,
            model=index_name or "unknown",
        ),
        output_content=output,
        trace_id=trace_id,
        parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=prompt_version or cfg.prompt_version,
        session_id=session_id or cfg.session_id,
        workflow_id=workflow_id or cfg.workflow_id,
        workflow_name=workflow_name or cfg.workflow_name,
        step_index=step_index,
        user_id=user_id,
        environment=environment or cfg.environment,
        error_code=error_code,
        error_message=mask_error_message(error_message) if error_message else None,
        metadata={
            **(metadata or {}),
            "span_type": "retrieval",
            "index_name": index_name,
            "retriever_version": retriever_version,
            "result_count": len(compacted or []),
            "documents": compacted,
        },
    )
    queue.enqueue(event)
    _notify_event(event)
    return event.call_id


def capture_memory(
    *,
    operation: str,
    namespace: str | None = None,
    keys: list[str] | None = None,
    item_count: int | None = None,
    bytes_count: int | None = None,
    value_preview: str | None = None,
    latency_ms: float | None = None,
    status: str = "success",
    error_code: str | None = None,
    error_message: str | None = None,
    call_id: str | None = None,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    session_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    prompt_version: str | None = None,
    step_index: int | None = None,
    user_id: str | None = None,
    environment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Capture a first-class memory operation span."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue
    resolved_namespace = namespace or "memory"
    bounded_keys = keys[:50] if keys else None
    fingerprint_text = ":".join([operation, resolved_namespace, *(sorted(bounded_keys or []))])

    event = CallEvent(
        provider="memory",
        model=resolved_namespace,
        messages=[],
        call_type="memory",
        call_id=call_id or CallEvent(provider="memory", model="unknown", messages=[]).call_id,
        status=status,
        latency_ms=latency_ms,
        prompt_fingerprint=generate_prompt_fingerprint(
            messages=[{"role": "user", "content": fingerprint_text}],
            tools=None,
            model=resolved_namespace,
        ),
        output_content=(mask_text(value_preview) if cfg.mask_pii else value_preview)[:4000] if value_preview else None,
        trace_id=trace_id,
        parent_call_id=parent_call_id,
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=prompt_version or cfg.prompt_version,
        session_id=session_id or cfg.session_id,
        workflow_id=workflow_id or cfg.workflow_id,
        workflow_name=workflow_name or cfg.workflow_name,
        step_index=step_index,
        user_id=user_id,
        environment=environment or cfg.environment,
        error_code=error_code,
        error_message=mask_error_message(error_message) if error_message else None,
        metadata={
            **(metadata or {}),
            "span_type": "memory",
            "operation": operation,
            "namespace": resolved_namespace,
            "keys": bounded_keys,
            "item_count": item_count,
            "bytes": bytes_count,
        },
    )
    queue.enqueue(event)
    _notify_event(event)
    return event.call_id


# ---------------------------------------------------------------------------
# Public: trace decorator
# ---------------------------------------------------------------------------

def trace(_fn: Any = None, *, name: str | None = None) -> Any:
    """Decorator to capture any function that makes AI provider calls."""
    def decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import zroky as _z  # lazy
            if _z._config is None or _z._queue is None:
                _z.init()
            cfg = _z._config
            queue = _z._queue

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
                    provider="unknown", model="unknown", messages=[],
                    call_type=CallType.CHAT,
                    agent_name=_get_agent() or cfg.default_agent or fn_name,
                    agent_framework=cfg.agent_framework,
                    prompt_version=cfg.prompt_version,
                    session_id=cfg.session_id,
                    workflow_id=cfg.workflow_id,
                    workflow_name=cfg.workflow_name,
                    environment=cfg.environment,
                    latency_ms=latency_ms,
                    status="failed" if exc_to_raise else "success",
                )
                if exc_to_raise:
                    event.error_code = _classify_error(exc_to_raise)
                    event.error_message = mask_error_message(exc_to_raise)
                    event.failure_reason = build_failure_reason(
                        exc_to_raise, error_code=event.error_code,
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
    """Context manager to tag all ZROKY-captured calls with a given agent name."""
    previous = getattr(_local, "agent_name", None)
    _local.agent_name = name
    try:
        yield
    finally:
        _local.agent_name = previous
