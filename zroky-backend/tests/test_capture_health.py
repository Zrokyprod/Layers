import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.outcome_attribution import ingest_outcome
from app.services import gateway_stream_consumer


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_capture_health.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    class _MockTaskResult:
        id = "task-capture-health-test"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    app.state.capture_test_session_local = testing_session_local
    monkeypatch.setattr("app.api.routes.ingest.process_diagnosis.delay", _mock_delay)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    if hasattr(app.state, "capture_test_session_local"):
        delattr(app.state, "capture_test_session_local")
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _event(call_id: str, call_type: str, provider: str, metadata: dict | None = None) -> dict:
    return {
        "schema_version": "v2",
        "call_id": call_id,
        "event_id": f"{call_id}:capture",
        "provider": provider,
        "model": "gpt-4o-mini",
        "call_type": call_type,
        "status": "success",
        "latency_ms": 10,
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "metadata": metadata or {},
    }


def _phase3_ready_event(call_id: str, call_type: str = "tool_call") -> dict:
    event = _event(call_id, call_type, "openai")
    event.update(
        {
            "span_type": "tool_call" if call_type == "tool_call" else "llm_call",
            "prompt_version": "support-v42",
            "input": {"system_prompt": "Follow policy v42.", "user_input": "hello"},
            "tool": {"name": "lookup", "arguments": {"id": "123"}, "result": {"ok": True}},
            "policy": {"name": "support_policy", "decision": "allow", "rule_version": "v42"},
            "versions": {
                "code_sha": "abc123",
                "model_version": "gpt-4o-mini-2026-06",
                "tool_schema_version": "tools-v1",
                "rag_version": "rag-v1",
            },
            "capture_source": "python_sdk",
            "masking_version": "python-sdk-pii-v1",
            "pii_masked": True,
        }
    )
    return event


