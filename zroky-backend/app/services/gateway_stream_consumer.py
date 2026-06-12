from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from redis.exceptions import ResponseError

from app.api.routes.ingest import process_ingest_batch_for_tenant
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.ingest import IngestBatchRequest
from app.schemas.ingest_event_v2 import IngestEventV2
from app.services.prompt_fingerprint import generate_prompt_fingerprint
from app.services.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class GatewayStreamResult:
    read: int = 0
    accepted: int = 0
    queued: int = 0
    duplicates: int = 0
    enqueue_failed: int = 0
    invalid: int = 0
    failed: int = 0
    dead_lettered: int = 0
    dead_letter_failed: int = 0
    acked: int = 0


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    rows = [item for item in value if isinstance(item, dict)]
    return rows or None


def _first_choice_message(response_body: dict[str, Any]) -> dict[str, Any]:
    choices = response_body.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first = choices[0]
    if not isinstance(first, dict):
        return {}
    return _as_dict(first.get("message"))


def _output_content(response_body: dict[str, Any]) -> str | None:
    message = _first_choice_message(response_body)
    content = message.get("content")
    return content[:4000] if isinstance(content, str) and content else None


def _tool_calls(response_body: dict[str, Any]) -> list[dict[str, Any]] | None:
    return _as_list_of_dicts(_first_choice_message(response_body).get("tool_calls"))


def _message_content(messages: list[dict[str, Any]], role: str) -> str | None:
    for message in reversed(messages):
        if message.get("role") == role and isinstance(message.get("content"), str):
            return str(message["content"])[:12000]
    return None


def _canonical_tool_calls(raw: dict[str, Any], response_body: dict[str, Any]) -> list[dict[str, Any]] | None:
    return _as_list_of_dicts(raw.get("tool_calls")) or _as_list_of_dicts(raw.get("tool_calls_made")) or _tool_calls(response_body)


def _error_code(status_code: int, error_message: str | None) -> str | None:
    text = (error_message or "").lower()
    if status_code in {401, 403}:
        return "AUTH_FAILURE"
    if status_code in {408, 504} or "timeout" in text:
        return "TIMEOUT"
    if status_code == 429 or "rate limit" in text:
        return "RATE_LIMIT"
    if status_code >= 500:
        return "PROVIDER_ERROR"
    return "UNKNOWN_ERROR" if error_message or status_code >= 400 else None


