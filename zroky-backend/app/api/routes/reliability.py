"""
/v1/reliability — Agent Reliability Scorecard API.

GET  /v1/reliability/leaderboard          — latest score per agent, sorted
GET  /v1/reliability/summary              — project-level aggregate
GET  /v1/reliability/agent/{name}         — 30-day history for one agent
POST /v1/reliability/compute              — trigger on-demand recomputation
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import AgentReliabilityScore
from app.db.session import get_db_session
from app.services.agent_reliability import (
    compute_project_scores,
    get_agent_history,
    get_leaderboard,
    get_project_summary,
)

router = APIRouter(
    prefix="/v1/reliability",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)


# ── Response schemas ───────────────────────────────────────────────────────────


class AgentScoreView(BaseModel):
    agent_name: str
    score_date: date
    health_score: float
    fail_rate: float
    fail_rate_score: float
    cost_efficiency_score: float
    determinism_score: float
    regression_trend_score: float
    call_count: int
    avg_cost_usd: float
    p95_latency_ms: float | None
    prev_week_fail_rate: float | None
    determinism_breakdown: dict | None
    top_failure_axis: str | None
    computed_at: datetime

    model_config = {"from_attributes": True}


class ProjectSummaryView(BaseModel):
    project_id: str
    agent_count: int
    avg_health_score: float
    worst_agent: str | None
    best_agent: str | None
    total_deterministic_failures: int
    total_stochastic_failures: int
    score_date: date


class ComputeResponse(BaseModel):
    agents_computed: int
    score_date: date
    message: str


# ── Helper ─────────────────────────────────────────────────────────────────────


def _to_view(row: AgentReliabilityScore) -> AgentScoreView:
    import json
    breakdown = None
    if row.determinism_breakdown_json:
        try:
            breakdown = json.loads(row.determinism_breakdown_json)
        except Exception:
            pass
    return AgentScoreView(
        agent_name=row.agent_name,
        score_date=row.score_date,
        health_score=float(row.health_score),
        fail_rate=float(row.fail_rate),
        fail_rate_score=float(row.fail_rate_score),
        cost_efficiency_score=float(row.cost_efficiency_score),
        determinism_score=float(row.determinism_score),
        regression_trend_score=float(row.regression_trend_score),
        call_count=row.call_count,
        avg_cost_usd=float(row.avg_cost_usd),
        p95_latency_ms=float(row.p95_latency_ms) if row.p95_latency_ms is not None else None,
        prev_week_fail_rate=float(row.prev_week_fail_rate) if row.prev_week_fail_rate is not None else None,
        determinism_breakdown=breakdown,
        top_failure_axis=row.top_failure_axis,
        computed_at=row.computed_at,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/leaderboard", response_model=list[AgentScoreView])
@limiter.limit("60/minute")
def leaderboard(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> list[AgentScoreView]:
    """Return the most recent health score per agent, sorted best-to-worst."""
    rows = get_leaderboard(db, project_id=tenant_id, limit=limit)
    return [_to_view(r) for r in rows]


@router.get("/summary", response_model=ProjectSummaryView)
@limiter.limit("60/minute")
def summary(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ProjectSummaryView:
    """Return project-level reliability aggregate (for dashboard banner)."""
    s = get_project_summary(db, project_id=tenant_id)
    return ProjectSummaryView(
        project_id=s.project_id,
        agent_count=s.agent_count,
        avg_health_score=s.avg_health_score,
        worst_agent=s.worst_agent,
        best_agent=s.best_agent,
        total_deterministic_failures=s.total_deterministic_failures,
        total_stochastic_failures=s.total_stochastic_failures,
        score_date=s.score_date,
    )


@router.get("/agent/{agent_name}", response_model=list[AgentScoreView])
@limiter.limit("60/minute")
def agent_history(
    request: Request,
    agent_name: str,
    days: int = Query(default=30, ge=7, le=90),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> list[AgentScoreView]:
    """Return daily health score history for one agent (for sparkline)."""
    rows = get_agent_history(db, project_id=tenant_id, agent_name=agent_name, days=days)
    return [_to_view(r) for r in rows]


@router.post("/compute", response_model=ComputeResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
def trigger_compute(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ComputeResponse:
    """On-demand recomputation for today. Idempotent — safe to call repeatedly."""
    scores = compute_project_scores(db, project_id=tenant_id)
    today = datetime.utcnow().date()
    return ComputeResponse(
        agents_computed=len(scores),
        score_date=today,
        message=f"Computed scores for {len(scores)} agents.",
    )
