from app.worker._internal.tasks_common import *


@celery_app.task(
    name="app.worker.tasks.process_final_domain_outbox_jobs",
    queue="diagnosis_fast",
)
def process_final_domain_outbox_jobs(limit: int | None = None) -> dict:
    """Drain server-owned final-domain outbox jobs."""
    from app.services.final_domain_outbox import process_final_domain_outbox_jobs as process_jobs

    session = SessionLocal()
    try:
        return process_jobs(
            session,
            worker_id="celery-final-domain-outbox",
            limit=int(limit) if limit and limit > 0 else 25,
        )
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.recheck_due_final_outcome_graphs",
    queue="verification_sweep",
)
def recheck_due_final_outcome_graphs(limit: int | None = None) -> dict:
    """Rebuild pending/unknown outcome graphs after new observations arrive."""
    from app.services.final_outcome_graphs import recheck_due_outcome_graphs

    settings = get_settings()
    session = SessionLocal()
    try:
        return recheck_due_outcome_graphs(
            session,
            limit=int(limit) if limit and limit > 0 else int(settings.FINAL_OUTCOME_GRAPH_RECHECK_LIMIT),
            verification_window_seconds=int(settings.FINAL_OUTCOME_GRAPH_VERIFICATION_WINDOW_SECONDS),
            observation_pull_max_per_sweep=int(settings.OBSERVATION_PULL_MAX_PER_SWEEP),
        )
    finally:
        session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