def _int_value(raw: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0
    return 0


def gateway_event_to_ingest_event(raw: dict[str, Any]) -> tuple[str, IngestEventV2]:
    project_id = str(raw.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("gateway event missing project_id")

    call_id = str(raw.get("call_id") or "").strip() or str(uuid4())
    event_id = str(raw.get("event_id") or "").strip() or f"{call_id}:gateway"
    request_body = _as_dict(raw.get("request_body"))
    response_body = _as_dict(raw.get("response_body"))
    model = str(raw.get("model") or request_body.get("model") or "unknown").strip() or "unknown"
    prompt_tokens = _int_value(raw, "prompt_tokens")
    completion_tokens = _int_value(raw, "completion_tokens", "output_tokens")
    status_code = _int_value(raw, "status_code")
    error_message = str(raw.get("error_message") or "").strip() or None
    tools = _as_list_of_dicts(request_body.get("tools"))
    messages = _as_list_of_dicts(request_body.get("messages")) or []
    tool_calls = _canonical_tool_calls(raw, response_body)
    input_payload = _as_dict(raw.get("input")) or {"messages": messages, "request": request_body}
    output_content = str(raw.get("output_content") or "").strip() or _output_content(response_body)

    event = IngestEventV2(
        schema_version="v2",
        call_id=call_id,
        event_id=event_id,
        request_id=str(raw.get("request_id") or "").strip() or None,
        provider=str(raw.get("provider") or "gateway").strip() or "gateway",
        model=model,
        call_type=str(raw.get("call_type") or "chat").strip() or "chat",
        status=str(raw.get("status") or "unknown").strip() or "unknown",
        latency_ms=raw.get("latency_ms"),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        actual_cost_usd=raw.get("cost_usd"),
        tool_definitions=tools,
        tool_calls=tool_calls,
        tool_calls_made=tool_calls,
        retrieval=_as_dict(raw.get("retrieval")) or None,
        outcome=_as_dict(raw.get("outcome")) or None,
        output_content=output_content,
        finish_reason=str(raw.get("finish_reason") or "").strip() or None,
        stop_reason=str(raw.get("stop_reason") or "").strip() or None,
        trace_id=str(raw.get("trace_id") or "").strip() or None,
        parent_call_id=str(raw.get("parent_call_id") or "").strip() or None,
        span_type=str(raw.get("span_type") or "llm_call").strip() or "llm_call",
        span_name=str(raw.get("span_name") or f"gateway/{model}").strip() or None,
        span_index=raw.get("span_index") if raw.get("span_index") is not None else raw.get("step_index"),
        input=input_payload,
        system_prompt=str(raw.get("system_prompt") or _message_content(messages, "system") or "").strip() or None,
        user_input=str(raw.get("user_input") or _message_content(messages, "user") or "").strip() or None,
        final_answer=str(raw.get("final_answer") or output_content or "").strip() or None,
        tool=_as_dict(raw.get("tool")) or ({"calls": tool_calls} if tool_calls else None),
        memory=_as_dict(raw.get("memory")) or None,
        handoff=_as_dict(raw.get("handoff")) or None,
        policy=_as_dict(raw.get("policy")) or None,
        versions=_as_dict(raw.get("versions")) or None,
        agent_name=str(raw.get("agent_name") or "").strip() or None,
        prompt_fingerprint=generate_prompt_fingerprint(messages, tools, model) if messages else None,
        prompt_version=str(raw.get("prompt_version") or "").strip() or None,
        error_code=_error_code(status_code, error_message),
        error_message=error_message,
        created_at=raw.get("created_at") or raw.get("timestamp_utc"),
        session_id=str(raw.get("session_id") or "").strip() or None,
        workflow_id=str(raw.get("workflow_id") or "").strip() or None,
        workflow_name=str(raw.get("workflow_name") or "").strip() or None,
        step_index=raw.get("step_index"),
        agent_framework=str(raw.get("agent_framework") or "").strip() or "gateway",
        capture_source=str(raw.get("capture_source") or "gateway_redis_stream").strip() or "gateway_redis_stream",
        masking_version=str(raw.get("masking_version") or "gateway-redact-v1").strip() or None,
        pii_masked=bool(raw.get("pii_masked", True)),
        metadata={
            "source": "gateway_redis_stream",
            "status_code": status_code or None,
            "gateway_event_id": event_id,
            "gateway_total_tokens": _int_value(raw, "total_tokens") or prompt_tokens + completion_tokens,
        },
    )
    return project_id, event


def _ensure_group(client: Any, *, stream: str, group: str) -> None:
    try:
        client.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _read_gateway_stream_batches(
    client: Any,
    *,
    stream: str,
    group: str,
    consumer: str,
    count: int,
    block_ms: int,
) -> list[Any]:
    pending = client.xreadgroup(
        group,
        consumer,
        {stream: "0"},
        count=count,
        block=0,
    )
    if pending:
        return pending
    return client.xreadgroup(
        group,
        consumer,
        {stream: ">"},
        count=count,
        block=block_ms,
    )


def _delivery_count(
    client: Any,
    *,
    stream: str,
    group: str,
    message_id: str,
) -> int:
    try:
        rows = client.xpending_range(stream, group, message_id, message_id, 1)
    except AttributeError:
        return 1
    except Exception:
        logger.exception(
            "gateway stream pending metadata lookup failed",
            extra={"redis_message_id": message_id},
        )
        return 1
    if not rows:
        return 1

    row = rows[0]
    raw_count: Any
    if isinstance(row, dict):
        raw_count = (
            row.get("times_delivered")
            or row.get("delivery_count")
            or row.get("deliveries")
        )
    elif isinstance(row, (list, tuple)) and len(row) >= 4:
        raw_count = row[3]
    else:
        raw_count = None
    try:
        return max(1, int(raw_count or 1))
    except (TypeError, ValueError):
        return 1


def _field_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return str(value)


def _dead_letter_gateway_event(
    client: Any,
    *,
    dead_letter_stream: str,
    source_stream: str,
    source_group: str,
    source_consumer: str,
    message_id: str,
    fields: dict[str, Any],
    attempts: int,
    exc: Exception,
) -> None:
    client.xadd(
        dead_letter_stream,
        {
            "event": _field_text(fields.get("event")),
            "source_stream": source_stream,
            "source_group": source_group,
            "source_consumer": source_consumer,
            "source_message_id": str(message_id),
            "attempts": str(attempts),
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
        },
    )


def consume_gateway_stream_once() -> GatewayStreamResult:
    settings = get_settings()
    result = GatewayStreamResult()
    client = get_redis_client()
    stream = settings.GATEWAY_INGEST_STREAM_NAME
    group = settings.GATEWAY_INGEST_CONSUMER_GROUP
    consumer = settings.GATEWAY_INGEST_CONSUMER_NAME
    count = max(1, int(settings.GATEWAY_INGEST_STREAM_BATCH_SIZE))
    block_ms = max(0, int(settings.GATEWAY_INGEST_STREAM_BLOCK_MS))
    max_attempts = max(
        1,
        int(getattr(settings, "GATEWAY_INGEST_STREAM_MAX_ATTEMPTS", 3)),
    )
    dead_letter_stream = (
        str(
            getattr(
                settings,
                "GATEWAY_INGEST_DEAD_LETTER_STREAM_NAME",
                f"{stream}:dead",
            )
        ).strip()
        or f"{stream}:dead"
    )

    _ensure_group(client, stream=stream, group=group)
    batches = _read_gateway_stream_batches(
        client,
        stream=stream,
        group=group,
        consumer=consumer,
        count=count,
        block_ms=block_ms,
    )

    for _stream_name, messages in batches or []:
        for message_id, fields in messages:
            result.read += 1
            message_id_text = _field_text(message_id)
            try:
                raw_event = json.loads(fields.get("event") or "{}")
                project_id, event = gateway_event_to_ingest_event(raw_event)
                body = IngestBatchRequest(events=[event])
                with SessionLocal() as db:
                    response = process_ingest_batch_for_tenant(
                        body=body,
                        tenant_id=project_id,
                        db=db,
                        idempotency_header=message_id_text,
                        enforce_rate_limit=False,
                        enforce_quota=True,
                    )
                result.accepted += response.accepted
                result.queued += response.queued
                result.duplicates += response.duplicates
                result.enqueue_failed += response.enqueue_failed
                client.xack(stream, group, message_id)
                result.acked += 1
            except Exception as exc:
                logger.exception(
                    "gateway stream event failed",
                    extra={"redis_message_id": message_id_text},
                )
                result.invalid += 1
                attempts = _delivery_count(
                    client,
                    stream=stream,
                    group=group,
                    message_id=message_id_text,
                )
                if attempts < max_attempts:
                    result.failed += 1
                    continue

                try:
                    _dead_letter_gateway_event(
                        client,
                        dead_letter_stream=dead_letter_stream,
                        source_stream=stream,
                        source_group=group,
                        source_consumer=consumer,
                        message_id=message_id_text,
                        fields=fields,
                        attempts=attempts,
                        exc=exc,
                    )
                except Exception:
                    logger.exception(
                        "gateway stream dead-letter write failed",
                        extra={"redis_message_id": message_id_text},
                    )
                    result.failed += 1
                    result.dead_letter_failed += 1
                    continue

                client.xack(stream, group, message_id)
                result.acked += 1
                result.dead_lettered += 1

    return result
