import calendar as _cal
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, load_only

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import AuditLog, Call, DiagnosisFeedback, DiagnosisJob, Issue, ProjectAlert, ProjectDashboardConfig
from app.db.session import get_db_session, get_db_session_read
from app.schemas.dashboard import (
    ActivityFeedItemResponse,
    ActivityFeedResponse,
    AnalyticsSummaryResponse,
    AuthSummaryResponse,
    SavingsSummaryResponse,
    AuthTrendPoint,
    BudgetConfigResponse,
    BudgetConfigUpdateRequest,
    BudgetStatusResponse,
    CacheSavingsPoint,
    CacheSavingsResponse,
    CostBreakdownItem,
    CostBreakdownResponse,
    CostDailyTrendPoint,
    CostDailyTrendResponse,
    CostHourlyPoint,
    CostHourlyResponse,
    CostTopCallItem,
    CostTopCallsResponse,
    LoopDayPoint,
    LoopIncidentItem,
    LoopIncidentsResponse,
    LoopSummaryResponse,
    FeedbackCategoryVisibility,
    FeedbackLoopVisibility,
    FixAdoptionSummary,
    FixAnalyticsResponse,
    HealthScoreResponse,
    ReasoningShareResponse,
    TraceListItem,
    TraceListResponse,
)
from app.services.audit_logs import AUDIT_ACTION_DIAGNOSIS_VIEWED, AUDIT_ACTION_RESOLVED, parse_metadata
from app.services.alerts import sync_alerts_from_jobs
from app.services.dashboard_config import ensure_project_exists, get_or_create_dashboard_config
from app.services.dashboard_data import (
    extract_call_metrics,
    extract_diagnosis_categories,
    percentile,
    safe_load_json,
    to_float,
    utc_now,
)
from app.services.cost_trust import (
    COST_ANALYTICS_WINDOW_DAYS,
    CostTrustMetadata,
    agent_key_from_call,
    evaluate_cost_trust,
    fetch_cost_calls,
    pricing_age_days,
    production_calls_query,
    user_key_from_call,
)
from app.services.currency import (
    CurrencyDisplayContext,
    aggregate_display_total,
    append_confidence_reason,
    build_currency_context,
    convert_usd_amount,
)
from app.services.privacy import mask_error_message
from app.services.fix_analytics import build_fix_analytics

router = APIRouter(prefix="/v1/analytics")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_FAILED_CALL_STATUSES: frozenset[str] = frozenset(
    {"failed", "error", "errored", "timeout", "dead_lettered", "enqueue_failed"}
)


def _is_failed_call(call: Call) -> bool:
    return str(call.status or "").strip().lower() in _FAILED_CALL_STATUSES


def _fetch_jobs(
    db: Session,
    tenant_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    legacy_only: bool = False,
) -> list[DiagnosisJob]:
    query = select(DiagnosisJob).where(DiagnosisJob.tenant_id == tenant_id)
    if legacy_only:
        query = query.where(DiagnosisJob.call_id.is_(None))
    if start_time is not None:
        query = query.where(DiagnosisJob.created_at >= _as_utc(start_time))
    if end_time is not None:
        query = query.where(DiagnosisJob.created_at <= _as_utc(end_time))
    query = query.order_by(DiagnosisJob.created_at.desc())
    return list(db.execute(query).scalars().all())


