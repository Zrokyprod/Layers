from app.api.routes._internal.analytics_common import *

_SAVINGS_PROJECTION_MULTIPLIER = 1.5


@router.get("/savings", response_model=SavingsSummaryResponse)
def get_savings_summary(
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> SavingsSummaryResponse:
    now = utc_now()
    window_start = now - timedelta(days=days)

    # Issues touching the window: created in window OR resolved in window OR
    # still open and first_seen in window. We bias to inclusion — a single
    # extra row doesn't materially change the headline figure but missing a
    # row makes the "saved you" total look smaller than reality.
    rows = (
        db.execute(
            select(Anomaly).where(
                Anomaly.project_id == tenant_id,
                or_(
                    Anomaly.last_seen_at >= window_start,
                    Anomaly.first_seen_at >= window_start,
                ),
            )
        )
        .scalars()
        .all()
    )

    total_caught = 0
    total_resolved = 0
    cumulative_open_wasted = 0.0
    cumulative_resolved_blast = 0.0
    affected_calls = 0
    severity_counts: dict[str, int] = defaultdict(int)

    for anomaly in rows:
        issue = issue_projection_from_anomaly(anomaly)
        # `blast_radius_usd` may be a Decimal (Numeric column) — coerce.
        blast = float(issue.blast_radius_usd or 0.0)
        occurrences = int(issue.occurrence_count or 0)
        severity = (issue.severity or "low").lower()
        severity_counts[severity] += 1
        affected_calls += occurrences
        total_caught += 1

        if (issue.status or "").lower() == "resolved":
            total_resolved += 1
            cumulative_resolved_blast += blast
        else:
            cumulative_open_wasted += blast

    projected_averted = cumulative_resolved_blast * _SAVINGS_PROJECTION_MULTIPLIER

    return SavingsSummaryResponse(
        window_days=days,
        total_caught_count=total_caught,
        total_resolved_count=total_resolved,
        cumulative_wasted_usd=round(cumulative_open_wasted, 4),
        cumulative_resolved_blast_usd=round(cumulative_resolved_blast, 4),
        projected_averted_usd=round(projected_averted, 4),
        affected_calls=affected_calls,
        incidents_by_severity=dict(severity_counts),
        updated_at=now,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
