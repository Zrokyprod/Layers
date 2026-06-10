from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes.replay import WorkerPollRequest, WorkerResultPayload, worker_poll, worker_result
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ReplayJob


@pytest.fixture()
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPLAY_WORKER_TOKEN", "worker-secret")
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'replay-claims.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def _seed_job(db_session, *, replay_id: str = "replay_1", status: str = "pending") -> ReplayJob:
    job = ReplayJob(
        id=replay_id,
        tenant_id="proj_claims",
        status=status,
        candidate_fix_diff="",
        artifact_url="https://artifacts.example/replay_1.json",
        artifact_signature="sig",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_worker_poll_claims_job_once_and_hides_active_lease(db_session) -> None:
    _seed_job(db_session)

    first = worker_poll(
        WorkerPollRequest(worker_token="worker-secret", worker_id="worker-a", capacity=1),
        db_session,
    )
    second = worker_poll(
        WorkerPollRequest(worker_token="worker-secret", worker_id="worker-b", capacity=1),
        db_session,
    )

    assert [job.replay_id for job in first.jobs] == ["replay_1"]
    assert second.jobs == []

    stored = db_session.execute(select(ReplayJob).where(ReplayJob.id == "replay_1")).scalar_one()
    assert stored.status == "running"
    assert stored.claimed_by == "worker-a"
    assert stored.lease_expires_at is not None
    assert stored.attempt_count == 1


def test_worker_poll_retries_stale_lease(db_session) -> None:
    _seed_job(db_session)
    worker_poll(WorkerPollRequest(worker_token="worker-secret", worker_id="worker-a", capacity=1), db_session)

    stored = db_session.execute(select(ReplayJob).where(ReplayJob.id == "replay_1")).scalar_one()
    stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(stored)
    db_session.commit()

    retry = worker_poll(
        WorkerPollRequest(worker_token="worker-secret", worker_id="worker-b", capacity=1),
        db_session,
    )

    assert [job.replay_id for job in retry.jobs] == ["replay_1"]
    db_session.refresh(stored)
    assert stored.claimed_by == "worker-b"
    assert stored.attempt_count == 2


def test_worker_result_rejects_different_claimed_worker(db_session) -> None:
    _seed_job(db_session)
    worker_poll(WorkerPollRequest(worker_token="worker-secret", worker_id="worker-a", capacity=1), db_session)

    payload = WorkerResultPayload(
        worker_token="worker-secret",
        worker_id="worker-b",
        result={"replay_id": "replay_1", "status": "pass", "diff_metric": 0.0},
    )

    with pytest.raises(HTTPException) as error:
        worker_result(payload, db_session)

    assert error.value.status_code == 409
