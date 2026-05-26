import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Anomaly, Call, DiagnosisFeedback, DiagnosisJob, DiagnosisShareToken
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.anomalies import compute_fingerprint


@pytest.fixture()
def test_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_dashboard_phase0.db"
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
        id = "task-dashboard-phase0"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.live.SessionLocal", testing_session_local)
    monkeypatch.setattr("app.api.routes.diagnosis.process_diagnosis.delay", _mock_delay)

    with TestClient(app) as client:
        yield {
            "client": client,
            "SessionLocal": testing_session_local,
        }

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _create_project(client: TestClient, name: str) -> str:
    response = client.post("/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["project_id"]


def _insert_job(
    session_local,
    *,
    tenant_id: str,
    diagnosis_id: str,
    payload: dict,
    result: dict,
    status: str = "completed",
) -> None:
    now = datetime.now(timezone.utc)
    pricing_raw = payload.get("pricing_last_updated_at")
    pricing_last_updated_at = None
    if isinstance(pricing_raw, str) and pricing_raw.strip():
        pricing_last_updated_at = datetime.fromisoformat(pricing_raw.replace("Z", "+00:00"))
        if pricing_last_updated_at.tzinfo is None:
            pricing_last_updated_at = pricing_last_updated_at.replace(tzinfo=timezone.utc)
    total_tokens = int(payload.get("total_tokens") or payload.get("prompt_tokens") or 1)
    cost_total = float(payload.get("total_cost_usd") or payload.get("cost_usd") or 0.0)
    call_status = "error" if status in {"failed", "error", "errored", "timeout"} else "success"
    with session_local() as session:
        call = Call(
            id=diagnosis_id,
            project_id=tenant_id,
            event_id=f"event-{diagnosis_id}",
            created_at=now,
            provider=str(payload.get("provider") or "unknown"),
            model=str(payload.get("model") or "unknown"),
            status=call_status,
            latency_ms=float(payload.get("latency_ms")) if payload.get("latency_ms") is not None else None,
            input_tokens=int(payload.get("prompt_tokens") or total_tokens),
            output_tokens=int(payload.get("completion_tokens") or 0),
            reasoning_tokens=int(payload.get("reasoning_tokens") or 0),
            total_tokens=total_tokens,
            cost_total=cost_total,
            reasoning_cost_total=float(payload.get("reasoning_cost_usd") or 0.0),
            cache_savings_total=float(payload.get("cache_savings_usd") or 0.0),
            pricing_version=str(payload.get("pricing_version") or "test-pricing-v1"),
            pricing_source=str(payload.get("pricing_source") or "cached_rate_card"),
            pricing_last_updated_at=pricing_last_updated_at or now,
            cost_currency="USD",
            token_unit="tokens",
            exchange_rate_usd_to_inr=float(payload.get("exchange_rate_usd_to_inr") or 83.0),
            exchange_rate_timestamp=now,
            exchange_rate_source=str(payload.get("exchange_rate_source") or "test_rate_card"),
            cost_confidence=str(payload.get("cost_confidence") or "high"),
            confidence_reason=str(payload.get("confidence_reason") or "fresh_pricing_full_baseline"),
            payload_json=json.dumps(payload, separators=(",", ":")),
            metadata_json=json.dumps(
                {
                    "user_id": payload.get("user_id"),
                    "agent_name": payload.get("agent_name"),
                    "call_type": payload.get("call_type"),
                    "trace_id": payload.get("trace_id"),
                    "parent_call_id": payload.get("parent_call_id"),
                },
                separators=(",", ":"),
            ),
        )
        session.add(call)
        session.add(
            DiagnosisJob(
                tenant_id=tenant_id,
                diagnosis_id=diagnosis_id,
                call_id=diagnosis_id,
                status=status,
                payload_json=json.dumps(payload, separators=(",", ":")),
                result_json=json.dumps(result, separators=(",", ":")),
                error_message=None,
            )
        )
        session.commit()


def test_calls_list_and_detail(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Calls Project")
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-calls-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "agent_name": "research-agent",
            "user_id": "user-123",
            "call_type": "chat",
            "prompt_tokens": 120,
            "completion_tokens": 44,
            "total_tokens": 164,
            "cost_usd": 0.023,
            "pricing_version": "1.0",
            "pricing_last_updated_at": "2026-04-21T00:00:00+00:00",
            "pricing_age_days": 4,
            "cost_confidence": "high",
            "latency_ms": 310,
        },
        result={
            "diagnoses": [
                {
                    "category": "TOKEN_OVERFLOW",
                    "root_cause": "Prompt exceeded model context",
                    "evidence": {"prompt_tokens": 4300, "model_limit": 4096},
                }
            ],
            "blast_radius": {"downstream_affected_calls": 2, "wasted_cost_usd": 1.2},
        },
    )

    headers = {"X-Project-Id": project_id}
    list_response = client.get("/v1/calls", headers=headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["call_id"] == "diag-calls-1"
    assert list_payload["items"][0]["model"] == "gpt-4o"
    assert list_payload["items"][0]["pricing_age_days"] >= 0
    assert list_payload["items"][0]["cost_confidence"] == "high"

    detail_response = client.get("/v1/calls/diag-calls-1", headers=headers)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["call"]["call_id"] == "diag-calls-1"
    assert detail_payload["call"]["pricing_last_updated_at"] == "2026-04-21T00:00:00+00:00"
    assert detail_payload["feedback_summary"]["helpful_count"] == 0

    feedback_response = client.post(
        "/v1/diagnosis/diag-calls-1/feedback",
        headers=headers,
        json={"was_helpful": True, "developer_note": "Good fix"},
    )
    assert feedback_response.status_code == 201

    detail_after_feedback = client.get("/v1/calls/diag-calls-1", headers=headers)
    assert detail_after_feedback.status_code == 200
    assert detail_after_feedback.json()["feedback_summary"]["helpful_count"] == 1


def test_calls_list_supports_user_id_filter_alias(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Calls User Filter Project")
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-user-filter-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "user-alpha",
            "call_type": "chat",
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "total_tokens": 125,
            "cost_usd": 0.02,
        },
        result={"diagnoses": []},
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-user-filter-2",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "user-beta",
            "call_type": "chat",
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "cost_usd": 0.03,
        },
        result={"diagnoses": []},
    )

    headers = {"X-Project-Id": project_id}

    filtered_by_user_id = client.get("/v1/calls?user_id=user-alpha", headers=headers)
    assert filtered_by_user_id.status_code == 200
    payload_user_id = filtered_by_user_id.json()
    assert payload_user_id["total"] == 1
    assert payload_user_id["items"][0]["call_id"] == "diag-user-filter-1"
    assert isinstance(payload_user_id["items"][0]["user_id"], str)
    assert payload_user_id["items"][0]["user_id"].strip() != ""

    filtered_by_legacy_user = client.get("/v1/calls?user=user-beta", headers=headers)
    assert filtered_by_legacy_user.status_code == 200
    payload_legacy_user = filtered_by_legacy_user.json()
    assert payload_legacy_user["total"] == 1
    assert payload_legacy_user["items"][0]["call_id"] == "diag-user-filter-2"
    assert isinstance(payload_legacy_user["items"][0]["user_id"], str)
    assert payload_legacy_user["items"][0]["user_id"].strip() != ""


