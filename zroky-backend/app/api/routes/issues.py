"""
GET /v1/issues - product-level issue triage.

The legacy issues table stores grouped detector rows. This route projects those
rows into the object the dashboard needs: a small set of plain-English product
problems with evidence, impact, replay coverage, and the next action.
"""
from __future__ import annotations

import base64
import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import Call, GoldenTrace, Issue, ReplayJob, ReplayRun, ReplayRunTrace
from app.db.session import get_db_session
from app.services.issues import VALID_STATUSES, ignore_issue, resolve_issue

router = APIRouter(prefix="/v1/issues")
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 100
_MAX_EVIDENCE_TRACES = 3


class IssueEvidenceTrace(BaseModel):
    call_id: str | None
    trace_id: str | None
    workflow_name: str | None
    prompt_version: str | None
    model: str | None
    provider: str | None
    status: str | None
    latency_ms: float | None
    cost_usd: float
    created_at: datetime | None
    evidence_summary: str | None


class IssueResponse(BaseModel):
    id: str
    project_id: str
    failure_code: str
    prompt_fingerprint: str | None
    agent_name: str | None
    status: str
    severity: str
    occurrence_count: int
    blast_radius_usd: float
    first_seen_at: datetime
    last_seen_at: datetime
    sample_call_id: str | None
    sample_diagnosis_id: str | None
    last_fix_id: str | None
    resolved_at: datetime | None
    resolution_source: str | None
    created_at: datetime
    updated_at: datetime

    # Product-level projection used by the dashboard.
    title: str
    affected_agent: str | None
    affected_workflow: str | None
    root_cause: str
    evidence_traces: list[IssueEvidenceTrace]
    cost_impact_usd: float
    user_impact: str
    replay_coverage_status: str
    recommended_next_action: str
    priority_score: float


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    next_cursor: str | None
    total_in_page: int


class IssueResolveRequest(BaseModel):
    fix_id: str | None = None
    resolution_source: str = "manual"


def _severity_rank(severity: str | None) -> int:
    return {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }.get((severity or "").lower(), 0)


def _severity_rank_expr():
    return case(
        (Issue.severity == "critical", 4),
        (Issue.severity == "high", 3),
        (Issue.severity == "medium", 2),
        (Issue.severity == "low", 1),
        else_=0,
    )


def _priority_score(issue: Issue) -> float:
    return round(
        (_severity_rank(issue.severity) * 1000.0)
        + (float(issue.blast_radius_usd or 0) * 25.0)
        + min(int(issue.occurrence_count or 0), 500),
        4,
    )


def _encode_cursor(issue: Issue) -> str:
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


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _deep_first_text(source: Mapping[str, Any], keys: tuple[str, ...], depth: int = 0) -> str | None:
    if depth > 2:
        return None
    for key in keys:
        if key in source:
            text = _as_text(source.get(key))
            if text:
                return text
    for value in source.values():
        if isinstance(value, Mapping):
            nested = _deep_first_text(value, keys, depth + 1)
            if nested:
                return nested
    return None


def _first_text(sources: tuple[Mapping[str, Any], ...], *keys: str) -> str | None:
    key_tuple = tuple(keys)
    for source in sources:
        text = _deep_first_text(source, key_tuple)
        if text:
            return text
    return None


def _display_name(name: str | None, fallback: str = "Agent") -> str:
    text = (name or "").replace("_", " ").replace("-", " ").strip()
    if not text:
        return fallback
    return text[:1].upper() + text[1:]


def _evidence_summary(evidence: Mapping[str, Any]) -> str | None:
    return _first_text(
        (evidence,),
        "summary",
        "root_cause",
        "failure_reason",
        "reason",
        "message",
        "explanation",
    )