def _fetch_calls(
    db: Session,
    tenant_id: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[Call]:
    query = select(Call).where(Call.project_id == tenant_id)
    if start_time is not None:
        query = query.where(Call.created_at >= _as_utc(start_time))
    if end_time is not None:
        query = query.where(Call.created_at <= _as_utc(end_time))
    query = query.order_by(Call.created_at.desc())
    return list(db.execute(query).scalars().all())


def _fetch_cost_context(db: Session, tenant_id: str, *, now: datetime) -> tuple[list[Call], CostTrustMetadata]:
    calls = fetch_cost_calls(db, tenant_id, now=now)
    return calls, evaluate_cost_trust(db, tenant_id, calls=calls, now=now)


def _fetch_cost_window_calls(
    db: Session,
    tenant_id: str,
    *,
    now: datetime,
    days: int,
) -> list[Call]:
    start_time = _as_utc(now) - timedelta(days=max(1, days))
    return list(
        db.execute(
            production_calls_query(tenant_id, start_time=start_time, end_time=now)
            .options(load_only(
                Call.created_at,
                Call.status,
                Call.model,
                Call.agent_name,
                Call.user_id,
                Call.cost_total,
                Call.reasoning_cost_total,
                Call.cache_savings_total,
                Call.exchange_rate_usd_to_inr,
                Call.exchange_rate_timestamp,
                Call.exchange_rate_source,
                Call.metadata_json,
            ))
            .order_by(Call.created_at.asc())
        )
        .scalars()
        .all()
    )


def _cost_response_metadata(
    trust: CostTrustMetadata,
    currency_context: CurrencyDisplayContext,
) -> dict[str, Any]:
    metadata = trust.as_dict()
    metadata.update(currency_context.as_dict())
    if currency_context.missing_exchange_rate:
        metadata["cost_confidence"] = "degraded"
        metadata["confidence_reason"] = append_confidence_reason(
            str(metadata.get("confidence_reason") or ""),
            "missing_exchange_rate",
        )
    return metadata


def _stored_cost(call: Call) -> float:
    return max(0.0, float(call.cost_total or 0.0))


def _stored_reasoning_cost(call: Call) -> float:
    return max(0.0, float(call.reasoning_cost_total or 0.0))


def _stored_cache_savings(call: Call) -> float:
    return max(0.0, float(call.cache_savings_total or 0.0))


def _call_type_from_call(call: Call) -> str | None:
    if call.call_type and str(call.call_type).strip():
        return str(call.call_type).strip()

    metadata = safe_load_json(call.metadata_json)
    value = metadata.get("call_type")
    if value and str(value).strip():
        return str(value).strip()

    payload = safe_load_json(call.payload_json)
    value = payload.get("call_type") if isinstance(payload, dict) else None
    return str(value).strip() if value and str(value).strip() else None


def _successful_legacy_job(job: DiagnosisJob) -> bool:
    return str(job.status).strip().lower() in {"completed", "done"}


def _normalize_category(value: str | None) -> str:
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized:
            return normalized
    return "UNKNOWN"


def _primary_category_from_job(job: DiagnosisJob) -> str:
    result_payload = safe_load_json(job.result_json)
    categories = extract_diagnosis_categories(result_payload)
    if categories:
        return _normalize_category(categories[0])
    return "UNKNOWN"


def _compute_fix_adoption_summary(db: Session, tenant_id: str) -> FixAdoptionSummary:
    window_start = utc_now() - timedelta(days=90)
    action_rows = db.execute(
        select(AuditLog.action, AuditLog.diagnosis_id).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_([AUDIT_ACTION_DIAGNOSIS_VIEWED, AUDIT_ACTION_RESOLVED]),
            AuditLog.created_at >= window_start,
        )
    ).all()

    viewed_diagnoses = {
        str(row.diagnosis_id)
        for row in action_rows
        if str(row.action).strip().lower() == AUDIT_ACTION_DIAGNOSIS_VIEWED
    }
    resolved_diagnoses = {
        str(row.diagnosis_id)
        for row in action_rows
        if str(row.action).strip().lower() == AUDIT_ACTION_RESOLVED
    }

    viewed_count = len(viewed_diagnoses)
    resolved_count = len(resolved_diagnoses)
    adoption_rate = 0.0
    if viewed_count > 0:
        adoption_rate = (resolved_count / viewed_count) * 100.0

    if adoption_rate >= 40.0:
        status_band: Literal["strong", "warning", "critical"] = "strong"
    elif adoption_rate >= 20.0:
        status_band = "warning"
    else:
        status_band = "critical"

    return FixAdoptionSummary(
        viewed_diagnoses=viewed_count,
        resolved_diagnoses=resolved_count,
        adoption_rate_percent=round(adoption_rate, 2),
        status_band=status_band,
    )


