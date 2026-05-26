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
from app.db.models import Anomaly, AuditLog, Call, DiagnosisFeedback, DiagnosisJob, ProjectAlert, ProjectDashboardConfig
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
from app.services.issue_projection import issue_projection_from_anomaly

router = APIRouter(prefix="/v1/analytics")


_FAILED_CALL_STATUSES: frozenset[str] = frozenset(
    {"failed", "error", "errored", "timeout", "dead_lettered", "enqueue_failed"}
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


__all__ = [name for name in globals() if not name.startswith("__")]
