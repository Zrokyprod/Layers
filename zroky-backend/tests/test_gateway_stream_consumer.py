import json
from types import SimpleNamespace

import pytest

import app.services.gateway_stream_consumer as consumer
from app.services.gateway_stream_consumer import gateway_event_to_ingest_event


def test_gateway_event_maps_to_backend_ingest_contract() -> None:
    project_id, event = gateway_event_to_ingest_event(
        {
            "schema_version": "v2",
            "call_id": "call_gateway_1",
            "event_id": "call_gateway_1:gateway",
            "request_id": "chatcmpl_123",
            "project_id": "proj_123",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "call_type": "chat",
            "timestamp_utc": "2026-05-23T12:00:00Z",
            "latency_ms": 42.5,
            "prompt_tokens": 5,
            "output_tokens": 7,
            "total_tokens": 12,
            "cost_usd": 0.001,
            "status": "success",
            "status_code": 200,
            "finish_reason": "tool_calls",
            "stop_reason": "tool_calls",
            "agent_name": "support-agent",
            "prompt_version": "support-v42",
            "session_id": "sess_1",
            "workflow_id": "wf_1",
            "workflow_name": "support-resolution",
            "step_index": 2,
            "agent_framework": "gateway",
            "trace_id": "trace_1",
            "parent_call_id": "parent_1",
            "retrieval": {"index_name": "support-kb", "result_count": 1},
            "outcome": {"type": "ticket_escalated", "amount_usd": 12.5},
            "request_body": {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "help me"}],
                "tools": [{"type": "function", "function": {"name": "lookup"}}],
            },
            "response_body": {
                "choices": [
                    {
                        "message": {
                            "content": "done",
                            "tool_calls": [{"id": "tool_1", "function": {"name": "lookup"}}],
                        }
                    }
                ]
            },
        }
    )

    assert project_id == "proj_123"
    assert event.call_id == "call_gateway_1"
    assert event.event_id == "call_gateway_1:gateway"
    assert event.request_id == "chatcmpl_123"
    assert event.provider == "openai"
    assert event.model == "gpt-4o-mini"
    assert event.prompt_tokens == 5
    assert event.completion_tokens == 7
    assert event.actual_cost_usd == 0.001
    assert event.output_content == "done"
    assert event.finish_reason == "tool_calls"
    assert event.stop_reason == "tool_calls"
    assert event.tool_definitions == [{"type": "function", "function": {"name": "lookup"}}]
    assert event.tool_calls == [{"id": "tool_1", "function": {"name": "lookup"}}]
    assert event.tool_calls_made == [{"id": "tool_1", "function": {"name": "lookup"}}]
    assert event.retrieval == {"index_name": "support-kb", "result_count": 1}
    assert event.outcome == {"type": "ticket_escalated", "amount_usd": 12.5}
    assert event.prompt_fingerprint == "6e572e615b8e749f2a5738d26e6ee27b39094c7d8f109405bd472b75ea85d80e"
    assert event.trace_id == "trace_1"
    assert event.parent_call_id == "parent_1"
    assert event.prompt_version == "support-v42"
    assert event.workflow_name == "support-resolution"
    assert event.metadata == {
        "source": "gateway_redis_stream",
        "status_code": 200,
        "gateway_event_id": "call_gateway_1:gateway",
        "gateway_total_tokens": 12,
    }


def test_gateway_event_requires_project_id() -> None:
    with pytest.raises(ValueError, match="project_id"):
        gateway_event_to_ingest_event({"call_id": "call_1"})


def test_gateway_error_event_gets_structured_error_code() -> None:
    _, event = gateway_event_to_ingest_event(
        {
            "project_id": "proj_123",
            "call_id": "call_timeout",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "status": "error",
            "status_code": 504,
            "error_message": "upstream timeout",
        }
    )

    assert event.status == "error"
    assert event.error_code == "TIMEOUT"
    assert event.error_message == "upstream timeout"


