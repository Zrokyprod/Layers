"""
/v1/goldens — CRUD for golden sets and their traces (Pilot tier).

API surface per ZROKY-TECHNICAL-PLAN-V2 §13:

  GET    /v1/goldens                            — list (cursor-paginated)
  POST   /v1/goldens                            — create
  GET    /v1/goldens/{id}                       — detail (with trace_count)
  PATCH  /v1/goldens/{id}                       — partial update
  DELETE /v1/goldens/{id}                       — cascade deletes traces
  GET    /v1/goldens/{id}/traces                — list traces
  POST   /v1/goldens/{id}/traces                — add trace
  DELETE /v1/goldens/{id}/traces/{trace_id}     — remove trace

`POST /v1/goldens/{id}/run` ships separately in Module 4.2 (Replay) once
the orchestrator lands.

Entitlements plan-gate (402 Payment Required) — Module 6 attaches
`require_entitlement("pilot.autopilot_enabled")` at the router level
so every endpoint here is gated uniformly per plan §10.x. The
`goldens.max_sets` cap is enforced inside `create_golden_set` itself.
"""
import base64
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import GoldenHistory
from app.db.session import get_db_session
from app.services.goldens import (
    GoldenSetNameConflict,
    add_trace,
    count_traces,
    create_golden_set,
    delete_golden_set,
    get_golden_set,
    list_golden_sets,
    list_traces,
    remove_trace,
    update_golden_set,
)
from app.services.replay_runs import (
    VALID_TRIGGERS,
    build_summary_url,
    dispatch_replay_run,
    get_replay_run,
    mark_call_as_golden,
    normalize_replay_mode,
    parse_summary,
    was_idempotent_hit,
)
from app.services.golden_contracts import build_golden_contract, criteria_with_contract, trusted_replay_summary

router = APIRouter(
    prefix="/v1/goldens",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


# ── schemas ──────────────────────────────────────────────────────────────────


class GoldenSetResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    judge_config_json: str | None
    is_flaky: bool
    blocks_ci: bool
    trace_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoldenSetListResponse(BaseModel):
    items: list[GoldenSetResponse]
    next_cursor: str | None
    total_in_page: int


class GoldenSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    judge_config_json: str | None = None


class GoldenSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    judge_config_json: str | None = None
    is_flaky: bool | None = None
    blocks_ci: bool | None = None
    clear_description: bool = False
    clear_judge_config: bool = False


class GoldenTraceResponse(BaseModel):
    id: str
    golden_set_id: str
    project_id: str
    call_id: str | None
    status: str
    expected_output_text: str | None
    source_output_text: str | None
    source_evidence_json: str | None
    expected_tokens: int | None
    expected_cost_usd: float | None
    expected_latency_ms: int | None
    criteria_json: str | None
    weight: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoldenTraceListResponse(BaseModel):
    items: list[GoldenTraceResponse]
    total_in_page: int


class GoldenHistoryResponse(BaseModel):
    id: str
    project_id: str
    golden_set_id: str | None
    golden_trace_id: str | None
    action: str
    actor_user_id: str | None
    reason: str | None
    before_json: str | None
    after_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GoldenHistoryListResponse(BaseModel):
    items: list[GoldenHistoryResponse]
    total_in_page: int


class GoldenTraceCreate(BaseModel):
    call_id: str | None = None
    status: str | None = None
    expected_output_text: str | None = None
    source_output_text: str | None = None
    source_evidence_json: str | None = None
    expected_tokens: int | None = Field(default=None, ge=0)
    expected_cost_usd: float | None = Field(default=None, ge=0)
    expected_latency_ms: int | None = Field(default=None, ge=0)
    criteria_json: str | None = None
    weight: float = Field(default=1.0, gt=0)


class GoldenTracePromoteRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=64)
    status: str = "draft"
    expected_output_text: str | None = None
    criteria_json: str | None = None
    linked_replay_run_id: str | None = None
    weight: float = Field(default=1.0, gt=0)


# ── cursor helpers ───────────────────────────────────────────────────────────


def _encode_cursor(created_at: datetime, golden_set_id: str) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "id": golden_set_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ts = datetime.fromisoformat(payload["t"])
        return ts, str(payload["id"])
    except Exception:
        return None


def _to_response(db: Session, *, golden_set, project_id: str) -> GoldenSetResponse:
    return GoldenSetResponse(
        id=golden_set.id,
        project_id=golden_set.project_id,
        name=golden_set.name,
        description=golden_set.description,
        judge_config_json=golden_set.judge_config_json,
        is_flaky=bool(golden_set.is_flaky),
        blocks_ci=bool(golden_set.blocks_ci),
        trace_count=count_traces(
            db, project_id=project_id, golden_set_id=golden_set.id
        ),
        created_at=golden_set.created_at,
        updated_at=golden_set.updated_at,
    )


# ── golden set routes ────────────────────────────────────────────────────────


