"""GET /v1/issues - customer-facing product issue triage.

`Anomaly` is the internal detector grouping model. This route keeps
`/v1/issues` as the stable public API by projecting those rows into
plain-English product problems.
"""
from __future__ import annotations

import base64
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, TypeVar

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.api.routes._internal.issues_response import (
    _build_issue_response,
    _load_evidence_calls,
    _replay_coverage_status,
    _root_cause,
    _safe_json_object,
)
from app.api.routes.issue_schemas import (
    IssueCiGateProof,
    IssueCiGateRequest,
    IssueCiGateResponse,
    IssueGoldenProof,
    IssueGoldenPromotionRequest,
    IssueGoldenPromotionResponse,
    IssueListResponse,
    IssueResolveRequest,
    IssueResponse,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import Anomaly, GoldenSet, GoldenTrace, Project, ReplayRun
from app.db.session import get_db_session
from app.services.discovery.sink import DISCOVERY_DETECTOR
from app.services.goldens import (
    GoldenSetNameConflict,
    count_traces,
    create_golden_set,
    get_golden_set,
)
from app.services.golden_contracts import build_golden_contract, criteria_with_contract
from app.services.issue_projection import (
    PUBLIC_ISSUE_STATUSES,
    IssueProjection,
    anomaly_status_from_public,
    issue_projection_from_anomaly,
)
from app.services.issues import ignore_issue, resolve_issue, update_issue_triage
from app.services.replay_runs import (
    VALID_REPLAY_MODES,
    build_summary_url,
    check_replay_monthly_quota,
    dispatch_replay_run,
    mark_call_as_golden,
    normalize_replay_mode,
    parse_summary,
)

router = APIRouter(prefix="/v1/issues")
logger = logging.getLogger(__name__)
_RequestModel = TypeVar("_RequestModel", bound=BaseModel)

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 100
_ISSUE_GOLDEN_SET_NAME = "Issue regression guards"
_TRUSTED_REPLAY_STATUSES = {"verified_fix", "real_replay_passed"}


def _optional_trimmed_text(value: str | None, *, max_len: int, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a string or null",
        )
    text = value.strip()
    if not text:
        return None
    if len(text) > max_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be at most {max_len} characters",
        )
    return text


