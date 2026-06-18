from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

@celery_app.task(name="app.worker.tasks.generate_weekly_digests", queue="diagnosis_fast")
def generate_weekly_digests(week_start_iso: str | None = None) -> dict:
    """Stage 1: compute one weekly digest row per active project."""
    settings = get_settings()
    if not settings.DIGEST_ENABLED:
        return {"skipped": True, "reason": "DIGEST_ENABLED=false"}

    session = SessionLocal()
    generated = 0
    failed = 0
    results: list[dict[str, Any]] = []
    try:
        week_start = (
            monday_of(datetime.fromisoformat(week_start_iso).date())
            if week_start_iso
            else monday_of(datetime.now(timezone.utc).date())
        )
        projects: list[Project] = list(
            session.execute(
                select(Project).where(Project.is_active.is_(True))
            ).scalars().all()
        )
        for project in projects:
            try:
                digest = generate_weekly_digest(
                    session,
                    project_id=project.id,
                    week_start=week_start,
                )
                generated += 1
                results.append({"project_id": project.id, "status": "ok", "digest_id": digest.id})
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                failed += 1
                results.append({"project_id": project.id, "status": "failed", "error": mask_error_message(exc)})
                logger.exception("generate_weekly_digest_failed", extra={"project_id": project.id})
        return {
            "week_start": week_start.isoformat(),
            "projects_processed": len(projects),
            "generated": generated,
            "failed": failed,
            "results": results,
        }
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.send_pending_digests", queue="diagnosis_fast")
def send_pending_digests(week_start_iso: str | None = None) -> dict:
    """Stage 2: send queued digest rows and stamp sent_at only on success."""
    settings = get_settings()
    if not settings.DIGEST_ENABLED:
        return {"skipped": True, "reason": "DIGEST_ENABLED=false"}

    session = SessionLocal()
    sent = 0
    failed = 0
    skipped_no_recipients = 0
    try:
        week_start = (
            monday_of(datetime.fromisoformat(week_start_iso).date())
            if week_start_iso
            else None
        )
        digests = list_pending_digests(
            session,
            week_start=week_start,
            limit=max(1, int(settings.DIGEST_SEND_BATCH_SIZE)),
        )
        for digest in digests:
            recipients = resolve_recipient_emails(session, digest.project_id)
            if not recipients:
                skipped_no_recipients += 1
                continue
            summary = parse_summary_json(digest.summary_json)
            prevented_waste = summary.get("cost", {}).get("prevented_waste_usd", 0)
            subject = f"ZROKY saved you ${float(prevented_waste or 0):.2f} this week"
            ok = send_email(
                recipients,
                subject,
                digest.html_blob or "",
                plain_body=render_plain(summary) if summary else None,
            )
            if ok:
                mark_digest_sent(session, digest=digest, sent_to_emails=recipients)
                sent += 1
            else:
                failed += 1
        return {
            "processed": len(digests),
            "sent": sent,
            "failed": failed,
            "skipped_no_recipients": skipped_no_recipients,
        }
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.notify_fix_watch_recurrences", queue="diagnosis_fast")
def notify_fix_watch_recurrences() -> dict:
    """Celery beat task: scan active fix watches, send email/Slack for new recurrences."""
    session = SessionLocal()
    notified = 0
    errors = 0

    try:
        now = datetime.now(timezone.utc)
        # Only watches that are still active (not yet expired)
        watches: list[DiagnosisFixWatch] = list(
            session.execute(
                select(DiagnosisFixWatch).where(DiagnosisFixWatch.watch_expires_at > now)
            ).scalars().all()
        )

        for watch in watches:
            try:
                set_db_tenant_context(session, watch.tenant_id)
                target_cats = json.loads(watch.target_categories_json or "[]")
                if not target_cats:
                    continue

                recurrence_jobs = []
                _candidate_jobs = list(
                    session.execute(
                        select(DiagnosisJob).where(
                            and_(
                                DiagnosisJob.tenant_id == watch.tenant_id,
                                DiagnosisJob.status.in_(SUCCESS_DIAGNOSIS_STATUSES),
                                DiagnosisJob.created_at > watch.resolved_at,
                            )
                        ).order_by(DiagnosisJob.created_at.desc()).limit(500)
                    ).scalars().all()
                )
                for _job in _candidate_jobs:
                    try:
                        _result = json.loads(_job.result_json or "{}")
                        _diagnoses = _result.get("diagnoses") if isinstance(_result, dict) else []
                        if not isinstance(_diagnoses, list):
                            continue
                        _job_cats = {
                            d.get("category") for d in _diagnoses
                            if isinstance(d, dict) and isinstance(d.get("category"), str)
                        }
                        if _job_cats & set(target_cats):
                            recurrence_jobs.append(_job)
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        continue
                if not recurrence_jobs:
                    continue

                # Check if we already sent a notification today for this watch
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                already_notified = session.execute(
                    select(AuditLog).where(
                        and_(
                            AuditLog.tenant_id == watch.tenant_id,
                            AuditLog.diagnosis_id == watch.diagnosis_id,
                            AuditLog.action == "fix_watch_recurrence_notified",
                            AuditLog.created_at >= today_start,
                        )
                    ).limit(1)
                ).scalars().first()
                if already_notified:
                    continue

                project = session.get(Project, watch.tenant_id)
                project_name = project.name if project else watch.tenant_id

                slack_msg = (
                    f":rotating_light: *Fix regression* in project {project_name}\n"
                    f"Diagnosis {watch.diagnosis_id} ({', '.join(target_cats)}) has recurred "
                    f"{len(recurrence_jobs)} time(s) since the fix. Review the dashboard."
                )
                send_slack_message(slack_msg)

                # Also deliver directly to the tenant's own Slack channel.
                from app.services.notification_dispatch import dispatch_alert_to_tenant_channels
                dispatch_alert_to_tenant_channels(
                    db=session,
                    tenant_id=watch.tenant_id,
                    categories=target_cats,
                    agent_name=None,
                    diagnosis_id=watch.diagnosis_id,
                )

                # Record notification in audit log to avoid re-notifying today
                audit = AuditLog(
                    tenant_id=watch.tenant_id,
                    diagnosis_id=watch.diagnosis_id,
                    action="fix_watch_recurrence_notified",
                    actor_subject="system",
                    metadata_json=json.dumps({"recurrence_count": len(recurrence_jobs)}),
                )
                session.add(audit)
                session.commit()
                notified += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.error("notify_fix_watch_recurrences: error for watch %s: %s", watch.id, exc)

        return {"watches_scanned": len(watches), "notifications_sent": notified, "errors": errors}
    finally:
        session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