@router.get("", response_model=GoldenSetListResponse)
@limiter.limit("60/minute")
def list_goldens(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenSetListResponse:
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

    rows = list_golden_sets(
        db,
        project_id=tenant_id,
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

    return GoldenSetListResponse(
        items=[
            _to_response(db, golden_set=row, project_id=tenant_id) for row in page
        ],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )


@router.post(
    "",
    response_model=GoldenSetResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
def create_golden(
    request: Request,
    body: GoldenSetCreate,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenSetResponse:
    try:
        golden_set = create_golden_set(
            db,
            project_id=tenant_id,
            name=body.name,
            description=body.description,
            judge_config_json=body.judge_config_json,
        )
    except GoldenSetNameConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_response(db, golden_set=golden_set, project_id=tenant_id)


@router.get("/{golden_set_id}", response_model=GoldenSetResponse)
@limiter.limit("120/minute")
def get_golden(
    request: Request,
    golden_set_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenSetResponse:
    golden_set = get_golden_set(
        db, project_id=tenant_id, golden_set_id=golden_set_id
    )
    if golden_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found"
        )
    return _to_response(db, golden_set=golden_set, project_id=tenant_id)


@router.get("/{golden_set_id}/history", response_model=GoldenHistoryListResponse)
@limiter.limit("60/minute")
def list_golden_history(
    request: Request,
    golden_set_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenHistoryListResponse:
    if get_golden_set(db, project_id=tenant_id, golden_set_id=golden_set_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Golden set not found",
        )
    rows = db.execute(
        select(GoldenHistory)
        .where(
            GoldenHistory.project_id == tenant_id,
            GoldenHistory.golden_set_id == golden_set_id,
        )
        .order_by(GoldenHistory.created_at.desc(), GoldenHistory.id.desc())
        .limit(100)
    ).scalars().all()
    return GoldenHistoryListResponse(
        items=[GoldenHistoryResponse.model_validate(row) for row in rows],
        total_in_page=len(rows),
    )


@router.patch("/{golden_set_id}", response_model=GoldenSetResponse)
@limiter.limit("30/minute")
def patch_golden(
    request: Request,
    golden_set_id: str,
    body: GoldenSetUpdate,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenSetResponse:
    try:
        updated = update_golden_set(
            db,
            project_id=tenant_id,
            golden_set_id=golden_set_id,
            name=body.name,
            description=body.description,
            judge_config_json=body.judge_config_json,
            is_flaky=body.is_flaky,
            blocks_ci=body.blocks_ci,
            clear_description=body.clear_description,
            clear_judge_config=body.clear_judge_config,
        )
    except GoldenSetNameConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found"
        )
    return _to_response(db, golden_set=updated, project_id=tenant_id)


@router.delete("/{golden_set_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@limiter.limit("30/minute")
def delete_golden(
    request: Request,
    golden_set_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> None:
    deleted = delete_golden_set(
        db, project_id=tenant_id, golden_set_id=golden_set_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found"
        )


# ── golden trace routes ──────────────────────────────────────────────────────


@router.get(
    "/{golden_set_id}/traces", response_model=GoldenTraceListResponse
)
@limiter.limit("60/minute")
def list_golden_traces(
    request: Request,
    golden_set_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenTraceListResponse:
    traces = list_traces(
        db, project_id=tenant_id, golden_set_id=golden_set_id
    )
    if traces is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found"
        )
    return GoldenTraceListResponse(
        items=[GoldenTraceResponse.model_validate(t) for t in traces],
        total_in_page=len(traces),
    )


@router.post(
    "/{golden_set_id}/traces",
    response_model=GoldenTraceResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
def add_golden_trace(
    request: Request,
    golden_set_id: str,
    body: GoldenTraceCreate,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenTraceResponse:
    try:
        trace = add_trace(
            db,
            project_id=tenant_id,
            golden_set_id=golden_set_id,
            call_id=body.call_id,
            status=body.status,
            expected_output_text=body.expected_output_text,
            source_output_text=body.source_output_text,
            source_evidence_json=body.source_evidence_json,
            expected_tokens=body.expected_tokens,
            expected_cost_usd=body.expected_cost_usd,
            expected_latency_ms=body.expected_latency_ms,
            criteria_json=body.criteria_json,
            weight=body.weight,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found"
        )
    return GoldenTraceResponse.model_validate(trace)


@router.post(
    "/{golden_set_id}/promote-trace",
    response_model=GoldenTraceResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
def promote_trace_to_golden(
    request: Request,
    golden_set_id: str,
    body: GoldenTracePromoteRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenTraceResponse:
    requested_status = (body.status or "draft").strip().lower()
    linked_summary: dict | None = None
    if requested_status == "active":
        if not body.linked_replay_run_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active Golden promotion requires linked trusted replay proof.",
            )
        replay_run = get_replay_run(
            db,
            project_id=tenant_id,
            run_id=body.linked_replay_run_id,
        )
        if replay_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay run not found")
        linked_summary = parse_summary(replay_run.summary_json)
        if not trusted_replay_summary(linked_summary, replay_mode=linked_summary.get("requested_replay_mode")):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active Golden promotion requires a trusted non-stub verified replay.",
            )

    contract = build_golden_contract(
        final_output=body.expected_output_text,
        linked_trace_id=body.call_id,
        linked_replay_run_id=body.linked_replay_run_id,
        proof_status=str((linked_summary or {}).get("verification_status") or "draft"),
    )
    try:
        criteria_json = criteria_with_contract(body.criteria_json, contract)
        trace = mark_call_as_golden(
            db,
            project_id=tenant_id,
            call_id=body.call_id,
            golden_set_id=golden_set_id,
            weight=body.weight,
            status=requested_status,
            expected_output_text=body.expected_output_text,
            criteria_json=criteria_json,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call or Golden set not found",
        )
    return GoldenTraceResponse.model_validate(trace)


@router.delete(
    "/{golden_set_id}/traces/{trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@limiter.limit("60/minute")
def remove_golden_trace(
    request: Request,
    golden_set_id: str,
    trace_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> None:
    deleted = remove_trace(
        db,
        project_id=tenant_id,
        golden_set_id=golden_set_id,
        trace_id=trace_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden trace not found"
        )


# ── replay run dispatch (Module 4.2) ─────────────────────────────────────────


class GoldenRunRequest(BaseModel):
    trigger: str = "manual"
    git_sha: str | None = None
    # Module 9 — optional CI-context metadata. Stored in summary_json by
    # the service so the dashboard / PR check can render "Run for PR #42
    # (feature/foo): fix typo".
    branch_name: str | None = None
    pr_number: int | None = None
    commit_message: str | None = None
    # Option A (honesty fix) — when set, the dispatcher requires
    # `Settings.REPLAY_REAL_LLM_ENABLED=True` and the executor (Option B)
    # will re-execute against this prompt/model instead of grading the
    # source call's recorded response. Without the global flag enabled
    # these fields are rejected with HTTP 422 to prevent silent no-ops.
    candidate_prompt_override: str | None = None
    candidate_model_override: str | None = None
    replay_mode: str | None = None


class GoldenRunDispatchResponse(BaseModel):
    id: str
    project_id: str
    golden_set_id: str
    trigger: str
    git_sha: str | None
    status: str
    created_at: datetime
    # Module 9 — link the GitHub Action posts back as the PR check
    # `details_url`. Always populated; points at the dashboard's
    # human-facing replay-run page.
    summary_url: str
    # Module 9 — true when this dispatch hit an existing run via the
    # (project_id, golden_set_id, git_sha) idempotency window. Lets the
    # Action skip the second poll loop if the run already terminated.
    idempotent: bool = False


@router.post(
    "/{golden_set_id}/run",
    response_model=GoldenRunDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("12/minute")
def run_golden_set(
    request: Request,
    golden_set_id: str,
    body: GoldenRunRequest = Body(default_factory=GoldenRunRequest),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> GoldenRunDispatchResponse:
    """Dispatch a replay run for a golden set.

    Creates a `ReplayRun` row in `pending` status. Actual replay execution
    is handled by a background worker (deferred to a later module). Clients
    should poll `GET /v1/replay/runs/{id}` for status.
    """
    payload = body
    if payload.trigger not in VALID_TRIGGERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"trigger must be one of {sorted(VALID_TRIGGERS)}",
        )

    try:
        replay_mode = normalize_replay_mode(payload.replay_mode) if payload.replay_mode else None
        run = dispatch_replay_run(
            db,
            project_id=tenant_id,
            golden_set_id=golden_set_id,
            trigger=payload.trigger,
            git_sha=payload.git_sha,
            branch_name=payload.branch_name,
            pr_number=payload.pr_number,
            commit_message=payload.commit_message,
            replay_mode=replay_mode,
            candidate_prompt_override=payload.candidate_prompt_override,
            candidate_model_override=payload.candidate_model_override,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found"
        )

    # Module 9: detect whether dispatch hit the idempotency window via
    # the transient flag stamped by the service. Pending or terminal,
    # an existing row counts as idempotent.
    is_idempotent = was_idempotent_hit(run)

    # Module 8 (plan §6.4): enqueue the Celery executor task. The route
    # still returns 202 immediately and the client polls
    # GET /v1/replay/runs/{id} for status — but instead of the pending row
    # sitting forever, a worker now picks it up and grades each trace via
    # judge_engine. Enqueue failure is non-fatal: the row exists and a
    # `requeue` beat task (future) can retry.
    #
    # Skip the enqueue on an idempotent hit — the original dispatch
    # already enqueued (or finished) so re-enqueuing would just race
    # with the existing worker / waste the slot.
    if not is_idempotent:
        try:
            from app.worker.tasks import process_replay_run

            process_replay_run.apply_async(
                args=(tenant_id, run.id),
                queue="diagnosis_pattern",
                countdown=2,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "run_golden_set.enqueue_failed run=%s — row remains pending",
                run.id,
                exc_info=True,
            )

    return GoldenRunDispatchResponse(
        id=run.id,
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        trigger=run.trigger,
        git_sha=run.git_sha,
        status=run.status,
        created_at=run.created_at,
        summary_url=build_summary_url(run),
        idempotent=is_idempotent,
    )
