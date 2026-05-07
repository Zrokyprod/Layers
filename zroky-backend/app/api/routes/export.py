from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import DiagnosisFeedback, DiagnosisJob, ProjectAlert
from app.db.session import get_db_session

from app.schemas.dashboard import (
    AlertItemResponse,
    CallFeedbackSummary,
    CallListItem,
    ExportCallItem,
    ExportDiagnosisItem,
    ExportResponse,
)
from app.services.alerts import alert_to_payload, sync_alerts_from_jobs
from app.services.privacy import mask_json_string
from app.services.dashboard_data import (
    build_call_item,
    extract_diagnosis_categories,
    extract_payload,
    extract_result,
    utc_now,
)

router = APIRouter(prefix="/v1")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


@router.get("/export", response_model=ExportResponse)
def export_project_data(
    limit: int = Query(default=200, ge=1, le=1000),
    status_filter: str | None = Query(default=None, alias="status"),
    alert_status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    include_payload: bool = Query(default=True),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> ExportResponse:
    normalized_status = _normalize_status(status_filter)
    normalized_alert_status = _normalize_status(alert_status)
    normalized_category = _normalize_category(category)

    jobs_query = select(DiagnosisJob).where(DiagnosisJob.tenant_id == tenant_id)
    if normalized_status is not None:
        jobs_query = jobs_query.where(DiagnosisJob.status == normalized_status)
    if start_time is not None:
        jobs_query = jobs_query.where(DiagnosisJob.created_at >= _as_utc(start_time))
    if end_time is not None:
        jobs_query = jobs_query.where(DiagnosisJob.created_at <= _as_utc(end_time))

    jobs = db.execute(
        jobs_query.order_by(DiagnosisJob.created_at.desc()).limit(min(limit * 5, 5000))
    ).scalars().all()

    if jobs:
        if sync_alerts_from_jobs(db, tenant_id, jobs[:500]) > 0:
            try:
                db.commit()
            except IntegrityError:
                db.rollback()

    selected_jobs: list[DiagnosisJob] = []
    for job in jobs:
        if normalized_category is not None:
            categories = [item.strip().upper() for item in extract_diagnosis_categories(extract_result(job)) if item.strip()]
            if normalized_category not in categories:
                continue
        selected_jobs.append(job)
        if len(selected_jobs) >= limit:
            break

    diagnosis_ids = [job.diagnosis_id for job in selected_jobs]
    feedback_rows = []
    if diagnosis_ids:
        feedback_rows = db.execute(
            select(DiagnosisFeedback).where(
                DiagnosisFeedback.tenant_id == tenant_id,
                DiagnosisFeedback.diagnosis_id.in_(diagnosis_ids),
            )
        ).scalars().all()

    feedback_summary_map: dict[str, CallFeedbackSummary] = {
        diagnosis_id: CallFeedbackSummary(helpful_count=0, not_helpful_count=0)
        for diagnosis_id in diagnosis_ids
    }
    for row in feedback_rows:
        summary = feedback_summary_map.get(row.diagnosis_id)
        if summary is None:
            continue
        if row.was_helpful:
            summary.helpful_count += 1
        else:
            summary.not_helpful_count += 1

    exported_calls: list[ExportCallItem] = []
    exported_diagnoses: list[ExportDiagnosisItem] = []
    for job in selected_jobs:
        result_payload = extract_result(job)
        call_payload = extract_payload(job)
        exported_calls.append(
            ExportCallItem(
                call=CallListItem.model_validate(build_call_item(job)),
                payload=call_payload if include_payload else {},
                diagnosis_result=result_payload or None,
                feedback_summary=feedback_summary_map.get(
                    job.diagnosis_id,
                    CallFeedbackSummary(helpful_count=0, not_helpful_count=0),
                ),
            )
        )
        exported_diagnoses.append(
            ExportDiagnosisItem(
                tenant_id=job.tenant_id,
                diagnosis_id=job.diagnosis_id,
                status=job.status,
                categories=extract_diagnosis_categories(result_payload),
                result_json=mask_json_string(job.result_json),
                error_message=job.error_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )

    alerts_query = select(ProjectAlert).where(ProjectAlert.tenant_id == tenant_id)
    if normalized_alert_status is not None:
        alerts_query = alerts_query.where(ProjectAlert.status == normalized_alert_status.upper())
    if normalized_category is not None:
        alerts_query = alerts_query.where(ProjectAlert.category == normalized_category)
    if start_time is not None:
        alerts_query = alerts_query.where(ProjectAlert.created_at >= _as_utc(start_time))
    if end_time is not None:
        alerts_query = alerts_query.where(ProjectAlert.created_at <= _as_utc(end_time))

    alert_rows = db.execute(alerts_query.order_by(ProjectAlert.created_at.desc()).limit(limit)).scalars().all()
    exported_alerts = [AlertItemResponse.model_validate(alert_to_payload(item)) for item in alert_rows]

    return ExportResponse(
        tenant_id=tenant_id,
        generated_at=utc_now(),
        call_count=len(exported_calls),
        diagnosis_count=len(exported_diagnoses),
        alert_count=len(exported_alerts),
        calls=exported_calls,
        diagnoses=exported_diagnoses,
        alerts=exported_alerts,
    )
