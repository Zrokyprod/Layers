"""
/v1/recommendations — Reliability Intelligence Queue API.

GET  /v1/recommendations              — list open/filtered recs, sorted by impact
GET  /v1/recommendations/summary      — open count, critical/high counts, est. saving
GET  /v1/recommendations/{id}         — single rec
PATCH /v1/recommendations/{id}/status — acknowledge / resolve / dismiss / snooze
POST /v1/recommendations/generate     — on-demand regeneration
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.recommendations import (
    generate_recommendations,
    get_recommendation,
    get_summary,
    list_recommendations,
    update_status,
    VALID_STATUSES,
)

router = APIRouter(
    prefix="/v1/recommendations",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)


# ── Response schemas ───────────────────────────────────────────────────────────


class RecView(BaseModel):
    id: str
    agent_name: str
    recommendation_type: str
    priority: str
    title: str
    detail: str | None
    fix_suggestion: str | None
    fix_difficulty: str | None
    top_axis: str | None
    axis_confidence: float | None
    estimated_monthly_impact_usd: float | None
    impact_score: float
    health_score_at_generation: float | None
    fail_rate_at_generation: float | None
    call_count_window: int | None
    ablation_job_id: str | None
    status: str
    actioned_by: str | None
    actioned_at: datetime | None
    snoozed_until: datetime | None
    generated_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class RecSummaryView(BaseModel):
    project_id: str
    total_open: int
    critical_count: int
    high_count: int
    total_estimated_saving_usd: float
    top_agents: list[str]


class StatusUpdateRequest(BaseModel):
    status: str
    actioned_by: str | None = None
    snoozed_until: datetime | None = None


class GenerateResponse(BaseModel):
    generated: int
    message: str


# ── Helper ─────────────────────────────────────────────────────────────────────


def _to_view(rec) -> RecView:
    return RecView(
        id=rec.id,
        agent_name=rec.agent_name,
        recommendation_type=rec.recommendation_type,
        priority=rec.priority,
        title=rec.title,
        detail=rec.detail,
        fix_suggestion=rec.fix_suggestion,
        fix_difficulty=rec.fix_difficulty,
        top_axis=rec.top_axis,
        axis_confidence=float(rec.axis_confidence) if rec.axis_confidence is not None else None,
        estimated_monthly_impact_usd=float(rec.estimated_monthly_impact_usd) if rec.estimated_monthly_impact_usd is not None else None,
        impact_score=float(rec.impact_score),
        health_score_at_generation=float(rec.health_score_at_generation) if rec.health_score_at_generation is not None else None,
        fail_rate_at_generation=float(rec.fail_rate_at_generation) if rec.fail_rate_at_generation is not None else None,
        call_count_window=rec.call_count_window,
        ablation_job_id=rec.ablation_job_id,
        status=rec.status,
        actioned_by=rec.actioned_by,
        actioned_at=rec.actioned_at,
        snoozed_until=rec.snoozed_until,
        generated_date=rec.generated_date,
        created_at=rec.created_at,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[RecView])
@limiter.limit("60/minute")
def list_recs(
    request: Request,
    rec_status: str | None = Query(default="open", alias="status"),
    priority: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> list[RecView]:
    rows = list_recommendations(
        db,
        project_id=tenant_id,
        status=rec_status,
        priority=priority,
        agent_name=agent_name,
        limit=limit,
    )
    return [_to_view(r) for r in rows]


@router.get("/summary", response_model=RecSummaryView)
@limiter.limit("60/minute")
def summary(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> RecSummaryView:
    s = get_summary(db, project_id=tenant_id)
    return RecSummaryView(
        project_id=s.project_id,
        total_open=s.total_open,
        critical_count=s.critical_count,
        high_count=s.high_count,
        total_estimated_saving_usd=s.total_estimated_saving_usd,
        top_agents=s.top_agents,
    )


@router.get("/{rec_id}", response_model=RecView)
@limiter.limit("60/minute")
def get_rec(
    request: Request,
    rec_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> RecView:
    rec = get_recommendation(db, project_id=tenant_id, rec_id=rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return _to_view(rec)


@router.patch("/{rec_id}/status", response_model=RecView)
@limiter.limit("30/minute")
def patch_status(
    request: Request,
    rec_id: str,
    body: StatusUpdateRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> RecView:
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {sorted(VALID_STATUSES)}",
        )
    try:
        rec = update_status(
            db,
            project_id=tenant_id,
            rec_id=rec_id,
            new_status=body.status,
            actioned_by=body.actioned_by,
            snoozed_until=body.snoozed_until,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_view(rec)


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
def generate(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GenerateResponse:
    recs = generate_recommendations(db, project_id=tenant_id)
    return GenerateResponse(
        generated=len(recs),
        message=f"Generated {len(recs)} recommendations.",
    )
