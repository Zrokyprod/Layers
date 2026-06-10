from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.api.routes import ingest as ingest_routes
from app.db.base import Base
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.privacy import hash_identifier


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_ingest.db"
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
        id = "task-ingest-test"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.ingest.process_diagnosis.delay", _mock_delay)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _event(call_id: str) -> dict:
    return {
        "call_id": call_id,
        "provider": "openai",
        "model": "gpt-4o",
        "call_type": "chat",
        "status": "completed",
        "latency_ms": 312,
        "prompt_tokens": 120,
        "estimated_prompt_tokens": 128,
        "model_context_limit": 128000,
        "model_context_limit_source": "catalog_exact",
        "model_context_limit_source_detail": "gpt-4o",
        "model_context_limit_confidence": 0.95,
        "model_context_limit_catalog_version": "model_context_limits_2026_05_05",
        "model_context_limit_catalog_updated_at": "2026-05-05",
        "model_context_limit_catalog_stale": False,
        "model_context_limit_catalog_stale_after_days": 180,
        "token_estimator_version": "chars_per_token_v1",
        "token_rules_version": "token_rules_v1",
        "completion_tokens": 40,
        "reasoning_tokens": 12,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "tool_definitions": [{"name": "search"}],
        "tool_calls_made": [{"name": "search", "args": {"q": "hello"}}],
        "retry_metadata": {"retry_count": 1, "retry_reason": "RATE_LIMIT"},
        "resolved_model": "gpt-4o-mini",
        "fallback_chain": ["gpt-4o", "gpt-4o-mini"],
        "fallback_attempts": 1,
        "circuit_open_models": ["gpt-4o"],
        "trace_id": "trace-1",
        "parent_call_id": None,
        "agent_name": "research-agent",
        "prompt_fingerprint": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
        "user_id": "user-1",
        "error_code": None,
        "error_message": None,
        "created_at": 1710000000,
    }


