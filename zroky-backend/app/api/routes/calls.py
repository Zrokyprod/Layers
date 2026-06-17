from datetime import datetime, timedelta, timezone
import csv
import io
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_role
from app.db.models import Call, DiagnosisFeedback, DiagnosisJob
from app.db.session import get_db_session
from app.schemas.dashboard import (
    AdjacentCallItem,
    AdjacentCallsResponse,
    CallTraceTreeResponse,
    CallDetailResponse,
    CallFeedbackSummary,
    CallListItem,
    CallListResponse,
    TraceRootFailureResponse,
    TraceTreeNodeResponse,
)
from app.services.audit_logs import (
    AUDIT_ACTION_DIAGNOSIS_VIEWED,
    create_audit_log_best_effort,
    safe_actor_subject_from_request,
)
from app.services.dashboard_data import (
    build_call_item,
    build_call_item_from_call,
    extract_call_payload,
    extract_payload,
    extract_result,
)
from app.services.privacy import hash_identifier
from app.services.cost_trust import cost_audit_from_call
from app.services.replay_runs import mark_call_as_golden

router = APIRouter(prefix="/v1/calls")
from app.api.routes._internal.calls_helpers import (
    MarkCallGoldenRequest,
    MarkCallGoldenResponse,
    _as_utc,
    _build_trace_tree_node,
    _build_trace_tree_node_from_call,
    _extract_model,
    _extract_root_failure,
    _extract_trace_id,
    _fetch_job_for_call,
    _matches_filter,
    _matches_status_filter,
    _matches_user_filter,
    _normalized_status_filter_values,
    _normalized_user_filter_values,
)

@router.get("", response_model=CallListResponse)
def list_calls(
    status_filter: str | None = Query(default=None, alias="status"),
    model: str | None = Query(default=None),
    user_id: str | None = Query(default=None, alias="user_id"),
    user: str | None = Query(default=None),
    call_type: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    sort_by: str = Query(default="created_at", pattern="^(created_at|cost_usd|total_tokens|latency_ms)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    min_cost_usd: float | None = Query(default=None),
    max_cost_usd: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> CallListResponse:
    effective_user_filter = user_id if user_id is not None else user

    fetch_limit = min(max(limit + offset + 200, 200), 2000)
    call_query = select(Call).where(Call.project_id == tenant_id)
    if start_time is not None:
        call_query = call_query.where(Call.created_at >= _as_utc(start_time))
    if end_time is not None:
        call_query = call_query.where(Call.created_at <= _as_utc(end_time))
    status_values = _normalized_status_filter_values(status_filter)
    if status_values:
        call_query = call_query.where(func.lower(Call.status).in_(status_values))
    if model is not None and model.strip():
        call_query = call_query.where(func.lower(Call.model) == model.strip().lower())
    user_values = _normalized_user_filter_values(effective_user_filter)
    if user_values:
        call_query = call_query.where(func.lower(Call.user_id).in_(user_values))
    if call_type is not None and call_type.strip():
        call_query = call_query.where(
            or_(
                func.lower(Call.call_type) == call_type.strip().lower(),
                Call.call_type.is_(None),
            )
        )
    if agent_name is not None and agent_name.strip():
        call_query = call_query.where(
            func.lower(Call.agent_name).contains(agent_name.strip().lower())
        )
    if min_cost_usd is not None:
        call_query = call_query.where(Call.cost_total >= min_cost_usd)
    if max_cost_usd is not None:
        call_query = call_query.where(Call.cost_total <= max_cost_usd)
    # Dynamic sort
    _sort_col_map = {
        "created_at": Call.created_at,
        "cost_usd": Call.cost_total,
        "total_tokens": Call.total_tokens,
        "latency_ms": Call.latency_ms,
    }
    sort_col = _sort_col_map.get(sort_by, Call.created_at)
    call_query = call_query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc()).limit(fetch_limit)
    calls = list(db.execute(call_query).scalars().all())

    jobs_by_call_id: dict[str, DiagnosisJob] = {}
    if calls:
        call_ids = [call.id for call in calls]
        linked_jobs = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.call_id.in_(call_ids),
            )
        ).scalars().all()
        jobs_by_call_id = {str(job.call_id): job for job in linked_jobs if job.call_id}

    legacy_query = select(DiagnosisJob).where(
        DiagnosisJob.tenant_id == tenant_id,
        DiagnosisJob.call_id.is_(None),
    )
    if start_time is not None:
        legacy_query = legacy_query.where(DiagnosisJob.created_at >= _as_utc(start_time))
    if end_time is not None:
        legacy_query = legacy_query.where(DiagnosisJob.created_at <= _as_utc(end_time))
    legacy_jobs = list(
        db.execute(
            legacy_query.order_by(DiagnosisJob.created_at.desc()).limit(fetch_limit),
        ).scalars().all()
    )

    candidate_items: list[CallListItem] = [
        CallListItem.model_validate(
            build_call_item_from_call(
                call,
                jobs_by_call_id.get(call.id),
                display_currency=display_currency,
            )
        )
        for call in calls
    ]
    candidate_items.extend(
        CallListItem.model_validate(build_call_item(job))
        for job in legacy_jobs
    )
    candidate_items.sort(key=lambda item: _as_utc(item.created_at), reverse=True)

    filtered_items: list[CallListItem] = []
    for item in candidate_items:
        if status_filter and not _matches_status_filter(item.status, status_filter):
            continue
        if not _matches_filter(item.model, model):
            continue
        if not _matches_user_filter(item.user_id, effective_user_filter):
            continue
        if not _matches_filter(item.call_type, call_type):
            continue
        if agent_name and agent_name.strip():
            if not (item.agent_name and agent_name.strip().lower() in item.agent_name.lower()):
                continue
        if min_cost_usd is not None and item.cost_usd < min_cost_usd:
            continue
        if max_cost_usd is not None and item.cost_usd > max_cost_usd:
            continue
        filtered_items.append(item)

    total = len(filtered_items)
    page = filtered_items[offset : offset + limit]

    return CallListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=page,
    )