def test_call_trace_tree_endpoint(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Trace Tree Project")
    trace_id = "trace-tree-1"

    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-trace-root",
        status="failed",
        payload={
            "trace_id": trace_id,
            "parent_call_id": None,
            "agent_name": "orchestrator-agent",
            "provider": "openai",
            "model": "gpt-4o",
            "cost_confidence": "stale",
            "cost_usd": 1.2,
        },
        result={
            "diagnoses": [
                {
                    "category": "RATE_LIMIT",
                    "root_cause": "Root planner hit provider throttling",
                }
            ]
        },
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-trace-child-1",
        status="failed",
        payload={
            "trace_id": trace_id,
            "parent_call_id": "diag-trace-root",
            "agent_name": "retriever-agent",
            "provider": "anthropic",
            "model": "claude-sonnet",
            "cost_confidence": "high",
            "cost_usd": 0.8,
        },
        result={"diagnoses": []},
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-trace-child-2",
        status="completed",
        payload={
            "trace_id": trace_id,
            "parent_call_id": "diag-trace-child-1",
            "agent_name": "tool-agent",
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "cost_confidence": "degraded",
            "cost_usd": 0.3,
        },
        result={"diagnoses": []},
    )

    headers = {"X-Project-Id": project_id}
    trace_response = client.get("/v1/calls/diag-trace-root/trace-tree", headers=headers)
    assert trace_response.status_code == 200

    trace_payload = trace_response.json()
    assert trace_payload["call_id"] == "diag-trace-root"
    assert trace_payload["trace_id"] == trace_id
    assert trace_payload["root_failure"]["category"] == "RATE_LIMIT"
    assert trace_payload["total_downstream_calls"] == 2
    assert trace_payload["total_wasted_cost_usd"] >= 2.0

    root_node = trace_payload["root_node"]
    assert root_node["call_id"] == "diag-trace-root"
    assert root_node["agent_name"] == "orchestrator-agent"
    assert root_node["provider"] == "openai"
    assert root_node["model"] == "gpt-4o"
    assert root_node["cost_confidence"] == "stale"
    assert len(root_node["children"]) == 1
    assert root_node["children"][0]["call_id"] == "diag-trace-child-1"
    assert root_node["children"][0]["provider"] == "anthropic"
    assert root_node["children"][0]["model"] == "claude-sonnet"
    assert root_node["children"][0]["cost_confidence"] == "high"
    assert root_node["children"][0]["children"][0]["call_id"] == "diag-trace-child-2"
    assert root_node["children"][0]["children"][0]["provider"] == "openai"
    assert root_node["children"][0]["children"][0]["model"] == "gpt-4.1-mini"
    assert root_node["children"][0]["children"][0]["cost_confidence"] == "degraded"


def test_call_trace_tree_cycle_guard(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Trace Tree Cycle Guard Project")
    trace_id = "trace-tree-cycle-1"

    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-trace-cycle-root",
        status="failed",
        payload={
            "trace_id": trace_id,
            "parent_call_id": "diag-trace-cycle-child",
            "agent_name": "root-agent",
            "cost_usd": 0.9,
        },
        result={"diagnoses": []},
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-trace-cycle-child",
        status="failed",
        payload={
            "trace_id": trace_id,
            "parent_call_id": "diag-trace-cycle-root",
            "agent_name": "child-agent",
            "cost_usd": 0.4,
        },
        result={"diagnoses": []},
    )

    headers = {"X-Project-Id": project_id}
    trace_response = client.get("/v1/calls/diag-trace-cycle-root/trace-tree", headers=headers)
    assert trace_response.status_code == 200

    trace_payload = trace_response.json()
    root_node = trace_payload["root_node"]
    assert root_node["call_id"] == "diag-trace-cycle-root"
    assert len(root_node["children"]) == 1
    child_node = root_node["children"][0]
    assert child_node["call_id"] == "diag-trace-cycle-child"
    assert child_node["children"] == []


