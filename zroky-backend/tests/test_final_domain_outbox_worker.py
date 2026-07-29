from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import FinalDomainOutboxJob
from app.services.final_domain_outbox import process_final_domain_outbox_jobs
from app.worker.celery_app import beat_schedule


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(*, job_type: str, status: str = "pending", **kwargs) -> FinalDomainOutboxJob:
    now = datetime.now(UTC) - timedelta(seconds=1)
    return FinalDomainOutboxJob(
        project_id="project_test",
        environment="test",
        job_type=job_type,
        aggregate_type=kwargs.pop("aggregate_type", "outcome_graph"),
        aggregate_id=kwargs.pop("aggregate_id", f"agg_{job_type}"),
        idempotency_key=kwargs.pop("idempotency_key", f"idem_{job_type}_{status}"),
        status=status,
        payload_json=json.dumps(kwargs.pop("payload", {"source": "test"})),
        available_at=kwargs.pop("available_at", now),
        lease_expires_at=kwargs.pop("lease_expires_at", None),
        **kwargs,
    )


def test_worker_fails_closed_for_unimplemented_server_owned_job() -> None:
    db = _session()
    db.add(_job(job_type="verify_outcome", max_attempts=1, payload={"outcome_graph_id": "graph_1"}))
    db.commit()

    result = process_final_domain_outbox_jobs(db, worker_id="pytest-worker", limit=5)

    row = db.execute(select(FinalDomainOutboxJob)).scalar_one()
    assert result == {"processed": 1, "succeeded": 0, "failed": 1, "dead": 1, "retrying": 0}
    assert row.status == "dead"
    assert row.claimed_by == "pytest-worker"
    assert row.completed_at is None
    assert row.result_json is None
    assert "handler not implemented" in (row.error_message or "")


def test_worker_leaves_execute_recovery_for_external_executor_claim_path() -> None:
    db = _session()
    db.add(
        _job(
            job_type="execute_recovery",
            aggregate_type="recovery_plan",
            payload={"recovery_plan_id": "plan_1", "executor_ref": "executor_a"},
        )
    )
    db.commit()

    result = process_final_domain_outbox_jobs(db, worker_id="pytest-worker", limit=5)

    row = db.execute(select(FinalDomainOutboxJob)).scalar_one()
    assert result == {"processed": 0, "succeeded": 0, "failed": 0, "dead": 0, "retrying": 0}
    assert row.status == "pending"
    assert row.claimed_by is None
    assert row.result_json is None


def test_worker_reclaims_expired_server_owned_claim_and_retries() -> None:
    db = _session()
    db.add(
        _job(
            job_type="generate_evidence",
            status="claimed",
            attempt_count=1,
            claimed_by="stale-worker",
            lease_expires_at=datetime.now(UTC) - timedelta(minutes=5),
            payload={"subject_id": "incident_1"},
        )
    )
    db.commit()

    result = process_final_domain_outbox_jobs(db, worker_id="pytest-worker", limit=5)

    row = db.execute(select(FinalDomainOutboxJob)).scalar_one()
    assert result == {"processed": 1, "succeeded": 0, "failed": 1, "dead": 0, "retrying": 1}
    assert row.status == "retrying"
    assert row.claimed_by == "pytest-worker"
    assert row.attempt_count == 2


def test_final_domain_outbox_worker_is_beat_scheduled() -> None:
    entry = beat_schedule["final-domain-outbox-sweep"]
    assert entry["task"] == "app.worker.tasks.process_final_domain_outbox_jobs"
    assert entry["options"]["queue"] == "diagnosis_fast"
