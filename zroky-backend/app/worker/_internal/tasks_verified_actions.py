from app.worker._internal.tasks_common import *


@celery_app.task(
    name="app.worker.tasks.process_action_post_execution_jobs",
    queue="diagnosis_fast",
)
def process_action_post_execution_jobs(limit: int | None = None) -> dict:
    """Poll the verified-action transactional outbox."""
    from app.services.action_post_execution import (
        process_action_post_execution_jobs as process_jobs,
    )

    settings = get_settings()
    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.ACTION_POST_EXECUTION_SWEEP_LIMIT)
    )
    session = SessionLocal()
    try:
        result = process_jobs(
            session,
            worker_id="celery-action-post-execution",
            limit=effective_limit,
        )
        logger.info(
            "action_post_execution_jobs.completed",
            extra={
                "event": "verified_action_post_execution",
                "processed": result["processed"],
            },
        )
        return result
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.sweep_stale_action_execution_attempts",
    queue="diagnosis_fast",
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
    queue="diagnosis_fast",
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
    queue="diagnosis_fast",
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