def test_analytics_and_budget_endpoints(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Analytics Project")
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-analytics-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "u1",
            "cost_usd": 0.10,
            "reasoning_cost_usd": 0.04,
            "cache_savings_usd": 0.02,
            "latency_ms": 500,
        },
        result={"diagnoses": []},
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-analytics-2",
        payload={
            "provider": "anthropic",
            "model": "claude-sonnet",
            "user_id": "u2",
            "cost_usd": 0.25,
            "reasoning_cost_usd": 0.05,
            "cache_savings_usd": 0.08,
            "latency_ms": 800,
        },
        result={
            "diagnoses": [
                {
                    "category": "RATE_LIMIT",
                    "root_cause": "Provider returned 429",
                    "evidence": {"status_code": 429},
                }
            ]
        },
    )

    headers = {"X-Project-Id": project_id}

    summary = client.get("/v1/analytics/summary", headers=headers)
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["calls_today"] >= 2
    assert summary_payload["cost_today_usd"] > 0
    assert "fix_adoption" in summary_payload
    assert "feedback_loop" in summary_payload
    assert summary_payload["fix_adoption"]["viewed_diagnoses"] >= 0
    assert summary_payload["fix_adoption"]["resolved_diagnoses"] >= 0
    assert summary_payload["fix_adoption"]["status_band"] in {"strong", "warning", "critical"}
    assert summary_payload["feedback_loop"]["feedback_total"] >= 0
    assert summary_payload["feedback_loop"]["thumbs_down_total"] >= 0
    assert isinstance(summary_payload["feedback_loop"]["by_category"], list)

    health = client.get("/v1/analytics/health-score", headers=headers)
    assert health.status_code == 200
    health_payload = health.json()
    assert "health_score" in health_payload
    assert "details" in health_payload

    by_model = client.get("/v1/analytics/cost/by-model", headers=headers)
    assert by_model.status_code == 200
    assert len(by_model.json()["items"]) >= 1

    activity_feed = client.get("/v1/analytics/activity-feed", headers=headers)
    assert activity_feed.status_code == 200
    activity_payload = activity_feed.json()
    assert "items" in activity_payload
    assert isinstance(activity_payload["items"], list)

    daily_trend = client.get("/v1/analytics/cost/daily-trend", headers=headers)
    assert daily_trend.status_code == 200
    daily_trend_payload = daily_trend.json()
    assert "pricing_last_updated_at" in daily_trend_payload
    assert "pricing_age_days" in daily_trend_payload
    assert daily_trend_payload["cost_confidence"] in {"high", "stale", "degraded", "unknown"}

    budget_put = client.put(
        "/v1/analytics/budget",
        headers=headers,
        json={"monthly_limit_usd": 250.0, "threshold_percentage": 85},
    )
    assert budget_put.status_code == 200
    assert budget_put.json()["threshold_percentage"] == 85.0


def test_summary_unusual_activity_multiplier_and_fields(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Unusual Activity Project")

    for index in range(10):
        _insert_job(
            session_local,
            tenant_id=project_id,
            diagnosis_id=f"diag-unusual-noisy-{index}",
            payload={
                "provider": "openai",
                "model": "gpt-4o",
                "user_id": "noisy-user",
                "cost_usd": 0.35,
                "latency_ms": 520,
            },
            result={"diagnoses": []},
        )

    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-unusual-normal-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "user_id": "normal-user-1",
            "cost_usd": 0.03,
            "latency_ms": 210,
        },
        result={"diagnoses": []},
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-unusual-normal-2",
        payload={
            "provider": "anthropic",
            "model": "claude-sonnet",
            "user_id": "normal-user-2",
            "cost_usd": 0.04,
            "latency_ms": 240,
        },
        result={"diagnoses": []},
    )

    headers = {"X-Project-Id": project_id}
    summary = client.get("/v1/analytics/summary", headers=headers)
    assert summary.status_code == 200

    payload = summary.json()
    unusual = payload.get("unusual_activity")
    assert isinstance(unusual, dict)
    assert unusual["impacted_user"] == "noisy-user"
    assert unusual["anomaly_multiplier"] >= 2.0
    assert unusual["call_multiplier"] >= 2.0
    assert unusual["cost_multiplier"] >= 2.0
    assert unusual["current_calls"] == 10
    assert unusual["normal_calls_per_user"] > 0
    assert unusual["current_cost_usd"] > unusual["normal_cost_per_user_usd"]
    assert isinstance(unusual["suggested_action"], str)
    assert unusual["suggested_action"]


def test_summary_tracks_fix_adoption_and_feedback_visibility_by_category(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Adoption Feedback Project")

    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-adoption-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "dev-1",
            "cost_usd": 0.12,
            "latency_ms": 410,
        },
        result={
            "diagnoses": [
                {
                    "category": "RATE_LIMIT",
                    "root_cause": "Provider returned 429",
                }
            ]
        },
    )
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-adoption-2",
        payload={
            "provider": "anthropic",
            "model": "claude-sonnet",
            "user_id": "dev-2",
            "cost_usd": 0.09,
            "latency_ms": 320,
        },
        result={
            "diagnoses": [
                {
                    "category": "AUTH_FAILURE",
                    "root_cause": "Invalid key",
                }
            ]
        },
    )

    headers = {"X-Project-Id": project_id}

    view_one = client.get("/v1/calls/diag-adoption-1", headers=headers)
    assert view_one.status_code == 200
    view_one_repeat = client.get("/v1/calls/diag-adoption-1", headers=headers)
    assert view_one_repeat.status_code == 200
    view_two = client.get("/v1/calls/diag-adoption-2", headers=headers)
    assert view_two.status_code == 200

    resolve_one = client.post("/v1/diagnosis/diag-adoption-1/resolve", headers=headers)
    assert resolve_one.status_code == 200

    feedback_down = client.post(
        "/v1/diagnosis/diag-adoption-1/feedback",
        headers=headers,
        json={"was_helpful": False, "developer_note": "Fix did not work"},
    )
    assert feedback_down.status_code == 201

    feedback_up = client.post(
        "/v1/diagnosis/diag-adoption-2/feedback",
        headers=headers,
        json={"was_helpful": True, "developer_note": "Worked"},
    )
    assert feedback_up.status_code == 201

    summary = client.get("/v1/analytics/summary", headers=headers)
    assert summary.status_code == 200
    payload = summary.json()

    fix_adoption = payload["fix_adoption"]
    assert fix_adoption["viewed_diagnoses"] == 2
    assert fix_adoption["resolved_diagnoses"] == 1
    assert fix_adoption["adoption_rate_percent"] == 50.0
    assert fix_adoption["status_band"] == "strong"

    feedback_loop = payload["feedback_loop"]
    assert feedback_loop["feedback_total"] == 2
    assert feedback_loop["thumbs_down_total"] == 1
    assert feedback_loop["thumbs_down_rate_percent"] == 50.0

    by_category = {item["category"]: item for item in feedback_loop["by_category"]}
    assert by_category["RATE_LIMIT"]["feedback_total"] == 1
    assert by_category["RATE_LIMIT"]["thumbs_down_count"] == 1
    assert by_category["RATE_LIMIT"]["thumbs_down_rate_percent"] == 100.0
    assert by_category["AUTH_FAILURE"]["feedback_total"] == 1
    assert by_category["AUTH_FAILURE"]["thumbs_down_count"] == 0
    assert by_category["AUTH_FAILURE"]["thumbs_down_rate_percent"] == 0.0