def _compute_feedback_loop_visibility(db: Session, tenant_id: str) -> FeedbackLoopVisibility:
    window_start = utc_now() - timedelta(days=90)
    feedback_rows = list(
        db.execute(
            select(DiagnosisFeedback).where(
                DiagnosisFeedback.tenant_id == tenant_id,
                DiagnosisFeedback.created_at >= window_start,
            )
        )
        .scalars()
        .all()
    )
    if not feedback_rows:
        return FeedbackLoopVisibility(
            feedback_total=0,
            thumbs_down_total=0,
            thumbs_down_rate_percent=0.0,
            by_category=[],
        )

    diagnosis_ids = sorted({row.diagnosis_id for row in feedback_rows if row.diagnosis_id})
    jobs_by_diagnosis_id: dict[str, DiagnosisJob] = {}
    if diagnosis_ids:
        jobs = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id.in_(diagnosis_ids),
            )
        ).scalars().all()
        jobs_by_diagnosis_id = {job.diagnosis_id: job for job in jobs}

    category_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "feedback_total": 0,
            "thumbs_down_count": 0,
        }
    )
    thumbs_down_total = 0

    for feedback in feedback_rows:
        job = jobs_by_diagnosis_id.get(feedback.diagnosis_id)
        category = _primary_category_from_job(job) if job is not None else "UNKNOWN"

        category_totals[category]["feedback_total"] += 1
        if not feedback.was_helpful:
            category_totals[category]["thumbs_down_count"] += 1
            thumbs_down_total += 1

    by_category = [
        FeedbackCategoryVisibility(
            category=category,
            feedback_total=counts["feedback_total"],
            thumbs_down_count=counts["thumbs_down_count"],
            thumbs_down_rate_percent=round(
                (counts["thumbs_down_count"] / counts["feedback_total"]) * 100.0
                if counts["feedback_total"] > 0
                else 0.0,
                2,
            ),
        )
        for category, counts in category_totals.items()
    ]
    by_category.sort(
        key=lambda item: (
            -item.thumbs_down_rate_percent,
            -item.thumbs_down_count,
            -item.feedback_total,
            item.category,
        )
    )

    feedback_total = len(feedback_rows)
    thumbs_down_rate_percent = round((thumbs_down_total / feedback_total) * 100.0, 2) if feedback_total > 0 else 0.0
    return FeedbackLoopVisibility(
        feedback_total=feedback_total,
        thumbs_down_total=thumbs_down_total,
        thumbs_down_rate_percent=thumbs_down_rate_percent,
        by_category=by_category,
    )


