from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.api.routes import ingest as ingest_routes
from app.api.routes import live as live_routes
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Call, DiagnosisJob
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.worker import tasks as worker_tasks
from app.worker.celery_app import celery_app

TERMINAL_JOB_STATUSES = {"done", "completed", "failed", "dead_lettered"}


@pytest.fixture()
def integration_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_ingest_integration.db"
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

    @contextmanager
    def _always_acquired(_task_key: str):
        yield True

    original_conf = {
        "broker_url": celery_app.conf.broker_url,
        "result_backend": celery_app.conf.result_backend,
        "task_always_eager": celery_app.conf.task_always_eager,
        "task_store_eager_result": celery_app.conf.task_store_eager_result,
        "task_default_queue": celery_app.conf.task_default_queue,
    }

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.live.SessionLocal", testing_session_local)
    monkeypatch.setattr(worker_tasks, "SessionLocal", testing_session_local)
    monkeypatch.setattr(worker_tasks, "idempotency_guard", _always_acquired)
    monkeypatch.setattr(worker_tasks, "set_db_tenant_context", lambda *_args, **_kwargs: None)

    celery_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=False,
        task_store_eager_result=False,
        task_default_queue="diagnosis_fast",
    )

    with start_worker(
        celery_app,
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
        loglevel="WARNING",
    ):
        with TestClient(app) as test_client:
            yield {
                "client": test_client,
                "SessionLocal": testing_session_local,
            }

    app.dependency_overrides.clear()
    celery_app.conf.update(**original_conf)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _event(call_id: str, *, user_id: str = "integration-user") -> dict:
    return {
        "call_id": call_id,
        "event_id": f"event-{call_id}",
        "provider": "openai",
        "model": "gpt-4o",
        "call_type": "chat",
        "status": "completed",
        "latency_ms": 210,
        "prompt_tokens": 80,
        "completion_tokens": 20,
        "reasoning_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "tool_definitions": [],
        "tool_calls_made": [],
        "trace_id": f"trace-{call_id}",
        "parent_call_id": None,
        "agent_name": "integration-agent",
        "prompt_fingerprint": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
        "user_id": user_id,
        "created_at": "2026-04-29T12:00:00+00:00",
    }


def _wait_for_terminal_job(client: TestClient, headers: dict[str, str], diagnosis_id: str, *, timeout_seconds: float = 12.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status_response = client.get(f"/v1/diagnosis/{diagnosis_id}", headers=headers)
        assert status_response.status_code == 200
        payload = status_response.json()
        if str(payload["status"]).strip().lower() in TERMINAL_JOB_STATUSES:
            return payload
        time.sleep(0.05)

    pytest.fail(f"Diagnosis {diagnosis_id} did not reach a terminal status within {timeout_seconds}s")


def _wait_for_terminal_job_count(
    session_local,
    *,
    tenant_id: str,
    expected_count: int,
    timeout_seconds: float = 20.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with session_local() as session:
            jobs = list(
                session.execute(
                    select(DiagnosisJob).where(DiagnosisJob.tenant_id == tenant_id)
                ).scalars().all()
            )

        if len(jobs) == expected_count and all(job.status in TERMINAL_JOB_STATUSES for job in jobs):
            return
        time.sleep(0.05)

    pytest.fail(
        f"Timed out waiting for {expected_count} terminal diagnosis jobs for tenant {tenant_id}"
    )


def test_sdk_ingest_to_ui_full_path_with_real_celery_worker(integration_ctx) -> None:
    client: TestClient = integration_ctx["client"]
    headers = {"X-Project-Id": "proj-ingest-e2e-1"}
    call_id = "ingest-e2e-call-1"

    ingest_response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event(call_id)]},
    )
    assert ingest_response.status_code == 202
    ingest_payload = ingest_response.json()
    assert ingest_payload["accepted"] == 1
    assert ingest_payload["queued"] == 1
    assert ingest_payload["enqueue_failed"] == 0

    status_payload = _wait_for_terminal_job(client, headers, call_id)
    assert status_payload["status"] == "done"
    result_json = json.loads(status_payload["result_json"] or "{}")
    assert result_json["status"] == "processed"

    detail_response = client.get(f"/v1/calls/{call_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["call"]["call_id"] == call_id
    assert isinstance(detail_payload["diagnosis_result"], dict)

    list_response = client.get("/v1/calls?limit=20&user_id=integration-user", headers=headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] >= 1
    assert any(item["call_id"] == call_id for item in list_payload["items"])


def test_ingest_flood_accepts_and_queues_high_volume_batch(
    integration_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGEST_ENFORCE_RATE_LIMIT", "false")
    get_settings.cache_clear()

    # Flood test validates ingest + queue scheduling under load; worker execution is
    # covered by the dedicated full-path real-worker test above.
    monkeypatch.setattr(
        ingest_routes,
        "enrich_payload_with_cost_buckets",
        lambda *, tenant_id, payload: dict(payload),
    )
    monkeypatch.setattr(ingest_routes, "_enqueue_diagnosis_job", lambda _job: None)

    client: TestClient = integration_ctx["client"]
    session_local = integration_ctx["SessionLocal"]
    headers = {"X-Project-Id": "proj-ingest-flood-1"}
    event_count = 200

    events = [_event(f"ingest-flood-{index}", user_id=f"flood-user-{index % 5}") for index in range(event_count)]
    ingest_response = client.post("/api/v1/ingest", headers=headers, json={"events": events})
    assert ingest_response.status_code == 202
    ingest_payload = ingest_response.json()
    assert ingest_payload["accepted"] == event_count
    assert ingest_payload["queued"] == event_count
    assert ingest_payload["enqueue_failed"] == 0

    with session_local() as session:
        call_count = len(
            session.execute(
                select(Call).where(Call.project_id == "proj-ingest-flood-1")
            ).scalars().all()
        )
        jobs = list(
            session.execute(
                select(DiagnosisJob).where(DiagnosisJob.tenant_id == "proj-ingest-flood-1")
            ).scalars().all()
        )

    assert call_count == event_count
    assert len(jobs) == event_count
    assert all(job.status == "pending" for job in jobs)


def test_live_calls_sse_uses_requested_poll_delay(
    integration_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client: TestClient = integration_ctx["client"]
    headers = {"X-Project-Id": "proj-sse-delay-1"}

    ingest_response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("sse-delay-call-1", user_id="sse-user-1")]},
    )
    assert ingest_response.status_code == 202

    _wait_for_terminal_job(client, headers, "sse-delay-call-1")

    observed_sleep_intervals: list[float] = []

    async def _fake_sleep(duration: float) -> None:
        observed_sleep_intervals.append(duration)

    monkeypatch.setattr(live_routes.asyncio, "sleep", _fake_sleep)

    with client.stream(
        "GET",
        "/v1/live/calls?limit=10&poll_interval_ms=750&max_events=2",
        headers=headers,
    ) as stream_response:
        assert stream_response.status_code == 200
        stream_text = "".join(stream_response.iter_text())

    assert "event: snapshot" in stream_text
    assert '"call_id":"sse-delay-call-1"' in stream_text
    assert ": ping" in stream_text
    assert observed_sleep_intervals
    assert all(abs(interval - 0.75) < 1e-9 for interval in observed_sleep_intervals)
