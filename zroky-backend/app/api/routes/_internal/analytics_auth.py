from app.api.routes._internal.analytics_common import *

def _extract_auth_evidence(result_json: str | None) -> dict[str, Any] | None:
    """Return the first AUTH_FAILURE diagnosis evidence dict, or None."""
    try:
        if not result_json:
            return None
        payload = json.loads(result_json)
        diagnoses = payload.get("diagnoses", [])
        if not isinstance(diagnoses, list):
            return None
        for diag in diagnoses:
            if isinstance(diag, dict) and str(diag.get("category", "")).upper() == "AUTH_FAILURE":
                ev = diag.get("evidence")
                return ev if isinstance(ev, dict) else {}
    except (ValueError, TypeError):
        pass
    return None


@router.get("/auth/summary", response_model=AuthSummaryResponse)
def get_auth_summary(
    hours: int = Query(default=24, ge=1, le=168),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> AuthSummaryResponse:
    now = utc_now()
    start_time = now - timedelta(hours=hours)

    # Sync latest alerts first so counts are fresh
    recent_jobs = list(
        db.execute(
            select(DiagnosisJob)
            .where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.status.in_(["completed", "done"]),
                DiagnosisJob.created_at >= _as_utc(start_time),
            )
            .order_by(DiagnosisJob.created_at.desc())
            .limit(500)
        ).scalars().all()
    )
    if recent_jobs:
        sync_alerts_from_jobs(db, tenant_id, recent_jobs)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    # Count open AUTH_FAILURE alerts from the alert table
    open_alert_count = int(
        db.execute(
            select(func.count(ProjectAlert.id)).where(
                ProjectAlert.tenant_id == tenant_id,
                ProjectAlert.category == "AUTH_FAILURE",
                ProjectAlert.status == "OPEN",
            )
        ).scalar() or 0
    )

    # Pull all AUTH_FAILURE DiagnosisJobs in the window to compute trend + MTTA
    auth_jobs = [j for j in recent_jobs if _extract_auth_evidence(j.result_json) is not None]

    total_auth_failures = len(auth_jobs)

    affected_providers: list[str] = []
    first_failure_at: str | None = None
    last_failure_at: str | None = None
    by_hour: dict[str, int] = defaultdict(int)
    ack_minutes: list[float] = []

    if auth_jobs:
        sorted_jobs = sorted(auth_jobs, key=lambda j: _as_utc(j.created_at))
        first_failure_at = _as_utc(sorted_jobs[0].created_at).isoformat()
        last_failure_at = _as_utc(sorted_jobs[-1].created_at).isoformat()

        provider_set: set[str] = set()
        for job in sorted_jobs:
            ev = _extract_auth_evidence(job.result_json) or {}
            provider = str(ev.get("provider") or "").strip()
            if provider:
                provider_set.add(provider)
            hour_key = _as_utc(job.created_at).replace(minute=0, second=0, microsecond=0).isoformat()
            by_hour[hour_key] += 1

        affected_providers = sorted(provider_set)

    # Compute MTTA from alert acknowledgement timestamps
    auth_alerts = list(
        db.execute(
            select(ProjectAlert).where(
                ProjectAlert.tenant_id == tenant_id,
                ProjectAlert.category == "AUTH_FAILURE",
                ProjectAlert.created_at >= _as_utc(start_time),
                ProjectAlert.acknowledged_at.is_not(None),
            )
        ).scalars().all()
    )
    for alert in auth_alerts:
        if alert.acknowledged_at and alert.created_at:
            delta = (_as_utc(alert.acknowledged_at) - _as_utc(alert.created_at)).total_seconds()
            if delta >= 0:
                ack_minutes.append(delta / 60.0)

    mtta = round(sum(ack_minutes) / len(ack_minutes), 2) if ack_minutes else None

    trend = [
        AuthTrendPoint(hour=h, count=c)
        for h, c in sorted(by_hour.items())
    ]

    # Consider ongoing if open alerts exist or last failure was within last 30 minutes
    is_ongoing = open_alert_count > 0
    if last_failure_at and not is_ongoing:
        try:
            last_dt = datetime.fromisoformat(last_failure_at)
            is_ongoing = (now - last_dt).total_seconds() < 1800
        except ValueError:
            pass

    return AuthSummaryResponse(
        window_hours=hours,
        total_auth_failures=total_auth_failures,
        open_alert_count=open_alert_count,
        is_ongoing=is_ongoing,
        affected_providers=affected_providers,
        first_failure_at=first_failure_at,
        last_failure_at=last_failure_at,
        mean_time_to_acknowledge_minutes=mtta,
        trend=trend,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