def _compute_health_score(
    db: Session,
    tenant_id: str,
    *,
    now: datetime,
    display_currency: str | None = "USD",
) -> HealthScoreResponse:
    start_24h = now - timedelta(hours=24)
    cost_calls, cost_trust = _fetch_cost_context(db, tenant_id, now=now)
    currency_context = build_currency_context(cost_calls, display_currency)
    calls_24h = _fetch_calls(db, tenant_id, start_time=start_24h, end_time=now)
    legacy_jobs_24h = _fetch_jobs(
        db,
        tenant_id,
        start_time=start_24h,
        end_time=now,
        legacy_only=True,
    )

    total_calls = len(calls_24h) + len(legacy_jobs_24h)
    successful_calls = sum(1 for call in calls_24h if call.status == "success")
    successful_calls += sum(1 for job in legacy_jobs_24h if _successful_legacy_job(job))
    success_rate = 100.0 * (successful_calls / max(total_calls, 1))

    latency_values = []
    for call in calls_24h:
        latency_ms = int(call.latency_ms) if call.latency_ms is not None else None
        if latency_ms is not None and latency_ms > 0:
            latency_values.append(float(latency_ms))
    for job in legacy_jobs_24h:
        metrics = extract_call_metrics(safe_load_json(job.payload_json))
        latency_ms = metrics["latency_ms"]
        if isinstance(latency_ms, int) and latency_ms > 0:
            latency_values.append(float(latency_ms))

    project_p95_latency_ms = percentile(latency_values, 0.95)
    latency_slo_ms = 2000.0
    if project_p95_latency_ms <= 0 or project_p95_latency_ms <= latency_slo_ms:
        latency_score = 100.0
    else:
        latency_score = max(0.0, 100.0 * (latency_slo_ms / project_p95_latency_ms))

    # Cost anomaly score from current 15m spend vs baseline avg 15m spend across last 14 days.
    current_15m_start = now - timedelta(minutes=15)
    current_15m_spend = 0.0
    baseline_total_spend = 0.0
    current_15m_calls: list[Call] = []
    baseline_calls: list[Call] = []
    for call in cost_calls:
        if _as_utc(call.created_at) >= current_15m_start:
            current_15m_spend += _stored_cost(call)
            current_15m_calls.append(call)
        else:
            baseline_total_spend += _stored_cost(call)
            baseline_calls.append(call)

    buckets_14d = COST_ANALYTICS_WINDOW_DAYS * 24 * 4
    baseline_15m_spend = baseline_total_spend / max(buckets_14d, 1)
    ratio = current_15m_spend / max(baseline_15m_spend, 0.01)
    if ratio <= 1.25:
        cost_anomaly_score = 100.0
    elif ratio <= 2.0:
        cost_anomaly_score = 70.0
    elif ratio <= 3.0:
        cost_anomaly_score = 40.0
    else:
        cost_anomaly_score = 10.0

    # Open issues score from high severity open issues per 1000 calls over 24h window.
    high_open_issues = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.severity.in_(["high", "critical"]),
            ProjectAlert.status.in_(["OPEN", "ACKNOWLEDGED"]),
        )
    ).scalars().all()
    issues_per_1000 = (len(high_open_issues) / max(total_calls, 1)) * 1000.0
    if issues_per_1000 == 0:
        open_issues_score = 100.0
    elif issues_per_1000 <= 3:
        open_issues_score = 70.0
    elif issues_per_1000 <= 6:
        open_issues_score = 40.0
    else:
        open_issues_score = 10.0

    health_score = (
        (success_rate * 0.40)
        + (latency_score * 0.25)
        + (cost_anomaly_score * 0.20)
        + (open_issues_score * 0.15)
    )
    health_score = round(health_score, 2)

    status_band: Literal["perfect", "green", "yellow", "red"]
    if health_score == 100.0:
        status_band = "perfect"
    elif health_score >= 85.0:
        status_band = "green"
    elif health_score >= 70.0:
        status_band = "yellow"
    else:
        status_band = "red"

    cost_meta = _cost_response_metadata(cost_trust, currency_context)
    return HealthScoreResponse(
        health_score=health_score,
        status_band=status_band,
        success_rate=round(success_rate, 2),
        latency_score=round(latency_score, 2),
        cost_anomaly_score=round(cost_anomaly_score, 2),
        cost_total_usd=round(sum(_stored_cost(call) for call in cost_calls), 6),
        cost_total_display=aggregate_display_total(cost_calls, _stored_cost, context=currency_context),
        **cost_meta,
        open_issues_score=round(open_issues_score, 2),
        details={
            "successful_calls_24h": successful_calls,
            "total_calls_24h": total_calls,
            "latency_slo_ms": latency_slo_ms,
            "project_p95_latency_ms": round(project_p95_latency_ms, 2),
            "current_15m_spend_usd": round(current_15m_spend, 6),
            "current_15m_spend_display": aggregate_display_total(
                current_15m_calls,
                _stored_cost,
                context=currency_context,
            ),
            "baseline_15m_spend_usd": round(baseline_15m_spend, 6),
            "baseline_15m_spend_display": round(
                aggregate_display_total(baseline_calls, _stored_cost, context=currency_context) / max(buckets_14d, 1),
                6,
            ),
            "cost_ratio": round(ratio, 6),
            "cost_confidence": cost_meta.get("cost_confidence"),
            "confidence_reason": cost_meta.get("confidence_reason"),
            "cost_baseline_window_days": cost_trust.baseline_window_days,
            "open_high_severity_issues": len(high_open_issues),
            "issues_per_1000_calls": round(issues_per_1000, 2),
        },
        updated_at=now,
    )


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


