import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import DiagnosisJob
from app.db.session import get_db_session
from app.main import app


@pytest.fixture()
def test_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_prompt_fingerprint_storage.db"
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
        id = "task-prompt-fingerprint-storage"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    app.dependency_overrides[get_db_session] = override_get_db_session
    monkeypatch.setattr("app.api.routes.ingest.process_diagnosis.delay", _mock_delay)

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


def _event(call_id: str, fingerprint: str, content: str) -> dict:
    return {
        "call_id": call_id,
        "provider": "openai",
        "model": "gpt-4o",
        "call_type": "chat",
        "status": "completed",
        "latency_ms": 120,
        "prompt_tokens": 90,
        "completion_tokens": 30,
        "reasoning_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "tool_definitions": [{"name": "search"}],
        "tool_calls_made": [],
        "trace_id": "trace-fingerprint-1",
        "parent_call_id": None,
        "agent_name": "research-agent",
        "prompt_fingerprint": fingerprint,
        "user_id": "user-1",
        "error_code": None,
        "error_message": None,
        "created_at": 1710000000,
        "messages": [{"role": "user", "content": content}],
    }


def test_ingest_persists_prompt_fingerprint_column(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Prompt Fingerprint Persist Project")
    headers = {"X-Project-Id": project_id}
    fingerprint = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd"

    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        json={"events": [_event("fp-store-1", fingerprint, "summarize report id 123")]},
    )
    assert response.status_code == 202

    with session_local() as session:
        row = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == project_id,
                DiagnosisJob.diagnosis_id == "fp-store-1",
            )
        ).scalar_one()

        assert row.agent_name == "research-agent"
        assert row.prompt_fingerprint == fingerprint
        payload = json.loads(row.payload_json)
        assert payload["agent_name"] == "research-agent"
        assert payload["prompt_fingerprint"] == fingerprint


def test_same_signature_across_five_calls_is_groupable(test_ctx) -> None:
    client: TestClient = test_ctx["client"]
    session_local = test_ctx["SessionLocal"]

    project_id = _create_project(client, "Prompt Fingerprint Grouping Project")
    headers = {"X-Project-Id": project_id}
    shared_fingerprint = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    report_ids = ["123", "456", "789", "999", "1001"]
    events = [
        _event(
            call_id=f"fp-group-{idx}",
            fingerprint=shared_fingerprint,
            content=f"summarize report id {report_id}",
        )
        for idx, report_id in enumerate(report_ids)
    ]

    response = client.post("/api/v1/ingest", headers=headers, json={"events": events})
    assert response.status_code == 202
    assert response.json()["accepted"] == 5

    with session_local() as session:
        rows = session.execute(
            select(DiagnosisJob).where(DiagnosisJob.tenant_id == project_id)
        ).scalars().all()

    fingerprints = {row.prompt_fingerprint for row in rows}
    agent_names = {row.agent_name for row in rows}
    assert len(rows) == 5
    assert fingerprints == {shared_fingerprint}
    assert agent_names == {"research-agent"}
