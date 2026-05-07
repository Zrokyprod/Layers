import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Call, DiagnosisJob, Project, ProjectDashboardConfig
from app.worker import tasks as worker_tasks


class _RetrySignal(Exception):
    def __init__(self, countdown: int, max_retries: int):
        super().__init__(f"retry countdown={countdown} max_retries={max_retries}")
        self.countdown = countdown
        self.max_retries = max_retries


@pytest.fixture()
def worker_task_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_worker_tasks.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    @contextmanager
    def _always_acquired(_task_key: str):
        yield True

    monkeypatch.setattr(worker_tasks, "SessionLocal", testing_session_local)
    monkeypatch.setattr(worker_tasks, "idempotency_guard", _always_acquired)
    monkeypatch.setattr(worker_tasks, "set_db_tenant_context", lambda *_args, **_kwargs: None)

    yield testing_session_local

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _insert_job(
    session_local,
    *,
    tenant_id: str,
    diagnosis_id: str,
    status: str = "queued",
    agent_name: str | None = None,
    prompt_fingerprint: str | None = None,
    payload: dict | None = None,
    result_json: dict | None = None,
    error_message: str | None = None,
    created_at: datetime | None = None,
) -> None:
    with session_local() as session:
        job = DiagnosisJob(
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            status=status,
            agent_name=agent_name,
            prompt_fingerprint=prompt_fingerprint,
            payload_json=json.dumps(payload or {}, separators=(",", ":")),
            result_json=json.dumps(result_json, separators=(",", ":")) if result_json is not None else None,
            error_message=error_message,
        )
        if created_at is not None:
            job.created_at = created_at
        session.add(job)
        session.commit()


def _insert_call_and_job(
    session_local,
    *,
    tenant_id: str,
    call_id: str,
    payload: dict,
    job_status: str = "pending",
) -> None:
    with session_local() as session:
        call = Call(
            id=call_id,
            project_id=tenant_id,
            event_id=call_id,
            provider=str(payload.get("provider") or "unknown"),
            model=str(payload.get("model") or "unknown"),
            status=str(payload.get("status") or "success"),
            error_code=payload.get("error_code"),
            latency_ms=payload.get("latency_ms"),
            input_tokens=int(payload.get("prompt_tokens") or 0),
            output_tokens=int(payload.get("completion_tokens") or 0),
            total_tokens=int(payload.get("total_tokens") or 0),
            cost_total=float(payload.get("cost_usd") or 0.0),
            payload_json=json.dumps(payload, separators=(",", ":")),
            metadata_json=json.dumps(
                {
                    "agent_name": payload.get("agent_name"),
                    "prompt_fingerprint": payload.get("prompt_fingerprint"),
                },
                separators=(",", ":"),
            ),
        )
        job = DiagnosisJob(
            tenant_id=tenant_id,
            diagnosis_id=call_id,
            call_id=call_id,
            status=job_status,
            agent_name=payload.get("agent_name"),
            prompt_fingerprint=payload.get("prompt_fingerprint"),
            payload_json="{}",
        )
        session.add(call)
        session.add(job)
        session.commit()


def _insert_project_with_retention(
    session_local,
    *,
    project_id: str,
    retention_days: int,
    is_active: bool = True,
) -> None:
    with session_local() as session:
        session.add(
            Project(
                id=project_id,
                name=f"Project {project_id}",
                is_active=is_active,
            )
        )
        session.add(
            ProjectDashboardConfig(
                tenant_id=project_id,
                retention_days=retention_days,
            )
        )
        session.commit()


def test_calculate_retry_countdown_caps_to_max() -> None:
    countdown = worker_tasks._calculate_retry_countdown(
        retry_count=3,
        base_seconds=2,
        max_seconds=10,
    )
    assert countdown == 10


