from app.api.routes._internal.analytics_common import *

@router.get("/budget", response_model=BudgetConfigResponse)
def get_budget_config(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> BudgetConfigResponse:
    try:
        ensure_project_exists(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=mask_error_message(exc),
        ) from exc

    config = get_or_create_dashboard_config(db, tenant_id)
    return BudgetConfigResponse(
        monthly_limit_usd=to_float(config.monthly_budget_usd, fallback=0.0) if config.monthly_budget_usd is not None else None,
        threshold_percentage=round(to_float(config.budget_threshold_percentage, fallback=80.0), 2),
        updated_at=config.updated_at,
    )


@router.put("/budget", response_model=BudgetConfigResponse)
def update_budget_config(
    body: BudgetConfigUpdateRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> BudgetConfigResponse:
    try:
        ensure_project_exists(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=mask_error_message(exc),
        ) from exc

    config = get_or_create_dashboard_config(db, tenant_id)
    config.monthly_budget_usd = body.monthly_limit_usd
    config.budget_threshold_percentage = body.threshold_percentage
    db.add(config)
    db.commit()
    db.refresh(config)

    return BudgetConfigResponse(
        monthly_limit_usd=to_float(config.monthly_budget_usd, fallback=0.0) if config.monthly_budget_usd is not None else None,
        threshold_percentage=round(to_float(config.budget_threshold_percentage, fallback=80.0), 2),
        updated_at=config.updated_at,
    )


@router.get("/budget/status", response_model=BudgetStatusResponse)
def get_budget_status(
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> BudgetStatusResponse:
    now = utc_now()
    period_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Current month spend
    spent_usd = round(
        float(
            db.execute(
                select(func.coalesce(func.sum(Call.cost_total), 0.0)).where(
                    Call.project_id == tenant_id,
                    Call.created_at >= period_start,
                )
            ).scalar() or 0.0
        ),
        6,
    )

    # Budget config (read-only, no write, so query directly)
    config_row = db.execute(
        select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()
    limit_usd: float | None = None
    threshold_pct = 80.0
    if config_row is not None:
        if config_row.monthly_budget_usd is not None:
            limit_usd = float(config_row.monthly_budget_usd)
        if config_row.budget_threshold_percentage is not None:
            threshold_pct = float(config_row.budget_threshold_percentage)

    # Days remaining in period
    days_in_month = _cal.monthrange(now.year, now.month)[1]
    days_remaining = max(0, days_in_month - now.day)

    # Budget status
    percent_used: float | None = None
    budget_status: Literal["ok", "warning", "critical", "no_limit"]
    if limit_usd is not None and limit_usd > 0:
        percent_used = round((spent_usd / limit_usd) * 100.0, 2)
        if percent_used >= 100.0:
            budget_status = "critical"
        elif percent_used >= threshold_pct:
            budget_status = "warning"
        else:
            budget_status = "ok"
    else:
        budget_status = "no_limit"

    # Forecast removed in Module 1 cuts (predictive_cost service deleted; not
    # statistically defensible without training data per ZROKY-PLAN-V2 §1.3).
    # The COST_SPIKE detector handles real-time anomaly signal instead.
    forecast_exhaust_in_days: float | None = None
    forecast_risk_level = "normal"
    forecast_recommendation = "Cost is within expected range."

    return BudgetStatusResponse(
        spent_usd=spent_usd,
        limit_usd=limit_usd,
        percent_used=percent_used,
        days_remaining_in_period=days_remaining,
        forecast_exhaust_in_days=forecast_exhaust_in_days,
        status=budget_status,
        forecast_risk_level=forecast_risk_level,
        forecast_recommendation=forecast_recommendation,
    )


@router.get("/cost/top-calls", response_model=CostTopCallsResponse)
def get_cost_top_calls(
    limit: int = Query(default=10, ge=1, le=50),
    hours: int = Query(default=168, ge=1, le=720),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CostTopCallsResponse:
    now = utc_now()
    start_time = now - timedelta(hours=hours)

    rows = list(
        db.execute(
            production_calls_query(tenant_id, start_time=start_time, end_time=now)
            .order_by(Call.cost_total.desc().nulls_last())
            .limit(limit)
        ).scalars().all()
    )

    items = []
    for call in rows:
        items.append(
            CostTopCallItem(
                call_id=str(call.id),
                model=call.model,
                provider=call.provider,
                cost_usd=round(_stored_cost(call), 6),
                status=str(call.status or "unknown"),
                agent_name=agent_key_from_call(call),
                user_id=user_key_from_call(call),
                call_type=_call_type_from_call(call),
                error_code=call.error_code,
                cost_confidence=call.cost_confidence,
                confidence_reason=call.confidence_reason,
                pricing_source=call.pricing_source,
                pricing_age_days=pricing_age_days(call.pricing_last_updated_at, now=now),
                created_at=_as_utc(call.created_at),
            )
        )

    return CostTopCallsResponse(window_hours=hours, items=items)


__all__ = [name for name in globals() if not name.startswith("__")]
