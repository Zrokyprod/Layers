import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import DiagnosisJob, DiagnosisPullRequest, FixEvent
from app.db.session import get_db_session, get_db_session_read
from app.main import app

_WEBHOOK_SECRET = "test-github-webhook-secret"


@pytest.fixture()
def client_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_PR_BOT_TOKEN", "bot-token-test")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    get_settings.cache_clear()

    db_path = tmp_path / "test_github_webhooks.db"
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
        id = "task-test-github-webhook"

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.diagnosis.process_diagnosis.delay", lambda *_args, **_kwargs: _MockTaskResult())

    with TestClient(app) as client:
        yield client, testing_session_local

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _signed_webhook_body(payload: dict) -> tuple[bytes, str]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = "sha256=" + hmac.new(_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, signature


def _post_webhook(client: TestClient, event_name: str, payload: dict, delivery_id: str = "delivery-1"):
    raw, signature = _signed_webhook_body(payload)
    return client.post(
        "/v1/integrations/github/webhook",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-github-event": event_name,
            "x-github-delivery": delivery_id,
            "x-hub-signature-256": signature,
        },
    )


def test_generate_pr_and_github_webhooks_drive_fix_lifecycle(client_context, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_factory = client_context
    headers = {"X-Project-Id": "proj-webhook-1"}

    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-webhook-1",
            "payload": {"provider": "openai", "model": "gpt-4o"},
        },
    )
    assert submit.status_code == 200

    with session_factory() as session:
        job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == "proj-webhook-1",
                DiagnosisJob.diagnosis_id == "diag-webhook-1",
            )
        ).scalar_one()
        job.status = "done"
        job.result_json = json.dumps(
            {
                "diagnoses": [
                    {
                        "category": "TOKEN_OVERFLOW",
                        "fix": {"fix_id": "fix-token_overflow-diag-webhook-1"},
                    }
                ]
            }
        )
        session.add(job)
        session.commit()

    captured_body: dict[str, str] = {}

    class _FakeGithubResult:
        branch_name = "zroky/fix/diag-webhook-1"
        pull_request_number = 17
        pull_request_url = "https://github.com/acme/demo/pull/17"
        pull_request_title = "[ZROKY Fix] diag-webhook-1"
        file_path = "zroky-generated-fixes/diag-webhook-1.md"
        commit_sha = "headsha123"

    def _fake_create_pull_request_with_patch(**kwargs):
        captured_body["body"] = kwargs["generated_patch"].body
        return _FakeGithubResult()

    monkeypatch.setattr(
        "app.api.routes.diagnosis.create_pull_request_with_patch",
        _fake_create_pull_request_with_patch,
    )

    generated = client.post(
        "/v1/diagnosis/diag-webhook-1/generate-pr",
        headers=headers,
        json={"repository_owner": "acme", "repository_name": "demo", "base_branch": "main"},
    )
    assert generated.status_code == 201
    assert generated.json()["fix_id"] == "fix-token_overflow-diag-webhook-1"
    assert "zroky:fix-tracking" in captured_body["body"]

    merge_payload = {
        "action": "closed",
        "repository": {"name": "demo", "full_name": "acme/demo", "owner": {"login": "acme"}},
        "sender": {"login": "octocat"},
        "pull_request": {
            "number": 17,
            "merged": True,
            "merged_at": "2030-05-06T02:00:00Z",
            "closed_at": "2030-05-06T02:00:01Z",
            "updated_at": "2030-05-06T02:00:01Z",
            "merge_commit_sha": "mergesha123",
            "html_url": "https://github.com/acme/demo/pull/17",
            "body": captured_body["body"],
        },
    }
    merged = _post_webhook(client, "pull_request", merge_payload, delivery_id="merge-delivery-1")
    assert merged.status_code == 200
    assert [item["event_type"] for item in merged.json()["recorded_events"]][:1] == ["pr_merged"]

    ci_payload = {
        "repository": {"name": "demo", "full_name": "acme/demo", "owner": {"login": "acme"}},
        "check_run": {
            "id": 991,
            "status": "completed",
            "conclusion": "failure",
            "completed_at": "2030-05-06T02:05:00Z",
            "html_url": "https://github.com/acme/demo/runs/991",
            "head_sha": "mergesha123",
            "head_branch": "zroky/fix/diag-webhook-1",
            "pull_requests": [{"number": 17}],
        },
    }
    regressed = _post_webhook(client, "check_run", ci_payload, delivery_id="ci-delivery-1")
    assert regressed.status_code == 200
    assert [item["event_type"] for item in regressed.json()["recorded_events"]] == ["regressed"]

    with session_factory() as session:
        link = session.execute(select(DiagnosisPullRequest)).scalar_one()
        assert link.fix_id == "fix-token_overflow-diag-webhook-1"
        assert link.merge_commit_sha == "mergesha123"
        assert link.last_ci_conclusion == "failure"

        events = session.execute(
            select(FixEvent).order_by(FixEvent.timestamp.asc(), FixEvent.id.asc())
        ).scalars().all()
        event_types = [event.event_type for event in events]
        assert event_types == ["shown", "copied", "pr_generated", "pr_merged", "regressed"]
        assert events[-2].source == "github_webhook"
        assert events[-1].source == "github_webhook"


def test_github_webhook_rejects_invalid_signature(client_context) -> None:
    client, _ = client_context
    response = client.post(
        "/v1/integrations/github/webhook",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "x-github-event": "ping",
            "x-hub-signature-256": "sha256=bad",
        },
    )
    assert response.status_code == 401
