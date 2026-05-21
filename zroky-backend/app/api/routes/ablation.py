"""
/v1/ablation — Ablation Root-Cause Attribution API.

POST /v1/ablation              — trigger ablation job for a failing call
GET  /v1/ablation/{job_id}     — get job result (polls until done)
GET  /v1/ablation/by-call/{call_id}  — all jobs for a given call
GET  /v1/ablation              — project-level recent jobs
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import AblationAxis, AblationJob
from app.db.session import get_db_session
from app.services.ablation.orchestrator import (
    get_ablation_job,
    get_ablation_jobs_for_call,
    list_ablation_jobs,
    run_ablation_job,
)

router = APIRouter(
    prefix="/v1/ablation",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({"pending", "running", "done", "error", "insufficient_data"})


# ── Response schemas ───────────────────────────────────────────────────────────


class AblationAxisView(BaseModel):
    id: str
    axis_type: str
    axis_label: str
    failing_value: str | None
    confidence: float
    evidence: dict | None

    model_config = {"from_attributes": True}


class AblationJobView(BaseModel):
    id: str
    project_id: str
    call_id: str
    diagnosis_job_id: str | None
    status: str
    determinism_class: str | None
    control_group_size: int
    root_cause_narrative: str | None
    fix_suggestion: str | None
    fix_difficulty: str | None
    synthesis_confidence: float | None
    error_message: str | None
    axes: list[AblationAxisView]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TriggerRequest(BaseModel):
    call_id: str
    diagnosis_job_id: str | None = None


class TriggerResponse(BaseModel):
    job_id: str
    status: str
    message: str


# ── Helpers ────────────────────────────────────────────────────────────────────


def _axis_to_view(ax: AblationAxis) -> AblationAxisView:
    evidence = None
    if ax.evidence_json:
        try:
            evidence = json.loads(ax.evidence_json)
        except Exception:
            pass
    return AblationAxisView(
        id=ax.id,
        axis_type=ax.axis_type,
        axis_label=ax.axis_label,
        failing_value=ax.failing_value,
        confidence=float(ax.confidence),
        evidence=evidence,
    )


def _job_to_view(job: AblationJob) -> AblationJobView:
    axes = sorted(job.axes, key=lambda a: float(a.confidence), reverse=True)
    return AblationJobView(
        id=job.id,
        project_id=job.project_id,
        call_id=job.call_id,
        diagnosis_job_id=job.diagnosis_job_id,
        status=job.status,
        determinism_class=job.determinism_class,
        control_group_size=job.control_group_size,
        root_cause_narrative=job.root_cause_narrative,
        fix_suggestion=job.fix_suggestion,
        fix_difficulty=job.fix_difficulty,
        synthesis_confidence=float(job.synthesis_confidence) if job.synthesis_confidence is not None else None,
        error_message=job.error_message,
        axes=[_axis_to_view(a) for a in axes],
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


def _run_in_background(project_id: str, call_id: str, diagnosis_job_id: str | None, job_id: str) -> None:
    """Fire-and-forget: run the ablation job in a daemon thread with its own DB session."""
    from app.db.session import SessionLocal
    try:
        with SessionLocal() as db:
            existing = db.get(AblationJob, job_id)
            if existing is None:
                return
            run_ablation_job(
                db,
                project_id=project_id,
                call_id=call_id,
                diagnosis_job_id=diagnosis_job_id,
            )
    except Exception:
        logger.exception("background ablation job %s failed", job_id)


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=TriggerResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
def trigger_ablation(
    request: Request,
    body: TriggerRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> TriggerResponse:
    """Trigger a new ablation root-cause analysis for a failing call.

    The job runs asynchronously in a background thread.  Poll GET /v1/ablation/{job_id}
    for status.  Typical completion time: 5-30 seconds.
    """
    from app.db.models import AblationJob as _AJ
    from uuid import uuid4

    job = _AJ(
        id=str(uuid4()),
        project_id=tenant_id,
        call_id=body.call_id,
        diagnosis_job_id=body.diagnosis_job_id,
        status="pending",
    )
    db.add(job)
    db.commit()

    t = threading.Thread(
        target=_run_in_background,
        args=(tenant_id, body.call_id, body.diagnosis_job_id, job.id),
        daemon=True,
    )
    t.start()

    return TriggerResponse(
        job_id=job.id,
        status="pending",
        message="Ablation job queued. Poll GET /v1/ablation/{job_id} for results.",
    )


@router.get("/by-call/{call_id}", response_model=list[AblationJobView])
@limiter.limit("60/minute")
def get_jobs_for_call(
    request: Request,
    call_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> list[AblationJobView]:
    jobs = get_ablation_jobs_for_call(db, project_id=tenant_id, call_id=call_id)
    return [_job_to_view(j) for j in jobs]


@router.get("", response_model=list[AblationJobView])
@limiter.limit("60/minute")
def list_jobs(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> list[AblationJobView]:
    if status_filter and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    jobs = list_ablation_jobs(db, project_id=tenant_id, limit=limit, status_filter=status_filter)
    return [_job_to_view(j) for j in jobs]


@router.get("/{job_id}", response_model=AblationJobView)
@limiter.limit("120/minute")
def get_job(
    request: Request,
    job_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AblationJobView:
    job = get_ablation_job(db, project_id=tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ablation job not found")
    return _job_to_view(job)
