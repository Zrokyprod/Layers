from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import DiagnosisJob, TraceRun, TraceSpan
from app.db.session import get_db_session_read
from app.schemas.dashboard import (
    TraceGraphResponse,
    TraceGraphSpanResponse,
    TraceGraphSummaryResponse,
    TraceListItem,
    TraceListResponse,
)


router = APIRouter(prefix="/v1/traces")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    parsed = _as_utc(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def _safe_json(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _safe_dict(raw: str | None) -> dict[str, Any]:
    parsed = _safe_json(raw)
    return parsed if isinstance(parsed, dict) else {}


def _safe_list(raw: str | None) -> list[Any]:
    parsed = _safe_json(raw)
    return parsed if isinstance(parsed, list) else []


def _trace_failure_categories(
    *,
    db: Session,
    tenant_id: str,
    root_call_ids: list[str],
) -> dict[str, str | None]:
    if not root_call_ids:
        return {}
    jobs = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.call_id.in_(root_call_ids),
            )
        ).scalars()
    )
    categories: dict[str, str | None] = {}
    for job in jobs:
        if not job.call_id:
            continue
        result = _safe_dict(job.result_json)
        diagnoses = result.get("diagnoses")
        if isinstance(diagnoses, list) and diagnoses and isinstance(diagnoses[0], dict):
            category = diagnoses[0].get("category")
            categories[str(job.call_id)] = str(category) if category else None
    return categories


def _span_sort_key(span: TraceSpan) -> tuple[int, int, str, str]:
    return (
        0 if span.span_index is not None else 1,
        span.span_index or 0,
        _iso(span.started_at) or "",
        span.span_id,
    )


def _span_response(span: TraceSpan) -> TraceGraphSpanResponse:
    return TraceGraphSpanResponse(
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        call_id=span.call_id,
        event_id=span.event_id,
        span_type=span.span_type,
        span_name=span.span_name,
        span_index=span.span_index,
        agent_name=span.agent_name,
        provider=span.provider,
        model=span.model,
        status=span.status,
        error_code=span.error_code,
        started_at=_iso(span.started_at),
        ended_at=_iso(span.ended_at),
        latency_ms=span.latency_ms,
        cost_usd=float(span.cost_total or 0),
        input=_safe_json(span.input_json),
        output=_safe_json(span.output_json),
        tool=_safe_json(span.tool_json),
        retrieval=_safe_json(span.retrieval_json),
        memory=_safe_json(span.memory_json),
        handoff=_safe_json(span.handoff_json),
        policy=_safe_json(span.policy_json),
        outcome=_safe_json(span.outcome_json),
        versions=_safe_json(span.versions_json),
        raw_payload=_safe_dict(span.payload_json),
    )


def _summary_response(run: TraceRun) -> TraceGraphSummaryResponse:
    return TraceGraphSummaryResponse(
        trace_id=run.trace_id,
        root_span_id=run.root_span_id,
        root_call_id=run.root_call_id,
        status=run.status,
        span_count=run.span_count,
        agent_count=run.agent_count,
        agents=[str(item) for item in _safe_list(run.agents_json)],
        providers=[str(item) for item in _safe_list(run.providers_json)],
        started_at=_iso(run.started_at),
        ended_at=_iso(run.ended_at),
        total_latency_ms=run.total_latency_ms,
        total_cost_usd=float(run.total_cost_usd or 0),
        error_count=run.error_count,
        has_failure=run.has_failure,
        has_outcome=run.has_outcome,
        capture_completeness_score=run.capture_completeness_score,
        completeness_warnings=[str(item) for item in _safe_list(run.completeness_warnings_json)],
        projection_error=run.projection_error,
    )