def test_alerts_lifecycle_and_channel_test(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Alerts Project")
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-alert-1",
        payload={"provider": "openai", "model": "gpt-4o", "cost_usd": 0.2},
        result={
            "diagnoses": [
                {
                    "category": "AUTH_FAILURE",
                    "root_cause": "Invalid API key",
                    "evidence": {"status_code": 401},
                }
            ]
        },
    )

    headers = {"X-Project-Id": project_id}
    alerts = client.get("/v1/alerts", headers=headers)
    assert alerts.status_code == 200
    alerts_payload = alerts.json()
    assert alerts_payload["total"] >= 1
    alert_id = alerts_payload["items"][0]["alert_id"]

    ack = client.post(f"/v1/alerts/{alert_id}/acknowledge", headers=headers)
    assert ack.status_code == 200
    assert ack.json()["status"] == "ACKNOWLEDGED"

    resolve = client.post(f"/v1/alerts/{alert_id}/resolve", headers=headers)
    assert resolve.status_code == 200
    assert resolve.json()["status"] == "RESOLVED"

    reopen = client.post(f"/v1/alerts/{alert_id}/reopen", headers=headers)
    assert reopen.status_code == 200
    assert reopen.json()["status"] == "OPEN"

    channel_test = client.post("/v1/alerts/channel-test", headers=headers, json={"channel": "email"})
    assert channel_test.status_code == 200
    assert channel_test.json()["status"] == "queued"


