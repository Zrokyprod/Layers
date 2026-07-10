from app.worker._internal.tasks_common import *


@celery_app.task(
    name="app.worker.tasks.process_action_post_execution_jobs",
    queue="verification_control",
)
def process_action_post_execution_jobs(limit: int | None = None) -> dict:
    """Fairly claim verified-action outbox rows and publish their work lanes."""
    from app.services.action_post_execution import (
        claim_action_post_execution_jobs,
        requeue_claimed_action_post_execution_job,
    )

    settings = get_settings()
    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.ACTION_POST_EXECUTION_SWEEP_LIMIT)
    )
    session = SessionLocal()
    try:
        jobs = claim_action_post_execution_jobs(
            session,
            worker_id="celery-action-post-execution-dispatcher",
            limit=effective_limit,
        )
        enqueued: list[dict[str, str]] = []
        requeued: list[str] = []
        for job in jobs:
            queue = "verification_fetch" if job.job_type == "verify_outcome" else "verification_control"
            try:
                celery_app.send_task(
                    "app.worker.tasks.execute_action_post_execution_job",
                    args=[job.id],
                    queue=queue,
                )
                enqueued.append({"job_id": job.id, "queue": queue})
            except Exception as exc:  # noqa: BLE001
                requeue_claimed_action_post_execution_job(
                    session,
                    job_id=job.id,
                    reason=exc.__class__.__name__,
                )
                requeued.append(job.id)
        result = {
            "claimed": len(jobs),
            "enqueued": len(enqueued),
            "requeued": len(requeued),
            "jobs": enqueued,
            "requeued_job_ids": requeued,
        }
        logger.info(
            "action_post_execution_jobs.dispatched",
            extra={
                "event": "verified_action_post_execution",
                "claimed": result["claimed"],
                "enqueued": result["enqueued"],
                "requeued": result["requeued"],
            },
        )
        return result
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.execute_action_post_execution_job",
    queue="verification_fetch",
)
def execute_action_post_execution_job(job_id: str) -> dict:
    """Run exactly one claimed outbox item in its already-selected lane."""
    from app.services.action_post_execution import (
        process_action_post_execution_job,
        start_claimed_action_post_execution_job,
    )

    session = SessionLocal()
    try:
        started = start_claimed_action_post_execution_job(
            session,
            job_id=str(job_id),
            worker_id="celery-action-post-execution-worker",
        )
        if started is None:
            return {"status": "skipped", "job_id": str(job_id)}
        processed = process_action_post_execution_job(session, job_id=started.id)
        return {
            "status": processed.job.status,
            "job_id": processed.job.id,
            "job_type": processed.job.job_type,
            "result": processed.result,
        }
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.sweep_stale_action_execution_attempts",
    queue="verification_sweep",
)
def sweep_stale_action_execution_attempts(
    stale_after_seconds: int | None = None,
    limit: int | None = None,
) -> dict:
    """Resolve runner attempts that never reported a terminal result."""
    from app.services.action_post_execution import sweep_stale_execution_attempts

    settings = get_settings()
    effective_stale_after = (
        int(stale_after_seconds)
        if stale_after_seconds is not None and stale_after_seconds > 0
        else int(settings.ACTION_EXECUTION_ATTEMPT_STALE_SECONDS)
    )
    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.ACTION_EXECUTION_ATTEMPT_SWEEP_LIMIT)
    )
    session = SessionLocal()
    try:
        result = sweep_stale_execution_attempts(
            session,
            stale_after_seconds=effective_stale_after,
            limit=effective_limit,
        )
        logger.info(
            "stale_action_execution_attempts.completed",
            extra={
                "event": "verified_action_stale_execution_attempts",
                "resolved": result["resolved"],
            },
        )
        return result
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.sweep_pending_proof_reconciliations",
    queue="verification_sweep",
)
def sweep_pending_proof_reconciliations(limit: int | None = None) -> dict:
    """Expire pending proof checks whose verification window has closed.

    This is the bounded-limbo guard for temporal proof. It does not re-fetch SOR
    evidence; a future reverify worker can consume the due rows surfaced by the
    service. This task ensures overdue pending rows settle to mismatched or
    unverifiable instead of staying pending forever.
    """
    from app.services.outcome_reconciliation import (
        sweep_pending_reconciliation_checks,
    )

    settings = get_settings()
    if not settings.PROOF_PENDING_SWEEP_ENABLED:
        logger.info(
            "sweep_pending_proof_reconciliations: PROOF_PENDING_SWEEP_ENABLED=false - skipping"
        )
        return {"skipped": True, "reason": "PROOF_PENDING_SWEEP_ENABLED=false"}

    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.PROOF_PENDING_SWEEP_LIMIT)
    )
    session = SessionLocal()
    try:
        result = sweep_pending_reconciliation_checks(
            session,
            limit=effective_limit,
        )
        payload = {
            "expired": result.expired,
            "due_for_reverify": result.due_for_reverify,
            "expired_check_ids": result.expired_check_ids,
            "due_check_ids": result.due_check_ids,
        }
        logger.info(
            "pending_proof_reconciliations.completed",
            extra={
                "event": "pending_proof_reconciliation",
                "task": "sweep_pending_proof_reconciliations",
                "expired": result.expired,
                "due_for_reverify": result.due_for_reverify,
            },
        )
        return payload
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.sweep_stale_private_runner_verifications",
    queue="verification_sweep",
)
def sweep_stale_private_runner_verifications(limit: int | None = None) -> dict:
    """Settle verification jobs when their assigned private runner disappears."""
    from app.services.private_runner_verification import (
        sweep_stale_private_runner_verifications as sweep_jobs,
    )

    settings = get_settings()
    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.PRIVATE_RUNNER_VERIFICATION_SWEEP_LIMIT)
    )
    session = SessionLocal()
    try:
        result = sweep_jobs(
            session,
            stale_after_seconds=int(settings.PRIVATE_RUNNER_VERIFICATION_STALE_SECONDS),
            limit=effective_limit,
        )
        session.commit()
        logger.info(
            "stale_private_runner_verifications.completed",
            extra={"event": "private_runner_verification", "expired": result["expired"]},
        )
        return result
    finally:
        session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
