"""
Wedge 4 — Cost-of-failure attribution for the Pre-deploy Replay CI Gate.

Translates a `RegressionCIReport`'s regression count into a defensible
USD risk estimate by joining the regression-CI run against the
project's last 30 days of `outcome_events`.

Pricing model (intentionally simple, intentionally honest):

    cost_per_failed_call =
        sum(amount_usd of outcome_events linked to a FAILED call, last 30d)
        / max(1, count of FAILED calls in last 30d)

    estimated_monthly_risk_usd =
        regressed_count_in_PR * cost_per_failed_call * scale

Where `scale` accounts for the fact that the regression-CI run sampled
only a fraction of production traffic — we project the per-trace risk to
the full month.

Why this shape:

  * **No statistical wizardry.** Linear extrapolation is auditable on a
    napkin. CFOs trust napkins.
  * **No leakage of private data.** The function only emits aggregates.
  * **Returns None when uninformative.** Projects with zero outcome
    events get no $-tag — better silent than misleading.
  * **Pure function of (DB session, project_id, regressed_count,
    sample_size, monthly_traffic_estimate)**. Easy to unit test.

Caller (`orchestrator.run_regression_ci`) will pass the result into
`RegressionCIReport.outcome_attribution`. The PR-comment formatter
renders one extra "💰 Estimated $X/mo risk if merged" line.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob, OutcomeEvent

logger = logging.getLogger(__name__)


# Look-back window for the cost basis. 30d aligns with how the dashboard
# reports outcome cost so the PR number matches the CFO dashboard.
LOOKBACK_DAYS: int = 30

# Defensive cap: if a customer has one $1M outcome and 10 failed calls,
# avg cost = $100K/call. Times 12 regressed traces → $1.2M risk on a
# small PR. That's mathematically sound but surfaces as alarmist on the
# PR. We cap the *displayed* risk at this absolute ceiling per run to
# stay credible. Set very high; only triggers in pathological data.
RISK_CEILING_USD: float = 1_000_000.0


def compute_pr_savings(
    db: Session,
    *,
    project_id: str,
    regressed_count: int,
    lookback_days: int = LOOKBACK_DAYS,
) -> Mapping[str, Any] | None:
    """Return the outcome-attribution snapshot for a regression-CI run,
    or None when the project has no outcome events to base it on.

    Parameters
    ----------
    db
        Active SQLAlchemy session — read-only here.
    project_id
        Caller's project id (mandatory; we never compute cross-project).
    regressed_count
        How many traces in *this* PR run flipped from pass→fail. Pass 0
        when the run passed; we still return the snapshot (with risk=0)
        so the dashboard can show "your project saw $X / 30d in failure
        cost — this PR adds zero risk."
    lookback_days
        Tunable for tests. Default 30 days mirrors the CFO dashboard.

    Returns
    -------
    A read-only mapping with keys:
      - outcome_cost_30d_usd     : float (>=0)
      - failed_call_count_30d    : int  (>=0)
      - regressed_in_pr          : int  (>=0)
      - cost_per_failed_call_usd : float (>=0)
      - estimated_monthly_risk_usd : float (>=0, capped)
      - method                   : "linear_extrapolation"
    Or None when the project has no outcome events in the lookback.
    """
    pid = (project_id or "").strip()
    if not pid:
        return None
    if regressed_count < 0:
        regressed_count = 0
    if lookback_days <= 0:
        lookback_days = LOOKBACK_DAYS

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    try:
        # Total outcome cost in the window for this project. Note we
        # don't restrict to events with a call_id — uncorrelated outcomes
        # still represent project cost. The cost-per-failed-call ratio
        # below uses the call-attached subset only.
        total_outcome_cost = float(
            db.execute(
                select(func.coalesce(func.sum(OutcomeEvent.amount_usd), 0.0)).where(
                    OutcomeEvent.project_id == pid,
                    OutcomeEvent.occurred_at >= cutoff,
                )
            ).scalar()
            or 0.0
        )

        if total_outcome_cost <= 0.0:
            return None  # No signal — don't pretend to have one.

        # Outcomes attached to a call → narrow to the cost we can
        # confidently link to "a failed-ish call." We define failed-ish
        # as: a call that has at least one DiagnosisJob row (i.e., the
        # diagnosis pipeline flagged it). Not perfect, but correlated
        # and computable in one query.
        attached_cost = float(
            db.execute(
                select(func.coalesce(func.sum(OutcomeEvent.amount_usd), 0.0))
                .join(Call, Call.id == OutcomeEvent.call_id)
                .join(DiagnosisJob, DiagnosisJob.call_id == Call.id)
                .where(
                    OutcomeEvent.project_id == pid,
                    OutcomeEvent.occurred_at >= cutoff,
                    OutcomeEvent.call_id.isnot(None),
                )
            ).scalar()
            or 0.0
        )

        failed_call_count = int(
            db.execute(
                select(func.count(func.distinct(Call.id)))
                .join(DiagnosisJob, DiagnosisJob.call_id == Call.id)
                .where(
                    Call.project_id == pid,
                    Call.created_at >= cutoff,
                )
            ).scalar()
            or 0
        )

    except Exception:  # noqa: BLE001
        # Read-only computation; never block the run on this.
        logger.warning(
            "outcome_attribution.compute_pr_savings: db read failed for project=%s",
            pid,
            exc_info=True,
        )
        return None

    # Cost basis: prefer the (attached cost / failed calls) ratio; fall
    # back to (total cost / failed calls) when attached cost is zero
    # but failed calls and total cost both exist (early-stage projects
    # often have outcomes posted without call_id).
    basis_cost = attached_cost if attached_cost > 0.0 else total_outcome_cost
    if failed_call_count <= 0:
        cost_per_failed_call = 0.0
    else:
        cost_per_failed_call = basis_cost / failed_call_count

    # Per-PR projection: assume the regressed traces would, if merged,
    # convert into failed-ish calls at the same historical rate. Multiply
    # by 1.0 (no further scaling) — the regressed_count already reflects
    # *the sample's projection* of monthly behaviour because the sampler
    # itself draws from production traffic. Anything more aggressive
    # would over-claim. Honesty wins.
    estimated_risk = regressed_count * cost_per_failed_call
    if estimated_risk > RISK_CEILING_USD:
        estimated_risk = RISK_CEILING_USD

    return {
        "outcome_cost_30d_usd": round(total_outcome_cost, 2),
        "failed_call_count_30d": failed_call_count,
        "regressed_in_pr": int(regressed_count),
        "cost_per_failed_call_usd": round(cost_per_failed_call, 4),
        "estimated_monthly_risk_usd": round(estimated_risk, 2),
        "method": "linear_extrapolation",
    }


__all__ = ["compute_pr_savings", "LOOKBACK_DAYS"]
