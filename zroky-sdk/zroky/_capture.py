from __future__ import annotations

import functools
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from zroky._internal.failure_reason import build_failure_reason
from zroky._internal.models import CallEvent, CallType
from zroky._internal.pii import mask_error_message, mask_text, mask_value
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint
from zroky._internal.metrics import notify_event as _notify_event
from zroky._telemetry import _classify_error, _get_agent, _local

@dataclass
class _TraceRunContext:
    trace_id: str
    root_call_id: str
    name: str | None = None
    agent_name: str | None = None
    user_input: Any | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] | None = None
    next_index: int = 1
    final_answer: Any | None = None
    children: list[str] = field(default_factory=list)

    def set_final_answer(self, value: Any) -> None:
        self.final_answer = value

    def capture_tool_call(self, *args: Any, **kwargs: Any) -> str:
        return capture_tool_call(*args, **kwargs)

    def capture_policy_decision(self, *args: Any, **kwargs: Any) -> str:
        return capture_policy_decision(*args, **kwargs)

    def capture_handoff(self, *args: Any, **kwargs: Any) -> str:
        return capture_handoff(*args, **kwargs)


def _version_metadata(cfg: Any, *, model: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    versions = {
        "code_sha": getattr(cfg, "code_sha", None),
        "deployment_id": getattr(cfg, "deployment_id", None),
        "model_version": getattr(cfg, "model_version", None) or model,
        "tool_schema_version": getattr(cfg, "tool_schema_version", None),
        "rag_version": getattr(cfg, "rag_version", None),
        "prompt_version": getattr(cfg, "prompt_version", None),
    }
    if extra:
        versions.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    clean = {k: v for k, v in versions.items() if v not in (None, "", [], {})}
    return clean or None


def _current_trace_context() -> _TraceRunContext | None:
    ctx = getattr(_local, "trace_run", None)
    return ctx if isinstance(ctx, _TraceRunContext) else None


def _next_span_index(default: int | None = None) -> int | None:
    if default is not None:
        return default
    ctx = _current_trace_context()
    if ctx is None:
        return None
    value = ctx.next_index
    ctx.next_index += 1
    return value


def _resolve_trace_link(
    *,
    trace_id: str | None,
    parent_call_id: str | None,
) -> tuple[str | None, str | None]:
    ctx = _current_trace_context()
    if ctx is None:
        return trace_id, parent_call_id
    return trace_id or ctx.trace_id, parent_call_id or ctx.root_call_id



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
    resolved_trace_id, resolved_parent_call_id = _resolve_trace_link(
        trace_id=trace_id,
        parent_call_id=parent_call_id,
    )
    resolved_step_index = _next_span_index(step_index)
    retrieval_payload = {
        "query": mask_text(query) if cfg.mask_pii else query,
        "index_name": index_name,
        "retriever_version": retriever_version,
        "documents": compacted,
        "result_count": len(compacted or []),
    }
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
        trace_id=resolved_trace_id,
        parent_call_id=resolved_parent_call_id,
        span_type="retrieval",
        span_name=index_name or "retrieval",
        span_index=resolved_step_index,
        input={"query": mask_text(query) if cfg.mask_pii else query},
        retrieval=retrieval_payload,
        versions=_version_metadata(
            cfg,
            model=index_name or "unknown",
            extra={"rag_version": retriever_version or getattr(cfg, "rag_version", None)},
        ),
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=prompt_version or cfg.prompt_version,
        session_id=session_id or cfg.session_id,
        workflow_id=workflow_id or cfg.workflow_id,
        workflow_name=workflow_name or cfg.workflow_name,
        step_index=resolved_step_index,
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
    resolved_trace_id, resolved_parent_call_id = _resolve_trace_link(
        trace_id=trace_id,
        parent_call_id=parent_call_id,
    )
    resolved_step_index = _next_span_index(step_index)
    memory_payload = {
        "operation": operation,
        "namespace": resolved_namespace,
        "keys": mask_value(bounded_keys),
        "item_count": item_count,
        "bytes": bytes_count,
        "value_preview": mask_text(value_preview) if cfg.mask_pii and value_preview else value_preview,
    }

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
        trace_id=resolved_trace_id,
        parent_call_id=resolved_parent_call_id,
        span_type="memory",
        span_name=f"{operation}:{resolved_namespace}",
        span_index=resolved_step_index,
        input={"operation": operation, "namespace": resolved_namespace, "keys": mask_value(bounded_keys)},
        memory=memory_payload,
        versions=_version_metadata(cfg),
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=prompt_version or cfg.prompt_version,
        session_id=session_id or cfg.session_id,
        workflow_id=workflow_id or cfg.workflow_id,
        workflow_name=workflow_name or cfg.workflow_name,
        step_index=resolved_step_index,
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


def capture_tool_call(
    *,
    name: str,
    arguments: dict[str, Any] | None = None,
    result: Any | None = None,
    error: Exception | str | None = None,
    latency_ms: float | None = None,
    call_id: str | None = None,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    span_name: str | None = None,
    span_index: int | None = None,
    user_id: str | None = None,
    environment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Capture a tool invocation as a first-class trace graph span."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue
    resolved_trace_id, resolved_parent_call_id = _resolve_trace_link(
        trace_id=trace_id,
        parent_call_id=parent_call_id,
    )
    resolved_span_index = _next_span_index(span_index)
    error_text = str(error) if error is not None else None
    tool_payload = {
        "name": name,
        "arguments": mask_value(arguments) if cfg.mask_pii else arguments,
        "result": mask_value(result) if cfg.mask_pii else result,
        "error": mask_error_message(error_text) if error_text else None,
    }
    event = CallEvent(
        provider="tool",
        model=name,
        messages=[],
        call_type=CallType.TOOL_CALL,
        call_id=call_id or str(uuid4()),
        status="failed" if error is not None else "success",
        latency_ms=latency_ms,
        trace_id=resolved_trace_id,
        parent_call_id=resolved_parent_call_id,
        span_type="tool_call",
        span_name=span_name or name,
        span_index=resolved_span_index,
        input={"arguments": tool_payload["arguments"]},
        tool=tool_payload,
        versions=_version_metadata(cfg),
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=cfg.prompt_version,
        session_id=cfg.session_id,
        workflow_id=cfg.workflow_id,
        workflow_name=cfg.workflow_name,
        step_index=resolved_span_index,
        user_id=user_id,
        environment=environment or cfg.environment,
        error_code="TOOL_ERROR" if error is not None else None,
        error_message=mask_error_message(error_text) if error_text else None,
        metadata=metadata,
    )
    queue.enqueue(event)
    _notify_event(event)
    return event.call_id


def capture_policy_decision(
    *,
    name: str,
    decision: str,
    reason: str | None = None,
    inputs: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    latency_ms: float | None = None,
    call_id: str | None = None,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    span_index: int | None = None,
    user_id: str | None = None,
    environment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Capture a policy decision as evidence; this does not enforce policy."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue
    resolved_trace_id, resolved_parent_call_id = _resolve_trace_link(
        trace_id=trace_id,
        parent_call_id=parent_call_id,
    )
    resolved_span_index = _next_span_index(span_index)
    policy_payload = {
        "name": name,
        "decision": decision,
        "reason": mask_text(reason) if cfg.mask_pii and reason else reason,
        "inputs": mask_value(inputs) if cfg.mask_pii else inputs,
        "evidence": mask_value(evidence) if cfg.mask_pii else evidence,
    }
    event = CallEvent(
        provider="policy",
        model=name,
        messages=[],
        call_type="policy_decision",
        call_id=call_id or str(uuid4()),
        status="success",
        latency_ms=latency_ms,
        trace_id=resolved_trace_id,
        parent_call_id=resolved_parent_call_id,
        span_type="policy",
        span_name=name,
        span_index=resolved_span_index,
        input={"inputs": policy_payload["inputs"]},
        policy=policy_payload,
        versions=_version_metadata(cfg),
        agent_name=_get_agent() or cfg.default_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=cfg.prompt_version,
        session_id=cfg.session_id,
        workflow_id=cfg.workflow_id,
        workflow_name=cfg.workflow_name,
        step_index=resolved_span_index,
        user_id=user_id,
        environment=environment or cfg.environment,
        metadata=metadata,
    )
    queue.enqueue(event)
    _notify_event(event)
    return event.call_id


def capture_handoff(
    *,
    from_agent: str,
    to_agent: str,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
    latency_ms: float | None = None,
    call_id: str | None = None,
    trace_id: str | None = None,
    parent_call_id: str | None = None,
    span_index: int | None = None,
    user_id: str | None = None,
    environment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Capture an agent-to-agent handoff span."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue
    resolved_trace_id, resolved_parent_call_id = _resolve_trace_link(
        trace_id=trace_id,
        parent_call_id=parent_call_id,
    )
    resolved_span_index = _next_span_index(span_index)
    handoff_payload = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "reason": mask_text(reason) if cfg.mask_pii and reason else reason,
        "payload": mask_value(payload) if cfg.mask_pii else payload,
    }
    event = CallEvent(
        provider="handoff",
        model=f"{from_agent}->{to_agent}",
        messages=[],
        call_type="handoff",
        call_id=call_id or str(uuid4()),
        status="success",
        latency_ms=latency_ms,
        trace_id=resolved_trace_id,
        parent_call_id=resolved_parent_call_id,
        span_type="handoff",
        span_name=f"{from_agent} to {to_agent}",
        span_index=resolved_span_index,
        input={"payload": handoff_payload["payload"]},
        handoff=handoff_payload,
        versions=_version_metadata(cfg),
        agent_name=from_agent,
        agent_framework=cfg.agent_framework,
        prompt_version=cfg.prompt_version,
        session_id=cfg.session_id,
        workflow_id=cfg.workflow_id,
        workflow_name=cfg.workflow_name,
        step_index=resolved_span_index,
        user_id=user_id,
        environment=environment or cfg.environment,
        metadata=metadata,
    )
    queue.enqueue(event)
    _notify_event(event)
    return event.call_id


@contextmanager
def trace_run(
    *,
    name: str | None = None,
    trace_id: str | None = None,
    call_id: str | None = None,
    user_input: Any | None = None,
    system_prompt: str | None = None,
    input: dict[str, Any] | None = None,
    agent_name: str | None = None,
    user_id: str | None = None,
    environment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[_TraceRunContext, None, None]:
    """Create a root agent-run span and link nested SDK captures to it."""
    import zroky as _z  # lazy

    if _z._config is None or _z._queue is None:
        _z.init()
    cfg = _z._config
    queue = _z._queue
    root_call_id = call_id or str(uuid4())
    resolved_trace_id = trace_id or root_call_id
    root_input = input or {}
    if user_input is not None and "user_input" not in root_input:
        root_input["user_input"] = user_input
    if system_prompt is not None and "system_prompt" not in root_input:
        root_input["system_prompt"] = system_prompt
    ctx = _TraceRunContext(
        trace_id=resolved_trace_id,
        root_call_id=root_call_id,
        name=name,
        agent_name=agent_name or _get_agent() or cfg.default_agent,
        user_input=user_input,
        system_prompt=system_prompt,
        metadata=metadata,
    )
    previous = getattr(_local, "trace_run", None)
    _local.trace_run = ctx
    start_ns = time.perf_counter_ns()
    start_wall = time.time()
    exc_to_raise: Exception | None = None
    try:
        yield ctx
    except Exception as exc:
        exc_to_raise = exc
        raise
    finally:
        _local.trace_run = previous
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        event = CallEvent(
            provider="agent",
            model=name or ctx.agent_name or "agent_run",
            messages=[],
            call_type="agent_run",
            call_id=root_call_id,
            trace_id=resolved_trace_id,
            span_type="agent_run",
            span_name=name or ctx.agent_name or "Agent run",
            span_index=0,
            input=mask_value(root_input) if cfg.mask_pii else root_input,
            system_prompt=mask_text(system_prompt) if cfg.mask_pii and system_prompt else system_prompt,
            user_input=(
                str(mask_value(user_input) if cfg.mask_pii else user_input)
                if user_input is not None
                else None
            ),
            final_answer=mask_value(ctx.final_answer) if cfg.mask_pii else ctx.final_answer,
            versions=_version_metadata(cfg),
            agent_name=ctx.agent_name,
            agent_framework=cfg.agent_framework,
            prompt_version=cfg.prompt_version,
            session_id=cfg.session_id,
            workflow_id=cfg.workflow_id,
            workflow_name=cfg.workflow_name,
            user_id=user_id,
            environment=environment or cfg.environment,
            metadata=metadata,
            status="failed" if exc_to_raise is not None else "success",
            latency_ms=latency_ms,
            created_at=start_wall,
        )
        if exc_to_raise is not None:
            event.error_code = _classify_error(exc_to_raise)
            event.error_message = mask_error_message(exc_to_raise)
            event.failure_reason = build_failure_reason(exc_to_raise, error_code=event.error_code)
        queue.enqueue(event)
        _notify_event(event)


# ---------------------------------------------------------------------------
# Public: trace decorator
# ---------------------------------------------------------------------------

def trace(_fn: Any = None, *, name: str | None = None) -> Any:
    """Decorator to capture any function that makes AI provider calls."""
    def decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            fn_name = name or fn.__name__
            input_payload = {"args": mask_value(args), "kwargs": mask_value(kwargs)}
            with trace_run(name=fn_name, input=input_payload) as run:
                result = fn(*args, **kwargs)
                run.set_final_answer(result)
                return result

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