def _call_context(call: Call | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if call is None:
        return {}, {}
    return _safe_json_object(call.payload_json), _safe_json_object(call.metadata_json)


def _context_value(
    evidence: Mapping[str, Any],
    calls: list[Call],
    *keys: str,
) -> str | None:
    sources: list[Mapping[str, Any]] = [evidence]
    for call in calls:
        payload, metadata = _call_context(call)
        sources.extend([payload, metadata])
    return _first_text(tuple(sources), *keys)


def _load_evidence_calls(db: Session, issue: Issue) -> list[Call]:
    calls: list[Call] = []
    seen: set[str] = set()

    if issue.sample_call_id:
        sample = db.execute(
            select(Call).where(
                Call.project_id == issue.project_id,
                Call.id == issue.sample_call_id,
            )
        ).scalar_one_or_none()
        if sample is not None:
            calls.append(sample)
            seen.add(sample.id)

    conditions = [Call.project_id == issue.project_id]
    if issue.agent_name:
        conditions.append(Call.agent_name == issue.agent_name)

    candidates = db.execute(
        select(Call)
        .where(*conditions)
        .order_by(Call.created_at.desc(), Call.id.desc())
        .limit(50)
    ).scalars().all()

    for call in candidates:
        if call.id in seen:
            continue
        if issue.prompt_fingerprint:
            payload, metadata = _call_context(call)
            fp = _first_text((payload, metadata), "prompt_fingerprint")
            if fp != issue.prompt_fingerprint:
                continue
        calls.append(call)
        seen.add(call.id)
        if len(calls) >= _MAX_EVIDENCE_TRACES:
            break

    return calls[:_MAX_EVIDENCE_TRACES]


def _trace_from_call(
    call: Call,
    evidence: Mapping[str, Any],
    summary: str | None,
) -> IssueEvidenceTrace:
    payload, metadata = _call_context(call)
    return IssueEvidenceTrace(
        call_id=call.id,
        trace_id=_first_text((payload, metadata, evidence), "trace_id"),
        workflow_name=_first_text((payload, metadata, evidence), "workflow_name", "workflow"),
        prompt_version=_first_text((payload, metadata, evidence), "prompt_version", "prompt_id"),
        model=call.model,
        provider=call.provider,
        status=call.status,
        latency_ms=float(call.latency_ms) if call.latency_ms is not None else None,
        cost_usd=float(call.cost_total or 0),
        created_at=call.created_at,
        evidence_summary=summary,
    )


def _fallback_trace(issue: Issue, evidence: Mapping[str, Any], summary: str | None) -> IssueEvidenceTrace:
    return IssueEvidenceTrace(
        call_id=issue.sample_call_id,
        trace_id=_first_text((evidence,), "trace_id"),
        workflow_name=_first_text((evidence,), "workflow_name", "workflow"),
        prompt_version=_first_text((evidence,), "prompt_version", "prompt_id"),
        model=_first_text((evidence,), "model"),
        provider=_first_text((evidence,), "provider"),
        status=None,
        latency_ms=None,
        cost_usd=0.0,
        created_at=issue.last_seen_at,
        evidence_summary=summary,
    )


def _build_evidence_traces(issue: Issue, evidence: Mapping[str, Any], calls: list[Call]) -> list[IssueEvidenceTrace]:
    summary = _evidence_summary(evidence)
    traces = [_trace_from_call(call, evidence, summary) for call in calls]
    if traces:
        return traces
    if issue.sample_call_id or summary:
        return [_fallback_trace(issue, evidence, summary)]
    return []


def _issue_title(issue: Issue, evidence: Mapping[str, Any], calls: list[Call]) -> str:
    code = issue.failure_code.upper()
    agent = _display_name(issue.agent_name)
    workflow = _context_value(evidence, calls, "workflow_name", "workflow")
    prompt_version = _context_value(evidence, calls, "prompt_version", "prompt_id")

    if "TOOL" in code:
        return f"{agent} is selecting the wrong tool"
    if "RETRIEVAL" in code or "RAG" in code:
        target = _context_value(evidence, calls, "missing_document", "missing_doc", "document_type")
        if target:
            return f"RAG retrieval is missing {target}"
        return "RAG retrieval is missing required context"
    if code == "SCHEMA_VIOLATION":
        if prompt_version:
            return f"Prompt {prompt_version} increased schema failures"
        return f"{agent} is returning schema-invalid output"
    if code == "LOOP_DETECTED":
        return f"{agent} is stuck in a repeated loop"
    if code == "COST_SPIKE":
        return f"{agent} cost increased above baseline"
    if code == "TOKEN_USAGE_DRIFT":
        return f"{agent} token usage drifted above baseline"
    if code == "TOKEN_OVERFLOW":
        return f"{agent} is exceeding the model context window"
    if code == "RATE_LIMIT":
        return f"{agent} is hitting provider rate limits"
    if code == "AUTH_FAILURE":
        return "Provider authentication is failing"
    if code == "PROVIDER_ERROR":
        return f"{agent} is failing on provider errors"
    if code in {"LATENCY_ANOMALY", "LATENCY_DRIFT"}:
        target = _display_name(workflow, agent)
        return f"{target} latency increased above baseline"
    if code == "ERROR_RATE_DRIFT":
        return f"{agent} error rate increased above baseline"
    if code == "EMPTY_OUTPUT":
        return f"{agent} is returning empty answers"
    if code == "OUTPUT_TRUNCATED":
        return f"{agent} output is being cut off"
    if code == "OUTPUT_LENGTH_DRIFT":
        return f"{agent} answer length changed unexpectedly"
    if code == "REPEATED_OUTPUT":
        return f"{agent} is repeating the same answer"
    if code == "HALLUCINATION_RISK":
        return f"{agent} is producing unsupported answers"
    if code == "ACCURACY_REGRESSION":
        return f"{agent} answer quality regressed"
    return f"{agent} has recurring {code.replace('_', ' ').lower()}"


def _root_cause(issue: Issue, evidence: Mapping[str, Any], calls: list[Call]) -> str:
    explicit = _first_text(
        (evidence,),
        "root_cause",
        "failure_reason",
        "reason",
        "summary",
        "explanation",
    )
    if explicit:
        return explicit

    code = issue.failure_code.upper()
    prompt_version = _context_value(evidence, calls, "prompt_version", "prompt_id")
    workflow = _context_value(evidence, calls, "workflow_name", "workflow")
    agent = _display_name(issue.agent_name).lower()

    if "TOOL" in code:
        return "Tool choice is unstable for the affected traces; the tool description or argument schema needs tightening."
    if "RETRIEVAL" in code or "RAG" in code:
        return "The retriever did not return required context before the model answered."
    if code == "SCHEMA_VIOLATION":
        suffix = f" after prompt {prompt_version}" if prompt_version else ""
        return f"Responses are failing the expected output schema{suffix}."
    if code == "LOOP_DETECTED":
        return "The agent repeated the same step/output pattern and did not converge."
    if code == "COST_SPIKE":
        return "Cost rose above the rolling baseline, usually from prompt bloat, larger context, retries, or extra tool calls."
    if code == "TOKEN_USAGE_DRIFT":
        return "Token usage changed materially versus the recent baseline."
    if code == "TOKEN_OVERFLOW":
        return "Prompt plus retrieved context exceeded the model context window."
    if code == "RATE_LIMIT":
        return "Provider quota or RPM/TPM limits are being hit in production traffic."
    if code == "AUTH_FAILURE":
        return "Provider credentials are missing, expired, or rejected."
    if code == "PROVIDER_ERROR":
        return "The upstream provider returned unexpected failures for the affected calls."
    if code in {"LATENCY_ANOMALY", "LATENCY_DRIFT"}:
        name = workflow or agent
        return f"{name} latency is above the expected baseline."
    if code == "ERROR_RATE_DRIFT":
        return "Recent failures are above the normal error-rate baseline."
    if code == "EMPTY_OUTPUT":
        return "The provider call succeeded, but the captured response body was blank."
    if code == "OUTPUT_TRUNCATED":
        return "The response stopped before completion, most likely because max_tokens or provider stop behavior cut it off."
    if code == "OUTPUT_LENGTH_DRIFT":
        return "Completion length shifted from baseline, usually from prompt/config drift."
    if code == "REPEATED_OUTPUT":
        return "Distinct inputs are receiving repeated output, which points to cache, state, or prompt collapse."
    if code == "HALLUCINATION_RISK":
        return "The answer is not sufficiently grounded in retrieved or tool evidence."
    if code == "ACCURACY_REGRESSION":
        return "Judge or replay evidence indicates answer quality dropped versus expected behavior."
    return "The same failure pattern is recurring across grouped traces."


def _user_impact(issue: Issue) -> str:
    count = int(issue.occurrence_count or 0)
    cost = float(issue.blast_radius_usd or 0)
    call_word = "call" if count == 1 else "calls"
    if cost > 0:
        return f"{count} affected {call_word}, ${cost:.2f} estimated wasted spend."
    return f"{count} affected {call_word}; cost impact is not yet measured."


def _replay_coverage_status(db: Session, issue: Issue) -> str:
    if not issue.sample_call_id:
        return "not_covered"

    golden = db.execute(
        select(GoldenTrace)
        .where(
            GoldenTrace.project_id == issue.project_id,
            GoldenTrace.call_id == issue.sample_call_id,
        )
        .order_by(GoldenTrace.created_at.desc(), GoldenTrace.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if golden is not None:
        latest_run = db.execute(
            select(ReplayRun)
            .where(
                ReplayRun.project_id == issue.project_id,
                ReplayRun.golden_set_id == golden.golden_set_id,
            )
            .order_by(ReplayRun.created_at.desc(), ReplayRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_run is not None and latest_run.status in {"pending", "running"}:
            return "replay_running"
        run_trace = db.execute(
            select(ReplayRunTrace)
            .where(
                ReplayRunTrace.project_id == issue.project_id,
                ReplayRunTrace.golden_trace_id == golden.id,
            )
            .order_by(ReplayRunTrace.created_at.desc(), ReplayRunTrace.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if run_trace is None:
            return "covered_not_run"
        if run_trace.status == "pass":
            return _mode_aware_replay_pass_status(db, run_trace)
        if run_trace.status in {"fail", "error"}:
            return "covered_failed"
        return "covered_not_run"

    replay_job = db.execute(
        select(ReplayJob)
        .where(
            ReplayJob.tenant_id == issue.project_id,
            ReplayJob.call_id == issue.sample_call_id,
        )
        .order_by(ReplayJob.created_at.desc(), ReplayJob.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if replay_job is not None:
        if replay_job.status == "pass":
            return "covered_passed"
        if replay_job.status in {"fail", "error"}:
            return "covered_failed"
        return "replay_running"

    if issue.last_fix_id:
        return "fix_pending_replay"
    return "not_covered"


def _mode_aware_replay_pass_status(db: Session, run_trace: ReplayRunTrace) -> str:
    run = db.execute(
        select(ReplayRun).where(
            ReplayRun.project_id == run_trace.project_id,
            ReplayRun.id == run_trace.replay_run_id,
        )
    ).scalar_one_or_none()
    if run is None:
        return "covered_passed"

    summary = _safe_json_object(run.summary_json)
    replay_mode = str(
        summary.get("requested_replay_mode")
        or summary.get("replay_mode")
        or "stub"
    )
    verification_status = str(summary.get("verification_status") or "")
    if summary.get("verified_fix") is True:
        return "verified_fix"
    if replay_mode == "stub":
        return "sanity_replay_passed"
    if verification_status == "real_comparison_missing_tool_proof":
        return "real_replay_missing_tool_proof"
    return "real_replay_passed"


def _recommended_next_action(issue: Issue, replay_status: str) -> str:
    code = issue.failure_code.upper()
    if replay_status in {"not_covered", "fix_pending_replay"}:
        replay_prefix = "Add this evidence trace to replay coverage, then "
    elif replay_status == "sanity_replay_passed":
        replay_prefix = "Promote the sanity replay to mocked-tool or shadow mode, then "
    elif replay_status == "real_replay_missing_tool_proof":
        replay_prefix = "Capture missing tool spans before trusting this replay, then "
    else:
        replay_prefix = "Use the covered replay trace to "

    if "TOOL" in code:
        return f"{replay_prefix}tighten tool descriptions and argument schema before redeploy."
    if "RETRIEVAL" in code or "RAG" in code:
        return f"{replay_prefix}verify the missing docs are retrieved in top-k before redeploy."
    if code == "SCHEMA_VIOLATION":
        return f"{replay_prefix}run the prompt version against schema golden traces and add a stricter output guard."
    if code == "LOOP_DETECTED":
        return f"{replay_prefix}add a max-step guard and stop condition for the affected agent."
    if code in {"COST_SPIKE", "TOKEN_USAGE_DRIFT"}:
        return f"{replay_prefix}compare prompt/context diff, cap fan-out, and confirm cost returns to baseline."
    if code == "TOKEN_OVERFLOW":
        return f"{replay_prefix}trim retrieved context or route to a larger context model."
    if code == "RATE_LIMIT":
        return "Throttle requests, add backoff, and replay once provider quota behavior is stable."
    if code == "AUTH_FAILURE":
        return "Rotate the provider key, verify key-vault configuration, and rerun the failing trace."
    if code == "PROVIDER_ERROR":
        return "Enable fallback/backoff for this provider and replay the failing trace."
    if code in {"LATENCY_ANOMALY", "LATENCY_DRIFT"}:
        return f"{replay_prefix}profile slow tool/provider spans and set a latency budget."
    if code == "ERROR_RATE_DRIFT":
        return f"{replay_prefix}isolate the deploy or provider change that raised the error rate."
    if code == "EMPTY_OUTPUT":
        return f"{replay_prefix}add an empty-response guard and retry policy."
    if code == "OUTPUT_TRUNCATED":
        return f"{replay_prefix}increase max_tokens or adjust stop conditions."
    if code == "OUTPUT_LENGTH_DRIFT":
        return f"{replay_prefix}compare prompt/output contract changes against baseline."
    if code == "REPEATED_OUTPUT":
        return f"{replay_prefix}check cache keys and agent state reset between calls."
    if code == "HALLUCINATION_RISK":
        return f"{replay_prefix}require citations/tool evidence before the final answer."
    if code == "ACCURACY_REGRESSION":
        return f"{replay_prefix}bisect prompt/model changes and block deploy until replay passes."
    return f"{replay_prefix}validate the grouped failure and ship the smallest targeted fix."


def _build_issue_response(db: Session, issue: Issue) -> IssueResponse:
    evidence = _safe_json_object(issue.sample_evidence_json)
    calls = _load_evidence_calls(db, issue)
    affected_workflow = _context_value(evidence, calls, "workflow_name", "workflow")
    replay_status = _replay_coverage_status(db, issue)
    return IssueResponse(
        id=issue.id,
        project_id=issue.project_id,
        failure_code=issue.failure_code,
        prompt_fingerprint=issue.prompt_fingerprint,
        agent_name=issue.agent_name,
        status=issue.status,
        severity=issue.severity,
        occurrence_count=int(issue.occurrence_count or 0),
        blast_radius_usd=float(issue.blast_radius_usd or 0),
        first_seen_at=issue.first_seen_at,
        last_seen_at=issue.last_seen_at,
        sample_call_id=issue.sample_call_id,
        sample_diagnosis_id=issue.sample_diagnosis_id,
        last_fix_id=issue.last_fix_id,
        resolved_at=issue.resolved_at,
        resolution_source=issue.resolution_source,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        title=_issue_title(issue, evidence, calls),
        affected_agent=issue.agent_name,
        affected_workflow=affected_workflow,
        root_cause=_root_cause(issue, evidence, calls),
        evidence_traces=_build_evidence_traces(issue, evidence, calls),
        cost_impact_usd=float(issue.blast_radius_usd or 0),
        user_impact=_user_impact(issue),
        replay_coverage_status=replay_status,
        recommended_next_action=_recommended_next_action(issue, replay_status),
        priority_score=_priority_score(issue),
    )


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
    if status_filter is not None and status_filter not in VALID_STATUSES and status_filter != "all":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: open, resolved, ignored, all",
        )

    conditions = [Issue.project_id == tenant_id]

    if status_filter and status_filter != "all":
        conditions.append(Issue.status == status_filter)
    if failure_code:
        conditions.append(Issue.failure_code == failure_code.upper())
    if agent_name:
        conditions.append(Issue.agent_name == agent_name)
    if severity:
        conditions.append(Issue.severity == severity.lower())
    if has_fix is True:
        conditions.append(Issue.last_fix_id.isnot(None))
    elif has_fix is False:
        conditions.append(Issue.last_fix_id.is_(None))

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
            cursor_blast = float(decoded["b"])
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
                and_(rank_expr == cursor_rank, Issue.blast_radius_usd < cursor_blast),
                and_(
                    rank_expr == cursor_rank,
                    Issue.blast_radius_usd == cursor_blast,
                    Issue.occurrence_count < cursor_count,
                ),
                and_(
                    rank_expr == cursor_rank,
                    Issue.blast_radius_usd == cursor_blast,
                    Issue.occurrence_count == cursor_count,
                    Issue.last_seen_at < cursor_ts,
                ),
                and_(
                    rank_expr == cursor_rank,
                    Issue.blast_radius_usd == cursor_blast,
                    Issue.occurrence_count == cursor_count,
                    Issue.last_seen_at == cursor_ts,
                    Issue.id < cursor_id,
                ),
            )
        )

    rows = db.execute(
        select(Issue)
        .where(*conditions)
        .order_by(
            rank_expr.desc(),
            Issue.blast_radius_usd.desc(),
            Issue.occurrence_count.desc(),
            Issue.last_seen_at.desc(),
            Issue.id.desc(),
        )
        .limit(limit + 1)
    ).scalars().all()

    has_next = len(rows) > limit
    page = list(rows[:limit])

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
        select(Issue).where(Issue.project_id == tenant_id, Issue.id == issue_id)
    ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, issue)


@router.post("/{issue_id}/resolve", response_model=IssueResponse)
@limiter.limit("30/minute")
def resolve_issue_endpoint(
    request: Request,
    issue_id: str,
    body: IssueResolveRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
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
    ignored = ignore_issue(db, project_id=tenant_id, issue_id=issue_id)
    if ignored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, ignored)
