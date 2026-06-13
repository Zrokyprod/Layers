from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.issue_schemas import (
    IssueBlastRadius,
    IssueCiGateProof,
    IssueEvidenceTrace,
    IssueGoldenProof,
    IssueProofSnapshot,
    IssueReplayProof,
    IssueResponse,
)
from app.db.models import (
    Anomaly,
    Call,
    GoldenSet,
    GoldenTrace,
    IssueOccurrence,
    ReplayJob,
    ReplayRun,
    ReplayRunTrace,
)
from app.services.goldens import count_traces
from app.services.issue_occurrences import IssueOccurrenceStats, issue_occurrence_stats
from app.services.issue_projection import IssueProjection, issue_projection_from_anomaly
from app.services.replay_runs import (
    build_summary_url,
    normalize_replay_mode,
    parse_summary,
)

_MAX_EVIDENCE_TRACES = 3


def _severity_rank(severity: str | None) -> int:
    return {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }.get((severity or "").lower(), 0)


def _priority_score(issue: IssueProjection) -> float:
    return round(
        (_severity_rank(issue.severity) * 1000.0)
        + (float(issue.blast_radius_usd or 0) * 25.0)
        + min(int(issue.occurrence_count or 0), 500),
        4,
    )

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

    occurrence_call_ids = [
        call_id
        for call_id in db.execute(
            select(IssueOccurrence.call_id)
            .where(
                IssueOccurrence.project_id == issue.project_id,
                IssueOccurrence.issue_id == issue.id,
                IssueOccurrence.call_id.is_not(None),
            )
            .order_by(IssueOccurrence.occurred_at.desc(), IssueOccurrence.id.desc())
            .limit(_MAX_EVIDENCE_TRACES)
        ).scalars().all()
        if call_id
    ]
    if occurrence_call_ids:
        occurrence_calls = db.execute(
            select(Call).where(
                Call.project_id == issue.project_id,
                Call.id.in_(occurrence_call_ids),
            )
        ).scalars().all()
        by_id = {call.id: call for call in occurrence_calls}
        for call_id in occurrence_call_ids:
            call = by_id.get(call_id)
            if call is None or call.id in seen:
                continue
            calls.append(call)
            seen.add(call.id)
        if calls:
            return calls[:_MAX_EVIDENCE_TRACES]

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


def _issue_occurrence_stats_or_fallback(
    db: Session,
    issue: IssueProjection,
) -> IssueOccurrenceStats:
    stats = issue_occurrence_stats(db, project_id=issue.project_id, issue_id=issue.id)
    if stats.occurrence_count > 0:
        return stats
    fallback = int(issue.occurrence_count or 0)
    return IssueOccurrenceStats(
        occurrence_count=fallback,
        affected_trace_count=fallback,
        affected_user_count=0,
    )


def _what_happened(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    calls: list[Call],
) -> str:
    explicit = _first_text((evidence,), "what_happened", "summary", "title")
    if explicit:
        return explicit
    return _issue_title(issue, evidence, calls)


def _why_it_matters(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    stats: IssueOccurrenceStats,
) -> str:
    explicit = _first_text((evidence,), "why_it_matters", "impact", "user_impact")
    if explicit:
        return explicit
    users = f"{stats.affected_user_count} users" if stats.affected_user_count else "unknown user count"
    return (
        f"{stats.affected_trace_count} traces are grouped under this root cause "
        f"with {users}; replay coverage is needed before the same failure can be blocked."
    )


def _suspected_introduced_version(
    evidence: Mapping[str, Any],
    calls: list[Call],
) -> str | None:
    explicit = _first_text((evidence,), "suspected_introduced_version")
    if explicit:
        return explicit
    version_evidence = evidence.get("version_evidence")
    sources: list[Mapping[str, Any]] = []
    if isinstance(version_evidence, Mapping):
        sources.append(version_evidence)
    for call in calls:
        payload, metadata = _call_context(call)
        sources.extend([payload, metadata])
        if isinstance(payload.get("versions"), Mapping):
            sources.append(payload["versions"])  # type: ignore[arg-type]
        if isinstance(metadata.get("versions"), Mapping):
            sources.append(metadata["versions"])  # type: ignore[arg-type]
    for key in ("deployment_id", "code_sha", "prompt_version", "model_version", "tool_schema_version", "rag_version"):
        value = _first_text(tuple(sources), key) if sources else None
        if value:
            return f"{key}:{value[:16]}"
    return None


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
    if code == "UNSAFE_ACTION":
        return f"{agent} attempted an unsafe action"
    if code == "TASK_OUTCOME_FAILURE":
        return f"{agent} failed the business outcome"
    if "RETRIEVAL" in code or "RAG" in code:
        target = _context_value(evidence, calls, "missing_document", "missing_doc", "document_type")
        if target:
            return f"RAG retrieval is missing {target}"
        if code == "RAG_GROUNDING_FAILURE":
            return f"{agent} answer is not grounded"
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
    if code == "UNSAFE_ACTION":
        return "A sensitive action path did not have trustworthy policy approval evidence."
    if code == "TASK_OUTCOME_FAILURE":
        return "The model call completed but the captured business outcome failed."
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
        if run_trace.status == "not_verified":
            return "not_verified"
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
    replay_mode = normalize_replay_mode(str(
        summary.get("requested_replay_mode")
        or summary.get("replay_mode")
        or "stub"
    ))
    verification_status = str(summary.get("verification_status") or "")
    if summary.get("verified_fix") is True:
        return "verified_fix"
    if replay_mode == "stub":
        return "sanity_replay_passed"
    if verification_status == "not_verified":
        return "not_verified"
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
    if code == "UNSAFE_ACTION":
        return f"{replay_prefix}add a policy approval assertion before allowing this action path."
    if code == "TASK_OUTCOME_FAILURE":
        return f"{replay_prefix}assert the business outcome in replay, not just the final answer text."
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


def _recommended_next_action_for_issue(
    issue: IssueProjection,
    evidence: Mapping[str, Any],
    replay_status: str,
) -> str:
    explicit = _first_text(
        (evidence,),
        "recommended_next_action",
        "next_action",
        "fix_primary",
    )
    if explicit:
        return explicit
    return _recommended_next_action(issue, replay_status)


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
    stats = _issue_occurrence_stats_or_fallback(db, issue)
    affected_workflow = _context_value(evidence, calls, "workflow_name", "workflow")
    replay_status = _replay_coverage_status(db, issue)
    what_happened = _what_happened(issue, evidence, calls)
    why_it_matters = _why_it_matters(issue, evidence, stats)
    suspected_version = _suspected_introduced_version(evidence, calls)
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
        what_happened=what_happened,
        why_it_matters=why_it_matters,
        affected_trace_count=stats.affected_trace_count,
        affected_user_count=stats.affected_user_count,
        suspected_introduced_version=suspected_version,
        blast_radius=IssueBlastRadius(
            affected_traces=stats.affected_trace_count,
            affected_users=stats.affected_user_count,
            cost_usd=float(issue.blast_radius_usd or 0),
            severity=issue.severity,
        ),
        root_cause=_root_cause(issue, evidence, calls),
        evidence_traces=_build_evidence_traces(issue, evidence, calls),
        cost_impact_usd=float(issue.blast_radius_usd or 0),
        user_impact=_user_impact(issue),
        replay_coverage_status=replay_status,
        recommended_next_action=_recommended_next_action_for_issue(issue, evidence, replay_status),
        priority_score=_priority_score(issue),
        proof=_issue_proof_snapshot(db, issue),
    )