@router.get("/recent", response_model=TraceListResponse)
def list_recent_traces(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> TraceListResponse:
    window_start = datetime.now(timezone.utc) - timedelta(days=days)
    base_filters = (TraceRun.project_id == tenant_id, TraceRun.started_at >= window_start)

    total = int(
        db.execute(select(func.count()).select_from(TraceRun).where(*base_filters)).scalar_one()
        or 0
    )
    failed_count = int(
        db.execute(
            select(func.count()).select_from(TraceRun).where(*base_filters, TraceRun.has_failure.is_(True))
        ).scalar_one()
        or 0
    )
    multi_agent_count = int(
        db.execute(
            select(func.count()).select_from(TraceRun).where(*base_filters, TraceRun.agent_count > 1)
        ).scalar_one()
        or 0
    )

    runs = list(
        db.execute(
            select(TraceRun)
            .where(*base_filters)
            .order_by(desc(TraceRun.started_at), desc(TraceRun.created_at))
            .limit(limit)
        ).scalars()
    )
    categories = _trace_failure_categories(
        db=db,
        tenant_id=tenant_id,
        root_call_ids=[run.root_call_id for run in runs if run.root_call_id],
    )
    items = [
        TraceListItem(
            trace_id=run.trace_id,
            root_call_id=run.root_call_id or run.root_span_id or run.trace_id,
            call_count=run.span_count,
            agent_count=run.agent_count,
            agents=[str(item) for item in _safe_list(run.agents_json)],
            providers=[str(item) for item in _safe_list(run.providers_json)],
            started_at=_iso(run.started_at) or "",
            last_seen_at=_iso(run.ended_at or run.started_at) or "",
            total_cost_usd=float(run.total_cost_usd or 0),
            has_failure=run.has_failure,
            root_failure_category=categories.get(run.root_call_id or ""),
        )
        for run in runs
    ]
    return TraceListResponse(
        window_days=days,
        total=total,
        multi_agent_count=multi_agent_count,
        failed_count=failed_count,
        items=items,
    )


@router.get("/{trace_id}", response_model=TraceGraphResponse)
def get_trace_graph(
    trace_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> TraceGraphResponse:
    run = db.execute(
        select(TraceRun).where(TraceRun.project_id == tenant_id, TraceRun.trace_id == trace_id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")

    spans = list(
        db.execute(
            select(TraceSpan)
            .where(TraceSpan.project_id == tenant_id, TraceSpan.trace_id == trace_id)
            .order_by(TraceSpan.span_index.asc().nullslast(), TraceSpan.started_at.asc())
        ).scalars()
    )
    spans.sort(key=_span_sort_key)
    nodes = {span.span_id: _span_response(span) for span in spans}
    roots: list[TraceGraphSpanResponse] = []
    for span in spans:
        node = nodes[span.span_id]
        parent = nodes.get(span.parent_span_id or "")
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)

    root = nodes.get(run.root_span_id or "") if run.root_span_id else None
    if root is None and roots:
        root = roots[0]

    user_input: Any | None = None
    system_prompt: Any | None = None
    final_answer: Any | None = None
    business_outcome: Any | None = None
    versions: dict[str, Any] = {}
    raw_payloads: list[dict[str, Any]] = []

    for span in spans:
        payload = _safe_dict(span.payload_json)
        if payload:
            raw_payloads.append(payload)
        input_payload = _safe_dict(span.input_json)
        if user_input is None and input_payload.get("user_input") is not None:
            user_input = input_payload.get("user_input")
        if system_prompt is None and input_payload.get("system_prompt") is not None:
            system_prompt = input_payload.get("system_prompt")
        output_payload = _safe_dict(span.output_json)
        if final_answer is None and output_payload.get("final_answer") is not None:
            final_answer = output_payload.get("final_answer")
        outcome_payload = _safe_json(span.outcome_json)
        if business_outcome is None and outcome_payload is not None:
            business_outcome = outcome_payload
        version_payload = _safe_dict(span.versions_json)
        for key, value in version_payload.items():
            if key not in versions and value not in (None, "", [], {}):
                versions[key] = value

    return TraceGraphResponse(
        summary=_summary_response(run),
        spans=roots,
        root_span=root,
        user_input=user_input,
        system_prompt=system_prompt,
        final_answer=final_answer,
        business_outcome=business_outcome,
        versions=versions,
        masked_raw_payloads=raw_payloads,
    )
