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


__all__ = [name for name in globals() if not name.startswith("__")]
