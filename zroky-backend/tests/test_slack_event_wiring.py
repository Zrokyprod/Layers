from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import regression_ci as regression_ci_routes
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import DiagnosisJob, GoldenSet, ReplayRun
from app.services.regression_ci import durable_gate
from app.services.notification_dispatch import (
    dispatch_ci_gate_failed_slack_alert,
    dispatch_replay_slack_alert,
)
from app.services.slack_integration import encrypt_slack_webhook_url
from app.worker import tasks as worker_tasks


@pytest.fixture()
def worker_session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_slack_event_wiring.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    @contextmanager
    def _always_acquired(_task_key: str):
        yield True

    monkeypatch.setattr(worker_tasks, "SessionLocal", factory)
    monkeypatch.setattr(worker_tasks, "idempotency_guard", _always_acquired)
    monkeypatch.setattr(worker_tasks, "set_db_tenant_context", lambda *_args, **_kwargs: None)

    yield factory

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _insert_job(
    factory,
    *,
    tenant_id: str,
    diagnosis_id: str,
    payload: dict,
) -> None:
    with factory() as session:
        session.add(
            DiagnosisJob(
                tenant_id=tenant_id,
                diagnosis_id=diagnosis_id,
                status="queued",
                payload_json=json.dumps(payload, separators=(",", ":")),
            )
        )
        session.commit()


def _patch_diagnosis_side_effects(monkeypatch: pytest.MonkeyPatch, new_issue_calls: list[dict]) -> None:
    monkeypatch.setattr(worker_tasks, "evaluate_fast_rules", lambda _payload: [])
    monkeypatch.setattr(worker_tasks, "evaluate_pattern_rules", lambda _payload: ([], []))
    monkeypatch.setattr(
        worker_tasks,
        "build_diagnosis_result",
        lambda **_kwargs: {
            "diagnoses": [
                {
                    "category": "SCHEMA_VIOLATION",
                    "confidence": 0.91,
                    "summary": "Schema validation failed.",
                }
            ],
            "informational": [],
        },
    )
    for name in (
        "record_diagnosis_job",
        "record_diagnosis_rule_hits",
        "sync_alerts_from_jobs",
        "ensure_fix_event_prerequisites",
        "record_fix_event",
        "publish_diagnosis",
        "publish_loop_alert",
        "publish_auth_failure_alert",
        "publish_rate_limit_alert",
        "publish_cost_spike",
        "evaluate_pending_fix_resolutions",
        "evaluate_fix_regressions",
        "calibrate_resolved_fix_confidence",
    ):
        monkeypatch.setattr(worker_tasks, name, lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.services.notification_dispatch.dispatch_alert_to_tenant_channels",
        lambda **_kwargs: {"slack": False, "teams": False},
    )
    monkeypatch.setattr(
        "app.services.notification_dispatch.dispatch_new_issue_slack_alert",
        lambda **kwargs: new_issue_calls.append(kwargs) or True,
    )


def test_diagnosis_new_issue_hook_notifies_only_first_anomaly(
    worker_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-slack-new-issue"
    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "status": "success",
        "agent_name": "refund-agent",
        "prompt_fingerprint": "fp-schema",
    }
    new_issue_calls: list[dict] = []
    _patch_diagnosis_side_effects(monkeypatch, new_issue_calls)

    _insert_job(
        worker_session_factory,
        tenant_id=tenant_id,
        diagnosis_id="diag-new",
        payload=payload,
    )
    worker_tasks.process_diagnosis.run(tenant_id, "diag-new", None)

    _insert_job(
        worker_session_factory,
        tenant_id=tenant_id,
        diagnosis_id="diag-repeat",
        payload=payload,
    )
    worker_tasks.process_diagnosis.run(tenant_id, "diag-repeat", None)

    assert len(new_issue_calls) == 1
    assert new_issue_calls[0]["tenant_id"] == tenant_id
    assert new_issue_calls[0]["failure_code"] == "SCHEMA_VIOLATION"
    assert new_issue_calls[0]["agent_name"] == "refund-agent"
    assert new_issue_calls[0]["diagnosis_id"] == "diag-new"