def _sdk_0_1_event(call_id: str) -> dict:
    # Mirrors the payload shape emitted by zroky-sdk 0.1.x CallEvent.to_ingest_payload().
    return {
        "call_id": call_id,
        "provider": "openai",
        "model": "gpt-4o",
        "call_type": "chat",
        "status": "completed",
        "latency_ms": 185,
        "prompt_tokens": 42,
        "completion_tokens": 18,
        "reasoning_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "tool_definitions": [],
        "tool_calls_made": [],
        "trace_id": "sdk-compat-trace-1",
        "parent_call_id": None,
        "agent_name": "sdk-agent",
        "prompt_fingerprint": None,
        "user_id": "sdk-user",
        "error_code": None,
        "error_message": None,
        "created_at": "2026-04-25T09:30:00+00:00",
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_ingest_accepts_sdk_payload_on_api_v1_path(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-ingest-1"}
    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={
            "events": [
                _event("ingest-call-1"),
            ]
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] == 1
    assert payload["queued"] == 1
    assert payload["duplicates"] == 0

    call = client.get("/v1/calls/ingest-call-1", headers=headers)
    assert call.status_code == 200
    call_payload = call.json()
    assert call_payload["call"]["call_id"] == "ingest-call-1"
    assert call_payload["call"]["provider"] == "openai"
    assert call_payload["call"]["agent_name"] == "research-agent"
    assert call_payload["call"]["user_id"] == hash_identifier("user-1")
    assert call_payload["call"]["call_type"] == "chat"
    assert call_payload["payload"]["prompt_fingerprint"] == "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd"
    assert call_payload["payload"]["estimated_prompt_tokens"] == 128
    assert call_payload["payload"]["model_context_limit"] == 128000
    assert call_payload["payload"]["model_context_limit_source"] == "catalog_exact"
    assert call_payload["payload"]["model_context_limit_confidence"] == 0.95
    assert call_payload["payload"]["model_context_limit_catalog_version"] == (
        "model_context_limits_2026_05_05"
    )
    assert call_payload["payload"]["retry_metadata"]["retry_reason"] == "RATE_LIMIT"
    assert call_payload["payload"]["resolved_model"] == "gpt-4o-mini"
    assert call_payload["payload"]["fallback_attempts"] == 1
    assert call_payload["payload"]["circuit_open_models"] == ["gpt-4o"]
    assert call_payload["payload"]["token_estimator_version"] == "chars_per_token_v1"
    assert call_payload["payload"]["token_rules_version"] == "token_rules_v1"


def test_ingest_masks_pii_before_storage_and_call_detail(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-ingest-privacy-1"}
    event = _event("ingest-privacy-1")
    event.update(
        {
            "status": "failed",
            "user_id": "customer@example.com",
            "error_message": (
                "provider failed for customer@example.com with "
                "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
            ),
            "tool_calls_made": [
                {
                    "name": "lookup",
                    "args": {
                        "email": "tool@example.com",
                        "api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
                        "nested": {"phone": "555-867-5309"},
                    },
                }
            ],
            "metadata": {
                "owner_email": "owner@example.com",
                "api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
                "binary": "a" * 120,
            },
        }
    )

    response = client.post("/api/v1/ingest", headers=headers, json={"events": [event]})
    assert response.status_code == 202

    detail = client.get("/v1/calls/ingest-privacy-1", headers=headers)
    assert detail.status_code == 200
    rendered = str(detail.json())

    assert "customer@example.com" not in rendered
    assert "tool@example.com" not in rendered
    assert "owner@example.com" not in rendered
    assert "sk-proj-" not in rendered
    assert "555-867-5309" not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "[REDACTED_KEY]" in rendered
    assert "[REDACTED_PHONE]" in rendered


def test_ingest_persists_loop_signal_fields(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-ingest-loop-signals-1"}
    event = _event("ingest-loop-signals-1")
    event.update(
        {
            "normalized_output": "same result for order 123 at 2026-04-27T12:00:00Z",
            "tool_lifecycle_summary": [
                {
                    "tool_called": True,
                    "tool_name": "lookup",
                    "tool_input_signature": "input-fp",
                    "tool_output_signature": "output-fp",
                    "tool_success": True,
                    "tool_duration_ms": 12,
                }
            ],
            "retry_metadata": {
                "retry_count": 3,
                "retry_reason": "timeout",
                "retry_interval": 100,
                "backoff_pattern": "exponential",
                "max_steps_reached": True,
            },
        }
    )

    response = client.post("/api/v1/ingest", headers=headers, json={"events": [event]})
    assert response.status_code == 202

    detail = client.get("/v1/calls/ingest-loop-signals-1", headers=headers)
    payload = detail.json()["payload"]
    assert payload["output_fingerprint"]
    assert payload["tool_lifecycle_summary"][0]["tool_name"] == "lookup"
    assert payload["retry_metadata"]["retry_count"] == 3


def test_sdk_0_1_x_payload_is_accepted_on_api_v1_ingest_path(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-sdk-compat-api-v1"}
    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_sdk_0_1_event("sdk-compat-api-v1-call-1")]},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] == 1
    assert payload["queued"] == 1
    assert payload["duplicates"] == 0

    call = client.get("/v1/calls/sdk-compat-api-v1-call-1", headers=headers)
    assert call.status_code == 200
    call_payload = call.json()
    assert call_payload["call"]["call_id"] == "sdk-compat-api-v1-call-1"
    assert call_payload["call"]["provider"] == "openai"
    assert call_payload["call"]["model"] == "gpt-4o"


def test_sdk_0_1_x_payload_is_accepted_on_v1_ingest_path(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-sdk-compat-v1"}
    response = client.post(
        "/v1/ingest",
        headers=headers,
        json={"events": [_sdk_0_1_event("sdk-compat-v1-call-1")]},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] == 1
    assert payload["queued"] == 1
    assert payload["duplicates"] == 0

    call = client.get("/v1/calls/sdk-compat-v1-call-1", headers=headers)
    assert call.status_code == 200
    call_payload = call.json()
    assert call_payload["call"]["call_id"] == "sdk-compat-v1-call-1"
    assert call_payload["payload"]["source"] == "sdk_ingest"


def test_ingest_enriches_payload_with_cost_bucket_metrics(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-ingest-cost-1"}
    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-cost-1")]},
    )
    assert response.status_code == 202

    call = client.get("/v1/calls/ingest-cost-1", headers=headers)
    assert call.status_code == 200
    payload = call.json()["payload"]

    assert "cost" in payload
    assert payload["cost"]["current_15m_spend_usd"] >= 0
    assert payload["cost"]["baseline_15m_spend_usd"] >= 0
    assert payload["cost"]["history_calls"] >= 1
    assert payload["cost"]["per_call_breakdown"]["total_cost_usd"] > 0
    assert payload["cost"]["pricing_version"]
    assert payload["cost"]["pricing_last_updated_at"] is not None
    assert payload["cost"]["pricing_age_days"] is not None
    assert payload["cost"]["pricing_age_days"] >= 0
    assert payload["cost"]["cost_confidence"] in {"high", "stale", "degraded"}
    provider_comparison = payload["cost"]["provider_comparison"]
    assert provider_comparison["comparison_type"] == "mock"
    assert isinstance(provider_comparison["items"], list)
    assert len(provider_comparison["items"]) >= 1

    detail = client.get("/v1/calls/ingest-cost-1", headers=headers)
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["call"]["pricing_version"] == payload["cost"]["pricing_version"]
    assert detail_payload["call"]["cost_confidence"] == payload["cost"]["cost_confidence"]
    assert detail_payload["call"]["pricing_age_days"] == payload["cost"]["pricing_age_days"]
    assert detail_payload["cost_audit"]["per_call_breakdown"]["provider"] == "openai"
    assert detail_payload["cost_audit"]["pricing_age_days"] == payload["cost"]["pricing_age_days"]


def test_ingest_cost_confidence_degraded_for_unknown_provider_model(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-ingest-cost-degraded-1"}
    event = _event("ingest-cost-degraded-1")
    event["provider"] = "mystery-provider"
    event["model"] = "unknown-model-v1"

    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [event]},
    )
    assert response.status_code == 202

    call = client.get("/v1/calls/ingest-cost-degraded-1", headers=headers)
    assert call.status_code == 200
    payload = call.json()["payload"]

    assert payload["cost"]["cost_confidence"] == "degraded"


def test_ingest_cost_confidence_stale_when_pricing_is_old(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_config = {
        "meta": {
            "schema_version": "stale-test-v1",
            "retrieved_at": "2025-01-01T00:00:00Z",
            "effective_from": "2025-01-01",
            "expires_after_days": 14,
        },
        "providers": {
            "openai": {
                "models": {
                    "gpt-4o": {
                        "input": 5.0,
                        "output": 15.0,
                        "reasoning": 0.0,
                        "cache_create": 0.0,
                        "cache_read": 0.0,
                    }
                }
            }
        },
        "loaded_from_file": True,
        "source_path": "stale-test",
    }

    monkeypatch.setattr("app.services.cost_buckets._load_pricing_config", lambda: stale_config)

    headers = {"X-Project-Id": "proj-ingest-cost-stale-1"}
    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-cost-stale-1")]},
    )
    assert response.status_code == 202

    call = client.get("/v1/calls/ingest-cost-stale-1", headers=headers)
    assert call.status_code == 200
    payload = call.json()["payload"]

    assert payload["cost"]["cost_confidence"] == "stale"
    assert payload["cost"]["pricing_age_days"] > 14


def test_ingest_duplicate_call_id_is_counted(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-ingest-2"}
    first = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-call-dup")]},
    )
    assert first.status_code == 202

    second = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-call-dup")]},
    )
    assert second.status_code == 202
    second_payload = second.json()
    assert second_payload["accepted"] == 0
    assert second_payload["duplicates"] == 1


def test_ingest_idempotency_event_id_prevents_duplicate_cost_and_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enrich_calls = 0

    def _fake_enrich(*, tenant_id: str, payload: dict) -> dict:
        nonlocal enrich_calls
        enrich_calls += 1
        enriched = dict(payload)
        enriched["cost_usd"] = 0.123
        enriched["total_cost_usd"] = 0.123
        enriched["cost"] = {
            "event_cost_usd": 0.123,
            "per_call_breakdown": {
                "total_cost_usd": 0.123,
            },
        }
        return enriched

    monkeypatch.setattr("app.api.routes.ingest.enrich_payload_with_cost_buckets", _fake_enrich)

    headers = {"X-Project-Id": "proj-ingest-idempotency-1"}
    first_event = _event("ingest-idempotent-call-1")
    first_event["event_id"] = "event-idempotent-1"
    second_event = _event("ingest-idempotent-call-2")
    second_event["event_id"] = "event-idempotent-1"

    first = client.post("/api/v1/ingest", headers=headers, json={"events": [first_event]})
    assert first.status_code == 202
    assert first.json()["accepted"] == 1

    second = client.post("/api/v1/ingest", headers=headers, json={"events": [second_event]})
    assert second.status_code == 202
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1
    assert enrich_calls == 1

    calls = client.get("/v1/calls", headers=headers)
    assert calls.status_code == 200
    calls_payload = calls.json()
    assert calls_payload["total"] == 1
    assert calls_payload["items"][0]["call_id"] == "ingest-idempotent-call-1"


def test_rich_ingest_event_creates_masked_trace_graph(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-flight-recorder-rich"}
    root = _event("trace-rich-root")
    root.update(
        {
            "event_id": "trace-rich-root:event",
            "created_at": _now_iso(),
            "trace_id": "trace-rich-1",
            "span_type": "agent_run",
            "span_name": "Refund supervisor",
            "span_index": 0,
            "input": {
                "system_prompt": "Only refund after checking policy v42.",
                "user_input": "Refund customer alice@example.com for order 123.",
            },
            "system_prompt": "Only refund after checking policy v42.",
            "user_input": "Refund customer alice@example.com for order 123.",
            "final_answer": "Refund approved for alice@example.com.",
            "versions": {
                "code_sha": "abc123",
                "deployment_id": "deploy-42",
                "model_version": "gpt-4o-2026-06",
                "tool_schema_version": "refund-tools-v3",
                "rag_version": "policy-index-v9",
            },
            "prompt_version": "refund-supervisor-v42",
            "capture_source": "python_sdk",
            "masking_version": "python-sdk-pii-v1",
            "pii_masked": True,
            "outcome": {
                "type": "refund_resolved",
                "success": True,
                "amount_usd": 25,
                "idempotency_key": "trace-rich-root:refund_resolved",
            },
        }
    )
    tool = _event("trace-rich-tool")
    tool.update(
        {
            "event_id": "trace-rich-tool:event",
            "created_at": _now_iso(),
            "trace_id": "trace-rich-1",
            "parent_call_id": "trace-rich-root",
            "call_type": "tool_call",
            "span_type": "tool_call",
            "span_name": "refund_tool",
            "span_index": 1,
            "tool": {
                "name": "refund_tool",
                "arguments": {
                    "email": "alice@example.com",
                    "api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
                },
                "result": {"approved": True, "refund_id": "rf_123"},
            },
            "policy": {"name": "refund_policy", "decision": "allow", "rule_version": "v42"},
            "versions": {
                "code_sha": "abc123",
                "tool_schema_version": "refund-tools-v3",
            },
            "capture_source": "python_sdk",
            "masking_version": "python-sdk-pii-v1",
            "pii_masked": True,
        }
    )

    response = client.post("/api/v1/ingest", headers=headers, json={"events": [root, tool]})
    assert response.status_code == 202
    assert response.json()["accepted"] == 2

    recent = client.get("/v1/traces/recent", headers=headers)
    assert recent.status_code == 200
    recent_payload = recent.json()
    assert recent_payload["total"] == 1
    assert recent_payload["items"][0]["trace_id"] == "trace-rich-1"
    assert recent_payload["items"][0]["call_count"] == 2

    detail = client.get("/v1/traces/trace-rich-1", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["summary"]["span_count"] == 2
    assert payload["summary"]["root_call_id"] == "trace-rich-root"
    assert payload["root_span"]["span_type"] == "agent_run"
    assert payload["root_span"]["children"][0]["span_type"] == "tool_call"
    assert payload["business_outcome"]["type"] == "refund_resolved"
    assert payload["versions"]["code_sha"] == "abc123"
    assert payload["versions"]["tool_schema_version"] == "refund-tools-v3"
    rendered = str(payload)
    assert "alice@example.com" not in rendered
    assert "sk-proj-" not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "[REDACTED_KEY]" in rendered


def test_missing_trace_id_becomes_one_node_trace(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-flight-recorder-fallback"}
    event = _event("trace-fallback-call")
    event.pop("trace_id", None)
    event.update(
        {
            "event_id": "trace-fallback-call:event",
            "created_at": _now_iso(),
            "user_input": "hello",
            "final_answer": "done",
            "versions": {"code_sha": "fallback-sha"},
        }
    )

    response = client.post("/api/v1/ingest", headers=headers, json={"events": [event]})
    assert response.status_code == 202

    detail = client.get("/v1/traces/trace-fallback-call", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["summary"]["trace_id"] == "trace-fallback-call"
    assert payload["summary"]["span_count"] == 1
    assert payload["root_span"]["call_id"] == "trace-fallback-call"


def test_duplicate_event_id_does_not_duplicate_trace_span_or_cost(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-flight-recorder-idem"}
    first = _event("trace-idem-call-1")
    first.update(
        {
            "event_id": "trace-idem:event",
            "created_at": _now_iso(),
            "trace_id": "trace-idem-1",
            "actual_cost_usd": 0.25,
            "versions": {"code_sha": "idem-sha"},
        }
    )
    second = _event("trace-idem-call-2")
    second.update({"event_id": "trace-idem:event", "created_at": _now_iso(), "trace_id": "trace-idem-1", "actual_cost_usd": 10.0})

    assert client.post("/api/v1/ingest", headers=headers, json={"events": [first]}).status_code == 202
    duplicate = client.post("/api/v1/ingest", headers=headers, json={"events": [second]})
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicates"] == 1

    detail = client.get("/v1/traces/trace-idem-1", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["summary"]["span_count"] == 1
    assert payload["summary"]["total_cost_usd"] < 1


def test_trace_graph_is_project_scoped(client: TestClient) -> None:
    first_headers = {"X-Project-Id": "proj-flight-recorder-a"}
    second_headers = {"X-Project-Id": "proj-flight-recorder-b"}
    event = _event("trace-scope-call")
    event.update({"event_id": "trace-scope:event", "created_at": _now_iso(), "trace_id": "trace-scope-1", "user_input": "project-a"})

    assert client.post("/api/v1/ingest", headers=first_headers, json={"events": [event]}).status_code == 202

    allowed = client.get("/v1/traces/trace-scope-1", headers=first_headers)
    assert allowed.status_code == 200
    assert allowed.json()["summary"]["trace_id"] == "trace-scope-1"

    denied = client.get("/v1/traces/trace-scope-1", headers=second_headers)
    assert denied.status_code == 404


def test_idempotency_key_priority_is_explicit() -> None:
    key, source = ingest_routes._resolve_idempotency_key(
        event={"event_id": " event-1 ", "request_id": "request-1"},
        call_id="call-1",
    )
    assert key == "event-1"
    assert source == "event_id"

    key, source = ingest_routes._resolve_idempotency_key(
        event={"event_id": "", "request_id": " request-1 "},
        call_id="call-1",
    )
    assert key == "request-1"
    assert source == "request_id"

    key, source = ingest_routes._resolve_idempotency_key(event={}, call_id="call-1")
    assert key == "call-1"
    assert source == "call_id"


def test_batch_idempotency_header_does_not_collapse_distinct_events(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_keys: set[str] = set()

    def _fake_check(key: str) -> bool:
        return key in seen_keys

    def _fake_set(key: str) -> None:
        seen_keys.add(key)

    monkeypatch.setattr("app.api.routes.ingest._check_redis_idempotency", _fake_check)
    monkeypatch.setattr("app.api.routes.ingest._set_redis_idempotency", _fake_set)

    headers = {
        "X-Project-Id": "proj-ingest-idempotency-batch-1",
        "X-Idempotency-Key": "retry-batch-1",
    }
    payload = {
        "events": [
            _event("ingest-batch-idem-call-1"),
            _event("ingest-batch-idem-call-2"),
        ]
    }

    first = client.post("/api/v1/ingest", headers=headers, json=payload)
    assert first.status_code == 202
    assert first.json()["accepted"] == 2
    assert first.json()["duplicates"] == 0

    second = client.post("/api/v1/ingest", headers=headers, json=payload)
    assert second.status_code == 202
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 2


def test_redis_idempotency_key_is_tenant_scoped(client: TestClient) -> None:
    request = client.build_request(
        "POST",
        "/api/v1/ingest",
        headers={"X-Idempotency-Key": "retry-1"},
    )

    first = ingest_routes._extract_redis_idempotency_key(
        request=request,
        event={"event_id": "event-1"},
        call_id="call-1",
        tenant_id="tenant-a",
    )
    second = ingest_routes._extract_redis_idempotency_key(
        request=request,
        event={"event_id": "event-1"},
        call_id="call-1",
        tenant_id="tenant-b",
    )

    assert first == "tenant-a:retry-1:event-1"
    assert second == "tenant-b:retry-1:event-1"
    assert first != second


def test_ingest_preserves_sdk_cost_budget_loop_fields_when_cost_enrichment_degrades(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_enrich(*, tenant_id: str, payload: dict) -> dict:
        raise RuntimeError("pricing service unavailable")

    monkeypatch.setattr("app.api.routes.ingest.enrich_payload_with_cost_buckets", _raise_enrich)

    event = _sdk_0_1_event("ingest-sdk-cost-loop-1")
    event.update(
        {
            "actual_cost_usd": 0.456,
            "estimated_cost_usd": 0.5,
            "budget_remaining_usd": 9.544,
            "budget_action_taken": "allowed",
            "loop_action_taken": "observed",
            "loop_call_count": 3,
            "loop_cumulative_cost_usd": 1.234,
            "output_content": "Done.",
        }
    )

    headers = {"X-Project-Id": "proj-ingest-sdk-cost-loop-1"}
    response = client.post("/api/v1/ingest", headers=headers, json={"events": [event]})
    assert response.status_code == 202
    assert response.json()["accepted"] == 1

    detail = client.get("/v1/calls/ingest-sdk-cost-loop-1", headers=headers)
    assert detail.status_code == 200
    detail_payload = detail.json()
    payload = detail_payload["payload"]

    assert detail_payload["call"]["cost_usd"] == 0.456
    assert payload["actual_cost_usd"] == 0.456
    assert payload["estimated_cost_usd"] == 0.5
    assert payload["budget_remaining_usd"] == 9.544
    assert payload["budget_action_taken"] == "allowed"
    assert payload["loop_action_taken"] == "observed"
    assert payload["loop_call_count"] == 3
    assert payload["loop_cumulative_cost_usd"] == 1.234
    assert payload["total_cost_usd"] == 0.456


def test_ingest_cost_enrichment_failure_degrades_call_cost_confidence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_enrich(*, tenant_id: str, payload: dict) -> dict:
        raise RuntimeError("pricing service unavailable")

    monkeypatch.setattr("app.api.routes.ingest.enrich_payload_with_cost_buckets", _raise_enrich)

    headers = {"X-Project-Id": "proj-ingest-cost-degraded-fallback-1"}
    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-cost-degraded-fallback-1")]},
    )
    assert response.status_code == 202
    assert response.json()["accepted"] == 1

    call = client.get("/v1/calls/ingest-cost-degraded-fallback-1", headers=headers)
    assert call.status_code == 200
    payload = call.json()["payload"]
    assert payload["cost_confidence"] == "degraded"
    assert payload["cost"]["confidence_reason"] == "cost_enrichment_failed"
    assert payload["cost"]["per_call_breakdown"]["cost_confidence"] == "degraded"


def test_ingest_rate_limit_returns_429_with_retry_after(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGEST_SOFT_LIMIT_RPM", "2")
    monkeypatch.setenv("INGEST_BURST_LIMIT_RPM", "3")
    monkeypatch.setenv("INGEST_SUSTAINED_BREACH_THRESHOLD", "50")
    monkeypatch.setenv("INGEST_RATE_LIMIT_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()

    headers = {"X-Project-Id": f"proj-ingest-rate-{uuid4().hex[:8]}"}
    for idx in range(3):
        allowed = client.post(
            "/api/v1/ingest",
            headers=headers,
            json={"events": [_event(f"ingest-rate-{idx}")]},
        )
        assert allowed.status_code == 202

    blocked = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-rate-blocked")]},
    )
    assert blocked.status_code == 429
    retry_after = blocked.headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) >= 1


def test_sustained_ingest_breach_enables_backpressure_alert(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGEST_SOFT_LIMIT_RPM", "1")
    monkeypatch.setenv("INGEST_BURST_LIMIT_RPM", "1")
    monkeypatch.setenv("INGEST_SUSTAINED_BREACH_THRESHOLD", "2")
    monkeypatch.setenv("INGEST_BACKPRESSURE_TTL_SECONDS", "120")
    monkeypatch.setenv("INGEST_RATE_LIMIT_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()

    headers = {"X-Project-Id": f"proj-ingest-backpressure-{uuid4().hex[:8]}"}
    allowed = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-backpressure-1")]},
    )
    assert allowed.status_code == 202

    breach_one = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-backpressure-2")]},
    )
    assert breach_one.status_code == 429

    breach_two = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("ingest-backpressure-3")]},
    )
    assert breach_two.status_code == 429

    alerts = client.get("/v1/alerts", headers=headers)
    assert alerts.status_code == 200
    items = alerts.json()["items"]
    assert any(item["category"] == "INGEST_BACKPRESSURE" for item in items)