def test_process_diagnosis_schedules_retry_and_marks_job_retrying(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIAGNOSIS_TASK_MAX_RETRIES", "2")
    monkeypatch.setenv("DIAGNOSIS_TASK_RETRY_BASE_SECONDS", "3")
    monkeypatch.setenv("DIAGNOSIS_TASK_RETRY_MAX_SECONDS", "30")
    get_settings.cache_clear()

    tenant_id = "proj-worker-retry"
    diagnosis_id = "diag-worker-retry"
    _insert_job(worker_task_ctx, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    def _raise_fast_rules(_payload: dict):
        raise RuntimeError("worker boom")

    def _retry_stub(*_args, **kwargs):
        raise _RetrySignal(
            countdown=int(kwargs["countdown"]),
            max_retries=int(kwargs["max_retries"]),
        )

    monkeypatch.setattr(worker_tasks, "evaluate_fast_rules", _raise_fast_rules)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "_current_retry_count", lambda _task: 0)
    monkeypatch.setattr(worker_tasks.process_diagnosis, "retry", _retry_stub, raising=False)

    with pytest.raises(_RetrySignal) as retry_error:
        worker_tasks.process_diagnosis.run(tenant_id, diagnosis_id, {"provider": "openai"})

    assert retry_error.value.countdown == 3
    assert retry_error.value.max_retries == 2

    with worker_task_ctx() as session:
        job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id == diagnosis_id,
            )
        ).scalar_one()

    assert job.status == "retrying"
    assert job.error_message == "worker boom"


def test_process_diagnosis_marks_dead_letter_after_retries_exhausted(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIAGNOSIS_TASK_MAX_RETRIES", "1")
    monkeypatch.setenv("DIAGNOSIS_TASK_RETRY_BASE_SECONDS", "2")
    monkeypatch.setenv("DIAGNOSIS_TASK_RETRY_MAX_SECONDS", "30")
    get_settings.cache_clear()

    tenant_id = "proj-worker-dead-letter"
    diagnosis_id = "diag-worker-dead-letter"
    _insert_job(worker_task_ctx, tenant_id=tenant_id, diagnosis_id=diagnosis_id)

    def _raise_fast_rules(_payload: dict):
        raise RuntimeError("persistent worker failure")

    def _retry_unexpected(*_args, **_kwargs):
        raise AssertionError("retry should not be called when retries are exhausted")

    monkeypatch.setattr(worker_tasks, "evaluate_fast_rules", _raise_fast_rules)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "_current_retry_count", lambda _task: 1)
    monkeypatch.setattr(worker_tasks.process_diagnosis, "retry", _retry_unexpected, raising=False)

    result = worker_tasks.process_diagnosis.run(tenant_id, diagnosis_id, {"provider": "openai"})
    assert result["status"] == "dead_lettered"
    assert result["retry_count"] == 1

    with worker_task_ctx() as session:
        job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id == diagnosis_id,
            )
        ).scalar_one()

    assert job.status == "dead_lettered"
    assert job.error_message == "persistent worker failure"
    dead_letter_payload = json.loads(job.result_json or "{}")
    assert dead_letter_payload["status"] == "dead_lettered"
    assert dead_letter_payload["max_retries"] == 1


def test_process_diagnosis_reads_payload_from_linked_call(worker_task_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = "proj-worker-call-linked"
    call_id = "call-worker-linked"
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        call_id=call_id,
        payload={
            "provider": "openai",
            "model": "gpt-test",
            "status": "success",
            "prompt_tokens": 120,
            "completion_tokens": 40,
            "agent_name": "agent-linked",
            "prompt_fingerprint": "fp-linked",
        },
    )

    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_rule_hits", lambda _categories: None)

    result = worker_tasks.process_diagnosis.run(tenant_id, call_id, None)

    assert result["status"] == "processed"
    assert result["diagnosis_id"] == call_id

    with worker_task_ctx() as session:
        job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id == call_id,
            )
        ).scalar_one()
        call = session.get(Call, call_id)

    assert job.status == "done"
    assert job.call_id == call_id
    assert json.loads(job.payload_json or "{}") == {}
    assert call is not None
    assert call.provider == "openai"
    assert call.status == "success"