def test_live_calls_sse_snapshot(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Live Feed Project")
    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-live-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "live-user",
            "cost_usd": 0.05,
            "latency_ms": 220,
        },
        result={"diagnoses": []},
    )

    headers = {"X-Project-Id": project_id}
    response = client.get("/v1/live/calls?limit=5&poll_interval_ms=500&max_events=1", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    lines = [line for line in response.text.splitlines() if line.strip()]
    event_line = next((line for line in lines if line.startswith("event:")), "")
    payload_line = next((line for line in lines if line.startswith("data:")), "")

    assert event_line == "event: snapshot"
    assert payload_line.startswith("data:")

    payload = json.loads(payload_line.replace("data:", "", 1).strip())
    assert isinstance(payload.get("items"), list)
    assert payload["items"][0]["call_id"] == "diag-live-1"


def test_onboarding_and_settings_endpoints(test_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash Settings Project")
    headers = {"X-Project-Id": project_id}

    monkeypatch.setattr(
        "app.api.routes.settings.verify_provider_connection",
        lambda provider: {
            "provider": provider,
            "verified": True,
            "provider_status": "operational",
            "message": "Provider check succeeded with status 'operational'.",
            "last_error": None,
            "checked_at": datetime.now(timezone.utc),
            "status_fetch_timeout_ms": 800,
            "status_cache_ttl_seconds": 300,
            "status_fallback_used": False,
        },
    )

    onboarding = client.post(
        "/v1/onboarding/trigger-test-failure",
        headers=headers,
        json={"category": "TOKEN_OVERFLOW"},
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["synthetic"] is True

    project_settings = client.get("/v1/settings/project", headers=headers)
    assert project_settings.status_code == 200
    assert project_settings.json()["project_id"] == project_id

    pii_update = client.put(
        "/v1/settings/pii-policy",
        headers=headers,
        json={"custom_patterns": ["ACC-[0-9]{4}"]},
    )
    assert pii_update.status_code == 200
    assert pii_update.json()["custom_patterns"] == ["ACC-[0-9]{4}"]

    pii_test = client.post(
        "/v1/settings/pii-policy/test-detector",
        headers=headers,
        json={"pattern": "ACC-[0-9]{4}", "sample_text": "ticket ACC-1234 opened"},
    )
    assert pii_test.status_code == 200
    assert pii_test.json()["valid"] is True
    assert pii_test.json()["match_count"] == 1

    retention = client.put("/v1/settings/retention", headers=headers, json={"retention_days": 45})
    assert retention.status_code == 200
    assert retention.json()["retention_days"] == 45

    notifications = client.put(
        "/v1/settings/notifications",
        headers=headers,
        json={
            "email_enabled": True,
            "slack_enabled": True,
            "browser_enabled": True,
            "terminal_enabled": False,
        },
    )
    assert notifications.status_code == 200
    assert notifications.json()["slack_enabled"] is True

    providers = client.get("/v1/settings/provider-verifications", headers=headers)
    assert providers.status_code == 200

    provider_test = client.post("/v1/settings/provider-verifications/openai/test", headers=headers)
    assert provider_test.status_code == 200
    assert provider_test.json()["status"] == "verified"

    pricing_lock_too_early = client.put(
        "/v1/settings/pricing-validation",
        headers=headers,
        json={
            "selected_launch_model": "tiered",
            "rationale": "Need lock without enough evidence",
            "migration_path": "n/a",
            "interviews": [
                {
                    "developer_ref": "dev-1",
                    "preferred_model": "tiered",
                    "fairness_score": 4.0,
                    "call_volume_context": "10k/month",
                    "notes": "looks fair",
                    "interviewed_at": "2026-04-25T10:00:00+00:00",
                }
            ],
            "lock_pricing_decision": True,
        },
    )
    assert pricing_lock_too_early.status_code == 400

    pricing_update = client.put(
        "/v1/settings/pricing-validation",
        headers=headers,
        json={
            "selected_launch_model": "tiered",
            "rationale": "Tiered model scored highest on willingness and fairness.",
            "migration_path": "Re-evaluate after 60 days with paid conversion data.",
            "interviews": [
                {
                    "developer_ref": f"dev-{index}",
                    "preferred_model": "tiered" if index < 4 else "usage_based",
                    "fairness_score": 4.0,
                    "call_volume_context": "25k/month",
                    "notes": "beta feedback",
                    "interviewed_at": f"2026-04-25T1{index}:00:00+00:00",
                }
                for index in range(5)
            ],
            "lock_pricing_decision": True,
        },
    )
    assert pricing_update.status_code == 200
    pricing_payload = pricing_update.json()
    assert pricing_payload["pricing_locked"] is True
    assert pricing_payload["interview_count"] == 5
    assert pricing_payload["unique_developer_count"] == 5
    assert pricing_payload["required_interviews"] == 5
    assert pricing_payload["missing_interviews"] == 0
    assert pricing_payload["minimum_interviews_met"] is True
    assert pricing_payload["launch_gate_passed"] is True
    assert pricing_payload["blockers"] == []

    pricing_update_after_lock = client.put(
        "/v1/settings/pricing-validation",
        headers=headers,
        json={
            "selected_launch_model": "usage_based",
            "rationale": "Attempting to modify lock",
            "migration_path": "n/a",
            "interviews": [],
            "lock_pricing_decision": False,
        },
    )
    assert pricing_update_after_lock.status_code == 409

    rollback_invalid_pass = client.put(
        "/v1/settings/rollback-drill",
        headers=headers,
        json={
            "deploy_revision": "rev-200",
            "rollback_revision": "rev-199",
            "deploy_test_passed": True,
            "rollback_test_passed": True,
            "failure_simulation_performed": False,
            "failure_simulation_category": None,
            "failure_simulation_notes": "",
            "drill_notes": "",
            "status": "passed",
        },
    )
    assert rollback_invalid_pass.status_code == 400

    rollback_update = client.put(
        "/v1/settings/rollback-drill",
        headers=headers,
        json={
            "deploy_revision": "rev-200",
            "rollback_revision": "rev-199",
            "deploy_test_passed": True,
            "rollback_test_passed": True,
            "failure_simulation_performed": True,
            "failure_simulation_category": "TOKEN_OVERFLOW",
            "failure_simulation_notes": "Triggered synthetic TOKEN_OVERFLOW and verified alert path.",
            "drill_notes": "Rollback stable within 3 minutes.",
            "status": "passed",
        },
    )
    assert rollback_update.status_code == 200
    rollback_payload = rollback_update.json()
    assert rollback_payload["status"] == "passed"
    assert rollback_payload["failure_simulation_performed"] is True
    assert rollback_payload["completed_at"] is not None


def test_pricing_validation_rejects_duplicate_developer_refs(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash Pricing Duplicate Ref Project")
    headers = {"X-Project-Id": project_id}

    response = client.put(
        "/v1/settings/pricing-validation",
        headers=headers,
        json={
            "selected_launch_model": "tiered",
            "rationale": "Evidence collection in progress",
            "migration_path": "n/a",
            "interviews": [
                {
                    "developer_ref": "beta-dev-1",
                    "preferred_model": "tiered",
                    "fairness_score": 4.0,
                    "call_volume_context": "30k/month",
                    "notes": "first session",
                    "interviewed_at": "2026-04-25T10:00:00+00:00",
                },
                {
                    "developer_ref": "BETA-DEV-1",
                    "preferred_model": "usage_based",
                    "fairness_score": 3.8,
                    "call_volume_context": "28k/month",
                    "notes": "duplicate ref by case",
                    "interviewed_at": "2026-04-25T11:00:00+00:00",
                },
            ],
            "lock_pricing_decision": False,
        },
    )
    assert response.status_code == 400
    assert "Duplicate developer_ref" in response.json()["detail"]


def test_rollback_drill_pass_blocked_when_pricing_gate_incomplete(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash Rollback Pricing Gate Project")
    headers = {"X-Project-Id": project_id}

    rollback_update = client.put(
        "/v1/settings/rollback-drill",
        headers=headers,
        json={
            "deploy_revision": "rev-500",
            "rollback_revision": "rev-499",
            "deploy_test_passed": True,
            "rollback_test_passed": True,
            "failure_simulation_performed": True,
            "failure_simulation_category": "TOKEN_OVERFLOW",
            "failure_simulation_notes": "sim complete",
            "drill_notes": "all operational checks done",
            "status": "passed",
        },
    )
    assert rollback_update.status_code == 400
    assert "Pricing validation launch gate is not complete" in rollback_update.json()["detail"]


def test_rollback_drill_verify_endpoint_sets_phase_flags(test_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash Rollback Verify Project")
    headers = {"X-Project-Id": project_id}

    monkeypatch.setenv("ENABLE_READY_DB_CHECK", "true")
    monkeypatch.setenv("ENABLE_READY_REDIS_CHECK", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.api.routes.settings.db_healthcheck", lambda: True)
    monkeypatch.setattr("app.api.routes.settings.redis_healthcheck", lambda: True)

    try:
        deploy_verify = client.post(
            "/v1/settings/rollback-drill/verify",
            headers=headers,
            json={"phase": "deploy", "deploy_revision": "rev-610"},
        )
        assert deploy_verify.status_code == 200
        deploy_payload = deploy_verify.json()
        assert deploy_payload["phase"] == "deploy"
        assert deploy_payload["passed"] is True
        check_map = {item["name"]: item for item in deploy_payload["checks"]}
        assert check_map["database"]["status"] == "ok"
        assert check_map["redis"]["status"] == "ok"
        assert deploy_payload["rollback_drill"]["deploy_revision"] == "rev-610"
        assert deploy_payload["rollback_drill"]["deploy_test_passed"] is True
        assert deploy_payload["rollback_drill"]["rollback_test_passed"] is False

        rollback_verify = client.post(
            "/v1/settings/rollback-drill/verify",
            headers=headers,
            json={"phase": "rollback", "rollback_revision": "rev-609"},
        )
        assert rollback_verify.status_code == 200
        rollback_payload = rollback_verify.json()
        assert rollback_payload["phase"] == "rollback"
        assert rollback_payload["passed"] is True
        assert rollback_payload["rollback_drill"]["rollback_revision"] == "rev-609"
        assert rollback_payload["rollback_drill"]["rollback_test_passed"] is True
    finally:
        get_settings.cache_clear()


def test_rollback_drill_verify_endpoint_reports_failed_checks(test_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash Rollback Verify Failure Project")
    headers = {"X-Project-Id": project_id}

    monkeypatch.setenv("ENABLE_READY_DB_CHECK", "true")
    monkeypatch.setenv("ENABLE_READY_REDIS_CHECK", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.api.routes.settings.db_healthcheck", lambda: True)
    monkeypatch.setattr("app.api.routes.settings.redis_healthcheck", lambda: False)

    try:
        rollback_verify = client.post(
            "/v1/settings/rollback-drill/verify",
            headers=headers,
            json={"phase": "rollback", "rollback_revision": "rev-702"},
        )
        assert rollback_verify.status_code == 200
        payload = rollback_verify.json()
        assert payload["phase"] == "rollback"
        assert payload["passed"] is False
        check_map = {item["name"]: item for item in payload["checks"]}
        assert check_map["database"]["status"] == "ok"
        assert check_map["redis"]["status"] == "failed"
        assert payload["rollback_drill"]["rollback_test_passed"] is False
    finally:
        get_settings.cache_clear()


def test_retention_data_erasure_endpoint_dry_run_and_delete(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Dash Retention Erasure Project")
    now = datetime.now(timezone.utc)

    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-erase-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "erase-user",
            "cost_usd": 0.07,
            "latency_ms": 210,
        },
        result={"diagnoses": []},
    )

    with session_local() as session:
        session.add(
            DiagnosisShareToken(
                tenant_id=project_id,
                diagnosis_id="diag-erase-1",
                token_prefix="tok_erase",
                token_hash="hash_erase",
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        )
        session.commit()

    headers = {"X-Project-Id": project_id}
    feedback = client.post(
        "/v1/diagnosis/diag-erase-1/feedback",
        headers=headers,
        json={"was_helpful": False, "developer_note": "cleanup"},
    )
    assert feedback.status_code == 201

    dry_run = client.delete(
        "/v1/settings/retention/data?dry_run=true&batch_size=25",
        headers=headers,
    )
    assert dry_run.status_code == 200
    dry_payload = dry_run.json()
    assert dry_payload["tenant_id"] == project_id
    assert dry_payload["dry_run"] is True
    assert dry_payload["deleted_by_table"]["calls"] == 1
    assert dry_payload["deleted_by_table"]["diagnosis_jobs"] == 1
    assert dry_payload["deleted_by_table"]["diagnosis_feedback"] == 1
    assert dry_payload["deleted_by_table"]["diagnosis_share_tokens"] == 1
    assert dry_payload["total_deleted"] == 4

    with session_local() as session:
        assert session.execute(select(Call).where(Call.project_id == project_id)).scalars().all() != []
        assert session.execute(select(DiagnosisJob).where(DiagnosisJob.tenant_id == project_id)).scalars().all() != []
        assert (
            session.execute(select(DiagnosisFeedback).where(DiagnosisFeedback.tenant_id == project_id))
            .scalars()
            .all()
            != []
        )
        assert (
            session.execute(select(DiagnosisShareToken).where(DiagnosisShareToken.tenant_id == project_id))
            .scalars()
            .all()
            != []
        )

    erase = client.delete("/v1/settings/retention/data?batch_size=25", headers=headers)
    assert erase.status_code == 200
    erase_payload = erase.json()
    assert erase_payload["tenant_id"] == project_id
    assert erase_payload["dry_run"] is False
    assert erase_payload["deleted_by_table"]["calls"] == 1
    assert erase_payload["deleted_by_table"]["diagnosis_jobs"] == 1
    assert erase_payload["deleted_by_table"]["diagnosis_feedback"] == 1
    assert erase_payload["deleted_by_table"]["diagnosis_share_tokens"] == 1
    assert erase_payload["total_deleted"] == 4

    with session_local() as session:
        assert session.execute(select(Call).where(Call.project_id == project_id)).scalars().all() == []
        assert session.execute(select(DiagnosisJob).where(DiagnosisJob.tenant_id == project_id)).scalars().all() == []
        assert (
            session.execute(select(DiagnosisFeedback).where(DiagnosisFeedback.tenant_id == project_id))
            .scalars()
            .all()
            == []
        )
        assert (
            session.execute(select(DiagnosisShareToken).where(DiagnosisShareToken.tenant_id == project_id))
            .scalars()
            .all()
            == []
        )


def test_retention_data_erasure_requires_admin_role(test_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client: TestClient = test_ctx["client"]

    project_id = _create_project(client, "Dash Retention Role Project")
    api_key_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"name": "retention-member-key"},
    )
    assert api_key_response.status_code == 201
    api_key = api_key_response.json()["api_key"]

    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    get_settings.cache_clear()

    try:
        forbidden = client.delete(
            "/v1/settings/retention/data",
            headers={"X-Api-Key": api_key},
        )
        assert forbidden.status_code == 403
    finally:
        get_settings.cache_clear()


def test_provider_alias_endpoints(test_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]
    project_id = _create_project(client, "Dash Provider Alias Project")
    headers = {"X-Project-Id": project_id}

    monkeypatch.setattr(
        "app.api.routes.settings.verify_provider_connection",
        lambda provider: {
            "provider": provider,
            "verified": True,
            "provider_status": "operational",
            "message": "Provider check succeeded with status 'operational'.",
            "last_error": None,
            "checked_at": datetime.now(timezone.utc),
            "status_fetch_timeout_ms": 800,
            "status_cache_ttl_seconds": 300,
            "status_fallback_used": False,
        },
    )

    _insert_job(
        session_local,
        tenant_id=project_id,
        diagnosis_id="diag-provider-alias-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "cost_usd": 0.07,
        },
        result={"diagnoses": []},
    )

    status_before = client.get("/v1/providers/status", headers=headers)
    assert status_before.status_code == 200
    providers_before = {item["provider"]: item for item in status_before.json()["items"]}
    assert "openai" in providers_before

    test_connection = client.post("/v1/providers/openai/test", headers=headers)
    assert test_connection.status_code == 200
    assert test_connection.json()["status"] == "verified"

    status_after = client.get("/v1/providers/status", headers=headers)
    assert status_after.status_code == 200
    providers_after = {item["provider"]: item for item in status_after.json()["items"]}
    assert providers_after["openai"]["status"] == "verified"

    status_after_api = client.get("/api/v1/providers/status", headers=headers)
    assert status_after_api.status_code == 200
    providers_after_api = {item["provider"]: item for item in status_after_api.json()["items"]}
    assert providers_after_api["openai"]["status"] == "verified"


def test_provider_test_surfaces_failed_reason(test_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash Provider Failure Project")
    headers = {"X-Project-Id": project_id}

    monkeypatch.setattr(
        "app.api.routes.settings.verify_provider_connection",
        lambda provider: {
            "provider": provider,
            "verified": False,
            "provider_status": "unknown",
            "message": "Provider status endpoint is not configured for this provider.",
            "last_error": "Provider status endpoint is not configured for this provider.",
            "checked_at": datetime.now(timezone.utc),
            "status_fetch_timeout_ms": 800,
            "status_cache_ttl_seconds": 300,
            "status_fallback_used": True,
        },
    )

    test_connection = client.post("/v1/providers/openai/test", headers=headers)
    assert test_connection.status_code == 200
    assert test_connection.json()["status"] == "failed"
    assert "not configured" in test_connection.json()["message"]

    status_after = client.get("/v1/providers/status", headers=headers)
    assert status_after.status_code == 200
    providers_after = {item["provider"]: item for item in status_after.json()["items"]}
    assert providers_after["openai"]["status"] == "failed"
    assert "not configured" in str(providers_after["openai"]["last_error"])


def test_export_endpoint_is_tenant_scoped(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_a = _create_project(client, "Dash Export Project A")
    project_b = _create_project(client, "Dash Export Project B")

    _insert_job(
        session_local,
        tenant_id=project_a,
        diagnosis_id="diag-export-a-1",
        payload={
            "provider": "openai",
            "model": "gpt-4o",
            "user_id": "export-user-a",
            "cost_usd": 0.11,
            "latency_ms": 330,
        },
        result={
            "diagnoses": [
                {
                    "category": "TOKEN_OVERFLOW",
                    "root_cause": "Prompt exceeded",
                }
            ]
        },
    )
    _insert_job(
        session_local,
        tenant_id=project_b,
        diagnosis_id="diag-export-b-1",
        payload={
            "provider": "anthropic",
            "model": "claude-sonnet",
            "user_id": "export-user-b",
            "cost_usd": 0.25,
            "latency_ms": 910,
        },
        result={
            "diagnoses": [
                {
                    "category": "AUTH_FAILURE",
                    "root_cause": "Bad key",
                }
            ]
        },
    )

    headers_a = {"X-Project-Id": project_a}
    export_response = client.get("/v1/export?limit=20", headers=headers_a)
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert export_payload["tenant_id"] == project_a
    assert export_payload["diagnosis_count"] == 1
    assert export_payload["call_count"] == 1
    assert export_payload["diagnoses"][0]["diagnosis_id"] == "diag-export-a-1"
    assert export_payload["calls"][0]["call"]["call_id"] == "diag-export-a-1"

    category_filtered = client.get("/v1/export?category=AUTH_FAILURE", headers=headers_a)
    assert category_filtered.status_code == 200
    assert category_filtered.json()["diagnosis_count"] == 0

    payload_excluded = client.get("/v1/export?include_payload=false", headers=headers_a)
    assert payload_excluded.status_code == 200
    assert payload_excluded.json()["calls"][0]["payload"] == {}

    export_alias = client.get("/api/v1/export?limit=20", headers=headers_a)
    assert export_alias.status_code == 200
    assert export_alias.json()["tenant_id"] == project_a


def test_diagnoses_plural_alias_paths(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    headers = {"X-Project-Id": "proj-diagnoses-alias-1"}

    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-alias-1",
            "payload": {
                "provider": "openai",
                "model": "gpt-4o",
                "prompt_tokens": 4100,
                "model_limit_tokens": 4096,
            },
        },
    )
    assert submit.status_code == 200

    list_alias = client.get("/api/v1/diagnoses", headers=headers)
    assert list_alias.status_code == 200
    assert any(item["diagnosis_id"] == "diag-alias-1" for item in list_alias.json())

    status_alias = client.get("/api/v1/diagnoses/diag-alias-1", headers=headers)
    assert status_alias.status_code == 200
    assert status_alias.json()["diagnosis_id"] == "diag-alias-1"

    feedback_alias = client.post(
        "/api/v1/diagnoses/diag-alias-1/feedback",
        headers=headers,
        json={"was_helpful": True, "developer_note": "good"},
    )
    assert feedback_alias.status_code == 201

    share_alias = client.post("/api/v1/diagnoses/diag-alias-1/share", headers=headers)
    assert share_alias.status_code == 201
    token = share_alias.json()["token"]

    share_read_alias = client.get(f"/api/v1/diagnoses/share/{token}")
    assert share_read_alias.status_code == 200
    assert share_read_alias.json()["diagnosis_id"] == "diag-alias-1"

    resolve_alias = client.post("/api/v1/diagnoses/diag-alias-1/resolve", headers=headers)
    assert resolve_alias.status_code == 200

    fix_watch_alias = client.get("/api/v1/diagnoses/diag-alias-1/fix-watch", headers=headers)
    assert fix_watch_alias.status_code == 200


def test_settings_pii_test_alias_path(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "Dash PII Alias Project")
    headers = {"X-Project-Id": project_id}

    response = client.post(
        "/api/v1/settings/pii/test",
        headers=headers,
        json={
            "pattern": "ACC-[0-9]{4}",
            "sample_text": "customer ACC-1234 opened a ticket",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["match_count"] == 1


def test_savings_summary_aggregates_open_and_resolved_issues(test_ctx) -> None:
    """The /v1/analytics/savings route is the data backing the dashboard's
    "Saved You" top-bar counter. It must:
      - count BOTH open + resolved issues in the window
      - keep `cumulative_wasted_usd` (open) separate from
        `cumulative_resolved_blast_usd` (resolved) — those drive different
        framing in the UI ("still bleeding" vs "already saved")
      - apply the 6h projection multiplier ONLY to resolved blast radius
      - bucket counts by severity
      - silently ignore issues outside the window
    """
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]
    project_id = _create_project(client, "savings-test")

    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=2)
    ancient = now - timedelta(days=120)

    def _savings_anomaly(
        *,
        failure_code: str,
        prompt_fingerprint: str,
        status: str,
        severity: str,
        occurrence_count: int,
        blast_radius_usd: float,
        seen_at: datetime,
    ) -> Anomaly:
        return Anomaly(
            project_id=project_id,
            fingerprint=compute_fingerprint(
                detector=failure_code,
                prompt_fingerprint=prompt_fingerprint,
                agent_name=None,
            ),
            detector=failure_code,
            status="resolved" if status == "resolved" else "open",
            severity=severity,
            occurrence_count=occurrence_count,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            evidence_json=json.dumps(
                {
                    "failure_code": failure_code,
                    "prompt_fingerprint": prompt_fingerprint,
                    "blast_radius_usd": blast_radius_usd,
                    "legacy_issue": {
                        "failure_code": failure_code,
                        "prompt_fingerprint": prompt_fingerprint,
                        "agent_name": None,
                        "blast_radius_usd": blast_radius_usd,
                        "resolved_at": seen_at.isoformat()
                        if status == "resolved"
                        else None,
                    },
                },
                separators=(",", ":"),
            ),
            created_at=seen_at,
            updated_at=seen_at,
        )

    with session_local() as session:
        # Open issue inside window — counts toward "still bleeding".
        session.add(
            _savings_anomaly(
                failure_code="LOOP_DETECTED",
                prompt_fingerprint="fp1",
                status="open",
                severity="high",
                occurrence_count=5,
                blast_radius_usd=10.0,
                seen_at=recent,
            )
        )
        # Resolved issue inside window — drives "already saved" + projection.
        session.add(
            _savings_anomaly(
                failure_code="COST_SPIKE",
                prompt_fingerprint="fp2",
                status="resolved",
                severity="critical",
                occurrence_count=3,
                blast_radius_usd=20.0,
                seen_at=recent,
            )
        )
        # Ancient issue OUTSIDE window — must be excluded.
        session.add(
            _savings_anomaly(
                failure_code="AUTH_FAILURE",
                prompt_fingerprint="fp3",
                status="resolved",
                severity="low",
                occurrence_count=1,
                blast_radius_usd=999.0,
                seen_at=ancient,
            )
        )
        session.commit()

    response = client.get(
        "/v1/analytics/savings?days=30",
        headers={"X-Project-Id": project_id},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["window_days"] == 30
    assert payload["total_caught_count"] == 2  # ancient row excluded
    assert payload["total_resolved_count"] == 1
    assert payload["cumulative_wasted_usd"] == pytest.approx(10.0)
    assert payload["cumulative_resolved_blast_usd"] == pytest.approx(20.0)
    # 1.5x projection multiplier on resolved blast
    assert payload["projected_averted_usd"] == pytest.approx(30.0)
    assert payload["affected_calls"] == 8  # 5 + 3
    assert payload["incidents_by_severity"] == {"high": 1, "critical": 1}


def test_savings_summary_empty_for_clean_project(test_ctx) -> None:
    """When a project has no issues, all aggregates must be zero — never
    null and never absent — so the dashboard counter renders deterministically."""
    client: TestClient = test_ctx["client"]
    project_id = _create_project(client, "clean-savings-test")

    response = client.get(
        "/v1/analytics/savings?days=7",
        headers={"X-Project-Id": project_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_caught_count"] == 0
    assert payload["total_resolved_count"] == 0
    assert payload["cumulative_wasted_usd"] == 0.0
    assert payload["cumulative_resolved_blast_usd"] == 0.0
    assert payload["projected_averted_usd"] == 0.0
    assert payload["affected_calls"] == 0
    assert payload["incidents_by_severity"] == {}
