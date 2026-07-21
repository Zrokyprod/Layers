from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import FinalDomainOutboxJob

SERVER_OWNED_JOB_TYPES = {"verify_outcome", "plan_recovery", "generate_evidence"}
EXTERNAL_EXECUTOR_JOB_TYPES = {"execute_recovery"}
logger = logging.getLogger(__name__)


def _load_payload(row: FinalDomainOutboxJob) -> dict[str, Any]:
    try:
        payload = json.loads(row.payload_json or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _claim_next_server_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int,
) -> FinalDomainOutboxJob | None:
    now = datetime.now(UTC)
    row = db.execute(
        select(FinalDomainOutboxJob)
        .where(
            FinalDomainOutboxJob.job_type.in_(SERVER_OWNED_JOB_TYPES),
            or_(
                FinalDomainOutboxJob.status == "pending",
                (FinalDomainOutboxJob.status == "retrying") & (FinalDomainOutboxJob.available_at <= now),
                (FinalDomainOutboxJob.status == "claimed") & (FinalDomainOutboxJob.lease_expires_at <= now),
            ),
        )
        .order_by(FinalDomainOutboxJob.available_at.asc(), FinalDomainOutboxJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if row is None:
        return None

    row.status = "claimed"
    row.claimed_by = worker_id[:128]
    row.claimed_at = now
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.attempt_count = int(row.attempt_count or 0) + 1
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _run_server_job(row: FinalDomainOutboxJob) -> dict[str, Any]:
    _load_payload(row)
    raise NotImplementedError(f"final-domain job handler not implemented: {row.job_type}")


def _process_server_job(db: Session, *, job_id: str) -> str:
    row = db.execute(select(FinalDomainOutboxJob).where(FinalDomainOutboxJob.id == job_id)).scalar_one()
    try:
        result = _run_server_job(row)
        row.status = "succeeded"
        row.result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
        row.error_message = None
        row.completed_at = datetime.now(UTC)
    except Exception as exc:
        row.error_message = str(exc)[:2000]
        row.status = "dead" if int(row.attempt_count or 0) >= int(row.max_attempts or 1) else "retrying"
        row.available_at = datetime.now(UTC) + timedelta(seconds=60)
        if row.status == "dead":
            logger.error(
                "final_domain_outbox.job_dead project_id=%s environment=%s job_id=%s job_type=%s error=%s",
                row.project_id,
                row.environment,
                row.id,
                row.job_type,
                row.error_message,
            )
    db.add(row)
    db.commit()
    return row.status


def process_final_domain_outbox_jobs(
    db: Session,
    *,
    worker_id: str = "final-domain-outbox-worker",
    limit: int = 25,
    lease_seconds: int = 300,
) -> dict[str, int]:
    processed = 0
    succeeded = 0
    failed = 0
    dead = 0
    retrying = 0

    for _ in range(max(0, int(limit))):
        row = _claim_next_server_job(db, worker_id=worker_id, lease_seconds=lease_seconds)
        if row is None:
            break
        status = _process_server_job(db, job_id=row.id)
        if status == "succeeded":
            succeeded += 1
        elif status in {"dead", "retrying"}:
            failed += 1
            dead += int(status == "dead")
            retrying += int(status == "retrying")
        processed += 1

    return {"processed": processed, "succeeded": succeeded, "failed": failed, "dead": dead, "retrying": retrying}