def test_process_diagnosis_skips_done_job_on_redelivery(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-worker-redelivery"
    call_id = "call-worker-redelivery"
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        call_id=call_id,
        payload={
            "provider": "openai",
            "model": "gpt-test",
            "status": "success",
        },
        job_status="done",
    )

    with worker_task_ctx() as session:
        job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id == call_id,
            )
        ).scalar_one()
        job.result_json = json.dumps({"status": "processed", "diagnosis_id": call_id}, separators=(",", ":"))
        session.add(job)
        session.commit()

    def _unexpected_fast_rules(_payload: dict):
        raise AssertionError("done job should not be reprocessed")

    monkeypatch.setattr(worker_tasks, "evaluate_fast_rules", _unexpected_fast_rules)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)

    result = worker_tasks.process_diagnosis.run(tenant_id, call_id, None)

    assert result["status"] == "processed"
    assert result["diagnosis_id"] == call_id


def test_process_diagnosis_treats_failed_as_terminal_on_redelivery(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-worker-failed-redelivery"
    call_id = "call-worker-failed-redelivery"
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        call_id=call_id,
        payload={
            "provider": "openai",
            "model": "gpt-test",
            "status": "error",
        },
        job_status="failed",
    )

    def _unexpected_fast_rules(_payload: dict):
        raise AssertionError("failed terminal job should not be reprocessed")

    monkeypatch.setattr(worker_tasks, "evaluate_fast_rules", _unexpected_fast_rules)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)

    result = worker_tasks.process_diagnosis.run(tenant_id, call_id, None)

    assert result["status"] == "already_done"
    assert result["diagnosis_id"] == call_id


def test_bounded_recent_repeat_count_filters_by_window_and_identity(worker_task_ctx) -> None:
    tenant_id = "proj-loop-window"
    now = datetime.now(timezone.utc)

    for idx in range(5):
        _insert_job(
            worker_task_ctx,
            tenant_id=tenant_id,
            diagnosis_id=f"diag-window-{idx}",
            agent_name="agent-alpha",
            prompt_fingerprint="fp-same",
            created_at=now - timedelta(seconds=idx * 10),
        )

    _insert_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        diagnosis_id="diag-window-old",
        agent_name="agent-alpha",
        prompt_fingerprint="fp-same",
        created_at=now - timedelta(seconds=150),
    )
    _insert_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        diagnosis_id="diag-window-other-agent",
        agent_name="agent-beta",
        prompt_fingerprint="fp-same",
        created_at=now - timedelta(seconds=20),
    )
    _insert_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        diagnosis_id="diag-window-other-fp",
        agent_name="agent-alpha",
        prompt_fingerprint="fp-other",
        created_at=now - timedelta(seconds=20),
    )

    with worker_task_ctx() as session:
        repeat_count = worker_tasks._bounded_recent_repeat_count(
            session,
            tenant_id=tenant_id,
            agent_name="agent-alpha",
            prompt_fingerprint="fp-same",
            window_seconds=90,
            now=now,
        )

    assert repeat_count == 5


def test_process_diagnosis_derives_repeat_count_from_db_and_triggers_loop(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-loop-threshold"
    agent_name = "agent-loop"
    prompt_fingerprint = "fp-loop-threshold"

    for idx in range(5):
        _insert_job(
            worker_task_ctx,
            tenant_id=tenant_id,
            diagnosis_id=f"diag-loop-{idx}",
            agent_name=agent_name,
            prompt_fingerprint=prompt_fingerprint,
            payload={
                "status": "failed",
                "error_code": "rate_limit_exceeded",
                "error_message": "rate limit exceeded",
                "prompt_tokens": 200,
                "completion_tokens": 0,
                "output_fingerprint": "repeat-output-fp",
            },
        )

    diagnosis_id = "diag-loop-4"
    captured_categories: list[str] = []
    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_rule_hits", lambda categories: captured_categories.extend(categories))

    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "agent_name": agent_name,
        "prompt_fingerprint": prompt_fingerprint,
        "output_fingerprint": "repeat-output-fp",
    }
    result = worker_tasks.process_diagnosis.run(tenant_id, diagnosis_id, payload)

    assert result["status"] == "processed"
    assert any(item.get("category") == "LOOP_DETECTED" for item in result.get("diagnoses", []))
    assert "LOOP_DETECTED" in captured_categories

    loop_diagnosis = next(
        item for item in result["diagnoses"] if item.get("category") == "LOOP_DETECTED"
    )
    evidence = loop_diagnosis.get("evidence", {})
    assert evidence.get("repeat_count") == 5
    assert evidence.get("repeat_window_seconds") == 90
    assert len(evidence.get("sample_timestamps", [])) >= 1
    assert evidence.get("error_pattern", {}).get("failure_count", 0) >= 3


