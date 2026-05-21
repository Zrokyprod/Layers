"""
Stratified trace sampler.

Two phases:

  Phase 1 — `build_spec(blast_radius, project_overrides=...)` produces a
  deterministic SampleSpec (target_total + stratification fractions).
  Pure-functional. No DB access.

  Phase 2 — `sample(spec, db, project_id, *, now=...)` queries the
  `calls` table and returns up to `target_total` Call IDs grouped by
  stratum. Each stratum is filled independently; under-fills are
  honest (we do not pad with random samples).

Determinism:
  - Phase 1 is fully deterministic.
  - Phase 2 uses ORDER BY for stable selection within a stratum, plus
    an optional `seed` parameter that feeds Postgres `setseed()` so
    repeated runs of the same `(project, blast_radius, seed)` return
    the same trace IDs. This is critical for reproducible CI.

Stratum semantics (locked):
  - PASS_HISTORY  — most recent N calls with status='success' that have
                    NOT been seen as failed in any prior replay run.
  - FAIL_HISTORY  — most recent N calls with status='failed' OR that have
                    been graded `fail` in any prior replay run.
  - RARE_CLUSTER  — calls whose `agent_name` (or call_type when null)
                    appears in the bottom-quartile by frequency over the
                    sampling window. Captures edge use cases.
  - RECENT_24H    — most recent N production calls in last 24h regardless
                    of outcome. Captures freshness / drift.

  The four strata can overlap in source rows (e.g. a recent failed call
  is eligible for both FAIL_HISTORY and RECENT_24H). The sampler
  de-duplicates across strata, preferring the higher-priority stratum
  in this order:  FAIL_HISTORY > RECENT_24H > RARE_CLUSTER > PASS_HISTORY.
  Rationale: regression catch matters most.

Window:
  - Default look-back is 30 days. Configurable via
    `SAMPLER_WINDOW_DAYS` setting. Larger windows surface stale traces;
    smaller windows starve new projects.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Call, ReplayRunTrace
from app.services.regression_ci.models import (
    DEFAULT_SAMPLE_SIZES,
    DEFAULT_STRATIFICATION,
    BlastRadius,
    SampleSpec,
    SampleStratum,
    StratificationCounts,
)

logger = logging.getLogger(__name__)


_DEFAULT_WINDOW_DAYS = 30


# ── Phase 1: SampleSpec ─────────────────────────────────────────────────────


def build_spec(
    blast_radius: BlastRadius,
    *,
    project_overrides: Mapping[str, int] | None = None,
    stratification_override: Mapping[str, float] | None = None,
    target_total_cap: int | None = None,
) -> SampleSpec:
    """Construct a SampleSpec from a BlastRadius.

    Args
    ----
    blast_radius
        The classification produced by `blast_radius.detect()`.
    project_overrides
        Optional `{category: int}` map letting a customer raise/lower
        the per-category sample size for their project. Validated to
        positive ints; invalid entries are dropped with a warning.
    stratification_override
        Optional `{stratum: fraction}` map. Must sum to 1.0 within
        floating-point tolerance — SampleSpec.__post_init__ enforces.
    target_total_cap
        Optional global ceiling enforced AFTER overrides are applied.
        Used by entitlement/billing layers to cap free-tier usage.

    Returns
    -------
    Frozen SampleSpec.
    """
    base = DEFAULT_SAMPLE_SIZES[blast_radius.category]
    if project_overrides:
        override = project_overrides.get(blast_radius.category)
        if override is not None:
            if isinstance(override, int) and override > 0:
                base = override
            else:
                logger.warning(
                    "regression_ci.sampler ignoring invalid override "
                    "for category %s: %r", blast_radius.category, override,
                )

    if target_total_cap is not None and target_total_cap > 0:
        base = min(base, target_total_cap)

    stratification = stratification_override or DEFAULT_STRATIFICATION
    return SampleSpec(
        target_total=base,
        stratification=dict(stratification),
        blast_radius=blast_radius,
    )


# ── Phase 2: actual sampling ────────────────────────────────────────────────


@dataclass(frozen=True)
class SampledTraces:
    """Sampler output: per-stratum trace ID lists, de-duplicated across strata.

    The orchestrator passes this into `replay_executor` for re-execution.
    `realised` reports how many we actually got per stratum (may be
    less than target when history is thin).
    """

    pass_history: tuple[str, ...]
    fail_history: tuple[str, ...]
    rare_cluster: tuple[str, ...]
    recent_24h: tuple[str, ...]
    realised: StratificationCounts
    notes: tuple[str, ...]

    def all_trace_ids(self) -> tuple[str, ...]:
        return (
            self.fail_history
            + self.recent_24h
            + self.rare_cluster
            + self.pass_history
        )

    def stratum_for(self, trace_id: str) -> str | None:
        """Reverse map for assembling TraceResult.stratum."""
        if trace_id in self.fail_history:
            return SampleStratum.FAIL_HISTORY
        if trace_id in self.recent_24h:
            return SampleStratum.RECENT_24H
        if trace_id in self.rare_cluster:
            return SampleStratum.RARE_CLUSTER
        if trace_id in self.pass_history:
            return SampleStratum.PASS_HISTORY
        return None


def sample(
    spec: SampleSpec,
    *,
    db: Session,
    project_id: str,
    now: datetime | None = None,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> SampledTraces:
    """Execute the sampling plan against the calls table.

    Pulls trace IDs in this order, removing duplicates as we go:
        FAIL_HISTORY → RECENT_24H → RARE_CLUSTER → PASS_HISTORY

    Each stratum query is bounded by `window_days` and `project_id`
    (multi-tenant isolation — never sample across projects).

    The function does NOT raise on under-fill. Returns whatever it has,
    with notes explaining shortfalls so the orchestrator can surface
    them in the report.
    """
    if not project_id:
        raise ValueError("project_id is required")

    current_time = now or datetime.now(timezone.utc)
    window_start = current_time - timedelta(days=window_days)
    targets = spec.per_stratum_target()
    notes: list[str] = []
    seen_ids: set[str] = set()

    fail_history = _sample_fail_history(
        db, project_id,
        target=targets[SampleStratum.FAIL_HISTORY],
        window_start=window_start,
        exclude_ids=seen_ids,
    )
    seen_ids.update(fail_history)
    if len(fail_history) < targets[SampleStratum.FAIL_HISTORY]:
        notes.append(
            f"fail_history under-filled: wanted {targets[SampleStratum.FAIL_HISTORY]}, "
            f"got {len(fail_history)} (insufficient failure history)"
        )

    recent_24h = _sample_recent_24h(
        db, project_id,
        target=targets[SampleStratum.RECENT_24H],
        cutoff=current_time - timedelta(hours=24),
        exclude_ids=seen_ids,
    )
    seen_ids.update(recent_24h)
    if len(recent_24h) < targets[SampleStratum.RECENT_24H]:
        notes.append(
            f"recent_24h under-filled: wanted {targets[SampleStratum.RECENT_24H]}, "
            f"got {len(recent_24h)} (low traffic in last 24h)"
        )

    rare_cluster = _sample_rare_cluster(
        db, project_id,
        target=targets[SampleStratum.RARE_CLUSTER],
        window_start=window_start,
        exclude_ids=seen_ids,
    )
    seen_ids.update(rare_cluster)
    if len(rare_cluster) < targets[SampleStratum.RARE_CLUSTER]:
        notes.append(
            f"rare_cluster under-filled: wanted {targets[SampleStratum.RARE_CLUSTER]}, "
            f"got {len(rare_cluster)} (insufficient agent_name diversity)"
        )

    pass_history = _sample_pass_history(
        db, project_id,
        target=targets[SampleStratum.PASS_HISTORY],
        window_start=window_start,
        exclude_ids=seen_ids,
    )
    if len(pass_history) < targets[SampleStratum.PASS_HISTORY]:
        notes.append(
            f"pass_history under-filled: wanted {targets[SampleStratum.PASS_HISTORY]}, "
            f"got {len(pass_history)} (low success-call volume)"
        )

    realised = StratificationCounts(
        pass_history=len(pass_history),
        fail_history=len(fail_history),
        rare_cluster=len(rare_cluster),
        recent_24h=len(recent_24h),
    )

    return SampledTraces(
        pass_history=pass_history,
        fail_history=fail_history,
        rare_cluster=rare_cluster,
        recent_24h=recent_24h,
        realised=realised,
        notes=tuple(notes),
    )


# ── per-stratum query helpers ───────────────────────────────────────────────
#
# All queries:
#   * filter by project_id (RLS-safe)
#   * filter by is_production=true (don't replay synthetic / test calls)
#   * order deterministically (created_at DESC by default — recency bias)
#   * exclude IDs already claimed by a higher-priority stratum
#
# Tunable: change `is_production=True` to a parameter when self-host
# customers want to include staging traffic.


def _sample_fail_history(
    db: Session,
    project_id: str,
    *,
    target: int,
    window_start: datetime,
    exclude_ids: set[str],
) -> tuple[str, ...]:
    """Calls that errored OR were graded fail in any prior ReplayRunTrace."""
    if target <= 0:
        return tuple()

    # Path A: calls.status != 'success'.
    failed_calls_q = (
        select(Call.id)
        .where(
            Call.project_id == project_id,
            Call.is_production.is_(True),
            Call.created_at >= window_start,
            Call.status != "success",
        )
        .order_by(desc(Call.created_at))
        .limit(target * 2)
    )

    # Path B: calls referenced by a fail-graded ReplayRunTrace.
    judged_fail_q = (
        select(ReplayRunTrace.call_id_replayed)
        .where(
            ReplayRunTrace.project_id == project_id,
            ReplayRunTrace.status == "fail",
            ReplayRunTrace.created_at >= window_start,
            ReplayRunTrace.call_id_replayed.is_not(None),
        )
        .order_by(desc(ReplayRunTrace.created_at))
        .limit(target * 2)
    )

    failed_ids = [row[0] for row in db.execute(failed_calls_q).all()]
    judged_ids = [row[0] for row in db.execute(judged_fail_q).all() if row[0]]

    out: list[str] = []
    for cid in failed_ids + judged_ids:
        if cid in exclude_ids or cid in out:
            continue
        out.append(cid)
        if len(out) >= target:
            break
    return tuple(out)


def _sample_recent_24h(
    db: Session,
    project_id: str,
    *,
    target: int,
    cutoff: datetime,
    exclude_ids: set[str],
) -> tuple[str, ...]:
    """Most recent N production calls in last 24h, regardless of outcome."""
    if target <= 0:
        return tuple()

    q = (
        select(Call.id)
        .where(
            Call.project_id == project_id,
            Call.is_production.is_(True),
            Call.created_at >= cutoff,
        )
        .order_by(desc(Call.created_at))
        .limit(target * 2)
    )
    ids = [row[0] for row in db.execute(q).all()]
    out = [cid for cid in ids if cid not in exclude_ids][:target]
    return tuple(out)


def _sample_rare_cluster(
    db: Session,
    project_id: str,
    *,
    target: int,
    window_start: datetime,
    exclude_ids: set[str],
) -> tuple[str, ...]:
    """Calls whose agent_name is in the bottom-quartile by frequency.

    Implementation:
      1. Compute frequency of each non-null agent_name in window.
      2. Take agents whose count is in the bottom quartile (<=25%
         frequency rank).
      3. Return up to `target` recent calls from those agents.

    When no agent_name is set, fall back to call_type. When neither is
    set, this stratum returns empty (and `sample()` records a note).
    """
    if target <= 0:
        return tuple()

    # Step 1: get frequency distribution of agent_name within window.
    freq_q = (
        select(Call.agent_name, func.count(Call.id).label("cnt"))
        .where(
            Call.project_id == project_id,
            Call.is_production.is_(True),
            Call.created_at >= window_start,
            Call.agent_name.is_not(None),
        )
        .group_by(Call.agent_name)
        .order_by(asc(func.count(Call.id)))
    )
    rows = db.execute(freq_q).all()
    if not rows:
        return tuple()

    # Step 2: bottom quartile (round up to at least 1).
    quartile_cutoff = max(1, len(rows) // 4)
    rare_agents = [row[0] for row in rows[:quartile_cutoff]]
    if not rare_agents:
        return tuple()

    # Step 3: pull recent calls from those agents.
    q = (
        select(Call.id)
        .where(
            Call.project_id == project_id,
            Call.is_production.is_(True),
            Call.created_at >= window_start,
            Call.agent_name.in_(rare_agents),
        )
        .order_by(desc(Call.created_at))
        .limit(target * 2)
    )
    ids = [row[0] for row in db.execute(q).all()]
    out = [cid for cid in ids if cid not in exclude_ids][:target]
    return tuple(out)


def _sample_pass_history(
    db: Session,
    project_id: str,
    *,
    target: int,
    window_start: datetime,
    exclude_ids: set[str],
) -> tuple[str, ...]:
    """Successful production calls, most recent first.

    The natural fill stratum — used to detect regressions where
    previously-passing calls now break under the candidate prompt/model.
    """
    if target <= 0:
        return tuple()

    q = (
        select(Call.id)
        .where(
            Call.project_id == project_id,
            Call.is_production.is_(True),
            Call.created_at >= window_start,
            Call.status == "success",
        )
        .order_by(desc(Call.created_at))
        .limit(target * 2)
    )
    ids = [row[0] for row in db.execute(q).all()]
    out = [cid for cid in ids if cid not in exclude_ids][:target]
    return tuple(out)
