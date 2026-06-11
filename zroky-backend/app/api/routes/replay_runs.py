"""
/v1/replay/runs — read-only golden-set replay run surface (Pilot tier).

API surface per ZROKY-TECHNICAL-PLAN-V2 §13:

  GET  /v1/replay/runs           — list (cursor-paginated; filters by
                                   golden_set_id and status)
  GET  /v1/replay/runs/{id}      — detail with per-trace verdicts embedded

The dispatch endpoint (`POST /v1/goldens/{id}/run`) lives on the goldens
router so it composes naturally as a sub-resource of the parent set.

Distinct from the legacy `/v1/replay/jobs` surface in `routes/replay.py`
which tracks single-fix replay jobs run by the customer-hosted worker.

Entitlements plan-gate (402 Payment Required) — Module 6 attaches
`require_entitlement("pilot.autopilot_enabled")` at the router level
so every endpoint here is gated uniformly per plan §10.x.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.replay_runs import (
    VALID_RUN_STATUSES,
    VALID_REPLAY_MODES,
    build_summary_url,
    check_replay_monthly_quota,
    create_replay_from_call,
    create_replay_from_issue,
    get_replay_run,
    list_replay_runs,
    list_run_traces,
    normalize_replay_mode,
    parse_summary,
)
from app.services.outcome_attribution import get_replay_prevented_savings

router = APIRouter(
    prefix="/v1/replay/runs",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


# ── schemas ──────────────────────────────────────────────────────────────────


class ReplayRunSummary(BaseModel):
    trace_count_at_dispatch: int = 0
    trace_count_executed: int = 0
    pass_count: int = 0
    fail_count: int = 0
    not_verified_count: int = 0
    error_count: int = 0
    reproduced_original_failure: bool | None = None
    fix_passed: bool | None = None
    verified_fix: bool = False
    verification_status: str = "sanity_check_only"
    output_diff: dict | None = None
    tool_behavior_diff: dict | None = None
    cost_delta_usd: float | None = None
    latency_delta_ms: int | None = None
    replay_cost_usd: float | None = None
    trust_level: str = "untrusted"
    proof_missing_reasons: list[str] = []
    budget: dict | None = None


class ReplaySourceContext(BaseModel):
    kind: str | None = None
    id: str | None = None
    call_id: str | None = None
    issue_id: str | None = None
    title: str | None = None
    reason: str | None = None
    failure_code: str | None = None
    severity: str | None = None
    affected_agent: str | None = None
    affected_workflow: str | None = None
    occurrence_count: int | None = None
    last_seen_at: datetime | None = None
    origin: str | None = None
    confidence: float | None = None
    discovery_signature: str | None = None


class ReplayRunResponse(BaseModel):
    id: str
    project_id: str
    golden_set_id: str
    trigger: str
    git_sha: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    summary: ReplayRunSummary
    created_at: datetime
    # Option A (honesty fix): "stub" = recorded response was re-graded
    # (cannot detect prompt-edit regressions); "real_llm" = a real
    # provider call was issued with optional overrides. Always populated
    # for runs dispatched after Option A landed; older rows default to
    # "stub" in the helper.
    replay_mode: str = "stub"
    executor_replay_mode: str = "stub"
    # Human-readable banner text on stub-mode runs. None on real-LLM runs.
    replay_mode_warning: str | None = None
    # Echo the override values so the dashboard can render "Replay used
    # this edited prompt:" and surface the experiment context. Truncated
    # to 4000 chars by the dispatcher.
    candidate_prompt_override: str | None = None
    candidate_model_override: str | None = None
    prevented_outcome_cost_usd: float | None = None
    source_context: ReplaySourceContext | None = None


class ReplayRunListResponse(BaseModel):
    items: list[ReplayRunResponse]
    next_cursor: str | None
    total_in_page: int


class ReplayRunTraceResponse(BaseModel):
    id: str
    replay_run_id: str
    golden_trace_id: str | None
    project_id: str
    call_id_replayed: str | None
    judge_scores_json: str | None
    status: str
    diff_metric: float | None
    output_text: str | None
    completed_at: datetime | None
    created_at: datetime
    output_diff: dict | None = None
    tool_behavior_diff: dict | None = None
    cost_delta_usd: float | None = None
    latency_delta_ms: int | None = None

    model_config = {"from_attributes": True}


class ReplayRunDetailResponse(ReplayRunResponse):
    traces: list[ReplayRunTraceResponse]


class ReplayCreateRequest(BaseModel):
    replay_mode: str = "stub"
    candidate_prompt_override: str | None = None
    candidate_model_override: str | None = None


class ReplayCreateResponse(BaseModel):
    id: str
    project_id: str
    golden_set_id: str
    trigger: str
    status: str
    created_at: datetime
    summary_url: str
    replay_mode: str


# ── helpers ──────────────────────────────────────────────────────────────────


def _encode_cursor(created_at: datetime, run_id: str) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "id": run_id}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ts = datetime.fromisoformat(payload["t"])
        return ts, str(payload["id"])
    except Exception:
        return None


def _source_context_from_summary(summary: dict) -> ReplaySourceContext | None:
    raw = summary.get("source_context")
    if isinstance(raw, dict):
        return ReplaySourceContext(**raw)

    source_kind = summary.get("source_kind")
    source_id = summary.get("source_id")
    source_call_id = summary.get("source_call_id")
    source_issue_id = summary.get("source_issue_id")
    if not any([source_kind, source_id, source_call_id, source_issue_id]):
        return None

    return ReplaySourceContext(
        kind=str(source_kind or "call"),
        id=str(source_issue_id or source_id or source_call_id),
        call_id=str(source_call_id) if source_call_id else None,
        issue_id=str(source_issue_id) if source_issue_id else None,
        failure_code=str(summary.get("source_issue_failure_code")) if summary.get("source_issue_failure_code") else None,
        severity=str(summary.get("source_issue_severity")) if summary.get("source_issue_severity") else None,
        origin="legacy",
    )


def _to_run_response(run) -> ReplayRunResponse:
    summary = parse_summary(run.summary_json)
    # Default older rows (pre-Option-A) to stub mode with the same
    # warning text — there is no way they ran in real-LLM mode and the
    # dashboard banner should still surface the limitation.
    replay_mode = normalize_replay_mode(str(
        summary.get("requested_replay_mode")
        or summary.get("replay_mode")
        or "stub"
    ))
    replay_mode_warning = summary.get("replay_mode_warning")
    if replay_mode == "stub" and not replay_mode_warning:
        # Backfill the warning so legacy rows still render the banner.
        from app.services.replay_runs import _STUB_MODE_WARNING  # local; avoid cycle at import

        replay_mode_warning = _STUB_MODE_WARNING
    return ReplayRunResponse(
        id=run.id,
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        trigger=run.trigger,
        git_sha=run.git_sha,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=ReplayRunSummary(
            trace_count_at_dispatch=int(summary.get("trace_count_at_dispatch", 0) or 0),
            trace_count_executed=int(summary.get("trace_count_executed", 0) or 0),
            pass_count=int(summary.get("pass_count", 0) or 0),
            fail_count=int(summary.get("fail_count", 0) or 0),
            not_verified_count=int(summary.get("not_verified_count", 0) or 0),
            error_count=int(summary.get("error_count", 0) or 0),
            reproduced_original_failure=summary.get("reproduced_original_failure"),
            fix_passed=summary.get("fix_passed"),
            verified_fix=bool(summary.get("verified_fix") or False),
            verification_status=str(summary.get("verification_status") or "sanity_check_only"),
            output_diff=summary.get("output_diff") if isinstance(summary.get("output_diff"), dict) else None,
            tool_behavior_diff=summary.get("tool_behavior_diff") if isinstance(summary.get("tool_behavior_diff"), dict) else None,
            cost_delta_usd=float(summary["cost_delta_usd"]) if summary.get("cost_delta_usd") is not None else None,
            latency_delta_ms=int(summary["latency_delta_ms"]) if summary.get("latency_delta_ms") is not None else None,
            replay_cost_usd=float(summary["replay_cost_usd"]) if summary.get("replay_cost_usd") is not None else None,
            trust_level=str(summary.get("trust_level") or ("sanity_only" if replay_mode == "stub" else "untrusted")),
            proof_missing_reasons=[
                str(item)
                for item in (summary.get("proof_missing_reasons") or [])
                if item is not None
            ]
            if isinstance(summary.get("proof_missing_reasons"), list)
            else [],
            budget=summary.get("budget") if isinstance(summary.get("budget"), dict) else None,
        ),
        created_at=run.created_at,
        replay_mode=replay_mode,
        executor_replay_mode=normalize_replay_mode(str(summary.get("replay_mode") or "stub")),
        replay_mode_warning=replay_mode_warning,
        candidate_prompt_override=summary.get("candidate_prompt_override"),
        candidate_model_override=summary.get("candidate_model_override"),
        source_context=_source_context_from_summary(summary),
    )


def _to_trace_response(trace) -> ReplayRunTraceResponse:
    scores = parse_summary(trace.judge_scores_json)
    response = ReplayRunTraceResponse.model_validate(trace)
    response.output_diff = scores.get("output_diff") if isinstance(scores.get("output_diff"), dict) else None
    response.tool_behavior_diff = scores.get("tool_behavior_diff") if isinstance(scores.get("tool_behavior_diff"), dict) else None
    response.cost_delta_usd = float(scores["cost_delta_usd"]) if scores.get("cost_delta_usd") is not None else None
    response.latency_delta_ms = int(scores["latency_delta_ms"]) if scores.get("latency_delta_ms") is not None else None
    return response


def _check_quota_or_raise(db: Session, tenant_id: str) -> None:
    quota = check_replay_monthly_quota(db, tenant_id)
    if quota.limit != -1 and quota.used >= quota.limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Monthly replay limit reached ({quota.used}/{quota.limit}). Resets {quota.resets_at}.",
            headers={"X-Zroky-Plan-Hint": quota.plan_code},
        )


def _enqueue_replay_run(run_id: str, tenant_id: str) -> None:
    try:
        from app.worker.tasks import process_replay_run

        process_replay_run.apply_async(
            args=(tenant_id, run_id),
            queue="diagnosis_pattern",
            countdown=2,
        )
    except Exception:
        logger.warning("replay_run.enqueue_failed run=%s — row remains pending", run_id, exc_info=True)


# ── routes ───────────────────────────────────────────────────────────────────


@router.get("", response_model=ReplayRunListResponse)
@limiter.limit("60/minute")
def list_runs(
    request: Request,
    golden_set_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayRunListResponse:
    if status_filter is not None and status_filter not in VALID_RUN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "status must be one of: " + ", ".join(sorted(VALID_RUN_STATUSES))
            ),
        )

    before_created_at: datetime | None = None
    before_id: str | None = None
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid cursor value.",
            )
        before_created_at, before_id = decoded

    rows = list_replay_runs(
        db,
        project_id=tenant_id,
        golden_set_id=golden_set_id,
        status=status_filter,
        limit=limit + 1,
        before_created_at=before_created_at,
        before_id=before_id,
    )
    has_next = len(rows) > limit
    page = rows[:limit]

    next_cursor: str | None = None
    if has_next and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return ReplayRunListResponse(
        items=[_to_run_response(r) for r in page],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )


@router.post(
    "/from-call/{call_id}",
    response_model=ReplayCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("12/minute")
def create_from_call(
    request: Request,
    call_id: str,
    body: ReplayCreateRequest | None = None,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayCreateResponse:
    payload = body or ReplayCreateRequest()
    replay_mode = normalize_replay_mode(payload.replay_mode)
    if payload.replay_mode not in VALID_REPLAY_MODES and replay_mode not in VALID_REPLAY_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="replay_mode must be one of: " + ", ".join(sorted(VALID_REPLAY_MODES)),
        )
    _check_quota_or_raise(db, tenant_id)
    try:
        run = create_replay_from_call(
            db,
            project_id=tenant_id,
            call_id=call_id,
            replay_mode=replay_mode,
            candidate_prompt_override=payload.candidate_prompt_override,
            candidate_model_override=payload.candidate_model_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    _enqueue_replay_run(run.id, tenant_id)
    return ReplayCreateResponse(
        id=run.id,
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        trigger=run.trigger,
        status=run.status,
        created_at=run.created_at,
        summary_url=build_summary_url(run),
        replay_mode=replay_mode,
    )


@router.post(
    "/from-issue/{issue_id}",
    response_model=ReplayCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("12/minute")
def create_from_issue(
    request: Request,
    issue_id: str,
    body: ReplayCreateRequest | None = None,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayCreateResponse:
    payload = body or ReplayCreateRequest()
    replay_mode = normalize_replay_mode(payload.replay_mode)
    if payload.replay_mode not in VALID_REPLAY_MODES and replay_mode not in VALID_REPLAY_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="replay_mode must be one of: " + ", ".join(sorted(VALID_REPLAY_MODES)),
        )
    _check_quota_or_raise(db, tenant_id)
    try:
        run = create_replay_from_issue(
            db,
            project_id=tenant_id,
            issue_id=issue_id,
            replay_mode=replay_mode,
            candidate_prompt_override=payload.candidate_prompt_override,
            candidate_model_override=payload.candidate_model_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    _enqueue_replay_run(run.id, tenant_id)
    return ReplayCreateResponse(
        id=run.id,
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        trigger=run.trigger,
        status=run.status,
        created_at=run.created_at,
        summary_url=build_summary_url(run),
        replay_mode=replay_mode,
    )


@router.get("/{run_id}", response_model=ReplayRunDetailResponse)
@limiter.limit("120/minute")
def get_run(
    request: Request,
    run_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayRunDetailResponse:
    run = get_replay_run(db, project_id=tenant_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Replay run not found"
        )
    traces = list_run_traces(db, project_id=tenant_id, run_id=run_id) or []
    base = _to_run_response(run)
    prevented = get_replay_prevented_savings(db, project_id=tenant_id, run_id=run_id)
    dumped = base.model_dump()
    dumped["prevented_outcome_cost_usd"] = prevented if prevented > 0 else None
    return ReplayRunDetailResponse(
        **dumped,
        traces=[_to_trace_response(t) for t in traces],
    )