def test_capture_health_reports_no_data(client: TestClient) -> None:
    response = client.get("/api/v1/capture/health", headers={"X-Project-Id": "proj_capture"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "no_data"
    assert payload["calls_24h"] == 0
    assert payload["last_call_id"] is None


def test_capture_health_summarizes_sdk_gateway_and_span_sources(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj_capture"}
    events = [
        _event(str(uuid4()), "chat", "openai"),
        _event(str(uuid4()), "chat", "openai", {"source": "gateway_redis_stream"}),
        _event(str(uuid4()), "retrieval", "retrieval"),
        _event(str(uuid4()), "memory", "memory"),
    ]

    ingest = client.post("/api/v1/ingest", headers=headers, json={"events": events})
    assert ingest.status_code == 202

    response = client.get("/api/v1/capture/health", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "connected"
    assert payload["calls_24h"] == 4
    assert payload["sdk_events_24h"] == 3
    assert payload["gateway_events_24h"] == 1
    assert payload["retrieval_spans_24h"] == 1
    assert payload["memory_spans_24h"] == 1
    assert payload["last_call_id"] is not None


def test_capture_health_reports_first_run_validation_warnings(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj_capture_validation"}
    ingest = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("call_validation_1", "chat", "openai")]},
    )
    assert ingest.status_code == 202

    response = client.get("/api/v1/capture/health", headers=headers)

    assert response.status_code == 200
    codes = {warning["code"] for warning in response.json()["validation_warnings"]}
    assert codes == {
        "input_missing",
        "version_metadata_missing",
        "policy_decisions_missing",
        "tool_spans_missing",
        "outcome_missing",
        "prompt_version_missing",
    }


def test_capture_health_clears_validation_warnings_when_signals_exist(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj_capture_ready"}
    call_id = "call_ready_1"
    event = _phase3_ready_event(call_id)

    ingest = client.post("/api/v1/ingest", headers=headers, json={"events": [event]})
    assert ingest.status_code == 202

    session_factory = client.app.state.capture_test_session_local
    with session_factory() as db:
        ingest_outcome(
            db,
            project_id="proj_capture_ready",
            call_id=call_id,
            outcome_type="ticket_escalated",
            amount_usd=12.5,
            source="api",
            idempotency_key=f"{call_id}:ticket_escalated",
        )

    response = client.get("/api/v1/capture/health", headers=headers)

    assert response.status_code == 200
    assert response.json()["validation_warnings"] == []


def test_capture_health_counts_inline_ingest_outcome(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj_capture_inline_outcome"}
    call_id = "call_inline_outcome_1"
    event = _phase3_ready_event(call_id)
    event["outcome"] = {
        "type": "ticket_escalated",
        "amount_usd": 12.5,
        "idempotency_key": f"{call_id}:ticket_escalated",
    }

    ingest = client.post("/api/v1/ingest", headers=headers, json={"events": [event]})
    assert ingest.status_code == 202

    response = client.get("/api/v1/capture/health", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome_events_24h"] == 1
    assert payload["validation_warnings"] == []


def test_gateway_stream_to_db_to_capture_health_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    db_path = tmp_path / "test_gateway_stream_e2e.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    class _MockTaskResult:
        id = "task-gateway-stream-e2e"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    class FakeStreamRedis:
        def __init__(self) -> None:
            self.acked: list[tuple[str, str, str]] = []

        def xgroup_create(self, *_args, **_kwargs) -> None:
            return None

        def xreadgroup(self, *_args, **_kwargs):
            return [
                (
                    "zroky:ingest:v2",
                    [
                        (
                            "1-0",
                            {
                                "event": json.dumps(
                                    {
                                        "schema_version": "v2",
                                        "project_id": "proj_gateway_e2e",
                                        "call_id": "call_gateway_e2e",
                                        "event_id": "call_gateway_e2e:gateway",
                                        "request_id": "chatcmpl_gateway_e2e",
                                        "provider": "openai",
                                        "model": "gpt-4o-mini",
                                        "call_type": "chat",
                                        "status": "success",
                                        "status_code": 200,
                                        "latency_ms": 42,
                                        "prompt_tokens": 5,
                                        "completion_tokens": 7,
                                        "total_tokens": 12,
                                        "agent_name": "gateway-agent",
                                        "trace_id": "trace_gateway_e2e",
                                        "request_body": {
                                            "model": "gpt-4o-mini",
                                            "messages": [{"role": "user", "content": "hello"}],
                                        },
                                        "response_body": {
                                            "id": "chatcmpl_gateway_e2e",
                                            "choices": [{"message": {"content": "done"}}],
                                        },
                                    }
                                )
                            },
                        )
                    ],
                )
            ]

        def xack(self, stream: str, group: str, message_id: str) -> None:
            self.acked.append((stream, group, message_id))

    fake_redis = FakeStreamRedis()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.ingest.process_diagnosis.delay", _mock_delay)
    monkeypatch.setattr("app.api.routes.ingest.get_redis_client", lambda: None)
    monkeypatch.setattr(gateway_stream_consumer, "SessionLocal", testing_session_local)
    monkeypatch.setattr(gateway_stream_consumer, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        gateway_stream_consumer,
        "get_settings",
        lambda: SimpleNamespace(
            GATEWAY_INGEST_STREAM_NAME="zroky:ingest:v2",
            GATEWAY_INGEST_CONSUMER_GROUP="zroky-backend",
            GATEWAY_INGEST_CONSUMER_NAME="worker-1",
            GATEWAY_INGEST_STREAM_BATCH_SIZE=100,
            GATEWAY_INGEST_STREAM_BLOCK_MS=0,
        ),
    )

    try:
        result = gateway_stream_consumer.consume_gateway_stream_once()
        assert result.read == 1
        assert result.accepted == 1
        assert result.queued == 1
        assert result.acked == 1
        assert fake_redis.acked == [("zroky:ingest:v2", "zroky-backend", "1-0")]

        with TestClient(app) as test_client:
            response = test_client.get(
                "/api/v1/capture/health",
                headers={"X-Project-Id": "proj_gateway_e2e"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "connected"
        assert payload["last_call_id"] == "call_gateway_e2e"
        assert payload["last_source"] == "gateway_redis_stream"
        assert payload["last_provider"] == "openai"
        assert payload["calls_24h"] == 1
        assert payload["gateway_events_24h"] == 1
        assert payload["sdk_events_24h"] == 0
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()