def test_process_diagnosis_retry_suppression_ignores_sdk_retry_rows(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-loop-retry-suppression"
    agent_name = "agent-loop"
    prompt_fingerprint = "fp-loop-retry-suppression"

    for idx in range(4):
        _insert_job(
            worker_task_ctx,
            tenant_id=tenant_id,
            diagnosis_id=f"diag-loop-retry-{idx}",
            agent_name=agent_name,
            prompt_fingerprint=prompt_fingerprint,
            payload={
                "status": "failed",
                "error_code": "timeout",
                "prompt_tokens": 150,
                "completion_tokens": 0,
            },
        )

    _insert_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        diagnosis_id="diag-loop-retry-sdk",
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
        payload={
            "status": "failed",
            "error_code": "timeout",
            "prompt_tokens": 150,
            "completion_tokens": 0,
            "retry": {
                "is_sdk_retry": True,
                "sdk_attempts": 1,
                "backoff_attempts": 1,
            },
        },
    )

    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_rule_hits", lambda _categories: None)

    result = worker_tasks.process_diagnosis.run(
        tenant_id,
        "diag-loop-retry-3",
        {
            "provider": "openai",
            "model": "gpt-test",
            "agent_name": agent_name,
            "prompt_fingerprint": prompt_fingerprint,
        },
    )

    assert all(item.get("category") != "LOOP_DETECTED" for item in result.get("diagnoses", []))


def test_process_diagnosis_cooldown_suppresses_duplicate_loop_alert(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-loop-cooldown"
    agent_name = "agent-loop"
    prompt_fingerprint = "fp-loop-cooldown"
    now = datetime.now(timezone.utc)

    for idx in range(5):
        _insert_job(
            worker_task_ctx,
            tenant_id=tenant_id,
            diagnosis_id=f"diag-loop-cooldown-{idx}",
            agent_name=agent_name,
            prompt_fingerprint=prompt_fingerprint,
            payload={
                "status": "failed",
                "error_code": "timeout",
                "prompt_tokens": 120,
                "completion_tokens": 0,
            },
            created_at=now - timedelta(seconds=20 - idx),
        )

    _insert_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        diagnosis_id="diag-loop-cooldown-previous",
        status="completed",
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
        payload={
            "status": "failed",
            "error_code": "timeout",
        },
        result_json={
            "diagnoses": [
                {
                    "category": "LOOP_DETECTED",
                    "confidence": 0.92,
                }
            ]
        },
        created_at=now - timedelta(minutes=5),
    )

    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_rule_hits", lambda _categories: None)

    result = worker_tasks.process_diagnosis.run(
        tenant_id,
        "diag-loop-cooldown-4",
        {
            "provider": "openai",
            "model": "gpt-test",
            "agent_name": agent_name,
            "prompt_fingerprint": prompt_fingerprint,
        },
    )

    assert all(item.get("category") != "LOOP_DETECTED" for item in result.get("diagnoses", []))


