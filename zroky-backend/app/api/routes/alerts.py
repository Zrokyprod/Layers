from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import DiagnosisJob, ProjectAlert
from app.db.session import get_db_session
from app.schemas.dashboard import (
    AlertChannelTestRequest,
    AlertChannelTestResponse,
    AlertItemResponse,
    AlertListResponse,
)
from app.services.alerts import alert_to_payload, sync_alerts_from_jobs

router = APIRouter(prefix="/v1/alerts")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_alert_or_404(db: Session, tenant_id: str, alert_id: str) -> ProjectAlert:
    alert = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.id == alert_id,
            ProjectAlert.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


def _sync_recent_alerts(db: Session, tenant_id: str) -> None:
    recent_jobs = db.execute(
        select(DiagnosisJob)
        .where(DiagnosisJob.tenant_id == tenant_id, DiagnosisJob.status.in_(["completed", "done"]))
        .order_by(DiagnosisJob.updated_at.desc())
        .limit(500)
    ).scalars().all()
    if sync_alerts_from_jobs(db, tenant_id, recent_jobs) > 0:
        try:
            db.commit()
        except IntegrityError:
            # Concurrent request already inserted the same alert; safe to ignore.
            db.rollback()


@router.get("", response_model=AlertListResponse)
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> AlertListResponse:
    _sync_recent_alerts(db, tenant_id)

    query = select(ProjectAlert).where(ProjectAlert.tenant_id == tenant_id)
    if status_filter:
        query = query.where(ProjectAlert.status == status_filter.upper())
    if severity:
        query = query.where(ProjectAlert.severity == severity.lower())
    if category:
        query = query.where(ProjectAlert.category == category.upper())
    if start_time is not None:
        query = query.where(ProjectAlert.created_at >= _as_utc(start_time))
    if end_time is not None:
        query = query.where(ProjectAlert.created_at <= _as_utc(end_time))

    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar() or 0

    page = db.execute(
        query.order_by(ProjectAlert.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    items = [AlertItemResponse.model_validate(alert_to_payload(item)) for item in page]
    return AlertListResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/{alert_id}", response_model=AlertItemResponse)
def get_alert_detail(
    alert_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> AlertItemResponse:
    _sync_recent_alerts(db, tenant_id)
    alert = _get_alert_or_404(db, tenant_id, alert_id)
    return AlertItemResponse.model_validate(alert_to_payload(alert))


def _update_alert_status(db: Session, alert: ProjectAlert, status_value: str) -> ProjectAlert:
    now = datetime.now(timezone.utc)
    alert.status = status_value
    if status_value == "ACKNOWLEDGED":
        if alert.acknowledged_at is None:
            alert.acknowledged_at = now
    elif status_value == "RESOLVED":
        if alert.acknowledged_at is None:
            alert.acknowledged_at = now
        alert.resolved_at = now
    elif status_value == "OPEN":
        alert.resolved_at = None

    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{alert_id}/acknowledge", response_model=AlertItemResponse)
def acknowledge_alert(
    alert_id: str,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> AlertItemResponse:
    alert = _get_alert_or_404(db, tenant_id, alert_id)
    alert = _update_alert_status(db, alert, "ACKNOWLEDGED")
    return AlertItemResponse.model_validate(alert_to_payload(alert))


@router.post("/{alert_id}/resolve", response_model=AlertItemResponse)
def resolve_alert(
    alert_id: str,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> AlertItemResponse:
    alert = _get_alert_or_404(db, tenant_id, alert_id)
    alert = _update_alert_status(db, alert, "RESOLVED")
    return AlertItemResponse.model_validate(alert_to_payload(alert))


@router.post("/{alert_id}/reopen", response_model=AlertItemResponse)
def reopen_alert(
    alert_id: str,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> AlertItemResponse:
    alert = _get_alert_or_404(db, tenant_id, alert_id)
    alert = _update_alert_status(db, alert, "OPEN")
    return AlertItemResponse.model_validate(alert_to_payload(alert))


@router.post("/channel-test", response_model=AlertChannelTestResponse)
def send_alert_channel_test(
    body: AlertChannelTestRequest,
    _: str = Depends(require_tenant_role("admin")),
) -> AlertChannelTestResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Alert channel test dispatch is not yet configured for channel '{body.channel}'.",
    )