def test_consume_gateway_stream_once_uses_canonical_ingest_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.acked: list[tuple[str, str, str]] = []
            self.reads: list[dict[str, str]] = []

        def xgroup_create(self, stream: str, group: str, id: str, mkstream: bool) -> None:
            assert stream == "zroky:ingest:v2"
            assert group == "zroky-backend"
            assert id == "0"
            assert mkstream is True

        def xreadgroup(self, group: str, consumer_name: str, streams: dict[str, str], count: int, block: int):
            assert group == "zroky-backend"
            assert consumer_name == "worker-1"
            assert count == 100
            self.reads.append(streams)
            if streams == {"zroky:ingest:v2": "0"}:
                assert block == 0
                return []
            assert streams == {"zroky:ingest:v2": ">"}
            assert block == 0
            return [
                (
                    "zroky:ingest:v2",
                    [
                        (
                            "1-0",
                            {
                                "event": json.dumps(
                                    {
                                        "project_id": "proj_123",
                                        "call_id": "call_gateway_1",
                                        "event_id": "call_gateway_1:gateway",
                                        "provider": "openai",
                                        "model": "gpt-4o-mini",
                                        "prompt_tokens": 5,
                                        "output_tokens": 7,
                                        "status": "success",
                                    }
                                )
                            },
                        )
                    ],
                )
            ]

        def xack(self, stream: str, group: str, message_id: str) -> None:
            self.acked.append((stream, group, message_id))

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    captured: dict[str, object] = {}
    fake_redis = FakeRedis()
    monkeypatch.setattr(consumer, "get_settings", lambda: SimpleNamespace(
        GATEWAY_INGEST_STREAM_NAME="zroky:ingest:v2",
        GATEWAY_INGEST_CONSUMER_GROUP="zroky-backend",
        GATEWAY_INGEST_CONSUMER_NAME="worker-1",
        GATEWAY_INGEST_STREAM_BATCH_SIZE=100,
        GATEWAY_INGEST_STREAM_BLOCK_MS=0,
        GATEWAY_INGEST_STREAM_MAX_ATTEMPTS=3,
        GATEWAY_INGEST_DEAD_LETTER_STREAM_NAME="zroky:ingest:v2:dead",
    ))
    monkeypatch.setattr(consumer, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(consumer, "SessionLocal", lambda: FakeSession())

    def fake_process_ingest_batch_for_tenant(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(accepted=1, queued=1, duplicates=0, enqueue_failed=0)

    monkeypatch.setattr(consumer, "process_ingest_batch_for_tenant", fake_process_ingest_batch_for_tenant)

    result = consumer.consume_gateway_stream_once()

    assert result.read == 1
    assert result.accepted == 1
    assert result.queued == 1
    assert result.acked == 1
    assert fake_redis.reads == [
        {"zroky:ingest:v2": "0"},
        {"zroky:ingest:v2": ">"},
    ]
    assert fake_redis.acked == [("zroky:ingest:v2", "zroky-backend", "1-0")]
    assert captured["tenant_id"] == "proj_123"
    assert captured["idempotency_header"] == "1-0"
    assert captured["enforce_rate_limit"] is False
    assert captured["enforce_quota"] is True
    body = captured["body"]
    assert body.events[0].call_id == "call_gateway_1"
    assert body.events[0].completion_tokens == 7


def test_consume_gateway_stream_once_leaves_failed_message_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.acked: list[tuple[str, str, str]] = []
            self.dead_letters: list[tuple[str, dict[str, str]]] = []

        def xgroup_create(self, stream: str, group: str, id: str, mkstream: bool) -> None:
            return None

        def xreadgroup(self, group: str, consumer_name: str, streams: dict[str, str], count: int, block: int):
            if streams == {"zroky:ingest:v2": "0"}:
                return []
            return [
                (
                    "zroky:ingest:v2",
                    [
                        (
                            "2-0",
                            {
                                "event": json.dumps(
                                    {
                                        "project_id": "proj_123",
                                        "call_id": "call_gateway_fail",
                                        "provider": "openai",
                                        "model": "gpt-4o-mini",
                                    }
                                )
                            },
                        )
                    ],
                )
            ]

        def xpending_range(self, stream: str, group: str, min: str, max: str, count: int):
            return [{"message_id": min, "times_delivered": 1}]

        def xack(self, stream: str, group: str, message_id: str) -> None:
            self.acked.append((stream, group, message_id))

        def xadd(self, stream: str, fields: dict[str, str]) -> None:
            self.dead_letters.append((stream, fields))

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(consumer, "get_settings", lambda: SimpleNamespace(
        GATEWAY_INGEST_STREAM_NAME="zroky:ingest:v2",
        GATEWAY_INGEST_CONSUMER_GROUP="zroky-backend",
        GATEWAY_INGEST_CONSUMER_NAME="worker-1",
        GATEWAY_INGEST_STREAM_BATCH_SIZE=100,
        GATEWAY_INGEST_STREAM_BLOCK_MS=0,
        GATEWAY_INGEST_STREAM_MAX_ATTEMPTS=3,
        GATEWAY_INGEST_DEAD_LETTER_STREAM_NAME="zroky:ingest:v2:dead",
    ))
    monkeypatch.setattr(consumer, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(consumer, "SessionLocal", lambda: FakeSession())

    def fail_ingest(**_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(consumer, "process_ingest_batch_for_tenant", fail_ingest)

    result = consumer.consume_gateway_stream_once()

    assert result.read == 1
    assert result.invalid == 1
    assert result.failed == 1
    assert result.dead_lettered == 0
    assert result.acked == 0
    assert fake_redis.acked == []
    assert fake_redis.dead_letters == []


def test_consume_gateway_stream_once_dead_letters_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.acked: list[tuple[str, str, str]] = []
            self.dead_letters: list[tuple[str, dict[str, str]]] = []

        def xgroup_create(self, stream: str, group: str, id: str, mkstream: bool) -> None:
            return None

        def xreadgroup(self, group: str, consumer_name: str, streams: dict[str, str], count: int, block: int):
            if streams == {"zroky:ingest:v2": "0"}:
                return [
                    (
                        "zroky:ingest:v2",
                        [
                            (
                                "3-0",
                                {
                                    "event": json.dumps(
                                        {
                                            "project_id": "proj_123",
                                            "call_id": "call_gateway_poison",
                                            "provider": "openai",
                                            "model": "gpt-4o-mini",
                                        }
                                    )
                                },
                            )
                        ],
                    )
                ]
            raise AssertionError("new messages should not be read while pending retries exist")

        def xpending_range(self, stream: str, group: str, min: str, max: str, count: int):
            return [{"message_id": min, "times_delivered": 3}]

        def xack(self, stream: str, group: str, message_id: str) -> None:
            self.acked.append((stream, group, message_id))

        def xadd(self, stream: str, fields: dict[str, str]) -> None:
            self.dead_letters.append((stream, fields))

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(consumer, "get_settings", lambda: SimpleNamespace(
        GATEWAY_INGEST_STREAM_NAME="zroky:ingest:v2",
        GATEWAY_INGEST_CONSUMER_GROUP="zroky-backend",
        GATEWAY_INGEST_CONSUMER_NAME="worker-1",
        GATEWAY_INGEST_STREAM_BATCH_SIZE=100,
        GATEWAY_INGEST_STREAM_BLOCK_MS=0,
        GATEWAY_INGEST_STREAM_MAX_ATTEMPTS=3,
        GATEWAY_INGEST_DEAD_LETTER_STREAM_NAME="zroky:ingest:v2:dead",
    ))
    monkeypatch.setattr(consumer, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(consumer, "SessionLocal", lambda: FakeSession())

    def fail_ingest(**_kwargs):
        raise RuntimeError("poison event")

    monkeypatch.setattr(consumer, "process_ingest_batch_for_tenant", fail_ingest)

    result = consumer.consume_gateway_stream_once()

    assert result.read == 1
    assert result.invalid == 1
    assert result.failed == 0
    assert result.dead_lettered == 1
    assert result.acked == 1
    assert fake_redis.acked == [("zroky:ingest:v2", "zroky-backend", "3-0")]
    assert fake_redis.dead_letters[0][0] == "zroky:ingest:v2:dead"
    assert fake_redis.dead_letters[0][1]["source_message_id"] == "3-0"
    assert fake_redis.dead_letters[0][1]["attempts"] == "3"