_CSV_EXPORT_LIMIT = 5000

@router.get("/export/csv")
def export_calls_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    model: str | None = Query(default=None),
    user_id: str | None = Query(default=None, alias="user_id"),
    call_type: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> Response:
    # Reuse list_calls logic with a high limit, no offset
    result = list_calls(
        status_filter=status_filter,
        model=model,
        user_id=user_id,
        user=None,
        call_type=call_type,
        agent_name=agent_name,
        sort_by="created_at",
        sort_order="desc",
        display_currency="USD",
        start_time=start_time,
        end_time=end_time,
        limit=_CSV_EXPORT_LIMIT,
        offset=0,
        tenant_id=tenant_id,
        db=db,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "call_id", "created_at", "provider", "model", "agent_name",
        "user_id", "call_type", "total_tokens", "cost_usd",
        "latency_ms", "status", "error_code",
    ])
    for item in result.items:
        writer.writerow([
            item.call_id,
            item.created_at,
            item.provider or "",
            item.model or "",
            item.agent_name or "",
            item.user_id or "",
            item.call_type or "",
            item.total_tokens,
            item.cost_usd,
            item.latency_ms if item.latency_ms is not None else "",
            item.status,
            item.error_code or "",
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=calls.csv"},
    )


@router.get("/{call_id}/trace-tree", response_model=CallTraceTreeResponse)
def get_call_trace_tree(
    call_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> CallTraceTreeResponse:
    root_call = db.execute(
        select(Call).where(
            Call.project_id == tenant_id,
            Call.id == call_id,
        )
    ).scalar_one_or_none()
    if root_call is not None:
        root_job = _fetch_job_for_call(db, tenant_id=tenant_id, call_id=call_id)
        root_payload = extract_call_payload(root_call)
        root_result = extract_result(root_job) if root_job is not None else {}
        trace_id = _extract_trace_id(root_payload)
        root_failure = _extract_root_failure(root_result)
        fallback_root_node = _build_trace_tree_node_from_call(
            call=root_call,
            job=root_job,
            payload=root_payload,
            result_payload=root_result,
        )

        if trace_id is None:
            return CallTraceTreeResponse(
                call_id=call_id,
                trace_id=None,
                root_failure=root_failure,
                total_downstream_calls=0,
                total_wasted_cost_usd=round(fallback_root_node.wasted_cost_usd, 6),
                root_node=fallback_root_node,
            )

        root_created_at = _as_utc(root_call.created_at)
        window_start = root_created_at - timedelta(days=7)
        window_end = root_created_at + timedelta(days=7)
        candidate_calls = list(
            db.execute(
                select(Call)
                .where(
                    Call.project_id == tenant_id,
                    Call.created_at >= window_start,
                    Call.created_at <= window_end,
                )
                .order_by(Call.created_at.asc())
            ).scalars().all()
        )

        jobs_by_call_id: dict[str, DiagnosisJob] = {}
        if candidate_calls:
            candidate_ids = [call.id for call in candidate_calls]
            linked_jobs = db.execute(
                select(DiagnosisJob).where(
                    DiagnosisJob.tenant_id == tenant_id,
                    DiagnosisJob.call_id.in_(candidate_ids),
                )
            ).scalars().all()
            jobs_by_call_id = {str(job.call_id): job for job in linked_jobs if job.call_id}

        node_map: dict[str, TraceTreeNodeResponse] = {}
        for candidate in candidate_calls:
            payload = extract_call_payload(candidate)
            candidate_trace_id = _extract_trace_id(payload)
            if candidate_trace_id != trace_id:
                continue

            candidate_job = jobs_by_call_id.get(candidate.id)
            result_payload = extract_result(candidate_job) if candidate_job is not None else {}
            node_map[candidate.id] = _build_trace_tree_node_from_call(
                call=candidate,
                job=candidate_job,
                payload=payload,
                result_payload=result_payload,
            )

        if call_id not in node_map:
            node_map[call_id] = fallback_root_node

        children_map: dict[str, list[str]] = {node_id: [] for node_id in node_map.keys()}
        for node_id, node in node_map.items():
            parent_id = node.parent_call_id
            if parent_id and parent_id in node_map and parent_id != node_id:
                children_map[parent_id].append(node_id)

        for parent_id, child_ids in children_map.items():
            child_ids.sort(key=lambda child_id: _as_utc(node_map[child_id].created_at))

        def _build_call_tree(
            node_id: str,
            lineage: set[str] | None = None,
        ) -> TraceTreeNodeResponse:
            node = node_map[node_id]
            lineage_next = set(lineage or set())
            lineage_next.add(node_id)
            child_nodes: list[TraceTreeNodeResponse] = []
            for child_id in children_map.get(node_id, []):
                if child_id in lineage_next:
                    continue
                child_nodes.append(_build_call_tree(child_id, lineage_next))

            return TraceTreeNodeResponse(
                call_id=node.call_id,
                parent_call_id=node.parent_call_id,
                agent_name=node.agent_name,
                provider=node.provider,
                model=node.model,
                cost_confidence=node.cost_confidence,
                status=node.status,
                wasted_cost_usd=node.wasted_cost_usd,
                latency_ms=node.latency_ms,
                error_code=node.error_code,
                created_at=node.created_at,
                children=child_nodes,
            )

        root_node = _build_call_tree(call_id)
        downstream_count = 0
        total_wasted_cost = root_node.wasted_cost_usd

        def _walk_call_tree(node: TraceTreeNodeResponse) -> None:
            nonlocal downstream_count
            nonlocal total_wasted_cost
            for child in node.children:
                downstream_count += 1
                total_wasted_cost += child.wasted_cost_usd
                _walk_call_tree(child)

        _walk_call_tree(root_node)

        return CallTraceTreeResponse(
            call_id=call_id,
            trace_id=trace_id,
            root_failure=root_failure,
            total_downstream_calls=downstream_count,
            total_wasted_cost_usd=round(total_wasted_cost, 6),
            root_node=root_node,
        )

    root_job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.diagnosis_id == call_id,
        )
    ).scalar_one_or_none()
    if root_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    root_payload = extract_payload(root_job)
    root_result = extract_result(root_job)
    trace_id = _extract_trace_id(root_payload)
    root_failure = _extract_root_failure(root_result)
    fallback_root_node = _build_trace_tree_node(job=root_job, payload=root_payload, result_payload=root_result)

    if trace_id is None:
        return CallTraceTreeResponse(
            call_id=call_id,
            trace_id=None,
            root_failure=root_failure,
            total_downstream_calls=0,
            total_wasted_cost_usd=round(fallback_root_node.wasted_cost_usd, 6),
            root_node=fallback_root_node,
        )

    root_created_at = _as_utc(root_job.created_at)
    window_start = root_created_at - timedelta(days=7)
    window_end = root_created_at + timedelta(days=7)
    candidate_jobs = db.execute(
        select(DiagnosisJob)
        .where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.created_at >= window_start,
            DiagnosisJob.created_at <= window_end,
        )
        .order_by(DiagnosisJob.created_at.asc())
    ).scalars().all()

    node_map: dict[str, TraceTreeNodeResponse] = {}
    for candidate in candidate_jobs:
        payload = extract_payload(candidate)
        candidate_trace_id = _extract_trace_id(payload)
        if candidate_trace_id != trace_id:
            continue

        result_payload = extract_result(candidate)
        node_map[candidate.diagnosis_id] = _build_trace_tree_node(
            job=candidate,
            payload=payload,
            result_payload=result_payload,
        )

    if call_id not in node_map:
        node_map[call_id] = fallback_root_node

    children_map: dict[str, list[str]] = {node_id: [] for node_id in node_map.keys()}
    for node_id, node in node_map.items():
        parent_id = node.parent_call_id
        if parent_id and parent_id in node_map and parent_id != node_id:
            children_map[parent_id].append(node_id)

    for parent_id, child_ids in children_map.items():
        child_ids.sort(key=lambda child_id: _as_utc(node_map[child_id].created_at))

    def _build_tree(node_id: str, lineage: set[str] | None = None) -> TraceTreeNodeResponse:
        node = node_map[node_id]
        lineage_next = set(lineage or set())
        lineage_next.add(node_id)
        child_nodes: list[TraceTreeNodeResponse] = []
        for child_id in children_map.get(node_id, []):
            if child_id in lineage_next:
                continue
            child_nodes.append(_build_tree(child_id, lineage_next))

        return TraceTreeNodeResponse(
            call_id=node.call_id,
            parent_call_id=node.parent_call_id,
            agent_name=node.agent_name,
            provider=node.provider,
            model=node.model,
            cost_confidence=node.cost_confidence,
            status=node.status,
            wasted_cost_usd=node.wasted_cost_usd,
            latency_ms=node.latency_ms,
            error_code=node.error_code,
            created_at=node.created_at,
            children=child_nodes,
        )

    root_node = _build_tree(call_id)

    downstream_count = 0
    total_wasted_cost = root_node.wasted_cost_usd

    def _walk(node: TraceTreeNodeResponse) -> None:
        nonlocal downstream_count
        nonlocal total_wasted_cost
        for child in node.children:
            downstream_count += 1
            total_wasted_cost += child.wasted_cost_usd
            _walk(child)

    _walk(root_node)

    return CallTraceTreeResponse(
        call_id=call_id,
        trace_id=trace_id,
        root_failure=root_failure,
        total_downstream_calls=downstream_count,
        total_wasted_cost_usd=round(total_wasted_cost, 6),
        root_node=root_node,
    )


