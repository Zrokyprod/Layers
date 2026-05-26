from app.api.routes._internal.analytics_common import *

@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    window_days: int = Query(default=1, ge=1, le=30),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> AnalyticsSummaryResponse:
    now = utc_now()
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    window_start = now - timedelta(days=window_days)
    previous_window_start = window_start - timedelta(days=window_days)
    yesterday_start = day_start - timedelta(days=1)
    cost_calls, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(cost_calls, display_currency)

    today_calls = _fetch_calls(db, tenant_id, start_time=window_start, end_time=now)
    today_jobs = _fetch_jobs(db, tenant_id, start_time=window_start, end_time=now, legacy_only=True)
    yesterday_calls = _fetch_calls(db, tenant_id, start_time=previous_window_start, end_time=window_start)
    yesterday_jobs = _fetch_jobs(db, tenant_id, start_time=previous_window_start, end_time=window_start, legacy_only=True)
    calls_today = len(today_calls) + len(today_jobs)
    calls_yesterday = len(yesterday_calls) + len(yesterday_jobs)
    cost_today_usd = 0.0
    cost_yesterday_usd = 0.0
    cost_today_calls: list[Call] = []
    user_counts: dict[str, int] = defaultdict(int)
    user_cost: dict[str, float] = defaultdict(float)

    for call in cost_calls:
        call_time = _as_utc(call.created_at)
        cost = _stored_cost(call)
        if call_time >= day_start:
            cost_today_usd += cost
            cost_today_calls.append(call)
            user_key = user_key_from_call(call)
            user_counts[user_key] += 1
            user_cost[user_key] += cost
        elif call_time >= yesterday_start:
            cost_yesterday_usd += cost

    recent_completed_jobs = list(
        db.execute(
            select(DiagnosisJob)
            .where(DiagnosisJob.tenant_id == tenant_id, DiagnosisJob.status.in_(["completed", "done"]))
            .order_by(DiagnosisJob.updated_at.desc())
            .limit(300)
        )
        .scalars()
        .all()
    )
    if sync_alerts_from_jobs(db, tenant_id, recent_completed_jobs) > 0:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    open_issues = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.status.in_(["OPEN", "ACKNOWLEDGED"]),
        )
    ).scalars().all()

    fix_adoption = _compute_fix_adoption_summary(db, tenant_id)
    feedback_loop = _compute_feedback_loop_visibility(db, tenant_id)
    health = _compute_health_score(db, tenant_id, now=now, display_currency=display_currency)

    unusual_activity = None
    if user_counts:
        top_user = max(
            user_counts.keys(),
            key=lambda user: (user_counts[user], user_cost.get(user, 0.0)),
        )
        top_user_calls = int(user_counts.get(top_user, 0))
        top_user_cost = float(user_cost.get(top_user, 0.0))

        average_calls = sum(user_counts.values()) / max(len(user_counts), 1)
        average_cost = sum(user_cost.values()) / max(len(user_cost), 1)

        call_multiplier = top_user_calls / max(average_calls, 1.0)
        cost_multiplier = top_user_cost / max(average_cost, 0.01)
        anomaly_multiplier = max(call_multiplier, cost_multiplier)

        # Trigger signal when either call volume or spend is clearly elevated.
        has_volume_signal = top_user_calls >= 5 and call_multiplier >= 2.0
        has_cost_signal = top_user_cost >= 0.25 and cost_multiplier >= 2.0

        if has_volume_signal or has_cost_signal:
            unusual_activity = {
                "impacted_user": top_user,
                "anomaly_multiplier": round(anomaly_multiplier, 2),
                "call_multiplier": round(call_multiplier, 2),
                "cost_multiplier": round(cost_multiplier, 2),
                "current_calls": top_user_calls,
                "normal_calls_per_user": round(average_calls, 2),
                "current_cost_usd": round(top_user_cost, 6),
                "current_cost_display": round(
                    sum(
                        convert_usd_amount(_stored_cost(call), call=call, context=currency_context)
                        for call in cost_today_calls
                        if user_key_from_call(call) == top_user
                    ),
                    6,
                ),
                "normal_cost_per_user_usd": round(average_cost, 6),
                "current_waste_estimate_usd": round(top_user_cost, 6),
                "suggested_action": "Investigate this user and apply temporary throttling if required.",
            }

    return AnalyticsSummaryResponse(
        calls_today=calls_today,
        calls_yesterday=calls_yesterday,
        cost_today_usd=round(cost_today_usd, 6),
        cost_yesterday_usd=round(cost_yesterday_usd, 6),
        cost_total_usd=round(sum(_stored_cost(call) for call in cost_calls), 6),
        cost_total_display=aggregate_display_total(cost_calls, _stored_cost, context=currency_context),
        **_cost_response_metadata(cost_trust, currency_context),
        open_issues=len(open_issues),
        health_score=health.health_score,
        fix_adoption=fix_adoption,
        feedback_loop=feedback_loop,
        unusual_activity=unusual_activity,
        updated_at=now,
    )


@router.get("/health-score", response_model=HealthScoreResponse)
def get_health_score(
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> HealthScoreResponse:
    now = utc_now()

    recent_completed_jobs = list(
        db.execute(
            select(DiagnosisJob)
            .where(DiagnosisJob.tenant_id == tenant_id, DiagnosisJob.status.in_(["completed", "done"]))
            .order_by(DiagnosisJob.updated_at.desc())
            .limit(300)
        )
        .scalars()
        .all()
    )
    if sync_alerts_from_jobs(db, tenant_id, recent_completed_jobs) > 0:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    return _compute_health_score(db, tenant_id, now=now, display_currency=display_currency)


__all__ = [name for name in globals() if not name.startswith("__")]
