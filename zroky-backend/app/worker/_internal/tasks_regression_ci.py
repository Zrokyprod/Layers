from app.worker._internal.tasks_common import *


@celery_app.task(
    name="app.worker.tasks.process_regression_ci_run",
    queue="diagnosis_pattern",
    bind=True,
    max_retries=2,
)
def process_regression_ci_run(
    self,
    tenant_id: str,
    run_id: str,
    request_payload: dict,
) -> dict:
    """Execute a persisted regression-CI run from the durable worker queue."""
    task_key = f"regression-ci:{tenant_id}:{run_id}"
    with idempotency_guard(task_key) as acquired:
        if not acquired:
            return {
                "status": "duplicate_ignored",
                "tenant_id": tenant_id,
                "run_id": run_id,
            }

        from app.api.routes.regression_ci import _run_regression_ci_background

        _run_regression_ci_background(
            tenant_id=tenant_id,
            run_id=run_id,
            request_payload=request_payload,
        )
        return {
            "status": "submitted",
            "tenant_id": tenant_id,
            "run_id": run_id,
        }


__all__ = [name for name in globals() if not name.startswith("__")]
