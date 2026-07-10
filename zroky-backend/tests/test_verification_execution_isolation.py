from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import redis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import ActionPostExecutionJob, VerificationDispatchState
from app.services._action_post_execution_core import (
    JOB_CLAIMED,
    JOB_PENDING,
    JOB_RUNNING,
    claim_action_post_execution_jobs,
    start_claimed_action_post_execution_job,
)
from app.services.outcome_reconciliation import SourceRecord
from app.services.verification_execution_controls import (
    ControlledConnector,
    VerificationExecutionControls,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.slots: dict[str, dict[str, float]] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, *, ex: int | None = None):
        self.values[key] = value
        return True

    def delete(self, key: str):
        existed = int(key in self.values)
        self.values.pop(key, None)
        return existed

    def incr(self, key: str):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    def expire(self, key: str, seconds: int):
        return True

    def eval(self, _script: str, _keys: int, key: str, now: float, expires_at: float, limit: int, token: str, _ttl: int):
        slots = self.slots.setdefault(key, {})
        for existing, deadline in list(slots.items()):
            if deadline <= float(now):
                del slots[existing]
        if token in slots:
            return 1
        if len(slots) >= int(limit):
            return 0
        slots[token] = float(expires_at)
        return 1

    def zrem(self, key: str, token: str):
        return int(self.slots.get(key, {}).pop(token, None) is not None)


class BrokenRedis:
    def get(self, _key: str):
        raise redis.ConnectionError("redis unavailable")


class RetryableConnector:
    connector_type = "stripe_refund"

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self) -> SourceRecord:
        self.calls += 1
        return SourceRecord(
            record=None,
            record_found=None,
            metadata={"retryable": True, "http_status": 503},
        )


def _session() -> tuple[Session, object]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory(), engine


def _add_job(session: Session, project_id: str, *, ordinal: int) -> ActionPostExecutionJob:
    now = datetime.now(timezone.utc)
    row = ActionPostExecutionJob(
        id=str(uuid4()),
        project_id=project_id,
        action_intent_id=str(uuid4()),
        execution_attempt_id=str(uuid4()),
        job_type="verify_outcome",
        status=JOB_PENDING,
        payload_json="{}",
        max_attempts=3,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    return row


def test_dispatcher_round_robins_projects_and_caps_a_noisy_tenant() -> None:
    session, engine = _session()
    try:
        session.add_all(
            [
                VerificationDispatchState(project_id="tenant-a"),
                VerificationDispatchState(project_id="tenant-b"),
            ]
        )
        for ordinal in range(5):
            _add_job(session, "tenant-a", ordinal=ordinal)
        for ordinal in range(2):
            _add_job(session, "tenant-b", ordinal=ordinal)
        session.commit()

        claimed = claim_action_post_execution_jobs(
            session,
            worker_id="test-dispatcher",
            limit=10,
            max_in_flight_per_project=2,
        )

        projects = [job.project_id for job in claimed]
        assert projects[:2] == ["tenant-a", "tenant-b"]
        assert projects.count("tenant-a") == 2
        assert projects.count("tenant-b") == 2
        assert all(job.status == JOB_CLAIMED for job in claimed)
    finally:
        session.close()
        engine.dispose()


def test_claimed_job_starts_once_even_when_celery_redelivers() -> None:
    session, engine = _session()
    try:
        session.add(VerificationDispatchState(project_id="tenant-a"))
        row = _add_job(session, "tenant-a", ordinal=1)
        session.commit()

        claimed = claim_action_post_execution_jobs(session, limit=1)
        assert [job.id for job in claimed] == [row.id]

        started = start_claimed_action_post_execution_job(
            session,
            job_id=row.id,
            worker_id="fetch-worker-a",
        )
        duplicate = start_claimed_action_post_execution_job(
            session,
            job_id=row.id,
            worker_id="fetch-worker-b",
        )

        assert started is not None
        assert started.status == JOB_RUNNING
        assert duplicate is None
    finally:
        session.close()
        engine.dispose()


def test_dispatch_task_routes_fetch_and_receipt_to_separate_lanes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.worker import tasks

    session, engine = _session()
    try:
        session.add(VerificationDispatchState(project_id="tenant-a"))
        verify = _add_job(session, "tenant-a", ordinal=1)
        receipt = _add_job(session, "tenant-a", ordinal=2)
        receipt.job_type = "generate_receipt"
        session.commit()

        sent: list[tuple[str, str]] = []
        monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
        monkeypatch.setattr(
            tasks.celery_app,
            "send_task",
            lambda name, args, queue: sent.append((args[0], queue)),
        )

        result = tasks.process_action_post_execution_jobs.run(limit=2)

        assert result["enqueued"] == 2
        assert dict(sent) == {
            verify.id: "verification_fetch",
            receipt.id: "verification_control",
        }
    finally:
        if session.is_active:
            session.close()
        engine.dispose()


def test_shared_connector_controls_open_circuit_and_do_not_call_sor() -> None:
    backend = FakeRedis()
    connector = RetryableConnector()

    for token in ("job-1", "job-2"):
        wrapped = ControlledConnector(
            connector=connector,
            controls=VerificationExecutionControls(
                project_id="tenant-a",
                connector_type="stripe_refund",
                token=token,
                redis_client=backend,
                enabled=True,
                max_in_flight=1,
                failure_threshold=2,
                failure_window_seconds=60,
                circuit_open_seconds=60,
            ),
        )
        assert wrapped.fetch().metadata == {"retryable": True, "http_status": 503}

    blocked = ControlledConnector(
        connector=connector,
        controls=VerificationExecutionControls(
            project_id="tenant-a",
            connector_type="stripe_refund",
            token="job-3",
            redis_client=backend,
            enabled=True,
            max_in_flight=1,
            failure_threshold=2,
        ),
    ).fetch()

    assert connector.calls == 2
    assert blocked.record is None
    assert blocked.metadata["error_code"] == "connector_circuit_open"
    assert blocked.metadata["retryable"] is True


def test_controls_limit_concurrency_and_fail_closed_when_redis_is_unavailable() -> None:
    backend = FakeRedis()
    first = VerificationExecutionControls(
        project_id="tenant-a",
        connector_type="netsuite_finance",
        token="job-1",
        redis_client=backend,
        enabled=True,
        max_in_flight=1,
    )
    second = VerificationExecutionControls(
        project_id="tenant-a",
        connector_type="netsuite_finance",
        token="job-2",
        redis_client=backend,
        enabled=True,
        max_in_flight=1,
    )

    assert first.acquire().allowed is True
    assert second.acquire().reason == "connector_concurrency_limited"
    first.release()
    assert second.acquire().allowed is True

    unavailable = VerificationExecutionControls(
        project_id="tenant-a",
        connector_type="netsuite_finance",
        token="job-3",
        redis_client=BrokenRedis(),
        enabled=True,
        fail_closed=True,
    )
    assert unavailable.acquire().reason == "verification_controls_unavailable"
