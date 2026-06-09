from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

from app.services.discovery.runtime import (
    DiscoveryRuntimeResult,
    refresh_baselines,
    scan_and_surface,
)


@celery_app.task(name="app.worker.tasks.refresh_discovery_baselines", queue="diagnosis_fast")
def refresh_discovery_baselines(
    *,
    project_id: str | None = None,
    project_limit: int | None = None,
) -> dict[str, Any]:
    """Refresh Discovery baselines for active projects.

    The task is a hard no-op while DISCOVERY_ENABLED=false.
    """
    settings = get_settings()
    if not settings.DISCOVERY_ENABLED:
        return _disabled_discovery_task_result("refresh_discovery_baselines")

    session = SessionLocal()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        project_ids = _resolve_discovery_project_ids(
            session,
            project_id=project_id,
            project_limit=project_limit,
            default_limit=settings.DISCOVERY_PROJECT_LIMIT,
        )
        for current_project_id in project_ids:
            try:
                set_db_tenant_context(session, current_project_id)
                result = refresh_baselines(
                    session,
                    project_id=current_project_id,
                    settings=settings,
                )
                results.append(_discovery_result_payload(current_project_id, result))
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                errors.append(
                    {
                        "project_id": current_project_id,
                        "error": mask_error_message(exc),
                    }
                )
                logger.exception(
                    "discovery_baseline_refresh_project_failed",
                    extra={
                        "event": "discovery_baseline_refresh",
                        "project_id": current_project_id,
                    },
                )
        return _discovery_task_summary(
            task="refresh_discovery_baselines",
            project_ids=project_ids,
            results=results,
            errors=errors,
        )
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.scan_discovery_anomalies", queue="diagnosis_fast")
def scan_discovery_anomalies(
    *,
    project_id: str | None = None,
    project_limit: int | None = None,
) -> dict[str, Any]:
    """Scan new production calls and surface Discovery anomalies.

    The runtime owns the watermark, so repeated task executions are idempotent
    for already-scanned call rows.
    """
    settings = get_settings()
    if not settings.DISCOVERY_ENABLED:
        return _disabled_discovery_task_result("scan_discovery_anomalies")

    session = SessionLocal()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        project_ids = _resolve_discovery_project_ids(
            session,
            project_id=project_id,
            project_limit=project_limit,
            default_limit=settings.DISCOVERY_PROJECT_LIMIT,
        )
        for current_project_id in project_ids:
            try:
                set_db_tenant_context(session, current_project_id)
                result = scan_and_surface(
                    session,
                    project_id=current_project_id,
                    settings=settings,
                )
                results.append(_discovery_result_payload(current_project_id, result))
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                errors.append(
                    {
                        "project_id": current_project_id,
                        "error": mask_error_message(exc),
                    }
                )
                logger.exception(
                    "discovery_scan_project_failed",
                    extra={
                        "event": "discovery_scan",
                        "project_id": current_project_id,
                    },
                )
        return _discovery_task_summary(
            task="scan_discovery_anomalies",
            project_ids=project_ids,
            results=results,
            errors=errors,
        )
    finally:
        session.close()


def _resolve_discovery_project_ids(
    session,
    *,
    project_id: str | None,
    project_limit: int | None,
    default_limit: int,
) -> list[str]:
    if project_id is not None:
        return [project_id]

    limit = max(1, int(project_limit if project_limit is not None else default_limit))
    return list(
        session.execute(
            select(Project.id).where(Project.is_active.is_(True)).order_by(Project.id.asc()).limit(limit)
        )
        .scalars()
        .all()
    )


def _discovery_result_payload(
    project_id: str,
    result: DiscoveryRuntimeResult,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "enabled": result.enabled,
        "skipped_reason": result.skipped_reason,
        "calls_loaded": result.calls_loaded,
        "baselines_written": result.baselines_written,
        "traces_scored": result.traces_scored,
        "candidates_found": result.candidates_found,
        "anomalies_written": result.anomalies_written,
        "watermark_advanced": result.watermark_advanced,
    }


def _discovery_task_summary(
    *,
    task: str,
    project_ids: list[str],
    results: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    status = "ok"
    if errors:
        status = "partial_failure" if results else "failed"
    return {
        "status": status,
        "task": task,
        "discovery_enabled": True,
        "projects_seen": len(project_ids),
        "projects_processed": len(results),
        "failed_projects": len(errors),
        "results": results,
        "errors": errors,
    }


def _disabled_discovery_task_result(task: str) -> dict[str, Any]:
    return {
        "status": "disabled",
        "task": task,
        "discovery_enabled": False,
        "reason": "DISCOVERY_ENABLED=false",
        "projects_seen": 0,
        "projects_processed": 0,
        "failed_projects": 0,
        "results": [],
        "errors": [],
    }


__all__ = [name for name in globals() if not name.startswith("__")]
