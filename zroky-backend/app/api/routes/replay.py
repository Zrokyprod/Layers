"""
Replay API — dispatch and track replay jobs for the customer-hosted replay worker.

Routes:
  POST /v1/replay/jobs            → create a replay job (dashboard trigger)
  GET  /v1/replay/jobs/{replay_id} → poll job status (dashboard polling)
  POST /v1/replay/poll            → worker pulls pending jobs (signed with WORKER_TOKEN)
  POST /v1/replay/result          → worker submits result
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.config import get_settings
from app.core.limiter import limiter
from fastapi import Request
from app.db.models import Call, DiagnosisPullRequest, ReplayJob
from app.db.session import get_db_session
from app.services.replay_runs import check_replay_monthly_quota

router = APIRouter(prefix="/v1/replay")
logger = logging.getLogger(__name__)

_VALID_STATUSES = {"pending", "running", "pass", "fail", "error"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateReplayJobRequest(BaseModel):
    call_id: str
    pr_id: str | None = None
    candidate_fix_diff: str | None = None
    artifact_url: str | None = None
    artifact_signature: str | None = None
    timeout_seconds: int = 300


class ReplayJobResponse(BaseModel):
    id: str
    tenant_id: str
    call_id: str | None
    pr_id: str | None
    status: str
    diff_metric: float | None
    error_message: str | None
    stdout_tail: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkerPollRequest(BaseModel):
    worker_token: str
    worker_id: str | None = None
    capacity: int = 1


class WorkerJobPayload(BaseModel):
    replay_id: str
    trace_id: str
    fix_pr_id: str
    candidate_fix_diff: str
    artifact_url: str
    artifact_signature: str
    created_at: datetime
    timeout_seconds: int


class WorkerPollResponse(BaseModel):
    jobs: list[WorkerJobPayload] = []


class WorkerResultPayload(BaseModel):
    worker_token: str
    worker_id: str | None = None
    result: dict[str, Any]


class ReplayQuotaResponse(BaseModel):
    enabled: bool
    used: int
    limit: int    # -1 = unlimited (Enterprise)
    resets_at: str  # ISO date — first day of next calendar month
    plan_code: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/quota", response_model=ReplayQuotaResponse)
@limiter.limit("120/minute")
def get_replay_quota(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayQuotaResponse:
    """Return the calling tenant's monthly replay quota state.

    Accessible to all plan tiers (no feature gate) so the dashboard can
    show the correct upgrade prompt to Free users.
    """
    result = check_replay_monthly_quota(db, tenant_id)
    return ReplayQuotaResponse(
        enabled=result.enabled,
        used=result.used,
        limit=result.limit,
        resets_at=result.resets_at,
        plan_code=result.plan_code,
    )


@router.post("/jobs", response_model=ReplayJobResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_replay_job(
    request: Request,
    body: CreateReplayJobRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayJobResponse:
    # ── monthly quota check ──────────────────────────────────────────
    quota = check_replay_monthly_quota(db, tenant_id)
    if quota.limit != -1 and quota.used >= quota.limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "detail": (
                    f"Monthly replay limit reached ({quota.used}/{quota.limit}). "
                    f"Resets {quota.resets_at}."
                ),
                "required_entitlement": "replay.monthly_runs",
                "current_plan": quota.plan_code,
                "used": quota.used,
                "limit": quota.limit,
                "resets_at": quota.resets_at,
                "upgrade_hint_url": "/settings/billing?upgrade_hint=replay.monthly_runs",
            },
            headers={"X-Zroky-Plan-Hint": quota.plan_code},
        )

    call = db.execute(
        select(Call).where(Call.id == body.call_id, Call.project_id == tenant_id)
    ).scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    if body.pr_id:
        pr = db.execute(
            select(DiagnosisPullRequest).where(
                DiagnosisPullRequest.id == body.pr_id,
                DiagnosisPullRequest.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if pr is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PR not found")

    job = ReplayJob(
        id=str(uuid4()),
        tenant_id=tenant_id,
        call_id=body.call_id,
        pr_id=body.pr_id,
        status="pending",
        candidate_fix_diff=body.candidate_fix_diff,
        artifact_url=body.artifact_url or "",
        artifact_signature=body.artifact_signature or "",
        timeout_seconds=body.timeout_seconds,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("replay_job_created tenant=%s job=%s call=%s", tenant_id, job.id, body.call_id)
    return ReplayJobResponse.model_validate(job)


@router.get("/jobs/{replay_id}", response_model=ReplayJobResponse)
@limiter.limit("120/minute")
def get_replay_job(
    request: Request,
    replay_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayJobResponse:
    job = db.execute(
        select(ReplayJob).where(ReplayJob.id == replay_id, ReplayJob.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay job not found")
    return ReplayJobResponse.model_validate(job)


@router.post("/poll", response_model=WorkerPollResponse)
def worker_poll(body: WorkerPollRequest, db: Session = Depends(get_db_session)) -> WorkerPollResponse:
    settings = get_settings()
    if not settings.REPLAY_WORKER_TOKEN or body.worker_token != settings.REPLAY_WORKER_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token")

    now = datetime.now(timezone.utc)
    worker_id = (body.worker_id or "legacy-worker").strip() or "legacy-worker"
    capacity = max(1, min(body.capacity, 10))
    lease_seconds = max(60, settings.REPLAY_JOB_LEASE_SECONDS)
    lease_expires_at = now + timedelta(seconds=lease_seconds)

    pending = db.execute(
        select(ReplayJob)
        .where(
            or_(
                ReplayJob.status == "pending",
                (
                    (ReplayJob.status == "running")
                    & ReplayJob.lease_expires_at.is_not(None)
                    & (ReplayJob.lease_expires_at <= now)
                ),
            )
        )
        .order_by(ReplayJob.created_at)
        .limit(capacity)
        .with_for_update(skip_locked=True)
    ).scalars().all()

    if not pending:
        return WorkerPollResponse(jobs=[])

    payloads: list[WorkerJobPayload] = []
    for job in pending:
        job.status = "running"
        job.claimed_by = worker_id
        job.claimed_at = now
        job.lease_expires_at = lease_expires_at
        job.attempt_count = (job.attempt_count or 0) + 1
        db.add(job)
        payloads.append(WorkerJobPayload(
            replay_id=job.id,
            trace_id=job.call_id or "",
            fix_pr_id=job.pr_id or "",
            candidate_fix_diff=job.candidate_fix_diff or "",
            artifact_url=job.artifact_url or "",
            artifact_signature=job.artifact_signature or "",
            created_at=job.created_at,
            timeout_seconds=job.timeout_seconds,
        ))
    db.commit()
    return WorkerPollResponse(jobs=payloads)


@router.post("/result", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def worker_result(
    body: WorkerResultPayload, db: Session = Depends(get_db_session)
) -> Response:
    settings = get_settings()
    if not settings.REPLAY_WORKER_TOKEN or body.worker_token != settings.REPLAY_WORKER_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token")

    result = body.result
    replay_id = result.get("replay_id")
    if not replay_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="replay_id required")

    job = db.execute(select(ReplayJob).where(ReplayJob.id == replay_id)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay job not found")

    worker_id = (body.worker_id or "legacy-worker").strip() or "legacy-worker"
    if job.claimed_by and job.claimed_by != worker_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Replay job is leased by a different worker.",
        )

    raw_status = str(result.get("status", "error"))
    job.status = raw_status if raw_status in _VALID_STATUSES else "error"
    job.diff_metric = result.get("diff_metric")
    job.error_message = result.get("error_message")
    job.stdout_tail = result.get("stdout_tail")
    job.completed_at = datetime.now(timezone.utc)
    job.lease_expires_at = None
    db.add(job)

    if job.pr_id:
        pr = db.execute(
            select(DiagnosisPullRequest).where(DiagnosisPullRequest.id == job.pr_id)
        ).scalar_one_or_none()
        if pr is not None:
            pr.replay_id = replay_id
            pr.replay_status = job.status
            pr.replay_completed_at = job.completed_at
            db.add(pr)

    db.commit()
    logger.info("replay_result tenant=%s job=%s status=%s", job.tenant_id, replay_id, job.status)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
