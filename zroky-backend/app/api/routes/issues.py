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
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.api.routes.issue_schemas import (
    IssueCiGateProof,
    IssueCiGateRequest,
    IssueCiGateResponse,
    IssueEvidenceTrace,
    IssueGoldenProof,
    IssueGoldenPromotionRequest,
    IssueGoldenPromotionResponse,
    IssueListResponse,
    IssueProofSnapshot,
    IssueReplayProof,
    IssueResolveRequest,
    IssueResponse,
)
from app.core.limiter import limiter
from app.db.models import Anomaly, Call, GoldenSet, GoldenTrace, Project, ReplayJob, ReplayRun, ReplayRunTrace
from app.db.session import get_db_session
from app.services.goldens import (
    GoldenSetNameConflict,
    count_traces,
    create_golden_set,
    get_golden_set,
)
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
    parse_summary,
)

router = APIRouter(prefix="/v1/issues")
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 100
_MAX_EVIDENCE_TRACES = 3
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


def _priority_score(issue: IssueProjection) -> float:
    return round(
        (_severity_rank(issue.severity) * 1000.0)
        + (float(issue.blast_radius_usd or 0) * 25.0)
        + min(int(issue.occurrence_count or 0), 500),
        4,
    )


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


def _load_evidence_calls(db: Session, issue: IssueProjection) -> list[Call]:
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


def _fallback_trace(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    summary: str | None,
) -> IssueEvidenceTrace:
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


def _build_evidence_traces(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    calls: list[Call],
) -> list[IssueEvidenceTrace]:
    summary = _evidence_summary(evidence)
    traces = [_trace_from_call(call, evidence, summary) for call in calls]
    if traces:
        return traces
    if issue.sample_call_id or summary:
        return [_fallback_trace(issue, evidence, summary)]
    return []


def _issue_title(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    calls: list[Call],
) -> str:
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


def _root_cause(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    calls: list[Call],
) -> str:
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


def _user_impact(issue: IssueProjection) -> str:
    count = int(issue.occurrence_count or 0)
    cost = float(issue.blast_radius_usd or 0)
    call_word = "call" if count == 1 else "calls"
    if cost > 0:
        return f"{count} affected {call_word}, ${cost:.2f} estimated wasted spend."
    return f"{count} affected {call_word}; cost impact is not yet measured."


def _replay_coverage_status(db: Session, issue: IssueProjection) -> str:
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


def _recommended_next_action(issue: IssueProjection, replay_status: str) -> str:
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


def _latest_replay_for_issue(
    db: Session,
    issue: IssueProjection,
    *,
    golden_set_id: str | None = None,
) -> ReplayRun | None:
    rows = db.execute(
        select(ReplayRun)
        .where(ReplayRun.project_id == issue.project_id)
        .order_by(ReplayRun.created_at.desc(), ReplayRun.id.desc())
        .limit(200)
    ).scalars().all()
    for run in rows:
        summary = parse_summary(run.summary_json)
        if summary.get("source_issue_id") == issue.id:
            return run
        if issue.sample_call_id and summary.get("source_call_id") == issue.sample_call_id:
            return run
        if golden_set_id and run.golden_set_id == golden_set_id:
            return run
    return None