def test_process_diagnosis_different_intent_does_not_false_positive_loop(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "proj-loop-false-positive"
    agent_name = "agent-loop"

    for idx in range(5):
        _insert_job(
            worker_task_ctx,
            tenant_id=tenant_id,
            diagnosis_id=f"diag-loop-fp-{idx}",
            agent_name=agent_name,
            prompt_fingerprint="fingerprint-A",
            payload={
                "status": "failed",
                "error_code": "timeout",
                "prompt_tokens": 140,
                "completion_tokens": 0,
            },
        )

    monkeypatch.setattr(worker_tasks, "record_diagnosis_job", lambda _status: None)
    monkeypatch.setattr(worker_tasks, "record_diagnosis_rule_hits", lambda _categories: None)

    result = worker_tasks.process_diagnosis.run(
        tenant_id,
        "diag-loop-fp-4",
        {
            "provider": "openai",
            "model": "gpt-test",
            "agent_name": agent_name,
            "prompt_fingerprint": "fingerprint-B",
            "status": "failed",
            "error_code": "timeout",
            "prompt_tokens": 140,
            "completion_tokens": 0,
        },
    )

    assert all(item.get("category") != "LOOP_DETECTED" for item in result.get("diagnoses", []))


def test_purge_project_retention_task_deletes_expired_rows(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    tenant_id = "proj-retention-one"

    _insert_project_with_retention(worker_task_ctx, project_id=tenant_id, retention_days=30)
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        call_id="call-retention-old",
        payload={
            "provider": "openai",
            "model": "gpt-test",
            "status": "success",
        },
        job_status="done",
    )
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id=tenant_id,
        call_id="call-retention-new",
        payload={
            "provider": "openai",
            "model": "gpt-test",
            "status": "success",
        },
        job_status="done",
    )

    with worker_task_ctx() as session:
        old_call = session.get(Call, "call-retention-old")
        old_job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id == "call-retention-old",
            )
        ).scalar_one()
        new_call = session.get(Call, "call-retention-new")
        new_job = session.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id == "call-retention-new",
            )
        ).scalar_one()
        old_call.created_at = now - timedelta(days=40)
        old_job.created_at = now - timedelta(days=40)
        new_call.created_at = now - timedelta(days=2)
        new_job.created_at = now - timedelta(days=2)
        session.add(old_call)
        session.add(old_job)
        session.add(new_call)
        session.add(new_job)
        session.commit()

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(worker_tasks, "datetime", _FakeDatetime)

    summary = worker_tasks.purge_project_retention.run(tenant_id)

    assert summary["retention_days"] == 30
    assert summary["total_deleted"] == 2
    assert summary["deleted_by_table"]["calls"] == 1
    assert summary["deleted_by_table"]["diagnosis_jobs"] == 1

    with worker_task_ctx() as session:
        assert session.get(Call, "call-retention-old") is None
        assert (
            session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == "call-retention-old",
                )
            ).scalar_one_or_none()
            is None
        )
        assert session.get(Call, "call-retention-new") is not None


def test_run_retention_enforcement_iterates_active_projects(
    worker_task_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    _insert_project_with_retention(worker_task_ctx, project_id="proj-retention-a", retention_days=30)
    _insert_project_with_retention(worker_task_ctx, project_id="proj-retention-b", retention_days=7)
    _insert_project_with_retention(
        worker_task_ctx,
        project_id="proj-retention-inactive",
        retention_days=1,
        is_active=False,
    )

    _insert_call_and_job(
        worker_task_ctx,
        tenant_id="proj-retention-a",
        call_id="call-retention-a",
        payload={"provider": "openai", "model": "gpt-test", "status": "success"},
        job_status="done",
    )
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id="proj-retention-b",
        call_id="call-retention-b",
        payload={"provider": "openai", "model": "gpt-test", "status": "success"},
        job_status="done",
    )
    _insert_call_and_job(
        worker_task_ctx,
        tenant_id="proj-retention-inactive",
        call_id="call-retention-inactive",
        payload={"provider": "openai", "model": "gpt-test", "status": "success"},
        job_status="done",
    )

    with worker_task_ctx() as session:
        for tenant_id, call_id in (
            ("proj-retention-a", "call-retention-a"),
            ("proj-retention-b", "call-retention-b"),
            ("proj-retention-inactive", "call-retention-inactive"),
        ):
            call = session.get(Call, call_id)
            job = session.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.diagnosis_id == call_id,
                )
            ).scalar_one()
            call.created_at = now - timedelta(days=40)
            job.created_at = now - timedelta(days=40)
            session.add(call)
            session.add(job)
        session.commit()

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(worker_tasks, "datetime", _FakeDatetime)

    summary = worker_tasks.run_retention_enforcement.run()

    assert summary["status"] == "ok"
    assert summary["processed_tenants"] == 2
    assert summary["failed_tenants"] == 0
    assert summary["total_deleted"] == 4

    processed_tenants = {item["tenant_id"] for item in summary["results"]}
    assert processed_tenants == {"proj-retention-a", "proj-retention-b"}

    with worker_task_ctx() as session:
        assert session.get(Call, "call-retention-a") is None
        assert session.get(Call, "call-retention-b") is None
        assert session.get(Call, "call-retention-inactive") is not None
