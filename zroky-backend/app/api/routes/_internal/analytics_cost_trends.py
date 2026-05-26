from app.api.routes._internal.analytics_common import *

@router.get("/cost/daily-trend", response_model=CostDailyTrendResponse)
def get_cost_daily_trend(
    days: int = Query(default=14, ge=1, le=90),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CostDailyTrendResponse:
    now = utc_now()
    calls = _fetch_cost_window_calls(db, tenant_id, now=now, days=days)
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(calls, display_currency)

    by_day: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"total_cost_usd": 0.0, "total_cost_display": 0.0, "call_count": 0, "failed_cost_usd": 0.0, "failed_call_count": 0}
    )
    for call in calls:
        created_at = _as_utc(call.created_at)
        key = created_at.date().isoformat()
        cost_usd = _stored_cost(call)
        by_day[key]["total_cost_usd"] = float(by_day[key]["total_cost_usd"]) + cost_usd
        by_day[key]["total_cost_display"] = float(by_day[key]["total_cost_display"]) + convert_usd_amount(
            cost_usd,
            call=call,
            context=currency_context,
        )
        by_day[key]["call_count"] = int(by_day[key]["call_count"]) + 1
        if _is_failed_call(call):
            by_day[key]["failed_cost_usd"] = float(by_day[key]["failed_cost_usd"]) + cost_usd
            by_day[key]["failed_call_count"] = int(by_day[key]["failed_call_count"]) + 1

    points = [
        CostDailyTrendPoint(
            day=day,
            total_cost_usd=round(float(values["total_cost_usd"]), 6),
            total_cost_display=round(float(values["total_cost_display"]), 6),
            call_count=int(values["call_count"]),
            failed_cost_usd=round(float(values["failed_cost_usd"]), 6),
            failed_call_count=int(values["failed_call_count"]),
        )
        for day, values in sorted(by_day.items())
    ]

    data_source = "postgres"
    from app.services.clickhouse_analytics import get_cost_daily_from_ch
    ch_rows = get_cost_daily_from_ch(tenant_id, days=days)
    if ch_rows is not None:
        points = [
            CostDailyTrendPoint(
                day=r["day"],
                total_cost_usd=round(r["cost_usd"], 6),
                total_cost_display=round(r["cost_usd"], 6),
                call_count=r["calls"],
            )
            for r in ch_rows
        ]
        data_source = "clickhouse"

    return CostDailyTrendResponse(
        days=days,
        points=points,
        cost_total_usd=round(sum(p.total_cost_usd for p in points), 6),
        cost_total_display=round(sum(p.total_cost_display for p in points), 6),
        data_source=data_source,
        **_cost_response_metadata(cost_trust, currency_context),
    )


@router.get("/cost/by-model", response_model=CostBreakdownResponse)
def get_cost_by_model(
    days: int = Query(default=14, ge=1, le=90),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CostBreakdownResponse:
    now = utc_now()
    calls = _fetch_cost_window_calls(db, tenant_id, now=now, days=days)
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(calls, display_currency)

    by_model: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"total_cost_usd": 0.0, "total_cost_display": 0.0, "call_count": 0, "failed_cost_usd": 0.0, "failed_call_count": 0}
    )
    for call in calls:
        model = call.model
        key = str(model) if model else "unknown"
        cost_usd = _stored_cost(call)
        by_model[key]["total_cost_usd"] = float(by_model[key]["total_cost_usd"]) + cost_usd
        by_model[key]["total_cost_display"] = float(by_model[key]["total_cost_display"]) + convert_usd_amount(
            cost_usd,
            call=call,
            context=currency_context,
        )
        by_model[key]["call_count"] = int(by_model[key]["call_count"]) + 1
        if _is_failed_call(call):
            by_model[key]["failed_cost_usd"] = float(by_model[key]["failed_cost_usd"]) + cost_usd
            by_model[key]["failed_call_count"] = int(by_model[key]["failed_call_count"]) + 1

    items = [
        CostBreakdownItem(
            key=key,
            total_cost_usd=round(float(values["total_cost_usd"]), 6),
            total_cost_display=round(float(values["total_cost_display"]), 6),
            call_count=int(values["call_count"]),
            failed_cost_usd=round(float(values["failed_cost_usd"]), 6),
            failed_call_count=int(values["failed_call_count"]),
        )
        for key, values in sorted(by_model.items(), key=lambda item: float(item[1]["total_cost_usd"]), reverse=True)
    ]
    return CostBreakdownResponse(
        days=days,
        items=items,
        cost_total_usd=round(sum(_stored_cost(call) for call in calls), 6),
        cost_total_display=aggregate_display_total(calls, _stored_cost, context=currency_context),
        **_cost_response_metadata(cost_trust, currency_context),
    )