def _seed_replay_run(factory, *, project_id: str, run_id: str, trigger: str = "manual") -> None:
    now = datetime.now(timezone.utc)
    with factory() as session:
        session.add(
            GoldenSet(
                id=f"set-{run_id}",
                project_id=project_id,
                name=f"Set {run_id}",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ReplayRun(
                id=run_id,
                project_id=project_id,
                golden_set_id=f"set-{run_id}",
                trigger=trigger,
                git_sha="abc1234" if trigger == "github" else None,
                status="pending",
                summary_json=json.dumps(
                    {
                        "replay_mode": "stub",
                        "requested_replay_mode": "stub",
                        "verification_status": "sanity_check_only",
                        "verified_fix": False,
                    },
                    separators=(",", ":"),
                ),
                created_at=now,
            )
        )
        session.commit()


def test_replay_worker_dispatches_verified_slack_event(
    worker_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-replay-verified"
    run_id = "run-verified"
    _seed_replay_run(worker_session_factory, project_id=tenant_id, run_id=run_id)
    calls: list[dict] = []

    def _execute(db, *, project_id, run_id, **_kwargs):
        run = db.get(ReplayRun, run_id)
        summary = json.loads(run.summary_json or "{}")
        summary.update(
            {
                "verified_fix": True,
                "verification_status": "verified_fix",
                "source_issue_id": "issue-123",
                "source_call_id": "call-123",
                "source_issue_failure_code": "SCHEMA_VIOLATION",
            }
        )
        run.status = "pass"
        run.completed_at = datetime.now(timezone.utc)
        run.summary_json = json.dumps(summary, separators=(",", ":"))
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    monkeypatch.setattr("app.services.entitlements_resolver.resolve_all", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("app.services.entitlements_resolver.get_plan_code", lambda *_args, **_kwargs: "pro")
    monkeypatch.setattr("app.services.judge_engine.get_evaluator", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("app.services.replay_executor.execute_replay_run", _execute)
    monkeypatch.setattr(
        "app.services.notification_dispatch.dispatch_replay_slack_alert",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    result = worker_tasks.process_replay_run.run(tenant_id, run_id)

    assert result["status"] == "pass"
    assert len(calls) == 1
    assert calls[0]["run_id"] == run_id
    assert calls[0]["summary"]["verified_fix"] is True
    assert calls[0]["summary"]["source_issue_id"] == "issue-123"


def test_replay_dispatch_builds_failed_and_ci_gate_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLACK_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    get_settings.cache_clear()
    mock_install = MagicMock()
    mock_install.webhook_url = encrypt_slack_webhook_url("https://hooks.slack.com/T123/B456/secret")
    mock_response = MagicMock(status_code=200)
    posted: list[dict] = []

    def _post(url, json, timeout):
        posted.append({"url": url, "json": json, "timeout": timeout})
        return mock_response

    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("httpx.post", side_effect=_post):
        replay_ok = dispatch_replay_slack_alert(
            MagicMock(),
            tenant_id="tenant-abc",
            run_id="run-replay",
            status="fail",
            trigger="manual",
            git_sha=None,
            summary={
                "source_issue_id": "issue-1",
                "source_call_id": "call-1",
                "source_issue_failure_code": "SCHEMA_VIOLATION",
                "fail_count": 2,
                "error_count": 0,
            },
        )
        ci_ok = dispatch_replay_slack_alert(
            MagicMock(),
            tenant_id="tenant-abc",
            run_id="run-ci",
            status="fail",
            trigger="github",
            git_sha="abcdef123456",
            summary={
                "source_issue_id": "issue-2",
                "source_issue_failure_code": "SCHEMA_VIOLATION",
                "fail_count": 3,
                "error_count": 1,
                "trace_count_executed": 10,
            },
        )

    assert replay_ok is True
    assert ci_ok is True
    assert posted[0]["json"]["text"] == "Replay failed: run-replay"
    assert posted[1]["json"]["text"] == "CI gate failed: run-ci"


def test_regression_ci_background_dispatches_failed_gate(
    worker_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _Report:
        verdict = "fail"

        def to_dict(self):
            return {
                "run_id": "run-ci-bg",
                "project_id": "proj-ci-bg",
                "git_sha": "abc1234",
                "verdict": "fail",
                "trace_count": 10,
                "regressed_count": 2,
                "error_count": 0,
                "regression_rate": 0.2,
                "threshold": 0.02,
            }

    monkeypatch.setattr(regression_ci_routes, "SessionLocal", worker_session_factory)
    monkeypatch.setattr(durable_gate, "SessionLocal", worker_session_factory)
    monkeypatch.setattr("app.services.entitlements_resolver.resolve_all", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("app.services.entitlements_resolver.get_plan_code", lambda *_args, **_kwargs: "pro")
    monkeypatch.setattr("app.services.entitlements_resolver.has", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("app.services.judge_engine.get_evaluator", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("app.services.embedding_service.get_embedding_service", lambda: None)
    monkeypatch.setattr(regression_ci_routes, "run_regression_ci", lambda *_args, **_kwargs: _Report())
    monkeypatch.setattr(durable_gate, "run_regression_ci", lambda *_args, **_kwargs: _Report())
    monkeypatch.setattr(durable_gate, "apply_golden_gate_policy", lambda _session, report: report)
    monkeypatch.setattr(
        "app.services.notification_dispatch.dispatch_ci_gate_failed_slack_alert",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    regression_ci_routes._run_regression_ci_background(
        tenant_id="proj-ci-bg",
        run_id="run-ci-bg",
        request_payload={
            "git_sha": "abc1234",
            "changed_files": [{"path": "prompt.md"}],
            "threshold": 0.02,
            "sample_window_days": 30,
        },
    )

    assert len(calls) == 1
    assert calls[0]["tenant_id"] == "proj-ci-bg"
    assert calls[0]["run_id"] == "run-ci-bg"
    assert calls[0]["status"] == "fail"
    assert calls[0]["report"]["regressed_count"] == 2


def test_direct_ci_gate_dispatch_ignores_passing_reports() -> None:
    with patch("app.services.notification_dispatch.get_slack_install") as get_install:
        ok = dispatch_ci_gate_failed_slack_alert(
            MagicMock(),
            tenant_id="tenant-abc",
            run_id="run-pass",
            status="pass",
            git_sha="abc",
            report={"verdict": "pass"},
        )

    assert ok is False
    get_install.assert_not_called()