def _latest_golden_for_issue(
    db: Session,
    issue: IssueProjection,
) -> tuple[GoldenTrace | None, GoldenSet | None]:
    if not issue.sample_call_id:
        return None, None
    row = db.execute(
        select(GoldenTrace, GoldenSet)
        .join(GoldenSet, GoldenSet.id == GoldenTrace.golden_set_id)
        .where(
            GoldenTrace.project_id == issue.project_id,
            GoldenTrace.call_id == issue.sample_call_id,
            GoldenSet.project_id == issue.project_id,
        )
        .order_by(GoldenTrace.created_at.desc(), GoldenTrace.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def _latest_ci_gate_for_golden_set(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str | None,
) -> ReplayRun | None:
    if not golden_set_id:
        return None
    return db.execute(
        select(ReplayRun)
        .where(
            ReplayRun.project_id == project_id,
            ReplayRun.golden_set_id == golden_set_id,
            ReplayRun.trigger == "github",
        )
        .order_by(ReplayRun.created_at.desc(), ReplayRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _issue_proof_snapshot(db: Session, issue: IssueProjection) -> IssueProofSnapshot:
    golden_trace, golden_set = _latest_golden_for_issue(db, issue)
    replay_run = _latest_replay_for_issue(
        db,
        issue,
        golden_set_id=golden_set.id if golden_set else None,
    )
    ci_run = _latest_ci_gate_for_golden_set(
        db,
        project_id=issue.project_id,
        golden_set_id=golden_set.id if golden_set else None,
    )

    replay_summary = parse_summary(replay_run.summary_json if replay_run else None)
    replay_mode = None
    if replay_run is not None:
        replay_mode = str(
            replay_summary.get("requested_replay_mode")
            or replay_summary.get("replay_mode")
            or "stub"
        )

    return IssueProofSnapshot(
        replay=IssueReplayProof(
            run_id=replay_run.id if replay_run else None,
            status=replay_run.status if replay_run else None,
            replay_mode=replay_mode,
            verified_fix=bool(replay_summary.get("verified_fix") or False),
            summary_url=build_summary_url(replay_run) if replay_run else None,
            created_at=replay_run.created_at if replay_run else None,
            completed_at=replay_run.completed_at if replay_run else None,
        ),
        golden=IssueGoldenProof(
            golden_set_id=golden_set.id if golden_set else None,
            golden_set_name=golden_set.name if golden_set else None,
            golden_trace_id=golden_trace.id if golden_trace else None,
            status=golden_trace.status if golden_trace else None,
            blocks_ci=bool(golden_set.blocks_ci) if golden_set else False,
            trace_count=count_traces(
                db,
                project_id=issue.project_id,
                golden_set_id=golden_set.id,
            )
            if golden_set
            else 0,
            created_at=golden_trace.created_at if golden_trace else None,
        ),
        ci_gate=IssueCiGateProof(
            run_id=ci_run.id if ci_run else None,
            status=ci_run.status if ci_run else None,
            git_sha=ci_run.git_sha if ci_run else None,
            summary_url=build_summary_url(ci_run) if ci_run else None,
            created_at=ci_run.created_at if ci_run else None,
            completed_at=ci_run.completed_at if ci_run else None,
        ),
    )


def _build_issue_response(db: Session, issue: IssueProjection | Anomaly) -> IssueResponse:
    if isinstance(issue, Anomaly):
        issue = issue_projection_from_anomaly(issue)
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
        assigned_to=issue.assigned_to,
        deploy_pr_url=issue.deploy_pr_url,
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
        proof=_issue_proof_snapshot(db, issue),
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
    if status_filter is not None and status_filter not in PUBLIC_ISSUE_STATUSES and status_filter != "all":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: open, resolved, ignored, all",
        )

    conditions = [Anomaly.project_id == tenant_id]

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
        select(Anomaly).where(Anomaly.project_id == tenant_id, Anomaly.id == issue_id)
    ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _build_issue_response(db, issue)


def _load_anomaly_or_404(db: Session, *, project_id: str, issue_id: str) -> Anomaly:
    anomaly = db.execute(
        select(Anomaly).where(Anomaly.project_id == project_id, Anomaly.id == issue_id)
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
        return provided.strip()

    return json.dumps(
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
    body: IssueGoldenPromotionRequest = Body(default_factory=IssueGoldenPromotionRequest),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
    _: None = Depends(require_entitlement("pilot.goldens_basic")),
) -> IssueGoldenPromotionResponse:
    anomaly = _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    trace = _promote_issue_to_golden(db, anomaly=anomaly, body=body)
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
    body: IssueCiGateRequest = Body(default_factory=IssueCiGateRequest),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
    _: None = Depends(require_entitlement("pro.ci_gate_nonblocking")),
) -> IssueCiGateResponse:
    anomaly = _load_anomaly_or_404(db, project_id=tenant_id, issue_id=issue_id)
    issue = issue_projection_from_anomaly(anomaly)
    if not issue.deploy_pr_url and not body.git_sha:
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

    replay_mode = body.replay_mode.strip() if body.replay_mode else None
    if replay_mode is not None and replay_mode not in VALID_REPLAY_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="replay_mode must be one of: " + ", ".join(sorted(VALID_REPLAY_MODES)),
        )

    pr_number = body.pr_number if body.pr_number is not None else _extract_pr_number(issue.deploy_pr_url)
    try:
        run = dispatch_replay_run(
            db,
            project_id=tenant_id,
            golden_set_id=trace.golden_set_id,
            trigger="github",
            git_sha=body.git_sha,
            branch_name=body.branch_name,
            pr_number=pr_number,
            commit_message=body.commit_message,
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