@router.get("/{call_id}/adjacent", response_model=AdjacentCallsResponse)
def get_adjacent_calls(
    call_id: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> AdjacentCallsResponse:
    call = db.execute(
        select(Call).where(Call.project_id == tenant_id, Call.id == call_id)
    ).scalar_one_or_none()

    if call is not None:
        created_at = _as_utc(call.created_at)
        prev_call = db.execute(
            select(Call).where(
                Call.project_id == tenant_id,
                Call.created_at < created_at,
            ).order_by(Call.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        next_call = db.execute(
            select(Call).where(
                Call.project_id == tenant_id,
                Call.created_at > created_at,
            ).order_by(Call.created_at.asc()).limit(1)
        ).scalar_one_or_none()
        return AdjacentCallsResponse(
            prev=AdjacentCallItem(id=prev_call.id, model=prev_call.model, status=prev_call.status) if prev_call else None,
            next=AdjacentCallItem(id=next_call.id, model=next_call.model, status=next_call.status) if next_call else None,
        )

    job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.diagnosis_id == call_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    created_at = _as_utc(job.created_at)
    prev_job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.call_id.is_(None),
            DiagnosisJob.created_at < created_at,
        ).order_by(DiagnosisJob.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    next_job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.call_id.is_(None),
            DiagnosisJob.created_at > created_at,
        ).order_by(DiagnosisJob.created_at.asc()).limit(1)
    ).scalar_one_or_none()

    def _model_from_job(j: DiagnosisJob) -> str | None:
        return _extract_model(extract_payload(j))

    return AdjacentCallsResponse(
        prev=AdjacentCallItem(id=prev_job.diagnosis_id, model=_model_from_job(prev_job), status=prev_job.status) if prev_job else None,
        next=AdjacentCallItem(id=next_job.diagnosis_id, model=_model_from_job(next_job), status=next_job.status) if next_job else None,
    )


@router.post(
    "/{call_id}/mark-golden",
    response_model=MarkCallGoldenResponse,
    status_code=status.HTTP_201_CREATED,
)
def mark_call_golden_route(
    call_id: str,
    body: MarkCallGoldenRequest,
    tenant_id: str = Depends(require_tenant_role("member")),
    db: Session = Depends(get_db_session),
) -> MarkCallGoldenResponse:
    try:
        trace = mark_call_as_golden(
            db,
            project_id=tenant_id,
            call_id=call_id,
            golden_set_id=body.golden_set_id,
            weight=body.weight,
            status=body.status,
            expected_output_text=body.expected_output_text,
            criteria_json=body.criteria_json,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call or golden set not found",
        )
    return MarkCallGoldenResponse.model_validate(trace)


@router.get("/{call_id}", response_model=CallDetailResponse)
def get_call_detail(
    call_id: str,
    request: Request,
    display_currency: str = Query(default="USD", pattern="^(USD|INR|usd|inr)$"),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session),
) -> CallDetailResponse:
    call = db.execute(
        select(Call).where(
            Call.project_id == tenant_id,
            Call.id == call_id,
        )
    ).scalar_one_or_none()
    if call is not None:
        job = _fetch_job_for_call(db, tenant_id=tenant_id, call_id=call_id)
        feedback_rows = db.execute(
            select(DiagnosisFeedback).where(
                DiagnosisFeedback.tenant_id == tenant_id,
                DiagnosisFeedback.diagnosis_id == call_id,
            )
        ).scalars().all()

        helpful_count = sum(1 for row in feedback_rows if row.was_helpful)
        not_helpful_count = len(feedback_rows) - helpful_count

        create_audit_log_best_effort(
            db,
            tenant_id=tenant_id,
            diagnosis_id=call_id,
            action=AUDIT_ACTION_DIAGNOSIS_VIEWED,
            actor_subject=safe_actor_subject_from_request(request),
            metadata={"status": call.status},
        )

        payload = extract_call_payload(call)
        cost_audit = cost_audit_from_call(call, display_currency=display_currency)
        result_payload = extract_result(job) if job is not None else {}
        return CallDetailResponse(
            call=CallListItem.model_validate(
                build_call_item_from_call(call, job, display_currency=display_currency)
            ),
            payload=payload,
            cost_audit=cost_audit,
            diagnosis_result=result_payload or None,
            feedback_summary=CallFeedbackSummary(
                helpful_count=helpful_count,
                not_helpful_count=not_helpful_count,
            ),
        )

    job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == tenant_id,
            DiagnosisJob.diagnosis_id == call_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    feedback_rows = db.execute(
        select(DiagnosisFeedback).where(
            DiagnosisFeedback.tenant_id == tenant_id,
            DiagnosisFeedback.diagnosis_id == call_id,
        )
    ).scalars().all()

    helpful_count = sum(1 for row in feedback_rows if row.was_helpful)
    not_helpful_count = len(feedback_rows) - helpful_count

    create_audit_log_best_effort(
        db,
        tenant_id=tenant_id,
        diagnosis_id=call_id,
        action=AUDIT_ACTION_DIAGNOSIS_VIEWED,
        actor_subject=safe_actor_subject_from_request(request),
        metadata={"status": job.status},
    )

    payload = extract_payload(job)
    cost_audit = payload.get("cost") if isinstance(payload.get("cost"), dict) else None
    result_payload = extract_result(job)
    return CallDetailResponse(
        call=CallListItem.model_validate(build_call_item(job)),
        payload=payload,
        cost_audit=cost_audit,
        diagnosis_result=result_payload or None,
        feedback_summary=CallFeedbackSummary(
            helpful_count=helpful_count,
            not_helpful_count=not_helpful_count,
        ),
    )
