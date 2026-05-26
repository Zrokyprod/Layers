from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

@celery_app.task(name="app.worker.tasks.run_judge_calibration_all_projects")
def run_judge_calibration_all_projects() -> dict:
    """Beat task: run judge calibration for every active project with
    labeled golden traces.

    Idempotent per (project_id, judge_model, run_date) â€” the runner
    short-circuits if a complete row already exists.
    """
    from datetime import date as _date

    from sqlalchemy import select

    from app.db.models import Project
    from app.services.judge_calibration_runner import run_calibration

    settings = get_settings()
    if not settings.JUDGE_CALIBRATION_ENABLED:
        logger.info("judge_calibration_all_projects: JUDGE_CALIBRATION_ENABLED=false â€” skipping")
        return {"skipped": True, "reason": "JUDGE_CALIBRATION_ENABLED=false"}

    today = _date.today()
    session = SessionLocal()
    results = []
    try:
        projects = session.execute(select(Project).where(Project.active.is_(True))).scalars().all()
        for project in projects:
            set_db_tenant_context(project.id)
            try:
                run = run_calibration(
                    db=session,
                    project_id=project.id,
                    judge_model=settings.JUDGE_SINGLE_MODEL,
                )
                results.append(
                    {
                        "project_id": project.id,
                        "run_id": run.id,
                        "status": run.status,
                        "accuracy": run.accuracy,
                        "sample_count": run.sample_count,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "judge_calibration.project_failed",
                    extra={
                        "project_id": project.id,
                        "error": str(exc),
                    },
                )
                results.append(
                    {
                        "project_id": project.id,
                        "status": "error",
                        "error": str(exc),
                    }
                )
    finally:
        session.close()

    logger.info(
        "judge_calibration_all_projects.completed",
        extra={
            "event": "judge_calibration_all_projects",
            "task": "run_judge_calibration_all_projects",
            "date": str(today),
            "projects": len(results),
            "completed": sum(1 for r in results if r.get("status") == "complete"),
        },
    )
    return {"date": str(today), "results": results}


@celery_app.task(name="app.worker.tasks.run_provider_drift_watch")
def run_provider_drift_watch() -> dict:
    """Beat task: dispatch probe suite for every active model, then run
    the aggregator for today's date.

    Two-phase so probes and alerts are never in an inconsistent state:
      1. Runner: one (model, date) at a time, budget-capped.
      2. Aggregator: compute drift metrics, upsert alerts.

    Returns:
        {"runs": list of RunOutcome dicts, "aggregator": AggregatorOutcome dict}
    """
    from datetime import date as _date

    from app.services.provider_drift.aggregator import run_aggregator
    from app.services.provider_drift.models import ModelSpec
    from app.services.provider_drift.prompt_suite import load_active_prompts
    from app.services.provider_drift.runner import execute_run, load_active_models as _load_active_models

    settings = get_settings()
    if not settings.PROVIDER_DRIFT_WATCH_ENABLED:
        logger.info("run_provider_drift_watch: PROVIDER_DRIFT_WATCH_ENABLED=false â€” skipping")
        return {"skipped": True, "reason": "PROVIDER_DRIFT_WATCH_ENABLED=false"}

    today = _date.today()
    session = SessionLocal()
    run_results = []
    try:
        models = _load_active_models(session)
        prompts = load_active_prompts(session)
        for model_row in models:
            model_spec = ModelSpec(
                id=model_row.id,
                provider=model_row.provider,
                model_id=model_row.model_id,
                display_name=model_row.display_name,
                family=model_row.family,
                active=model_row.active,
            )
            outcome = execute_run(
                db=session,
                model_spec=model_spec,
                run_date=today,
                prompts=prompts,
                provider_client=None,
                embedder=None,
                budget_usd=settings.PROVIDER_DRIFT_WATCH_BUDGET_USD,
            )
            run_results.append({
                "run_id": outcome.run_id,
                "model_id": outcome.model_id,
                "status": outcome.status,
                "prompts_total": outcome.prompts_total,
                "prompts_ok": outcome.prompts_ok,
                "cost_usd": outcome.cost_usd,
            })

        agg = run_aggregator(db=session, current_date=today)

        logger.info(
            "provider_drift_watch.completed",
            extra={
                "event": "provider_drift_watch",
                "task": "run_provider_drift_watch",
                "date": str(today),
                "runs": len(run_results),
                "metrics_evaluated": agg.metrics_evaluated,
                "alerts_published": agg.alerts_published,
                "candidates": agg.candidates_recorded,
                "skipped": agg.skipped_for_coverage,
            },
        )

        return {
            "date": str(today),
            "runs": run_results,
            "aggregator": {
                "metrics_evaluated": agg.metrics_evaluated,
                "alerts_published": agg.alerts_published,
                "candidates_recorded": agg.candidates_recorded,
                "skipped_for_coverage": agg.skipped_for_coverage,
            },
        }
    finally:
        session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
