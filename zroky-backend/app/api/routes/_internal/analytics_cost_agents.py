from app.api.routes._internal.analytics_common import *

@router.get("/cost/by-agent", response_model=CostBreakdownResponse)
def get_cost_by_agent(
    days: int = Query(default=14, ge=1, le=90),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CostBreakdownResponse:
    now = utc_now()
    calls = _fetch_cost_window_calls(db, tenant_id, now=now, days=days)
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(calls, display_currency)

    by_agent: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "total_cost_usd": 0.0,
            "total_cost_display": 0.0,
            "call_count": 0,
            "failed_cost_usd": 0.0,
            "failed_call_count": 0,
        }
    )
    for call in calls:
        key = agent_key_from_call(call)
        cost_usd = _stored_cost(call)
        by_agent[key]["total_cost_usd"] = float(by_agent[key]["total_cost_usd"]) + cost_usd
        by_agent[key]["total_cost_display"] = float(by_agent[key]["total_cost_display"]) + convert_usd_amount(
            cost_usd, call=call, context=currency_context
        )
        by_agent[key]["call_count"] = int(by_agent[key]["call_count"]) + 1
        if _is_failed_call(call):
            by_agent[key]["failed_cost_usd"] = float(by_agent[key]["failed_cost_usd"]) + cost_usd
            by_agent[key]["failed_call_count"] = int(by_agent[key]["failed_call_count"]) + 1

    items = [
        CostBreakdownItem(
            key=key,
            total_cost_usd=round(float(v["total_cost_usd"]), 6),
            total_cost_display=round(float(v["total_cost_display"]), 6),
            call_count=int(v["call_count"]),
            failed_cost_usd=round(float(v["failed_cost_usd"]), 6),
            failed_call_count=int(v["failed_call_count"]),
        )
        for key, v in sorted(by_agent.items(), key=lambda x: float(x[1]["total_cost_usd"]), reverse=True)
    ]

    return CostBreakdownResponse(
        days=days,
        items=items,
        cost_total_usd=round(sum(_stored_cost(call) for call in calls), 6),
        cost_total_display=aggregate_display_total(calls, _stored_cost, context=currency_context),
        **_cost_response_metadata(cost_trust, currency_context),
    )


@router.get("/cost/hourly", response_model=CostHourlyResponse)
def get_cost_hourly(
    hours: int = Query(default=48, ge=1, le=168),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CostHourlyResponse:
    now = utc_now()
    start_time = now - timedelta(hours=hours)

    hour_calls = list(
        db.execute(
            production_calls_query(tenant_id, start_time=start_time, end_time=now)
        ).scalars().all()
    )
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(hour_calls, display_currency)

    by_hour: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "total_cost_usd": 0.0,
            "total_cost_display": 0.0,
            "call_count": 0,
            "failed_cost_usd": 0.0,
            "failed_count": 0,
        }
    )
    for call in hour_calls:
        created_at = _as_utc(call.created_at)
        key = created_at.replace(minute=0, second=0, microsecond=0).isoformat()
        cost_usd = _stored_cost(call)
        by_hour[key]["total_cost_usd"] = float(by_hour[key]["total_cost_usd"]) + cost_usd
        by_hour[key]["total_cost_display"] = float(by_hour[key]["total_cost_display"]) + convert_usd_amount(
            cost_usd, call=call, context=currency_context
        )
        by_hour[key]["call_count"] = int(by_hour[key]["call_count"]) + 1
        if _is_failed_call(call):
            by_hour[key]["failed_cost_usd"] = float(by_hour[key]["failed_cost_usd"]) + cost_usd
            by_hour[key]["failed_count"] = int(by_hour[key]["failed_count"]) + 1

    points = [
        CostHourlyPoint(
            hour=hour,
            total_cost_usd=round(float(v["total_cost_usd"]), 6),
            call_count=int(v["call_count"]),
            failed_cost_usd=round(float(v["failed_cost_usd"]), 6),
            failed_count=int(v["failed_count"]),
        )
        for hour, v in sorted(by_hour.items())
    ]

    return CostHourlyResponse(
        hours=hours,
        points=points,
        cost_total_usd=round(sum(_stored_cost(c) for c in hour_calls), 6),
        cost_total_display=aggregate_display_total(hour_calls, _stored_cost, context=currency_context),
        **_cost_response_metadata(cost_trust, currency_context),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
