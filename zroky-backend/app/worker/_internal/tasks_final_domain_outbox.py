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


__all__ = [name for name in globals() if not name.startswith("__")]

