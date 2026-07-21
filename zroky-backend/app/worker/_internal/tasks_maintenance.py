from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

@celery_app.task(name="app.worker.tasks.requeue_pending_diagnosis_jobs", queue="diagnosis_fast")
def requeue_pending_diagnosis_jobs(
    tenant_id: str,
    *,
    older_than_seconds: int = 60,
    limit: int = 100,
) -> dict[str, Any]:
    return {"status": "skipped", "tenant_id": tenant_id, "reason": "diagnosis_worker_removed"}


@celery_app.task(name="app.worker.tasks.purge_project_retention", queue="diagnosis_fast")
def purge_project_retention(
    tenant_id: str,
    *,
    retention_days: int | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    effective_dry_run = settings.RETENTION_PURGE_DRY_RUN if dry_run is None else bool(dry_run)
    session = SessionLocal()
    try:
        set_db_tenant_context(session, tenant_id)
        configured_days = retention_days
        if configured_days is None:
            config = session.execute(
                select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
            ).scalar_one_or_none()
            configured_days = config.retention_days if config is not None else DEFAULT_RETENTION_DAYS

        summary = purge_project_retention_data(
            session=session,
            tenant_id=tenant_id,
            retention_days=normalize_retention_days(configured_days),
            now=datetime.now(timezone.utc),
            batch_size=settings.RETENTION_PURGE_BATCH_SIZE,
            dry_run=effective_dry_run,
        )

        for table_name, row_count in summary["deleted_by_table"].items():
            record_retention_rows(table_name, row_count, dry_run=effective_dry_run)

        logger.info(
            "retention_project_purge_completed",
            extra={
                "event": "retention_enforcement",
                "tenant_id": tenant_id,
                "retention_days": summary["retention_days"],
                "dry_run": effective_dry_run,
                "total_deleted": summary["total_deleted"],
            },
        )
        return summary
    except Exception:
        session.rollback()
        logger.exception(
            "retention_project_purge_failed",
            extra={"event": "retention_enforcement", "tenant_id": tenant_id},
        )
        raise
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.run_retention_enforcement", queue="diagnosis_fast")
def run_retention_enforcement(
    *,
    dry_run: bool | None = None,
    tenant_limit: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.RETENTION_ENFORCEMENT_ENABLED:
        record_retention_run("disabled")
        return {
            "status": "disabled",
            "retention_enforcement_enabled": False,
            "processed_tenants": 0,
            "failed_tenants": 0,
            "total_deleted": 0,
            "results": [],
            "errors": [],
        }

    effective_dry_run = settings.RETENTION_PURGE_DRY_RUN if dry_run is None else bool(dry_run)
    bounded_limit = max(1, int(tenant_limit)) if tenant_limit is not None else None
    session = SessionLocal()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    try:
        tenant_query = select(Project.id).where(Project.is_active.is_(True)).order_by(Project.id.asc())
        if bounded_limit is not None:
            tenant_query = tenant_query.limit(bounded_limit)
        tenant_ids = list(session.execute(tenant_query).scalars().all())

        for tenant_id in tenant_ids:
            try:
                set_db_tenant_context(session, tenant_id)
                config = session.execute(
                    select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
                ).scalar_one_or_none()
                retention_days = normalize_retention_days(
                    config.retention_days if config is not None else DEFAULT_RETENTION_DAYS
                )
                summary = purge_project_retention_data(
                    session=session,
                    tenant_id=tenant_id,
                    retention_days=retention_days,
                    now=datetime.now(timezone.utc),
                    batch_size=settings.RETENTION_PURGE_BATCH_SIZE,
                    dry_run=effective_dry_run,
                )
                for table_name, row_count in summary["deleted_by_table"].items():
                    record_retention_rows(table_name, row_count, dry_run=effective_dry_run)
                results.append(summary)
            except Exception as exc:
                session.rollback()
                errors.append(
                    {
                        "tenant_id": tenant_id,
                        "error": mask_error_message(exc),
                    }
                )
                logger.exception(
                    "retention_tenant_run_failed",
                    extra={"event": "retention_enforcement", "tenant_id": tenant_id},
                )

        total_deleted = sum(int(item.get("total_deleted", 0) or 0) for item in results)
        status = "ok"
        if errors:
            status = "partial_failure" if results else "failed"

        record_retention_run(status)
        summary_payload = {
            "status": status,
            "retention_enforcement_enabled": True,
            "dry_run": effective_dry_run,
            "processed_tenants": len(results),
            "failed_tenants": len(errors),
            "total_deleted": total_deleted,
            "results": results,
            "errors": errors,
        }
        logger.info(
            "retention_enforcement_run_completed",
            extra={
                "event": "retention_enforcement",
                "status": status,
                "processed_tenants": len(results),
                "failed_tenants": len(errors),
                "total_deleted": total_deleted,
                "dry_run": effective_dry_run,
            },
        )
        return summary_payload
    finally:
        session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
