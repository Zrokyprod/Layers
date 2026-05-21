"""Agent Reliability Scorecard service.

Computes a daily 0-100 health score per (project_id, agent_name) from
existing production data.  No new telemetry; pure aggregation.

Score composition (weights sum to 1.0):
  fail_rate_score        0.35 — 100 × (1 - fail_rate)
  cost_efficiency_score  0.25 — relative cost vs. project median
  determinism_score      0.25 — penalises deterministic failures heavily
  regression_trend_score 0.15 — week-over-week fail rate delta bonus/penalty

Public surface:
  compute_project_scores(db, project_id, as_of_date?) → list[AgentReliabilityScore]
      Compute and upsert scores for ALL agents in a project.
      Call daily from a scheduler or via the API's /v1/reliability/compute.

  get_leaderboard(db, project_id, limit?) → list[AgentReliabilityScore]
      Latest score per agent, sorted by health_score DESC.

  get_agent_history(db, project_id, agent_name, days?) → list[AgentReliabilityScore]
      30-day history for one agent (for sparkline).

  get_project_summary(db, project_id) → ProjectReliabilitySummary
      Aggregate project-level stats.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import AblationAxis, AblationJob, AgentReliabilityScore, Call

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

WINDOW_DAYS = 7
FAIL_STATUSES = frozenset({"error", "failed", "timeout", "rate_limited"})

_W_FAIL_RATE = 0.35
_W_COST_EFF = 0.25
_W_DETERMINISM = 0.25
_W_TREND = 0.15

# Determinism class penalty: deterministic failures are worst (they recur 100%)
_DETERMINISM_PENALTY = {
    "deterministic": 0.0,   # completely penalised
    "stochastic": 0.50,     # partial penalty
    "environmental": 0.75,  # mostly forgiven (not your code)
    "unknown": 0.60,        # unknown is moderately penalised
}


@dataclass
class ProjectReliabilitySummary:
    project_id: str
    agent_count: int
    avg_health_score: float
    worst_agent: str | None
    best_agent: str | None
    total_deterministic_failures: int
    total_stochastic_failures: int
    score_date: date


# ── Public API ────────────────────────────────────────────────────────────────


def compute_project_scores(
    db: Session,
    *,
    project_id: str,
    as_of_date: date | None = None,
) -> list[AgentReliabilityScore]:
    """Compute and upsert daily reliability scores for every agent.

    Idempotent: re-running for the same date replaces the row.
    """
    today = as_of_date or datetime.now(timezone.utc).date()
    agents = _list_active_agents(db, project_id=project_id, as_of_date=today)
    if not agents:
        return []

    project_median_cost = _project_median_cost(db, project_id=project_id, as_of_date=today)
    rows: list[AgentReliabilityScore] = []

    for agent_name in agents:
        score = _compute_agent_score(
            db,
            project_id=project_id,
            agent_name=agent_name,
            as_of_date=today,
            project_median_cost=project_median_cost,
        )
        _upsert_score(db, score)
        rows.append(score)

    db.commit()
    return rows


def get_leaderboard(
    db: Session,
    *,
    project_id: str,
    limit: int = 50,
) -> list[AgentReliabilityScore]:
    """Return the most recent score per agent, sorted by health_score desc."""
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
        .order_by(AgentReliabilityScore.health_score.desc())
        .limit(limit)
    )
    return list(db.execute(q).scalars().all())


def get_agent_history(
    db: Session,
    *,
    project_id: str,
    agent_name: str,
    days: int = 30,
) -> list[AgentReliabilityScore]:
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    q = (
        select(AgentReliabilityScore)
        .where(
            AgentReliabilityScore.project_id == project_id,
            AgentReliabilityScore.agent_name == agent_name,
            AgentReliabilityScore.score_date >= since,
        )
        .order_by(AgentReliabilityScore.score_date.asc())
    )
    return list(db.execute(q).scalars().all())


def get_project_summary(
    db: Session,
    *,
    project_id: str,
) -> ProjectReliabilitySummary:
    rows = get_leaderboard(db, project_id=project_id)
    if not rows:
        return ProjectReliabilitySummary(
            project_id=project_id,
            agent_count=0,
            avg_health_score=0.0,
            worst_agent=None,
            best_agent=None,
            total_deterministic_failures=0,
            total_stochastic_failures=0,
            score_date=datetime.now(timezone.utc).date(),
        )
    scores = [float(r.health_score) for r in rows]
    avg = sum(scores) / len(scores)
    det_total = 0
    sto_total = 0
    for r in rows:
        if r.determinism_breakdown_json:
            try:
                bd = json.loads(r.determinism_breakdown_json)
                det_total += bd.get("deterministic", 0)
                sto_total += bd.get("stochastic", 0)
            except Exception:
                pass
    return ProjectReliabilitySummary(
        project_id=project_id,
        agent_count=len(rows),
        avg_health_score=round(avg, 2),
        worst_agent=rows[-1].agent_name if rows else None,
        best_agent=rows[0].agent_name if rows else None,
        total_deterministic_failures=det_total,
        total_stochastic_failures=sto_total,
        score_date=rows[0].score_date,
    )


# ── Internal computation ──────────────────────────────────────────────────────


def _compute_agent_score(
    db: Session,
    *,
    project_id: str,
    agent_name: str,
    as_of_date: date,
    project_median_cost: float,
) -> AgentReliabilityScore:
    window_end = datetime.combine(as_of_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    window_start = window_end - timedelta(days=WINDOW_DAYS)
    prev_window_start = window_start - timedelta(days=WINDOW_DAYS)

    # ── Fetch call stats ───────────────────────────────────────────────────────
    calls_q = db.execute(
        select(Call.status, Call.cost_total, Call.latency_ms).where(
            Call.project_id == project_id,
            Call.agent_name == agent_name,
            Call.created_at >= window_start,
            Call.created_at <= window_end,
        )
    ).all()

    call_count = len(calls_q)
    if call_count == 0:
        return _zero_score(project_id, agent_name, as_of_date)

    fail_count = sum(
        1 for c in calls_q
        if c.status in FAIL_STATUSES or c.status not in {"completed", "success", "ok"}
    )
    fail_rate = fail_count / call_count
    costs = [float(c.cost_total or 0) for c in calls_q]
    avg_cost = sum(costs) / len(costs)
    latencies = sorted([float(c.latency_ms) for c in calls_q if c.latency_ms is not None])
    p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else None

    # ── Previous window fail rate (for trend) ─────────────────────────────────
    prev_calls = db.execute(
        select(Call.status).where(
            Call.project_id == project_id,
            Call.agent_name == agent_name,
            Call.created_at >= prev_window_start,
            Call.created_at < window_start,
        )
    ).all()
    prev_fail_rate: float | None = None
    if prev_calls:
        prev_fail_count = sum(
            1 for c in prev_calls
            if c.status in FAIL_STATUSES or c.status not in {"completed", "success", "ok"}
        )
        prev_fail_rate = prev_fail_count / len(prev_calls)

    # ── Ablation determinism breakdown ────────────────────────────────────────
    ablation_rows = db.execute(
        select(AblationJob.determinism_class)
        .where(
            AblationJob.project_id == project_id,
            AblationJob.status == "done",
            AblationJob.created_at >= window_start,
            AblationJob.created_at <= window_end,
        )
        .join(
            Call,
            (Call.id == AblationJob.call_id) & (Call.agent_name == agent_name),
        )
    ).all()

    breakdown = {"deterministic": 0, "stochastic": 0, "environmental": 0, "unknown": 0}
    for row in ablation_rows:
        cls = row.determinism_class or "unknown"
        if cls in breakdown:
            breakdown[cls] += 1

    # Top failure axis
    top_axis = _get_top_failure_axis(db, project_id=project_id, agent_name=agent_name, since=window_start, until=window_end)

    # ── Score components ───────────────────────────────────────────────────────
    fail_rate_score = 100.0 * (1.0 - fail_rate)

    # Cost efficiency: ratio vs. project median; clamp [0, 100]
    if project_median_cost > 0 and avg_cost > 0:
        ratio = project_median_cost / avg_cost  # > 1 = cheaper than median
        cost_eff_score = min(100.0, 50.0 * ratio)
    else:
        cost_eff_score = 50.0  # neutral when no cost data

    # Determinism score: weighted average of class penalties × 100
    total_ablation = sum(breakdown.values())
    if total_ablation > 0:
        det_score = sum(
            breakdown[cls] * _DETERMINISM_PENALTY[cls]
            for cls in breakdown
        ) / total_ablation * 100.0
    else:
        det_score = 75.0  # assume mostly environmental when unknown

    # Regression trend: bonus for improvement, penalty for regression
    if prev_fail_rate is not None:
        delta = prev_fail_rate - fail_rate  # positive = getting better
        trend_score = 50.0 + (delta * 200.0)  # ±50 points for ±25% change
        trend_score = max(0.0, min(100.0, trend_score))
    else:
        trend_score = 50.0  # neutral baseline

    health_score = (
        _W_FAIL_RATE * fail_rate_score
        + _W_COST_EFF * cost_eff_score
        + _W_DETERMINISM * det_score
        + _W_TREND * trend_score
    )
    health_score = max(0.0, min(100.0, round(health_score, 2)))

    return AgentReliabilityScore(
        id=str(uuid4()),
        project_id=project_id,
        agent_name=agent_name,
        score_date=as_of_date,
        health_score=health_score,
        fail_rate=round(fail_rate, 5),
        fail_rate_score=round(fail_rate_score, 2),
        cost_efficiency_score=round(cost_eff_score, 2),
        determinism_score=round(det_score, 2),
        regression_trend_score=round(trend_score, 2),
        call_count=call_count,
        avg_cost_usd=round(avg_cost, 8),
        p95_latency_ms=round(p95_latency, 2) if p95_latency else None,
        prev_week_fail_rate=round(prev_fail_rate, 5) if prev_fail_rate is not None else None,
        determinism_breakdown_json=json.dumps(breakdown, separators=(",", ":")),
        top_failure_axis=top_axis,
    )


def _get_top_failure_axis(
    db: Session,
    *,
    project_id: str,
    agent_name: str,
    since: datetime,
    until: datetime,
) -> str | None:
    rows = db.execute(
        select(AblationAxis.axis_type)
        .join(AblationJob, AblationJob.id == AblationAxis.ablation_job_id)
        .join(Call, (Call.id == AblationJob.call_id) & (Call.agent_name == agent_name))
        .where(
            AblationAxis.project_id == project_id,
            AblationJob.status == "done",
            AblationJob.created_at >= since,
            AblationJob.created_at <= until,
            AblationAxis.confidence >= 0.5,
        )
    ).all()
    if not rows:
        return None
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.axis_type] = counts.get(r.axis_type, 0) + 1
    return max(counts, key=lambda k: counts[k])


def _list_active_agents(
    db: Session,
    *,
    project_id: str,
    as_of_date: date,
) -> list[str]:
    since = datetime.combine(as_of_date, datetime.min.time()).replace(tzinfo=timezone.utc) - timedelta(days=WINDOW_DAYS)
    rows = db.execute(
        select(Call.agent_name)
        .where(
            Call.project_id == project_id,
            Call.agent_name.isnot(None),
            Call.created_at >= since,
        )
        .group_by(Call.agent_name)
    ).all()
    return [r.agent_name for r in rows]


def _project_median_cost(
    db: Session,
    *,
    project_id: str,
    as_of_date: date,
) -> float:
    since = datetime.combine(as_of_date, datetime.min.time()).replace(tzinfo=timezone.utc) - timedelta(days=WINDOW_DAYS)
    rows = db.execute(
        select(func.avg(Call.cost_total)).where(
            Call.project_id == project_id,
            Call.created_at >= since,
            Call.cost_total > 0,
        )
    ).scalar()
    return float(rows or 0.0)


def _zero_score(project_id: str, agent_name: str, score_date: date) -> AgentReliabilityScore:
    return AgentReliabilityScore(
        id=str(uuid4()),
        project_id=project_id,
        agent_name=agent_name,
        score_date=score_date,
        health_score=0.0,
        fail_rate=0.0,
        fail_rate_score=0.0,
        cost_efficiency_score=0.0,
        determinism_score=0.0,
        regression_trend_score=0.0,
        call_count=0,
        avg_cost_usd=0.0,
    )


def _upsert_score(db: Session, score: AgentReliabilityScore) -> None:
    existing = db.execute(
        select(AgentReliabilityScore).where(
            AgentReliabilityScore.project_id == score.project_id,
            AgentReliabilityScore.agent_name == score.agent_name,
            AgentReliabilityScore.score_date == score.score_date,
        )
    ).scalar_one_or_none()

    if existing:
        for field in (
            "health_score", "fail_rate", "fail_rate_score", "cost_efficiency_score",
            "determinism_score", "regression_trend_score", "call_count", "avg_cost_usd",
            "p95_latency_ms", "prev_week_fail_rate", "determinism_breakdown_json",
            "top_failure_axis", "computed_at",
        ):
            setattr(existing, field, getattr(score, field, None))
    else:
        score.computed_at = datetime.now(timezone.utc)
        db.add(score)
