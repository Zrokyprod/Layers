"""
/v1/regression-ci/* — Pre-deploy Replay CI Gate (Wedge 1).

Two endpoints:

  POST /v1/regression-ci/run     — kick off a regression-CI run
  GET  /v1/regression-ci/runs/{id} — poll for status + report + comment

Auth model mirrors `replay_dispatch.py`:
  * tenant-scoped via `require_tenant_id` (API key OR JWT)
  * plan-gated at router level via `require_entitlement("pilot.autopilot_enabled")`
    so Free/Watch tier customers receive 402 Payment Required

Architecture notes:

  * The POST endpoint creates a `ReplayRun` row in `status='queued'`,
    commits, then schedules a `BackgroundTasks` callback that calls
    `run_regression_ci(..., run_id_override=run_id)`. The orchestrator
    transitions the row to `running` then to `pass`/`fail`/`error`.

  * The GET endpoint reads the same `ReplayRun` row. When `summary_json`
    is populated (terminal state), the rendered `RegressionCIReport`
    plus PR-comment markdown are returned. While the run is queued or
    running, only the status string is returned.

  * The route does NOT use Celery. The orchestrator is bounded
    (typically <60s for tool_prompt blast radius) and FastAPI's
    BackgroundTasks gives us a thread per request. Customers can
    swap in Celery later by replacing the BackgroundTasks shim with
    `celery_app.send_task("...")` — the orchestrator function is
    completely decoupled from the dispatch mechanism.

  * Tenant isolation: every read filters by `project_id == tenant_id`.
    A run in project A is never visible to a caller in project B.

  * Idempotency on `(project_id, git_sha)` is intentionally NOT
    implemented in this iteration. Customers running the same SHA
    twice get two distinct runs. Add a 60-second idempotency window
    later if duplicate dispatches become a real-world problem.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import GoldenSet, ReplayRun
from app.db.session import SessionLocal, get_db_session
from app.services.regression_ci.blast_radius import ChangedFile
from app.services.regression_ci.models import (
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    VALID_CATEGORIES,
)
from app.services.regression_ci.orchestrator import (
    DEFAULT_REGRESSION_THRESHOLD,
    CandidateOutput,
    RegressionCIInputs,
    run_regression_ci,
)
from app.services.regression_ci.pr_comment import format_markdown

router = APIRouter(
    prefix="/v1/regression-ci",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)


# ── request / response schemas ──────────────────────────────────────────────


class ChangedFilePayload(BaseModel):
    """Schema-less in transit; the orchestrator's auto-detector tolerates
    missing hunks by skipping hunk-rule matches and relying on path rules."""

    path: str = Field(..., min_length=1, max_length=1024)
    hunks: str = ""


class OperatorOverridePayload(BaseModel):
    """Manual blast-radius override from the dashboard.

    Validated against `VALID_CATEGORIES`; `target` is free-form (e.g. tool
    name). When supplied, this beats every other source — by design, an
    operator's deliberate decision overrides both auto-detection and any
    declaration in the PR body / .zroky.yml.
    """

    category: str
    target: Optional[str] = None


class RegressionCIRunRequest(BaseModel):
    """POST body. Every field is optional except `git_sha` (which we
    require for audit / dashboard linking — runs without a SHA can't be
    tied back to a commit so we reject them at the schema layer)."""

    git_sha: str = Field(..., min_length=4, max_length=64)
    pr_body: Optional[str] = Field(None, max_length=65_536)
    zroky_yaml: Optional[str] = Field(None, max_length=16_384)
    changed_files: list[ChangedFilePayload] = Field(default_factory=list)
    threshold: float = Field(
        default=DEFAULT_REGRESSION_THRESHOLD, ge=0.0, le=1.0,
    )
    operator_override: Optional[OperatorOverridePayload] = None
    target_total_cap: Optional[int] = Field(default=None, ge=1, le=100_000)
    sample_window_days: int = Field(default=30, ge=1, le=365)


class RegressionCIRunResponse(BaseModel):
    run_id: str
    project_id: str
    git_sha: str
    status: str
    summary_url: str


class RegressionCIRunDetailResponse(BaseModel):
    """GET response. `report` and `pr_comment_markdown` are populated
    only after the run reaches a terminal state (`pass`/`fail`/`error`)."""

    run_id: str
    project_id: str
    git_sha: Optional[str]
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    report: Optional[dict[str, Any]] = None
    pr_comment_markdown: Optional[str] = None


# ── helpers ─────────────────────────────────────────────────────────────────


def _synthetic_golden_set_id(project_id: str) -> str:
    """Deterministic id for the regression-CI synthetic golden set.

    Matches `orchestrator._synthetic_golden_set_id`. Kept duplicated here
    rather than imported because the route owns the upsert lifecycle —
    the orchestrator only references the value.
    """
    return f"regression-ci:{project_id}"


def _ensure_synthetic_golden_set(db: Session, *, project_id: str) -> None:
    """Create the regression-CI placeholder GoldenSet on first use.

    `ReplayRun.golden_set_id` is `NOT NULL` with an FK to `golden_sets`.
    Regression-CI runs aren't tied to a real golden set, so we use a
    per-project synthetic row. Idempotent via ON-CONFLICT-equivalent
    select-then-insert; tolerable because this only runs on first
    regression-CI dispatch per project.
    """
    set_id = _synthetic_golden_set_id(project_id)
    existing = db.execute(
        select(GoldenSet.id).where(
            GoldenSet.id == set_id,
            GoldenSet.project_id == project_id,
        )
    ).first()
    if existing is not None:
        return
    db.add(GoldenSet(
        id=set_id,
        project_id=project_id,
        name="Regression CI (synthetic)",
        description=(
            "Auto-managed placeholder used by the regression-CI Wedge to "
            "satisfy the ReplayRun.golden_set_id FK. Do not edit."
        ),
        created_at=datetime.now(timezone.utc),
    ))
    db.flush()


def _build_summary_url(run_id: str) -> str:
    """Absolute path to the run-detail GET. Returned to GitHub Action so
    it can use it as the PR check `details_url`."""
    return f"/v1/regression-ci/runs/{run_id}"


def _coerce_override(
    payload: Optional[OperatorOverridePayload],
) -> Optional[BlastRadius]:
    if payload is None:
        return None
    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"operator_override.category must be one of "
                f"{sorted(VALID_CATEGORIES)}"
            ),
        )
    return BlastRadius(
        category=payload.category,
        source=BlastRadiusSource.OVERRIDE,
        target=payload.target,
        confidence=1.0,
    )


def _coerce_changed_files(
    payloads: list[ChangedFilePayload],
) -> list[ChangedFile]:
    return [ChangedFile(path=p.path, hunks=p.hunks) for p in payloads]


# ── background task ─────────────────────────────────────────────────────────


def _run_regression_ci_background(
    *,
    tenant_id: str,
    run_id: str,
    request_payload: dict[str, Any],
) -> None:
    """Background entry point. Spins up its own DB session.

    Failures are caught and the ReplayRun row is marked status='error'
    with the failure reason captured in summary_json.notes so the GET
    endpoint can show something useful. Never re-raises — the
    BackgroundTasks runner has nowhere meaningful to report to.

    Resolver / embedder / judge selection (production wiring):
      * Real-LLM resolver is built via `make_live_llm_resolver` when
        the tenant has the `pilot.real_llm_replay_enabled` entitlement.
        Otherwise we fall back to `default_resolver` (echoes baseline
        output → every diff is identical → run always passes). The
        latter is a safety net for free-tier customers whose first
        run shouldn't crash on a missing API key.
      * Embedder is the prod `EmbeddingService` instance.
      * Judge is `judge_engine.get_evaluator()` — same path as the
        existing replay-runs worker.
    """
    session: Session = SessionLocal()
    try:
        # Lazy imports — keep this module importable without the heavy
        # service singletons being constructed at routing time.
        from app.services.embedding_service import get_embedding_service
        from app.services.entitlements_resolver import (
            get_plan_code, has, resolve_all,
        )
        from app.services.judge_engine import get_evaluator
        from app.services.replay_executor import (
            ReplayBudgetTracker, default_resolver, make_live_llm_resolver,
        )

        from app.db.models import Call, GoldenTrace
        from app.services.regression_ci.orchestrator import CandidateOutput

        # Resolve plan + entitlements (best-effort).
        try:
            ents = resolve_all(session, tenant_id)
            plan = get_plan_code(session, tenant_id)
            real_llm_entitled = has(
                session, tenant_id, "pilot.real_llm_replay_enabled",
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "regression_ci.background.entitlements_lookup_failed tenant=%s",
                tenant_id, exc_info=True,
            )
            ents, plan, real_llm_entitled = None, None, False

        evaluator = get_evaluator(plan_code=plan, entitlements_dict=ents)

        # Build the candidate resolver. The replay_executor's resolver
        # signature is (GoldenTrace, Call) → ActualOutput; the regression-CI
        # orchestrator's is (Call) → CandidateOutput. Adapt with a tiny
        # synthetic GoldenTrace.
        budget_tracker: ReplayBudgetTracker | None = None
        if real_llm_entitled:
            from app.core.config import get_settings
            budget_tracker = ReplayBudgetTracker(
                budget_usd=float(get_settings().REPLAY_REAL_LLM_BUDGET_USD)
            )
            inner_resolver = make_live_llm_resolver(
                candidate_prompt_override=None,
                candidate_model_override=None,
                budget_tracker=budget_tracker,
            )
        else:
            inner_resolver = default_resolver

        def _adapter(call: Call) -> CandidateOutput:
            synthetic_trace = GoldenTrace(
                id=f"regression-ci-syn-{call.id}",
                golden_set_id=_synthetic_golden_set_id(call.project_id),
                project_id=call.project_id,
                expected_output="",
                input_payload_json="{}",
            )
            actual = inner_resolver(synthetic_trace, call)
            return CandidateOutput(
                text=actual.text,
                error_message=actual.reason,
                cost_usd=actual.cost_total,
                latency_ms=actual.latency_ms,
            )

        # Reconstruct the orchestrator inputs from the JSON payload.
        op_override = None
        if request_payload.get("operator_override"):
            op_payload = request_payload["operator_override"]
            op_override = BlastRadius(
                category=op_payload["category"],
                source=BlastRadiusSource.OVERRIDE,
                target=op_payload.get("target"),
                confidence=1.0,
            )

        inputs = RegressionCIInputs(
            project_id=tenant_id,
            git_sha=request_payload.get("git_sha"),
            pr_body=request_payload.get("pr_body"),
            zroky_yaml=request_payload.get("zroky_yaml"),
            changed_files=[
                ChangedFile(path=cf["path"], hunks=cf.get("hunks", ""))
                for cf in request_payload.get("changed_files") or []
            ],
            threshold=float(
                request_payload.get("threshold", DEFAULT_REGRESSION_THRESHOLD)
            ),
            target_total_cap=request_payload.get("target_total_cap"),
            sample_window_days=int(
                request_payload.get("sample_window_days", 30)
            ),
        )

        embedder = None
        try:
            embedder = get_embedding_service()
        except Exception:  # noqa: BLE001
            logger.warning(
                "regression_ci.background.embedder_unavailable tenant=%s",
                tenant_id, exc_info=True,
            )

        run_regression_ci(
            inputs,
            db=session,
            candidate_resolver=_adapter,
            embedder=embedder,
            judge=evaluator,
            operator_override=op_override,
            run_id_override=run_id,
        )
        # Orchestrator commits at the end. Nothing else to do.
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "regression_ci.background.failed tenant=%s run=%s",
            tenant_id, run_id,
        )
        try:
            session.rollback()
            row = session.execute(
                select(ReplayRun).where(
                    ReplayRun.id == run_id,
                    ReplayRun.project_id == tenant_id,
                )
            ).scalar_one_or_none()
            if row is not None:
                row.status = "error"
                row.completed_at = datetime.now(timezone.utc)
                row.summary_json = json.dumps({
                    "schema_version": "v1",
                    "run_id": run_id,
                    "project_id": tenant_id,
                    "verdict": "error",
                    "notes": [f"background_task_failed:{type(exc).__name__}"],
                })
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "regression_ci.background.finalize_error_failed run=%s", run_id,
            )
    finally:
        session.close()


# ── routes ──────────────────────────────────────────────────────────────────


@router.post(
    "/run",
    response_model=RegressionCIRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("30/minute")
def post_run(
    request: Request,
    body: RegressionCIRunRequest,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> RegressionCIRunResponse:
    """Kick off a regression-CI run. Returns 202 with the run_id; the
    actual work proceeds in a BackgroundTask.

    Validation:
      * `git_sha` required (4-64 chars).
      * `threshold` in [0, 1].
      * `operator_override.category` must be a known blast-radius.

    The synthetic GoldenSet is upserted on first call per project so
    the FK-bound ReplayRun row is creatable without a separate
    onboarding step.
    """
    # Validate override up-front (raises 422 on bad category).
    _coerce_override(body.operator_override)

    # Ensure the FK target exists.
    _ensure_synthetic_golden_set(db, project_id=tenant_id)

    run_id = str(uuid4())
    now = datetime.now(timezone.utc)

    queued_run = ReplayRun(
        id=run_id,
        project_id=tenant_id,
        golden_set_id=_synthetic_golden_set_id(tenant_id),
        trigger="github",
        git_sha=body.git_sha,
        status="pending",
        created_at=now,
        summary_json=None,
    )
    db.add(queued_run)
    db.commit()

    request_payload = body.model_dump(mode="json")

    background_tasks.add_task(
        _run_regression_ci_background,
        tenant_id=tenant_id,
        run_id=run_id,
        request_payload=request_payload,
    )

    logger.info(
        "regression_ci.dispatch tenant=%s run=%s sha=%s files=%d",
        tenant_id, run_id, body.git_sha, len(body.changed_files),
    )

    return RegressionCIRunResponse(
        run_id=run_id,
        project_id=tenant_id,
        git_sha=body.git_sha,
        status="queued",
        summary_url=_build_summary_url(run_id),
    )


@router.get(
    "/runs/{run_id}",
    response_model=RegressionCIRunDetailResponse,
)
@limiter.limit("120/minute")
def get_run(
    request: Request,
    run_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> RegressionCIRunDetailResponse:
    """Fetch the current status + (when terminal) full report for a run.

    Status semantics:
      * `queued`         — accepted, not started yet.
      * `running`        — orchestrator is mid-loop.
      * `pass`/`fail`    — terminal, report + comment available.
      * `error`          — terminal, summary may still be partially populated.

    Tenant isolation: a run from another project is reported as 404 so
    the existence of the run_id is not leaked.
    """
    row = db.execute(
        select(ReplayRun).where(
            ReplayRun.id == run_id,
            ReplayRun.project_id == tenant_id,
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )

    report_dict: Optional[dict[str, Any]] = None
    pr_comment: Optional[str] = None

    if row.summary_json:
        try:
            report_dict = json.loads(row.summary_json)
        except json.JSONDecodeError:
            logger.warning(
                "regression_ci.get_run.summary_json_unparsable run=%s", run_id,
            )
            report_dict = None

        if report_dict and report_dict.get("schema_version"):
            # Re-render the markdown server-side. The Action gets a stable
            # body even when older runs predate a formatter change.
            try:
                pr_comment = _render_pr_comment_from_dict(report_dict)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "regression_ci.get_run.markdown_render_failed run=%s",
                    run_id, exc_info=True,
                )
                pr_comment = None

    return RegressionCIRunDetailResponse(
        run_id=row.id,
        project_id=row.project_id,
        git_sha=row.git_sha,
        status=row.status,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        report=report_dict,
        pr_comment_markdown=pr_comment,
    )


def _render_pr_comment_from_dict(report_dict: dict[str, Any]) -> Optional[str]:
    """Re-hydrate a `RegressionCIReport` from its serialized form and
    format it as markdown.

    We don't store the markdown directly — we keep the canonical
    `RegressionCIReport` JSON and re-render on demand so any formatter
    improvements take effect for past runs without a backfill.
    """
    from app.services.regression_ci.models import (
        RegressionCIReport,
        RegressionCluster,
        SampleSpec,
        StratificationCounts,
    )

    try:
        br_dict = report_dict["blast_radius"]
        spec_dict = report_dict["sample_spec"]
        strat_dict = report_dict["stratification_realised"]

        blast = BlastRadius(
            category=br_dict["category"],
            source=br_dict["source"],
            files=tuple(br_dict.get("files") or ()),
            target=br_dict.get("target"),
            confidence=float(br_dict.get("confidence", 1.0)),
        )
        sample_spec = SampleSpec(
            target_total=int(spec_dict["target_total"]),
            stratification=spec_dict["stratification"],
            blast_radius=blast,
        )
        strat = StratificationCounts(
            pass_history=int(strat_dict.get("pass_history", 0)),
            fail_history=int(strat_dict.get("fail_history", 0)),
            rare_cluster=int(strat_dict.get("rare_cluster", 0)),
            recent_24h=int(strat_dict.get("recent_24h", 0)),
        )
        clusters = tuple(
            RegressionCluster(
                label=c["label"],
                keywords=tuple(c.get("keywords") or ()),
                size=int(c["size"]),
                sample_trace_id=c["sample_trace_id"],
                sample_input=c["sample_input"],
            )
            for c in report_dict.get("clusters") or ()
        )
        report = RegressionCIReport(
            schema_version=report_dict["schema_version"],
            run_id=report_dict["run_id"],
            project_id=report_dict["project_id"],
            git_sha=report_dict.get("git_sha"),
            blast_radius=blast,
            sample_spec=sample_spec,
            stratification_realised=strat,
            trace_count=int(report_dict["trace_count"]),
            regressed_count=int(report_dict["regressed_count"]),
            regression_rate=float(report_dict["regression_rate"]),
            threshold=float(report_dict["threshold"]),
            verdict=report_dict["verdict"],
            error_count=int(report_dict.get("error_count", 0)),
            error_rate=float(report_dict.get("error_rate", 0.0)),
            judge_used_count=int(report_dict.get("judge_used_count", 0)),
            cost_usd=float(report_dict.get("cost_usd", 0.0)),
            duration_seconds=int(report_dict.get("duration_seconds", 0)),
            clusters=clusters,
            notes=tuple(report_dict.get("notes") or ()),
        )
    except (KeyError, TypeError, ValueError):
        return None

    return format_markdown(report)
