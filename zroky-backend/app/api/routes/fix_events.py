from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import ROLE_RANK, TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import DiagnosisJob
from app.db.session import get_db_session
from app.schemas.fix_events import (
    FixEventCreateRequest,
    FixEventCreateResponse,
    FixEventType,
    FixResolutionStatus,
)
from app.services.fix_adoption import (
    ensure_fix_event_prerequisites,
    fix_event_metadata,
    mark_resolved_if_no_recurrence,
    record_fix_event,
)
from app.services.privacy import mask_error_message

router = APIRouter(prefix="/v1/fix-events")
MEMBER_EVENT_TYPES = {
    FixEventType.PR_GENERATED,
    FixEventType.PR_MERGED,
    FixEventType.APPLIED,
    FixEventType.RESOLVED,
    FixEventType.REGRESSED,
}


@router.post("", response_model=FixEventCreateResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_fix_event(
    request: Request,
    body: FixEventCreateRequest,
    tenant: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> FixEventCreateResponse:
    if body.event_type in MEMBER_EVENT_TYPES and ROLE_RANK.get(tenant.role, 0) < ROLE_RANK["member"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant role '{tenant.role}' does not allow this fix event.",
        )

    diagnosis = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant.tenant_id,
            DiagnosisJob.diagnosis_id == body.diagnosis_id,
        )
    ).scalar_one_or_none()
    if diagnosis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")

    try:
        ensure_fix_event_prerequisites(
            db,
            project_id=tenant.tenant_id,
            diagnosis_id=body.diagnosis_id,
            fix_id=body.fix_id,
            event_type=body.event_type.value,
            anchor_time=body.occurred_at,
            source=body.source,
            inferred_from=body.event_type.value,
            metadata={"feed": "fix_events_api"},
        )
        event = record_fix_event(
            db,
            project_id=tenant.tenant_id,
            diagnosis_id=body.diagnosis_id,
            fix_id=body.fix_id,
            event_type=body.event_type.value,
            metadata=body.metadata,
            idempotency_key=body.idempotency_key,
            source=body.source,
            timestamp=body.occurred_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=mask_error_message(exc),
        ) from exc

    resolution: FixResolutionStatus | None = None
    if body.event_type in {FixEventType.APPLIED, FixEventType.PR_MERGED}:
        evaluation, _ = mark_resolved_if_no_recurrence(
            db,
            project_id=tenant.tenant_id,
            diagnosis_id=event.diagnosis_id,
            fix_id=event.fix_id,
            since=event.timestamp,
            correlation_signal=event.event_type,
        )
        resolution = FixResolutionStatus(**evaluation.to_metadata(), resolved=evaluation.resolved)

    return FixEventCreateResponse(
        id=event.id,
        project_id=event.project_id,
        diagnosis_id=event.diagnosis_id,
        fix_id=event.fix_id,
        event_type=FixEventType(event.event_type),
        source=event.source,
        idempotency_key=event.idempotency_key,
        timestamp=event.timestamp,
        metadata=fix_event_metadata(event),
        resolution=resolution,
    )