@router.get("/activity-feed", response_model=ActivityFeedResponse)
def get_activity_feed(
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> ActivityFeedResponse:
    base_query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    total_query = select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant_id)

    normalized_action = action.strip().lower() if isinstance(action, str) and action.strip() else None
    if normalized_action:
        base_query = base_query.where(AuditLog.action == normalized_action)
        total_query = total_query.where(AuditLog.action == normalized_action)

    rows = db.execute(
        base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    total = int(db.execute(total_query).scalar_one() or 0)

    return ActivityFeedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            ActivityFeedItemResponse(
                log_id=row.id,
                tenant_id=row.tenant_id,
                diagnosis_id=row.diagnosis_id,
                action=row.action,
                actor_subject=row.actor_subject,
                metadata=parse_metadata(row.metadata_json),
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get("/fixes", response_model=FixAnalyticsResponse)
def get_fix_analytics(
    days: int = Query(default=30, ge=1, le=180),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> FixAnalyticsResponse:
    return build_fix_analytics(db, tenant_id=tenant_id, window_days=days)


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


def _extract_loop_evidence(result_json: str | None) -> dict[str, Any] | None:
    """Return the first LOOP_DETECTED diagnosis evidence dict, or None."""
    payload = safe_load_json(result_json)
    diagnoses = payload.get("diagnoses", [])
    if not isinstance(diagnoses, list):
        return None
    for diag in diagnoses:
        if isinstance(diag, dict) and str(diag.get("category", "")).upper() == "LOOP_DETECTED":
            ev = diag.get("evidence")
            return ev if isinstance(ev, dict) else {}
    return None


@router.get("/loops/summary", response_model=LoopSummaryResponse)
def get_loop_summary(
    days: int = Query(default=7, ge=1, le=90),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> LoopSummaryResponse:
    now = utc_now()
    start_time = now - timedelta(days=days)

    jobs = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.status.in_(["completed", "done"]),
                DiagnosisJob.created_at >= _as_utc(start_time),
            ).order_by(DiagnosisJob.created_at.desc())
        ).scalars().all()
    )

    # Collect call costs in a single query for all linked call_ids
    call_ids = [j.call_id for j in jobs if j.call_id]
    call_cost_map: dict[str, float] = {}
    if call_ids:
        for call in db.execute(
            select(Call).where(Call.id.in_(call_ids))
        ).scalars().all():
            call_cost_map[call.id] = _stored_cost(call)

    total_loop_count = 0
    estimated_waste_usd = 0.0
    agent_counter: dict[str, int] = defaultdict(int)
    pattern_counter: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)

    for job in jobs:
        evidence = _extract_loop_evidence(job.result_json)
        if evidence is None:
            continue
        total_loop_count += 1
        day_key = _as_utc(job.created_at).date().isoformat()
        by_day[day_key] += 1

        agent = str(evidence.get("agent_name") or job.agent_name or "unknown")
        agent_counter[agent] += 1

        pattern = str(evidence.get("dominant_pattern") or evidence.get("detected_by") or "unknown")
        pattern_counter[pattern] += 1

        if job.call_id:
            estimated_waste_usd += call_cost_map.get(job.call_id, 0.0)

    top_looping_agent = max(agent_counter, key=lambda k: agent_counter[k]) if agent_counter else None
    most_common_pattern = max(pattern_counter, key=lambda k: pattern_counter[k]) if pattern_counter else None

    loop_count_by_day = [
        LoopDayPoint(day=day, count=count)
        for day, count in sorted(by_day.items())
    ]

    return LoopSummaryResponse(
        window_days=days,
        total_loop_count=total_loop_count,
        estimated_waste_usd=round(estimated_waste_usd, 6),
        top_looping_agent=top_looping_agent,
        most_common_pattern=most_common_pattern,
        loop_count_by_day=loop_count_by_day,
    )