@router.get("/cost/by-user", response_model=CostBreakdownResponse)
def get_cost_by_user(
    days: int = Query(default=14, ge=1, le=90),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CostBreakdownResponse:
    now = utc_now()
    calls = _fetch_cost_window_calls(db, tenant_id, now=now, days=days)
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(calls, display_currency)

    by_user: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "total_cost_usd": 0.0,
            "total_cost_display": 0.0,
            "call_count": 0,
            "failed_cost_usd": 0.0,
            "failed_call_count": 0,
        }
    )
    for call in calls:
        key = user_key_from_call(call)
        cost_usd = _stored_cost(call)
        by_user[key]["total_cost_usd"] = float(by_user[key]["total_cost_usd"]) + cost_usd
        by_user[key]["total_cost_display"] = float(by_user[key]["total_cost_display"]) + convert_usd_amount(
            cost_usd,
            call=call,
            context=currency_context,
        )
        by_user[key]["call_count"] = int(by_user[key]["call_count"]) + 1
        if _is_failed_call(call):
            by_user[key]["failed_cost_usd"] = float(by_user[key]["failed_cost_usd"]) + cost_usd
            by_user[key]["failed_call_count"] = int(by_user[key]["failed_call_count"]) + 1

    items = [
        CostBreakdownItem(
            key=key,
            total_cost_usd=round(float(values["total_cost_usd"]), 6),
            total_cost_display=round(float(values["total_cost_display"]), 6),
            call_count=int(values["call_count"]),
            failed_cost_usd=round(float(values["failed_cost_usd"]), 6),
            failed_call_count=int(values["failed_call_count"]),
        )
        for key, values in sorted(by_user.items(), key=lambda item: float(item[1]["total_cost_usd"]), reverse=True)
    ]
    return CostBreakdownResponse(
        days=days,
        items=items,
        cost_total_usd=round(sum(_stored_cost(call) for call in calls), 6),
        cost_total_display=aggregate_display_total(calls, _stored_cost, context=currency_context),
        **_cost_response_metadata(cost_trust, currency_context),
    )


@router.get("/cost/reasoning-share", response_model=ReasoningShareResponse)
def get_reasoning_cost_share(
    days: int = Query(default=14, ge=1, le=90),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> ReasoningShareResponse:
    now = utc_now()
    calls = _fetch_cost_window_calls(db, tenant_id, now=now, days=days)
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(calls, display_currency)

    total_cost = 0.0
    reasoning_cost = 0.0
    for call in calls:
        total_cost += _stored_cost(call)
        reasoning_cost += _stored_reasoning_cost(call)

    share = 0.0
    if total_cost > 0:
        share = (reasoning_cost / total_cost) * 100.0

    return ReasoningShareResponse(
        days=days,
        total_cost_usd=round(total_cost, 6),
        total_cost_display=aggregate_display_total(calls, _stored_cost, context=currency_context),
        reasoning_cost_usd=round(reasoning_cost, 6),
        reasoning_cost_display=aggregate_display_total(calls, _stored_reasoning_cost, context=currency_context),
        reasoning_share_percent=round(share, 2),
        **_cost_response_metadata(cost_trust, currency_context),
    )


@router.get("/cost/cache-savings", response_model=CacheSavingsResponse)
def get_cache_savings_trend(
    days: int = Query(default=14, ge=1, le=90),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> CacheSavingsResponse:
    now = utc_now()
    calls = _fetch_cost_window_calls(db, tenant_id, now=now, days=days)
    _, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(calls, display_currency)

    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"usd": 0.0, "display": 0.0})
    total = 0.0
    for call in calls:
        created_at = _as_utc(call.created_at)
        key = created_at.date().isoformat()
        cache_savings = _stored_cache_savings(call)
        by_day[key]["usd"] += cache_savings
        by_day[key]["display"] += convert_usd_amount(cache_savings, call=call, context=currency_context)
        total += cache_savings

    points = [
        CacheSavingsPoint(
            day=day,
            cache_savings_usd=round(value["usd"], 6),
            cache_savings_display=round(value["display"], 6),
        )
        for day, value in sorted(by_day.items())
    ]

    return CacheSavingsResponse(
        days=days,
        total_cache_savings_usd=round(total, 6),
        total_cache_savings_display=aggregate_display_total(calls, _stored_cache_savings, context=currency_context),
        points=points,
        **_cost_response_metadata(cost_trust, currency_context),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