def _optional_deploy_url(value: str | None) -> str | None:
    text = _optional_trimmed_text(value, max_len=500, field_name="deploy_pr_url")
    if text is None:
        return None
    if not text.startswith(("https://", "http://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="deploy_pr_url must start with http:// or https://",
        )
    return text


def _validated_body(model: type[_RequestModel], body: Mapping[str, Any]) -> _RequestModel:
    try:
        return model.model_validate(body or {})
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


def _severity_rank(severity: str | None) -> int:
    return {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }.get((severity or "").lower(), 0)


def _severity_rank_expr():
    return case(
        (Anomaly.severity == "critical", 4),
        (Anomaly.severity == "high", 3),
        (Anomaly.severity == "medium", 2),
        (Anomaly.severity == "low", 1),
        else_=0,
    )


def _customer_issue_conditions() -> list[Any]:
    if get_settings().DISCOVERY_CUSTOMER_SURFACE_ENABLED:
        return []
    return [Anomaly.detector != DISCOVERY_DETECTOR]


def _encode_cursor(issue: IssueProjection) -> str:
    payload = json.dumps(
        {
            "s": _severity_rank(issue.severity),
            "b": float(issue.blast_radius_usd or 0),
            "c": int(issue.occurrence_count or 0),
            "t": issue.last_seen_at.isoformat(),
            "id": issue.id,
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        return None


@router.get("", response_model=IssueListResponse)
@limiter.limit("60/minute")
def list_issues(
    request: Request,
    status_filter: str | None = Query(default="open", alias="status"),
    failure_code: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    has_fix: bool | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueListResponse:
    if status_filter is not None and status_filter not in PUBLIC_ISSUE_STATUSES and status_filter != "all":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: open, resolved, ignored, all",
        )

    conditions = [Anomaly.project_id == tenant_id, *_customer_issue_conditions()]

    if status_filter and status_filter != "all":
        anomaly_status = anomaly_status_from_public(status_filter)
        if anomaly_status == "open":
            conditions.append(Anomaly.status.in_(["open", "acknowledged"]))
        else:
            conditions.append(Anomaly.status == anomaly_status)
    if severity:
        conditions.append(Anomaly.severity == severity.lower())

    rank_expr = _severity_rank_expr()

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid cursor value.",
            )
        try:
            cursor_rank = int(decoded["s"])
            cursor_count = int(decoded["c"])
            cursor_ts = datetime.fromisoformat(str(decoded["t"]))
            cursor_id = str(decoded["id"])
        except Exception as exc:
            logger.debug("invalid issues cursor payload: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid cursor value.",
            ) from exc

        conditions.append(
            or_(
                rank_expr < cursor_rank,
                and_(rank_expr == cursor_rank, Anomaly.occurrence_count < cursor_count),
                and_(
                    rank_expr == cursor_rank,
                    Anomaly.occurrence_count == cursor_count,
                    Anomaly.last_seen_at < cursor_ts,
                ),
                and_(
                    rank_expr == cursor_rank,
                    Anomaly.occurrence_count == cursor_count,
                    Anomaly.last_seen_at == cursor_ts,
                    Anomaly.id < cursor_id,
                ),
            )
        )

    fetch_limit = min(max((limit * 4) + 1, limit + 1), 401)
    rows = db.execute(
        select(Anomaly)
        .where(*conditions)
        .order_by(
            rank_expr.desc(),
            Anomaly.occurrence_count.desc(),
            Anomaly.last_seen_at.desc(),
            Anomaly.id.desc(),
        )
        .limit(fetch_limit)
    ).scalars().all()

    projections = [issue_projection_from_anomaly(row) for row in rows]
    if failure_code:
        expected_code = failure_code.upper()
        projections = [
            item for item in projections if item.failure_code.upper() == expected_code
        ]
    if agent_name:
        projections = [item for item in projections if item.agent_name == agent_name]
    if has_fix is True:
        projections = [item for item in projections if item.last_fix_id is not None]
    elif has_fix is False:
        projections = [item for item in projections if item.last_fix_id is None]

    has_next = len(projections) > limit
    page = list(projections[:limit])

    next_cursor: str | None = None
    if has_next and page:
        next_cursor = _encode_cursor(page[-1])

    return IssueListResponse(
        items=[_build_issue_response(db, row) for row in page],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )


@router.get("/{issue_id}", response_model=IssueResponse)
@limiter.limit("120/minute")
def get_issue(
    request: Request,
    issue_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
    issue = db.execute(
        select(Anomaly).where(
            Anomaly.project_id == tenant_id,
            Anomaly.id == issue_id,
            *_customer_issue_conditions(),
        )
    ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, issue)


def _load_anomaly_or_404(db: Session, *, project_id: str, issue_id: str) -> Anomaly:
    anomaly = db.execute(
        select(Anomaly).where(
            Anomaly.project_id == project_id,
            Anomaly.id == issue_id,
            *_customer_issue_conditions(),
        )
    ).scalar_one_or_none()
    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return anomaly


def _criteria_json_for_issue(
    issue: IssueProjection,
    *,
    root_cause: str,
    provided: str | None,
) -> str:
    if provided and provided.strip():
        try:
            json.loads(provided)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="criteria_json must be valid JSON",
            ) from exc
        base = provided.strip()
    else:
        base = json.dumps(
            {
                "kind": "issue_regression_guard",
                "issue_id": issue.id,
                "failure_code": issue.failure_code,
                "root_cause": root_cause,
                "must_not_reproduce_failure": True,
                "evidence_call_id": issue.sample_call_id,
            },
            separators=(",", ":"),
        )

    contract = build_golden_contract(
        final_output=None,
        business_outcome="must_not_reproduce_failure",
        linked_issue_id=issue.id,
        linked_trace_id=issue.sample_call_id,
        proof_status="verified_fix",
    )
    try:
        return criteria_with_contract(base, contract)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _extract_pr_number(url: str | None) -> int | None:
    if not url:
        return None
    marker = "/pull/"
    if marker not in url:
        return None
    suffix = url.rsplit(marker, 1)[-1].split("/", 1)[0].split("?", 1)[0]
    try:
        return int(suffix)
    except ValueError:
        return None


def _set_project_default_golden_if_empty(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
) -> None:
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if project is None or project.default_golden_set_id:
        return
    project.default_golden_set_id = golden_set_id
    db.add(project)


def _ensure_issue_golden_set(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str | None,
    blocks_ci: bool,
) -> GoldenSet:
    if golden_set_id:
        golden_set = get_golden_set(db, project_id=project_id, golden_set_id=golden_set_id)
        if golden_set is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Golden set not found",
            )
    else:
        golden_set = db.execute(
            select(GoldenSet)
            .where(
                GoldenSet.project_id == project_id,
                GoldenSet.name == _ISSUE_GOLDEN_SET_NAME,
            )
            .order_by(GoldenSet.created_at.desc(), GoldenSet.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if golden_set is None:
            try:
                golden_set = create_golden_set(
                    db,
                    project_id=project_id,
                    name=_ISSUE_GOLDEN_SET_NAME,
                    description="Verified issue scenarios promoted from the Failure Inbox.",
                )
            except GoldenSetNameConflict:
                golden_set = db.execute(
                    select(GoldenSet).where(
                        GoldenSet.project_id == project_id,
                        GoldenSet.name == _ISSUE_GOLDEN_SET_NAME,
                    )
                ).scalar_one()

    if blocks_ci and not bool(golden_set.blocks_ci):
        golden_set.blocks_ci = True
        golden_set.updated_at = datetime.now(timezone.utc)
        db.add(golden_set)
    _set_project_default_golden_if_empty(
        db,
        project_id=project_id,
        golden_set_id=golden_set.id,
    )
    db.commit()
    db.refresh(golden_set)
    return golden_set


def _existing_issue_trace(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    call_id: str,
) -> GoldenTrace | None:
    return db.execute(
        select(GoldenTrace)
        .where(
            GoldenTrace.project_id == project_id,
            GoldenTrace.golden_set_id == golden_set_id,
            GoldenTrace.call_id == call_id,
        )
        .order_by(GoldenTrace.created_at.desc(), GoldenTrace.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _stamp_issue_trace_evidence(
    trace: GoldenTrace,
    issue: IssueProjection,
    *,
    root_cause: str,
) -> None:
    evidence = _safe_json_object(trace.source_evidence_json)
    evidence.update(
        {
            "source_issue_id": issue.id,
            "source_issue_failure_code": issue.failure_code,
            "source_issue_severity": issue.severity,
            "source_issue_root_cause": root_cause,
            "source_issue_last_seen_at": issue.last_seen_at.isoformat(),
        }
    )
    trace.source_evidence_json = json.dumps(evidence, separators=(",", ":"), default=str)


def _record_issue_proof(
    anomaly: Anomaly,
    *,
    golden_set_id: str | None = None,
    golden_trace_id: str | None = None,
    ci_run_id: str | None = None,
) -> None:
    evidence = _safe_json_object(anomaly.evidence_json)
    proof = evidence.get("issue_proof")
    if not isinstance(proof, dict):
        proof = {}
    if golden_set_id:
        proof["golden_set_id"] = golden_set_id
    if golden_trace_id:
        proof["golden_trace_id"] = golden_trace_id
        proof["golden_promoted_at"] = datetime.now(timezone.utc).isoformat()
    if ci_run_id:
        proof["ci_run_id"] = ci_run_id
        proof["ci_dispatched_at"] = datetime.now(timezone.utc).isoformat()
    evidence["issue_proof"] = proof
    anomaly.evidence_json = json.dumps(evidence, separators=(",", ":"), default=str)
    anomaly.updated_at = datetime.now(timezone.utc)


def _promote_issue_to_golden(
    db: Session,
    *,
    anomaly: Anomaly,
    body: IssueGoldenPromotionRequest,
) -> GoldenTrace:
    issue = issue_projection_from_anomaly(anomaly)
    if not issue.sample_call_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Issue has no sample_call_id to promote.",
        )

    replay_status = _replay_coverage_status(db, issue)
    if replay_status not in _TRUSTED_REPLAY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trusted replay must verify the fix before Golden promotion.",
        )

    evidence = _safe_json_object(issue.sample_evidence_json)
    calls = _load_evidence_calls(db, issue)
    root_cause = _root_cause(issue, evidence, calls)
    criteria_json = _criteria_json_for_issue(
        issue,
        root_cause=root_cause,
        provided=body.criteria_json,
    )
    expected_output_text = body.expected_output_text.strip() if body.expected_output_text else None

    golden_set = _ensure_issue_golden_set(
        db,
        project_id=issue.project_id,
        golden_set_id=body.golden_set_id,
        blocks_ci=body.blocks_ci,
    )
    trace = _existing_issue_trace(
        db,
        project_id=issue.project_id,
        golden_set_id=golden_set.id,
        call_id=issue.sample_call_id,
    )
    if trace is None:
        try:
            trace = mark_call_as_golden(
                db,
                project_id=issue.project_id,
                call_id=issue.sample_call_id,
                golden_set_id=golden_set.id,
                status="active",
                expected_output_text=expected_output_text,
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
                detail="Call or golden set not found",
            )
    else:
        trace.status = "active"
        trace.criteria_json = criteria_json
        if expected_output_text:
            trace.expected_output_text = expected_output_text
        trace.updated_at = datetime.now(timezone.utc)

    _stamp_issue_trace_evidence(trace, issue, root_cause=root_cause)
    _record_issue_proof(
        anomaly,
        golden_set_id=golden_set.id,
        golden_trace_id=trace.id,
    )
    db.add(trace)
    db.add(anomaly)
    db.commit()
    db.refresh(trace)
    db.refresh(anomaly)
    return trace


def _golden_proof_from_trace(db: Session, trace: GoldenTrace) -> IssueGoldenProof:
    golden_set = get_golden_set(
        db,
        project_id=trace.project_id,
        golden_set_id=trace.golden_set_id,
    )
    return IssueGoldenProof(
        golden_set_id=trace.golden_set_id,
        golden_set_name=golden_set.name if golden_set else None,
        golden_trace_id=trace.id,
        status=trace.status,
        blocks_ci=bool(golden_set.blocks_ci) if golden_set else False,
        trace_count=count_traces(
            db,
            project_id=trace.project_id,
            golden_set_id=trace.golden_set_id,
        ),
        created_at=trace.created_at,
    )


def _check_replay_quota_or_raise(db: Session, tenant_id: str) -> None:
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
    except Exception:  # noqa: BLE001
        logger.warning("issue_gate.enqueue_failed run=%s - row remains pending", run_id, exc_info=True)


def _ci_gate_proof_from_run(run: ReplayRun) -> IssueCiGateProof:
    return IssueCiGateProof(
        run_id=run.id,
        status=run.status,
        git_sha=run.git_sha,
        summary_url=build_summary_url(run),
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.post(
    "/{issue_id}/promote-golden",
    response_model=IssueGoldenPromotionResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def promote_issue_golden_endpoint(
    request: Request,
    issue_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
    _: None = Depends(require_entitlement("pilot.goldens_basic")),
) -> IssueGoldenPromotionResponse:
    promotion_request = _validated_body(IssueGoldenPromotionRequest, body)
    anomaly = _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    trace = _promote_issue_to_golden(
        db,
        anomaly=anomaly,
        body=promotion_request,
    )
    return IssueGoldenPromotionResponse(
        issue=_build_issue_response(db, anomaly),
        golden=_golden_proof_from_trace(db, trace),
    )


@router.post(
    "/{issue_id}/ci-gate",
    response_model=IssueCiGateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("12/minute")
def run_issue_ci_gate_endpoint(
    request: Request,
    issue_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
    _: None = Depends(require_entitlement("pro.ci_gate_nonblocking")),
) -> IssueCiGateResponse:
    ci_gate_request = _validated_body(IssueCiGateRequest, body)
    anomaly = _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    issue = issue_projection_from_anomaly(anomaly)
    if not issue.deploy_pr_url and not ci_gate_request.git_sha:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Link a deploy PR or provide git_sha before running an issue CI gate.",
        )

    _check_replay_quota_or_raise(db, tenant_id)
    trace = _promote_issue_to_golden(
        db,
        anomaly=anomaly,
        body=IssueGoldenPromotionRequest(blocks_ci=True),
    )

    replay_mode = normalize_replay_mode(ci_gate_request.replay_mode) if ci_gate_request.replay_mode else None
    if replay_mode is not None and replay_mode not in VALID_REPLAY_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="replay_mode must be one of: " + ", ".join(sorted(VALID_REPLAY_MODES)),
        )

    pr_number = (
        ci_gate_request.pr_number
        if ci_gate_request.pr_number is not None
        else _extract_pr_number(issue.deploy_pr_url)
    )
    try:
        run = dispatch_replay_run(
            db,
            project_id=tenant_id,
            golden_set_id=trace.golden_set_id,
            trigger="github",
            git_sha=ci_gate_request.git_sha,
            branch_name=ci_gate_request.branch_name,
            pr_number=pr_number,
            commit_message=ci_gate_request.commit_message,
            replay_mode=replay_mode,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Golden set not found",
        )

    summary = parse_summary(run.summary_json)
    summary.update(
        {
            "source_kind": "issue_ci_gate",
            "source_issue_id": issue.id,
            "source_issue_failure_code": issue.failure_code,
            "source_issue_severity": issue.severity,
            "golden_set_id": trace.golden_set_id,
            "golden_trace_id": trace.id,
            "pr_url": issue.deploy_pr_url,
        }
    )
    if pr_number is not None:
        summary["pr_number"] = pr_number
    run.summary_json = json.dumps(summary, separators=(",", ":"), default=str)
    _record_issue_proof(anomaly, ci_run_id=run.id)
    db.add(run)
    db.add(anomaly)
    db.commit()
    db.refresh(run)
    db.refresh(anomaly)
    _enqueue_replay_run(run.id, tenant_id)

    return IssueCiGateResponse(
        issue=_build_issue_response(db, anomaly),
        ci_gate=_ci_gate_proof_from_run(run),
    )


@router.patch("/{issue_id}/triage", response_model=IssueResponse)
@limiter.limit("60/minute")
def update_issue_triage_endpoint(
    request: Request,
    issue_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
    updates: dict[str, str | None] = {}
    if "assigned_to" in body:
        updates["assigned_to"] = _optional_trimmed_text(
            body.get("assigned_to"),
            max_len=120,
            field_name="assigned_to",
        )
    if "deploy_pr_url" in body:
        updates["deploy_pr_url"] = _optional_deploy_url(body.get("deploy_pr_url"))

    _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    updated = update_issue_triage(
        db,
        project_id=tenant_id,
        issue_id=issue_id,
        **updates,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, updated)


@router.post("/{issue_id}/resolve", response_model=IssueResponse)
@limiter.limit("30/minute")
def resolve_issue_endpoint(
    request: Request,
    issue_id: str,
    body: IssueResolveRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
    _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    resolved = resolve_issue(
        db,
        project_id=tenant_id,
        issue_id=issue_id,
        fix_id=body.fix_id,
        resolution_source=body.resolution_source,
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, resolved)


@router.post("/{issue_id}/ignore", response_model=IssueResponse)
@limiter.limit("30/minute")
def ignore_issue_endpoint(
    request: Request,
    issue_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
    _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    ignored = ignore_issue(db, project_id=tenant_id, issue_id=issue_id)
    if ignored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, ignored)