@router.get("/loops/incidents", response_model=LoopIncidentsResponse)
def get_loop_incidents(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> LoopIncidentsResponse:
    now = utc_now()
    start_time = now - timedelta(days=days)

    all_jobs = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.status.in_(["completed", "done"]),
                DiagnosisJob.created_at >= _as_utc(start_time),
            ).order_by(DiagnosisJob.created_at.desc())
        ).scalars().all()
    )

    # Filter to LOOP_DETECTED jobs and extract evidence
    loop_jobs: list[tuple[DiagnosisJob, dict[str, Any]]] = []
    for job in all_jobs:
        evidence = _extract_loop_evidence(job.result_json)
        if evidence is not None:
            loop_jobs.append((job, evidence))

    total = len(loop_jobs)
    page_jobs = loop_jobs[offset : offset + limit]

    call_ids = [j.call_id for j, _ in page_jobs if j.call_id]
    call_cost_map: dict[str, float] = {}
    if call_ids:
        for call in db.execute(
            select(Call).where(Call.id.in_(call_ids))
        ).scalars().all():
            call_cost_map[call.id] = _stored_cost(call)

    items: list[LoopIncidentItem] = []
    for job, evidence in page_jobs:
        items.append(
            LoopIncidentItem(
                diagnosis_id=job.diagnosis_id,
                agent_name=str(evidence.get("agent_name") or job.agent_name or "") or None,
                created_at=_as_utc(job.created_at),
                loop_score=round(float(evidence.get("loop_score") or 0.0), 3),
                dominant_pattern=str(evidence.get("dominant_pattern") or evidence.get("detected_by") or "") or None,
                repeat_count=int(evidence.get("repeat_count") or 0),
                no_progress=bool(evidence.get("no_progress", False)),
                estimated_cost_usd=round(call_cost_map.get(job.call_id or "", 0.0), 6),
                retry_suppression_applied=bool(evidence.get("retry_suppression_applied", False)),
            )
        )

    return LoopIncidentsResponse(
        total=total,
        limit=limit,
        offset=offset,
        window_days=days,
        items=items,
    )


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


_FAILED_STATUSES_TRACE = {"failed", "error", "timeout", "auth_failure", "loop_detected"}


@router.get("/traces/recent", response_model=TraceListResponse)
def get_recent_traces(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> TraceListResponse:
    now = utc_now()
    window_start = now - timedelta(days=days)

    calls = list(
        db.execute(
            select(Call)
            .where(
                Call.project_id == tenant_id,
                Call.created_at >= window_start,
            )
            .options(load_only(
                Call.id,
                Call.status,
                Call.provider,
                Call.cost_total,
                Call.created_at,
                Call.payload_json,
            ))
            .order_by(Call.created_at.asc())
        ).scalars().all()
    )

    # Group calls by trace_id extracted from payload_json
    by_trace: dict[str, list[Call]] = {}
    agent_by_call: dict[str, str | None] = {}
    parent_by_call: dict[str, str | None] = {}
    for call in calls:
        payload = safe_load_json(call.payload_json)
        trace_id = payload.get("trace_id") if payload else None
        if not trace_id or not isinstance(trace_id, str):
            continue
        agent_by_call[call.id] = payload.get("agent_name") or None
        parent_by_call[call.id] = payload.get("parent_call_id") or None
        by_trace.setdefault(trace_id, []).append(call)

    # Identify root calls (earliest call with no parent inside same trace) and batch-fetch diagnosis jobs
    root_call_ids: list[str] = []
    root_by_trace: dict[str, str] = {}
    for trace_id, trace_calls in by_trace.items():
        call_id_set = {c.id for c in trace_calls}
        root = None
        for c in sorted(trace_calls, key=lambda x: x.created_at):
            parent = parent_by_call.get(c.id)
            if not parent or parent not in call_id_set:
                root = c
                break
        if root is None:
            root = min(trace_calls, key=lambda x: x.created_at)
        root_by_trace[trace_id] = root.id
        root_call_ids.append(root.id)

    jobs_by_root: dict[str, DiagnosisJob] = {}
    if root_call_ids:
        linked_jobs = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.call_id.in_(root_call_ids),
            )
        ).scalars().all()
        jobs_by_root = {str(job.call_id): job for job in linked_jobs if job.call_id}

    items: list[TraceListItem] = []
    total_multi_agent = 0
    total_failed = 0
    for trace_id, trace_calls in by_trace.items():
        sorted_calls = sorted(trace_calls, key=lambda x: x.created_at)

        # Agents in first-seen chronological order (not alphabetical) so "A → B → C" is meaningful
        seen_agents: list[str] = []
        seen_agent_set: set[str] = set()
        for c in sorted_calls:
            name = agent_by_call.get(c.id)
            if name and name not in seen_agent_set:
                seen_agents.append(name)
                seen_agent_set.add(name)
        agents = seen_agents

        providers: list[str] = sorted(
            {c.provider for c in trace_calls if c.provider and c.provider not in ("unknown", "")}
        )
        has_failure = any(c.status.lower() in _FAILED_STATUSES_TRACE for c in trace_calls)
        total_cost = sum(float(c.cost_total or 0) for c in trace_calls)

        root_call_id = root_by_trace[trace_id]
        root_failure_category: str | None = None
        root_job = jobs_by_root.get(root_call_id)
        if root_job and root_job.result_json:
            result = safe_load_json(root_job.result_json)
            diagnoses = result.get("diagnoses") if result else None
            if isinstance(diagnoses, list) and diagnoses and isinstance(diagnoses[0], dict):
                root_failure_category = diagnoses[0].get("category") or None

        if len(agents) > 1:
            total_multi_agent += 1
        if has_failure:
            total_failed += 1

        items.append(
            TraceListItem(
                trace_id=trace_id,
                root_call_id=root_call_id,
                call_count=len(trace_calls),
                agent_count=len(agents),
                agents=agents,
                providers=providers,
                started_at=sorted_calls[0].created_at.isoformat() + "Z",
                last_seen_at=sorted_calls[-1].created_at.isoformat() + "Z",
                total_cost_usd=round(total_cost, 6),
                has_failure=has_failure,
                root_failure_category=root_failure_category,
            )
        )

    items.sort(key=lambda x: x.last_seen_at, reverse=True)
    total_traces = len(items)
    items = items[:limit]

    return TraceListResponse(
        window_days=days,
        total=total_traces,
        multi_agent_count=total_multi_agent,
        failed_count=total_failed,
        items=items,
    )


