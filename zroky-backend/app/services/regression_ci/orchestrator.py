"""
Top-level regression-CI pipeline.

`run_regression_ci()` is the single public entry point. It:

  1. Resolves BlastRadius     (blast_radius.detect)
  2. Builds SampleSpec        (sampler.build_spec)
  3. Samples traces           (sampler.sample → list of Call ids)
  4. For each sampled Call:
        a. Fetches the source Call row
        b. Extracts baseline output (recorded response)
        c. Re-executes against PR's candidate prompt/model via
           the injected `actual_output_resolver` (production uses
           `make_live_llm_resolver` from replay_executor — Option B).
        d. Scores the diff (diff_metric.score)
  5. Clusters regressed inputs (cluster.cluster_regressions)
  6. Aggregates into a frozen RegressionCIReport (schema v1)
  7. Persists summary_json to ReplayRun row for the dashboard

Design choices:

  - **Synchronous core, async-friendly entry.** The pipeline is a
    plain function so it can run inside a Celery task, a FastAPI
    BackgroundTask, or a unit test. No event loop assumptions.
  - **Hard failure isolation.** A single trace's provider error never
    poisons the whole run. error_count / error_rate aggregate the
    damage; verdict goes to `error` only when error_rate >= the
    configured threshold (default 5%).
  - **Hard budget cap.** Reuses `ReplayBudgetTracker` — the live
    resolver returns `reason="budget_exceeded"` past the cap and
    subsequent traces short-circuit to error. No silent overruns.
  - **Truncation everywhere.** baseline/candidate outputs and inputs
    are truncated to ~2 KB / ~4 KB before storage so summary_json
    doesn't bloat past the Postgres TOAST threshold for typical runs.
  - **All injectable.** Embedder, judge, resolver, sampler, and clock
    are all parameters. Tests pass deterministic stubs.

This module IS the surface the API route and Celery task call.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, ReplayRun, ReplayRunTrace
from app.services.regression_ci import (
    blast_radius as br_mod,
    cluster as cluster_mod,
    diff_metric,
    cost_of_failure as cost_of_failure_mod,
    pr_comment,
    sampler as sampler_mod,
)
from app.services.regression_ci.models import (
    SCHEMA_VERSION,
    BlastRadius,
    DiffVerdict,
    RegressionCIReport,
    SampleSpec,
    StratificationCounts,
    TraceResult,
)

logger = logging.getLogger(__name__)


# ── defaults / tunables ─────────────────────────────────────────────────────

DEFAULT_REGRESSION_THRESHOLD: float = 0.02   # 2% regressed → fail
ERROR_RATE_ERROR_THRESHOLD: float = 0.05     # 5%+ errors → run verdict = "error"

INPUT_TRUNC_CHARS: int = 4000
OUTPUT_TRUNC_CHARS: int = 2000


# ── injection points ────────────────────────────────────────────────────────


class _Embedder(Protocol):
    def generate_embedding(self, text: str) -> list[float] | None: ...


class _Judge(Protocol):
    def evaluate(self, actual: str, expected: str, *, context: Mapping[str, Any] | None = None) -> Any: ...


# Resolver signature: (Call) -> (candidate_output, error_message, cost_usd, latency_ms).
# We adapt `make_live_llm_resolver` from replay_executor at the call site.
CandidateResolver = Callable[[Call], "CandidateOutput"]


@dataclass(frozen=True)
class CandidateOutput:
    """What a resolver returns for one re-executed call."""

    text: str | None
    error_message: str | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0


# ── orchestrator inputs ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class RegressionCIInputs:
    """All inputs the orchestrator needs. Built by the API route or
    Celery task. Kept frozen so a single value passes through the pipeline
    without accidental mutation."""

    project_id: str
    git_sha: str | None
    pr_body: str | None
    zroky_yaml: str | None
    changed_files: Sequence[br_mod.ChangedFile]
    threshold: float = DEFAULT_REGRESSION_THRESHOLD
    target_total_cap: int | None = None       # entitlement cap (e.g. free tier)
    sample_window_days: int = 30


# ── public entry point ──────────────────────────────────────────────────────


def run_regression_ci(
    inputs: RegressionCIInputs,
    *,
    db: Session,
    candidate_resolver: CandidateResolver,
    embedder: _Embedder | None = None,
    judge: _Judge | None = None,
    operator_override: BlastRadius | None = None,
    project_overrides: Mapping[str, int] | None = None,
    stratification_override: Mapping[str, float] | None = None,
    now: datetime | None = None,
    persist_run: bool = True,
    run_id_override: str | None = None,
) -> RegressionCIReport:
    """Run the full Wedge-1 pipeline and return a frozen report.

    Parameters
    ----------
    inputs
        Frozen pipeline inputs (project, git sha, PR context, threshold).
    db
        SQLAlchemy session for sampling + persistence.
    candidate_resolver
        Re-executes a single Call under the candidate prompt/model.
        Production passes an adapter around `make_live_llm_resolver`;
        tests pass a deterministic stub.
    embedder
        Optional embedding service (Tier 2 of diff_metric + clustering).
        When None, the pipeline degrades gracefully — verdicts become
        INCONCLUSIVE for borderline cases and clustering collapses to
        a single bucket.
    judge
        Optional LLM judge (Tier 3 of diff_metric).
    operator_override
        Optional manual blast-radius override from the dashboard.
    project_overrides
        Optional per-project sample-size overrides.
    stratification_override
        Optional per-project stratum-mix overrides.
    now
        Injectable clock for deterministic tests.
    persist_run
        When True, writes ReplayRun + ReplayRunTrace rows and stamps
        summary_json. When False (used by some tests), the report is
        built in memory only.
    run_id_override
        When provided AND `persist_run=True`, the orchestrator reuses
        the existing ReplayRun row (created upstream by the API route
        in status='queued') instead of creating a new one. This is the
        async-dispatch path: route creates the row + commits, returns
        202 immediately, then a background task calls this function
        with the same run_id so polling clients see a single coherent
        row. Raises ValueError if the row doesn't exist for this tenant.
    """
    start = time.monotonic()
    current_time = now or datetime.now(timezone.utc)
    run_id = run_id_override or str(uuid4())

    # Step 1 — Blast radius.
    blast_radius = br_mod.detect(
        changed_files=inputs.changed_files,
        pr_body=inputs.pr_body,
        zroky_yaml=inputs.zroky_yaml,
        operator_override=operator_override,
    )

    # Step 2 — SampleSpec.
    spec = sampler_mod.build_spec(
        blast_radius,
        project_overrides=project_overrides,
        stratification_override=stratification_override,
        target_total_cap=inputs.target_total_cap,
    )

    # Step 3 — Sample traces.
    sampled = sampler_mod.sample(
        spec,
        db=db,
        project_id=inputs.project_id,
        now=current_time,
        window_days=inputs.sample_window_days,
    )

    notes: list[str] = list(sampled.notes)

    # Optional ReplayRun row (created up-front so the dashboard can
    # show "running" status while the loop progresses).
    replay_run: ReplayRun | None = None
    if persist_run:
        if run_id_override:
            # Async-dispatch path: route already created the row in
            # status='queued'. Transition it to 'running' and reuse.
            replay_run = db.execute(
                select(ReplayRun).where(
                    ReplayRun.id == run_id_override,
                    ReplayRun.project_id == inputs.project_id,
                )
            ).scalar_one_or_none()
            if replay_run is None:
                raise ValueError(
                    f"run_id_override {run_id_override!r} not found "
                    f"for project {inputs.project_id!r}"
                )
            replay_run.status = "running"
            replay_run.started_at = current_time
        else:
            replay_run = ReplayRun(
                id=run_id,
                project_id=inputs.project_id,
                golden_set_id=_synthetic_golden_set_id(inputs.project_id),
                trigger="github",
                git_sha=inputs.git_sha,
                status="running",
                started_at=current_time,
                summary_json=None,
            )
            db.add(replay_run)
        db.flush()

    # Step 4 — Re-execute each sampled trace.
    trace_results: list[TraceResult] = []
    aggregate_cost = 0.0
    judge_used_count = 0

    for trace_id in sampled.all_trace_ids():
        call = db.execute(
            select(Call).where(
                Call.id == trace_id,
                Call.project_id == inputs.project_id,
            )
        ).scalar_one_or_none()

        if call is None:
            # Trace vanished between sampling and execution (race).
            # Skip with an explicit note rather than synthesize an error row.
            notes.append(f"trace {trace_id} disappeared between sampling and replay")
            continue

        baseline_output = _truncate(_extract_baseline_output(call), OUTPUT_TRUNC_CHARS)
        prompt_context = _truncate(_extract_prompt_context(call), INPUT_TRUNC_CHARS)

        try:
            candidate = candidate_resolver(call)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "regression_ci.orchestrator resolver crashed for trace=%s err=%s",
                trace_id, exc, exc_info=True,
            )
            candidate = CandidateOutput(
                text=None,
                error_message=f"resolver_exception:{type(exc).__name__}",
            )

        aggregate_cost += candidate.cost_usd

        stratum = sampled.stratum_for(trace_id) or "unknown"

        if candidate.text is None:
            # Resolver-level error (provider 5xx, budget exceeded, missing prompt).
            score_obj = diff_metric.score(
                diff_metric.ScoreInputs(
                    baseline_output=baseline_output,
                    candidate_output="",
                    prompt_context=prompt_context,
                ),
                embedder=None, judge=None,
            )
            trace_results.append(TraceResult(
                trace_id=trace_id,
                stratum=stratum,
                baseline_output=baseline_output,
                candidate_output="",
                diff_score=_force_verdict_error(score_obj),
                cost_usd=candidate.cost_usd,
                latency_ms=candidate.latency_ms,
                error_message=candidate.error_message,
            ))
            continue

        candidate_output = _truncate(candidate.text, OUTPUT_TRUNC_CHARS)
        score_obj = diff_metric.score(
            diff_metric.ScoreInputs(
                baseline_output=baseline_output,
                candidate_output=candidate_output,
                prompt_context=prompt_context,
            ),
            embedder=embedder,
            judge=judge,
        )
        if score_obj.judge_used:
            judge_used_count += 1

        trace_results.append(TraceResult(
            trace_id=trace_id,
            stratum=stratum,
            baseline_output=baseline_output,
            candidate_output=candidate_output,
            diff_score=score_obj,
            cost_usd=candidate.cost_usd,
            latency_ms=candidate.latency_ms,
            error_message=None,
        ))

        if persist_run and replay_run is not None:
            db.add(ReplayRunTrace(
                id=str(uuid4()),
                replay_run_id=replay_run.id,
                golden_trace_id=None,
                project_id=inputs.project_id,
                call_id_replayed=trace_id,
                judge_scores_json=json.dumps(score_obj.to_dict()),
                status=_trace_status_from_verdict(score_obj.verdict),
                diff_metric=score_obj.cosine if score_obj.cosine is not None else score_obj.jaccard,
                output_text=candidate_output[:OUTPUT_TRUNC_CHARS],
                completed_at=datetime.now(timezone.utc),
            ))

    # Step 5 — Cluster the regressions.
    regressed_traces = [
        cluster_mod.RegressedTrace(
            trace_id=r.trace_id,
            input_text=_extract_input_text_for_clustering(
                db, inputs.project_id, r.trace_id,
            ),
        )
        for r in trace_results
        if r.diff_score.verdict == DiffVerdict.FAIL
    ]
    clusters = cluster_mod.cluster_regressions(
        regressed_traces, embedder=embedder,
    )

    # Step 6 — Aggregate counts.
    trace_count = len(trace_results)
    regressed_count = sum(
        1 for r in trace_results if r.diff_score.verdict == DiffVerdict.FAIL
    )
    error_count = sum(
        1 for r in trace_results if r.diff_score.verdict == DiffVerdict.ERROR
    )
    regression_rate = (regressed_count / trace_count) if trace_count else 0.0
    error_rate = (error_count / trace_count) if trace_count else 0.0

    # Verdict — error rate above threshold poisons the whole run.
    if trace_count == 0:
        verdict = "error"
        notes.append("no traces were replayable (empty sample)")
    elif error_rate >= ERROR_RATE_ERROR_THRESHOLD:
        verdict = "error"
        notes.append(
            f"error rate {_pct(error_rate)} exceeds tolerance "
            f"{_pct(ERROR_RATE_ERROR_THRESHOLD)} — verdict forced to error"
        )
    elif regression_rate > inputs.threshold:
        verdict = "fail"
    else:
        verdict = "pass"

    duration_seconds = int(time.monotonic() - start)

    # Wedge 4 — attach outcome cost-of-failure attribution. Read-only,
    # graceful: any failure returns None (the report just omits the
    # $-tag rather than blowing up the run).
    try:
        outcome_attribution = cost_of_failure_mod.compute_pr_savings(
            db, project_id=inputs.project_id, regressed_count=regressed_count,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "regression_ci.orchestrator: outcome attribution failed",
            exc_info=True,
        )
        outcome_attribution = None

    report = RegressionCIReport(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        project_id=inputs.project_id,
        git_sha=inputs.git_sha,
        blast_radius=blast_radius,
        sample_spec=spec,
        stratification_realised=sampled.realised,
        trace_count=trace_count,
        regressed_count=regressed_count,
        regression_rate=regression_rate,
        threshold=inputs.threshold,
        verdict=verdict,
        error_count=error_count,
        error_rate=error_rate,
        judge_used_count=judge_used_count,
        cost_usd=aggregate_cost,
        duration_seconds=duration_seconds,
        clusters=clusters,
        outcome_attribution=outcome_attribution,
        notes=tuple(notes),
    )

    # Step 7 — Persist summary.
    if persist_run and replay_run is not None:
        replay_run.status = verdict
        replay_run.completed_at = datetime.now(timezone.utc)
        replay_run.summary_json = json.dumps(report.to_dict())
        db.add(replay_run)
        db.commit()

    return report


# ── helpers ─────────────────────────────────────────────────────────────────


def _trace_status_from_verdict(verdict: str) -> str:
    """Map DiffVerdict → ReplayRunTrace.status (constrained by DB CHECK)."""
    if verdict == DiffVerdict.PASS:
        return "pass"
    if verdict == DiffVerdict.FAIL:
        return "fail"
    return "error"  # INCONCLUSIVE / ERROR both become error at DB level


def _force_verdict_error(score: Any) -> Any:
    """Wrap a score with the ERROR verdict (used when resolver returns no text)."""
    from app.services.regression_ci.models import DiffScore
    return DiffScore(
        verdict=DiffVerdict.ERROR,
        jaccard=score.jaccard,
        cosine=score.cosine,
        judge_used=score.judge_used,
        judge_confidence=score.judge_confidence,
        reason="resolver_no_output",
    )


def _extract_baseline_output(call: Call) -> str:
    """Pull the originally-recorded response text out of Call.payload_json.

    Robust to:
      - payload_json being malformed (returns "")
      - response being absent (returns "")
      - response being a non-string (str-coerced)
    """
    try:
        payload = json.loads(call.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    response = payload.get("response")
    if response is None:
        return ""
    return str(response)


def _extract_prompt_context(call: Call) -> str:
    """Pull the prompt/messages out of Call.payload_json for diff context."""
    try:
        payload = json.loads(call.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""

    # Prefer modern messages array; fall back to legacy prompt field.
    messages = payload.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        for msg in messages:
            if isinstance(msg, dict):
                role = str(msg.get("role", "") or "")
                content = str(msg.get("content", "") or "")
                if content:
                    parts.append(f"[{role}] {content}")
        return "\n".join(parts)

    prompt = payload.get("prompt")
    return str(prompt) if prompt is not None else ""


def _extract_input_text_for_clustering(
    db: Session, project_id: str, trace_id: str,
) -> str:
    """Fetch the input text again for clustering. Bounded to 1 KB.

    Re-fetching is wasteful but keeps the orchestrator's data flow
    one-directional (trace_results → clusters). At ~1000 traces this
    adds maybe 100 ms total — well below the rest of the pipeline.
    """
    call = db.execute(
        select(Call).where(
            Call.id == trace_id,
            Call.project_id == project_id,
        )
    ).scalar_one_or_none()
    if call is None:
        return ""
    return _truncate(_extract_prompt_context(call), 1024)


def _truncate(text: str, n: int) -> str:
    if not text:
        return ""
    if len(text) <= n:
        return text
    return text[: n - 3] + "..."


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _synthetic_golden_set_id(project_id: str) -> str:
    """ReplayRun.golden_set_id is NOT NULL but regression-CI runs aren't
    tied to a golden set. We use a deterministic per-project synthetic
    id with the "regression-ci:" prefix so the dashboard can distinguish
    these from real golden-set runs.

    NOTE: A migration adds a `regression_ci` synthetic GoldenSet row per
    project on first use (handled at the API-route layer; not part of
    orchestrator's contract).
    """
    return f"regression-ci:{project_id}"


# ── public re-exports ──────────────────────────────────────────────────────


__all__ = [
    "CandidateOutput",
    "CandidateResolver",
    "RegressionCIInputs",
    "run_regression_ci",
    "DEFAULT_REGRESSION_THRESHOLD",
    "ERROR_RATE_ERROR_THRESHOLD",
]
