"""Reliability Intelligence Queue — recommendation generator + CRUD.

Generates prioritised, actionable fix items by joining:
  - agent_reliability_scores   (health + fail rate + cost + determinism)
  - ablation_jobs + axes       (root cause confidence + fix suggestion)
  - outcome_events             (dollar cost per failure)

Generation is idempotent: same (project_id, agent_name, type, axis, date)
upserts the row.  Safe to call daily via scheduler or on-demand POST.

Public surface:
  generate_recommendations(db, project_id, as_of_date?) → list[ReliabilityRecommendation]
  list_recommendations(db, project_id, status?, priority?, agent?, limit?)
  get_recommendation(db, project_id, rec_id) → ReliabilityRecommendation | None
  update_status(db, project_id, rec_id, status, actioned_by?) → ReliabilityRecommendation
  get_summary(db, project_id) → RecommendationSummary
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AblationAxis,
    AblationJob,
    AgentReliabilityScore,
    OutcomeEvent,
    ReliabilityRecommendation,
)

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({"open", "acknowledged", "resolved", "dismissed", "snoozed"})
_DAYS_LOOKBACK = 7

# Thresholds for each recommendation type
_DETERMINISM_HIGH_THRESHOLD = 0.60   # health_score ≤ 60 AND primarily deterministic
_SCORE_DROP_THRESHOLD = 10.0          # health_score dropped ≥ 10 pts week-over-week
_COST_SPIKE_RATIO = 1.5               # avg_cost ≥ 1.5× previous week


@dataclass
class RecommendationSummary:
    project_id: str
    total_open: int
    critical_count: int
    high_count: int
    total_estimated_saving_usd: float
    top_agents: list[str]  # agents with most critical/high recs


# ── Public API ────────────────────────────────────────────────────────────────


def generate_recommendations(
    db: Session,
    *,
    project_id: str,
    as_of_date: date | None = None,
) -> list[ReliabilityRecommendation]:
    today = as_of_date or datetime.now(timezone.utc).date()
    recs: list[ReliabilityRecommendation] = []

    agents = _latest_scores(db, project_id)
    if not agents:
        return []

    # avg failure cost per project for relative ranking
    project_avg_cost = _project_avg_failure_cost(db, project_id)

    for score in agents:
        recs += _gen_axis_causal(db, project_id=project_id, score=score, today=today, project_avg_cost=project_avg_cost)
        recs += _gen_determinism_high(project_id=project_id, score=score, today=today, project_avg_cost=project_avg_cost)
        recs += _gen_score_drop(project_id=project_id, score=score, today=today, project_avg_cost=project_avg_cost)
        recs += _gen_cost_spike(db, project_id=project_id, score=score, today=today)

    # Assign priority based on impact_score quantile
    if recs:
        scores_sorted = sorted([float(r.impact_score) for r in recs], reverse=True)
        p75 = scores_sorted[int(len(scores_sorted) * 0.25)]
        p50 = scores_sorted[int(len(scores_sorted) * 0.50)]
        for r in recs:
            s = float(r.impact_score)
            if s >= p75:
                r.priority = "critical"
            elif s >= p50:
                r.priority = "high"
            else:
                r.priority = "medium"

    for rec in recs:
        _upsert_rec(db, rec)

    db.commit()
    return recs


def list_recommendations(
    db: Session,
    *,
    project_id: str,
    status: str | None = None,
    priority: str | None = None,
    agent_name: str | None = None,
    limit: int = 50,
) -> list[ReliabilityRecommendation]:
    q = select(ReliabilityRecommendation).where(
        ReliabilityRecommendation.project_id == project_id,
    )
    if status:
        q = q.where(ReliabilityRecommendation.status == status)
    if priority:
        q = q.where(ReliabilityRecommendation.priority == priority)
    if agent_name:
        q = q.where(ReliabilityRecommendation.agent_name == agent_name)
    q = q.order_by(ReliabilityRecommendation.impact_score.desc()).limit(limit)
    return list(db.execute(q).scalars().all())


def get_recommendation(
    db: Session,
    *,
    project_id: str,
    rec_id: str,
) -> ReliabilityRecommendation | None:
    return db.execute(
        select(ReliabilityRecommendation).where(
            ReliabilityRecommendation.project_id == project_id,
            ReliabilityRecommendation.id == rec_id,
        )
    ).scalar_one_or_none()


def update_status(
    db: Session,
    *,
    project_id: str,
    rec_id: str,
    new_status: str,
    actioned_by: str | None = None,
    snoozed_until: datetime | None = None,
) -> ReliabilityRecommendation:
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    rec = get_recommendation(db, project_id=project_id, rec_id=rec_id)
    if rec is None:
        raise LookupError(f"Recommendation {rec_id} not found")
    rec.status = new_status
    rec.actioned_by = actioned_by
    rec.actioned_at = datetime.now(timezone.utc)
    if new_status == "snoozed" and snoozed_until:
        rec.snoozed_until = snoozed_until
    db.commit()
    db.refresh(rec)
    return rec


def get_summary(
    db: Session,
    *,
    project_id: str,
) -> RecommendationSummary:
    open_recs = list_recommendations(db, project_id=project_id, status="open", limit=200)
    critical = [r for r in open_recs if r.priority == "critical"]
    high = [r for r in open_recs if r.priority == "high"]
    total_saving = sum(
        float(r.estimated_monthly_impact_usd or 0) for r in open_recs
    )
    # top agents by critical+high count
    agent_counts: dict[str, int] = {}
    for r in critical + high:
        agent_counts[r.agent_name] = agent_counts.get(r.agent_name, 0) + 1
    top_agents = sorted(agent_counts, key=lambda k: agent_counts[k], reverse=True)[:3]
    return RecommendationSummary(
        project_id=project_id,
        total_open=len(open_recs),
        critical_count=len(critical),
        high_count=len(high),
        total_estimated_saving_usd=round(total_saving, 4),
        top_agents=top_agents,
    )


# ── Generators ────────────────────────────────────────────────────────────────


def _gen_axis_causal(
    db: Session,
    *,
    project_id: str,
    score: AgentReliabilityScore,
    today: date,
    project_avg_cost: float,
) -> list[ReliabilityRecommendation]:
    """One rec per high-confidence ablation axis in the last 7 days."""
    since = datetime.now(timezone.utc) - timedelta(days=_DAYS_LOOKBACK)
    axes = db.execute(
        select(AblationAxis, AblationJob)
        .join(AblationJob, AblationJob.id == AblationAxis.ablation_job_id)
        .where(
            AblationAxis.project_id == project_id,
            AblationJob.status == "done",
            AblationJob.created_at >= since,
            AblationAxis.confidence >= 0.6,
        )
        .order_by(AblationAxis.confidence.desc())
        .limit(3)
    ).all()

    recs = []
    for axis_row, job_row in axes:
        axis_name = axis_row.axis_type
        conf = float(axis_row.confidence)
        health = float(score.health_score)
        cost = project_avg_cost
        call_count = score.call_count or 1
        fail_rate = float(score.fail_rate or 0)

        impact_score = conf * cost * call_count * (100.0 - health)
        monthly_impact = cost * call_count * fail_rate * 30

        rec = _make_rec(
            project_id=project_id,
            agent_name=score.agent_name,
            rec_type="axis_causal",
            title=f"{axis_name} axis causing failures (confidence {conf:.0%})",
            detail=job_row.root_cause_narrative,
            fix_suggestion=job_row.fix_suggestion,
            fix_difficulty=job_row.fix_difficulty,
            top_axis=axis_name,
            axis_confidence=conf,
            impact_score=impact_score,
            monthly_impact=monthly_impact,
            health_score=health,
            fail_rate=fail_rate,
            call_count=call_count,
            ablation_job_id=job_row.id,
            generated_date=today,
        )
        recs.append(rec)
    return recs


def _gen_determinism_high(
    *,
    project_id: str,
    score: AgentReliabilityScore,
    today: date,
    project_avg_cost: float,
) -> list[ReliabilityRecommendation]:
    """Fire when majority of ablation jobs are deterministic and score is low."""
    import json
    if not score.determinism_breakdown_json:
        return []
    try:
        bd = json.loads(score.determinism_breakdown_json)
    except Exception:
        return []
    total = sum(bd.values())
    if total == 0:
        return []
    det_ratio = bd.get("deterministic", 0) / total
    if det_ratio < 0.5 or float(score.health_score) > _DETERMINISM_HIGH_THRESHOLD * 100:
        return []

    health = float(score.health_score)
    fail_rate = float(score.fail_rate or 0)
    call_count = score.call_count or 1
    impact_score = det_ratio * project_avg_cost * call_count * (100.0 - health)
    monthly_impact = project_avg_cost * call_count * fail_rate * 30

    return [_make_rec(
        project_id=project_id,
        agent_name=score.agent_name,
        rec_type="determinism_high",
        title=f"{det_ratio:.0%} of failures are deterministic — code-level bug likely",
        detail=(
            f"Agent '{score.agent_name}' has {bd.get('deterministic', 0)} deterministic "
            f"failures in the last 7 days. Deterministic failures recur 100% — "
            f"they will not self-heal and require a code or config fix."
        ),
        fix_suggestion="Review the top ablation axis for this agent and inspect recent prompt or tool changes.",
        fix_difficulty="medium",
        top_axis=None,
        axis_confidence=det_ratio,
        impact_score=impact_score,
        monthly_impact=monthly_impact,
        health_score=health,
        fail_rate=fail_rate,
        call_count=call_count,
        ablation_job_id=None,
        generated_date=today,
    )]


def _gen_score_drop(
    *,
    project_id: str,
    score: AgentReliabilityScore,
    today: date,
    project_avg_cost: float,
) -> list[ReliabilityRecommendation]:
    """Fire when health_score dropped ≥ 10 points vs. prev week."""
    if score.prev_week_fail_rate is None:
        return []
    prev_fail = float(score.prev_week_fail_rate)
    curr_fail = float(score.fail_rate or 0)
    delta_pct = (curr_fail - prev_fail) * 100.0
    if delta_pct < 5.0:  # less than 5 percentage-point increase
        return []

    health = float(score.health_score)
    call_count = score.call_count or 1
    impact_score = delta_pct * project_avg_cost * call_count * (100.0 - health) / 100.0
    monthly_impact = project_avg_cost * call_count * curr_fail * 30

    return [_make_rec(
        project_id=project_id,
        agent_name=score.agent_name,
        rec_type="score_drop",
        title=f"Fail rate increased {delta_pct:+.1f}pp week-over-week",
        detail=(
            f"Agent '{score.agent_name}' fail rate rose from {prev_fail*100:.1f}% "
            f"to {curr_fail*100:.1f}% — a {delta_pct:+.1f} percentage-point regression. "
            f"This may indicate a recent deployment or provider change."
        ),
        fix_suggestion="Check recent deployments, prompt fingerprint changes, or provider status for the affected agent.",
        fix_difficulty="easy",
        top_axis=score.top_failure_axis,
        axis_confidence=None,
        impact_score=impact_score,
        monthly_impact=monthly_impact,
        health_score=health,
        fail_rate=curr_fail,
        call_count=call_count,
        ablation_job_id=None,
        generated_date=today,
    )]


def _gen_cost_spike(
    db: Session,
    *,
    project_id: str,
    score: AgentReliabilityScore,
    today: date,
) -> list[ReliabilityRecommendation]:
    """Fire when avg cost per call spiked ≥ 1.5× vs. prior week."""
    since_curr = datetime.now(timezone.utc) - timedelta(days=_DAYS_LOOKBACK)
    since_prev = since_curr - timedelta(days=_DAYS_LOOKBACK)

    from app.db.models import Call

    def _avg(start: datetime, end: datetime) -> float | None:
        row = db.execute(
            select(func.avg(Call.cost_total)).where(
                Call.project_id == project_id,
                Call.agent_name == score.agent_name,
                Call.cost_total > 0,
                Call.created_at >= start,
                Call.created_at < end,
            )
        ).scalar()
        return float(row) if row else None

    curr_avg = _avg(since_curr, datetime.now(timezone.utc))
    prev_avg = _avg(since_prev, since_curr)

    if curr_avg is None or prev_avg is None or prev_avg == 0:
        return []
    ratio = curr_avg / prev_avg
    if ratio < _COST_SPIKE_RATIO:
        return []

    call_count = score.call_count or 1
    overspend_per_call = curr_avg - prev_avg
    monthly_overspend = overspend_per_call * call_count * 30
    health = float(score.health_score)
    impact_score = ratio * monthly_overspend

    return [_make_rec(
        project_id=project_id,
        agent_name=score.agent_name,
        rec_type="cost_spike",
        title=f"Cost per call spiked {ratio:.1f}× vs. prior week",
        detail=(
            f"Agent '{score.agent_name}' avg cost per call rose from "
            f"${prev_avg:.4f} to ${curr_avg:.4f} ({ratio:.1f}×). "
            f"Estimated monthly overspend: ${monthly_overspend:.2f}."
        ),
        fix_suggestion="Check if the model version changed (e.g. gpt-4o-mini → gpt-4o) or if output token length increased.",
        fix_difficulty="easy",
        top_axis="model_version",
        axis_confidence=None,
        impact_score=impact_score,
        monthly_impact=monthly_overspend,
        health_score=health,
        fail_rate=float(score.fail_rate or 0),
        call_count=call_count,
        ablation_job_id=None,
        generated_date=today,
    )]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _make_rec(
    *,
    project_id: str,
    agent_name: str,
    rec_type: str,
    title: str,
    detail: str | None,
    fix_suggestion: str | None,
    fix_difficulty: str | None,
    top_axis: str | None,
    axis_confidence: float | None,
    impact_score: float,
    monthly_impact: float | None,
    health_score: float,
    fail_rate: float,
    call_count: int,
    ablation_job_id: str | None,
    generated_date: date,
) -> ReliabilityRecommendation:
    return ReliabilityRecommendation(
        id=str(uuid4()),
        project_id=project_id,
        agent_name=agent_name,
        recommendation_type=rec_type,
        priority="medium",
        title=title[:255],
        detail=detail,
        fix_suggestion=fix_suggestion,
        fix_difficulty=fix_difficulty,
        top_axis=top_axis,
        axis_confidence=round(axis_confidence, 4) if axis_confidence else None,
        estimated_monthly_impact_usd=round(monthly_impact, 4) if monthly_impact else None,
        impact_score=round(max(0.0, impact_score), 6),
        health_score_at_generation=round(health_score, 2),
        fail_rate_at_generation=round(fail_rate, 5),
        call_count_window=call_count,
        ablation_job_id=ablation_job_id,
        status="open",
        generated_date=generated_date,
    )


def _latest_scores(
    db: Session,
    project_id: str,
) -> list[AgentReliabilityScore]:
    subq = (
        select(
            AgentReliabilityScore.agent_name,
            func.max(AgentReliabilityScore.score_date).label("max_date"),
        )
        .where(AgentReliabilityScore.project_id == project_id)
        .group_by(AgentReliabilityScore.agent_name)
        .subquery()
    )
    q = (
        select(AgentReliabilityScore)
        .join(
            subq,
            (AgentReliabilityScore.agent_name == subq.c.agent_name)
            & (AgentReliabilityScore.score_date == subq.c.max_date),
        )
        .where(AgentReliabilityScore.project_id == project_id)
    )
    return list(db.execute(q).scalars().all())


def _project_avg_failure_cost(
    db: Session,
    project_id: str,
) -> float:
    row = db.execute(
        select(func.avg(OutcomeEvent.estimated_cost_usd)).where(
            OutcomeEvent.project_id == project_id,
            OutcomeEvent.outcome_type == "failure",
            OutcomeEvent.estimated_cost_usd > 0,
        )
    ).scalar()
    return float(row) if row else 0.01  # fallback: $0.01 per failure


def _upsert_rec(db: Session, rec: ReliabilityRecommendation) -> None:
    existing = db.execute(
        select(ReliabilityRecommendation).where(
            ReliabilityRecommendation.project_id == rec.project_id,
            ReliabilityRecommendation.agent_name == rec.agent_name,
            ReliabilityRecommendation.recommendation_type == rec.recommendation_type,
            ReliabilityRecommendation.top_axis == rec.top_axis,
            ReliabilityRecommendation.generated_date == rec.generated_date,
        )
    ).scalar_one_or_none()

    if existing:
        for field in (
            "title", "detail", "fix_suggestion", "fix_difficulty", "axis_confidence",
            "estimated_monthly_impact_usd", "impact_score", "priority",
            "health_score_at_generation", "fail_rate_at_generation", "call_count_window",
            "ablation_job_id",
        ):
            setattr(existing, field, getattr(rec, field, None))
    else:
        db.add(rec)