@router.get("/traces/{trace_id}", response_model=TraceListItem)
def get_trace_by_id(
    trace_id: str,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> TraceListItem:
    """Return metadata for a single trace id within a recent window.

    This mirrors the aggregation done by `/traces/recent` but scoped to a single
    `trace_id`. It searches calls and legacy diagnosis jobs within the last
    `days` and returns a `TraceListItem` describing the trace.
    """
    now = utc_now()
    window_start = now - timedelta(days=days)

    calls = list(
        db.execute(
            select(Call)
            .where(
                Call.project_id == tenant_id,
                Call.created_at >= window_start,
            )
            .order_by(Call.created_at.asc())
        ).scalars().all()
    )

    trace_calls: list[Call] = []
    agent_by_call: dict[str, str | None] = {}
    parent_by_call: dict[str, str | None] = {}
    for call in calls:
        payload = safe_load_json(call.payload_json)
        if not payload:
            continue
        candidate = payload.get("trace_id") if isinstance(payload, dict) else None
        if candidate == trace_id:
            trace_calls.append(call)
            agent_by_call[call.id] = payload.get("agent_name") or None
            parent_by_call[call.id] = payload.get("parent_call_id") or None

    # include legacy diagnosis jobs (call-less) in the same window
    legacy_jobs = _fetch_jobs(db, tenant_id=tenant_id, start_time=window_start, end_time=now, legacy_only=True)
    legacy_matches: list[DiagnosisJob] = []
    for job in legacy_jobs:
        payload = safe_load_json(job.payload_json)
        if not payload:
            continue
        candidate = payload.get("trace_id") if isinstance(payload, dict) else None
        if candidate == trace_id:
            legacy_matches.append(job)

    if not trace_calls and not legacy_matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")

    # build chronological ordering across calls and jobs
    combined_items: list[tuple[str, Any]] = []  # (created_at_iso, item)
    for c in trace_calls:
        combined_items.append((c.created_at.isoformat() + "Z", c))
    for j in legacy_matches:
        combined_items.append((j.created_at.isoformat() + "Z", j))
    combined_items.sort(key=lambda t: t[0])

    # Agents (chronological first-seen)
    seen_agents: list[str] = []
    seen_set: set[str] = set()
    for _, item in combined_items:
        if isinstance(item, Call):
            name = agent_by_call.get(item.id)
        else:
            payload = safe_load_json(item.payload_json)
            name = payload.get("agent_name") if isinstance(payload, dict) else None
        if name and name not in seen_set:
            seen_agents.append(name)
            seen_set.add(name)

    providers: set[str] = set()
    total_cost = 0.0
    has_failure = False
    call_count = 0
    for c in trace_calls:
        if c.provider and c.provider not in ("unknown", ""):
            providers.add(c.provider)
        total_cost += float(c.cost_total or 0)
        if str(c.status or "").strip().lower() in _FAILED_STATUSES_TRACE:
            has_failure = True
        call_count += 1
    # legacy jobs may contribute failure info and root failure
    for j in legacy_matches:
        if str(j.status or "").strip().lower() in _FAILED_STATUSES_TRACE:
            has_failure = True

    root_call_id = None
    # determine root among calls if present
    if trace_calls:
        call_id_set = {c.id for c in trace_calls}
        root = None
        for c in sorted(trace_calls, key=lambda x: x.created_at):
            parent = parent_by_call.get(c.id)
            if not parent or parent not in call_id_set:
                root = c
                break
        if root is None:
            root = min(trace_calls, key=lambda x: x.created_at)
        root_call_id = root.id
    else:
        # fallback to first legacy job id
        root_call_id = legacy_matches[0].diagnosis_id if legacy_matches else None

    root_failure_category = None
    root_job = None
    if root_call_id:
        # try to find a linked DiagnosisJob for the root
        root_job = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                or_(DiagnosisJob.call_id == root_call_id, DiagnosisJob.diagnosis_id == root_call_id),
            )
        ).scalar_one_or_none()
        if root_job and root_job.result_json:
            result = safe_load_json(root_job.result_json)
            diagnoses = result.get("diagnoses") if result else None
            if isinstance(diagnoses, list) and diagnoses and isinstance(diagnoses[0], dict):
                root_failure_category = diagnoses[0].get("category") or None

    started_at = combined_items[0][0]
    last_seen_at = combined_items[-1][0]

    return TraceListItem(
        trace_id=trace_id,
        root_call_id=root_call_id or "",
        call_count=call_count + len(legacy_matches),
        agent_count=len(seen_agents),
        agents=seen_agents,
        providers=sorted(list(providers)),
        started_at=started_at,
        last_seen_at=last_seen_at,
        total_cost_usd=round(total_cost, 6),
        has_failure=has_failure,
        root_failure_category=root_failure_category,
    )


# ── Savings ("what Zroky saved you") ─────────────────────────────────────────
#
# This route aggregates the legacy `issues` table — the canonical projection
# for resolved-incident value. Numbers shown:
#   - cumulative_wasted_usd: sum of blast_radius_usd across OPEN issues in
#                            the window (the "still bleeding" figure)
#   - cumulative_resolved_blast_usd: sum across RESOLVED issues in the window
#                                    (the "already saved" figure)
#   - projected_averted_usd: optimistic 6h forward-projection on resolved
#                            issues — frames the "you would have lost X more
#                            if Zroky hadn't caught it" story
#
# Projection multiplier of 1.5 picked deliberately conservative: we don't want
# to over-promise. A real incident left untriaged for 6h typically continues
# burning at its observed rate; multiplying the already-wasted blast by 1.5
# represents "continued at the same rate for ~6h until manual catch".
#
# All currency values are USD raw — display-currency conversion happens
# client-side via the dashboard locale layer.


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
            select(Issue).where(
                Issue.project_id == tenant_id,
                or_(
                    Issue.last_seen_at >= window_start,
                    Issue.resolved_at >= window_start,
                    Issue.first_seen_at >= window_start,
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

    for issue in rows:
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
