from app.api.routes._internal.analytics_common import *

_FAILED_STATUSES_TRACE = {"failed", "error", "timeout", "auth_failure", "loop_detected"}


@router.get("/traces/recent", response_model=TraceListResponse)
def get_recent_traces(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> TraceListResponse:
    now = utc_now()
    window_start = now - timedelta(days=days)

    calls = list(
        db.execute(
            select(Call)
            .where(
                Call.project_id == tenant_id,
                Call.created_at >= window_start,
            )
            .options(load_only(
                Call.id,
                Call.status,
                Call.provider,
                Call.cost_total,
                Call.created_at,
                Call.payload_json,
            ))
            .order_by(Call.created_at.asc())
        ).scalars().all()
    )

    # Group calls by trace_id extracted from payload_json
    by_trace: dict[str, list[Call]] = {}
    agent_by_call: dict[str, str | None] = {}
    parent_by_call: dict[str, str | None] = {}
    for call in calls:
        payload = safe_load_json(call.payload_json)
        trace_id = payload.get("trace_id") if payload else None
        if not trace_id or not isinstance(trace_id, str):
            continue
        agent_by_call[call.id] = payload.get("agent_name") or None
        parent_by_call[call.id] = payload.get("parent_call_id") or None
        by_trace.setdefault(trace_id, []).append(call)

    # Identify root calls (earliest call with no parent inside same trace) and batch-fetch diagnosis jobs
    root_call_ids: list[str] = []
    root_by_trace: dict[str, str] = {}
    for trace_id, trace_calls in by_trace.items():
        call_id_set = {c.id for c in trace_calls}
        root = None
        for c in sorted(trace_calls, key=lambda x: x.created_at):
            parent = parent_by_call.get(c.id)
            if not parent or parent not in call_id_set:
                root = c
                break
        if root is None:
            root = min(trace_calls, key=lambda x: x.created_at)
        root_by_trace[trace_id] = root.id
        root_call_ids.append(root.id)

    jobs_by_root: dict[str, DiagnosisJob] = {}
    if root_call_ids:
        linked_jobs = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.call_id.in_(root_call_ids),
            )
        ).scalars().all()
        jobs_by_root = {str(job.call_id): job for job in linked_jobs if job.call_id}

    items: list[TraceListItem] = []
    total_multi_agent = 0
    total_failed = 0
    for trace_id, trace_calls in by_trace.items():
        sorted_calls = sorted(trace_calls, key=lambda x: x.created_at)

        # Agents in first-seen chronological order (not alphabetical) so "A → B → C" is meaningful
        seen_agents: list[str] = []
        seen_agent_set: set[str] = set()
        for c in sorted_calls:
            name = agent_by_call.get(c.id)
            if name and name not in seen_agent_set:
                seen_agents.append(name)
                seen_agent_set.add(name)
        agents = seen_agents

        providers: list[str] = sorted(
            {c.provider for c in trace_calls if c.provider and c.provider not in ("unknown", "")}
        )
        has_failure = any(c.status.lower() in _FAILED_STATUSES_TRACE for c in trace_calls)
        total_cost = sum(float(c.cost_total or 0) for c in trace_calls)

        root_call_id = root_by_trace[trace_id]
        root_failure_category: str | None = None
        root_job = jobs_by_root.get(root_call_id)
        if root_job and root_job.result_json:
            result = safe_load_json(root_job.result_json)
            diagnoses = result.get("diagnoses") if result else None
            if isinstance(diagnoses, list) and diagnoses and isinstance(diagnoses[0], dict):
                root_failure_category = diagnoses[0].get("category") or None

        if len(agents) > 1:
            total_multi_agent += 1
        if has_failure:
            total_failed += 1

        items.append(
            TraceListItem(
                trace_id=trace_id,
                root_call_id=root_call_id,
                call_count=len(trace_calls),
                agent_count=len(agents),
                agents=agents,
                providers=providers,
                started_at=sorted_calls[0].created_at.isoformat() + "Z",
                last_seen_at=sorted_calls[-1].created_at.isoformat() + "Z",
                total_cost_usd=round(total_cost, 6),
                has_failure=has_failure,
                root_failure_category=root_failure_category,
            )
        )

    items.sort(key=lambda x: x.last_seen_at, reverse=True)
    total_traces = len(items)
    items = items[:limit]

    return TraceListResponse(
        window_days=days,
        total=total_traces,
        multi_agent_count=total_multi_agent,
        failed_count=total_failed,
        items=items,
    )


@router.get("/traces/{trace_id}", response_model=TraceListItem)
def get_trace_by_id(
    trace_id: str,
    days: int = Query(default=30, ge=1, le=365),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> TraceListItem:
    """Return metadata for a single trace id within a recent window.

    This mirrors the aggregation done by `/traces/recent` but scoped to a single
    `trace_id`. It searches calls and legacy diagnosis jobs within the last
    `days` and returns a `TraceListItem` describing the trace.
    """
    now = utc_now()
    window_start = now - timedelta(days=days)

    calls = list(
        db.execute(
            select(Call)
            .where(
                Call.project_id == tenant_id,
                Call.created_at >= window_start,
            )
            .order_by(Call.created_at.asc())
        ).scalars().all()
    )

    trace_calls: list[Call] = []
    agent_by_call: dict[str, str | None] = {}
    parent_by_call: dict[str, str | None] = {}
    for call in calls:
        payload = safe_load_json(call.payload_json)
        if not payload:
            continue
        candidate = payload.get("trace_id") if isinstance(payload, dict) else None
        if candidate == trace_id:
            trace_calls.append(call)
            agent_by_call[call.id] = payload.get("agent_name") or None
            parent_by_call[call.id] = payload.get("parent_call_id") or None

    # include legacy diagnosis jobs (call-less) in the same window
    legacy_jobs = _fetch_jobs(db, tenant_id=tenant_id, start_time=window_start, end_time=now, legacy_only=True)
    legacy_matches: list[DiagnosisJob] = []
    for job in legacy_jobs:
        payload = safe_load_json(job.payload_json)
        if not payload:
            continue
        candidate = payload.get("trace_id") if isinstance(payload, dict) else None
        if candidate == trace_id:
            legacy_matches.append(job)

    if not trace_calls and not legacy_matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")

    # build chronological ordering across calls and jobs
    combined_items: list[tuple[str, Any]] = []  # (created_at_iso, item)
    for c in trace_calls:
        combined_items.append((c.created_at.isoformat() + "Z", c))
    for j in legacy_matches:
        combined_items.append((j.created_at.isoformat() + "Z", j))
    combined_items.sort(key=lambda t: t[0])

    # Agents (chronological first-seen)
    seen_agents: list[str] = []
    seen_set: set[str] = set()
    for _, item in combined_items:
        if isinstance(item, Call):
            name = agent_by_call.get(item.id)
        else:
            payload = safe_load_json(item.payload_json)
            name = payload.get("agent_name") if isinstance(payload, dict) else None
        if name and name not in seen_set:
            seen_agents.append(name)
            seen_set.add(name)

    providers: set[str] = set()
    total_cost = 0.0
    has_failure = False
    call_count = 0
    for c in trace_calls:
        if c.provider and c.provider not in ("unknown", ""):
            providers.add(c.provider)
        total_cost += float(c.cost_total or 0)
        if str(c.status or "").strip().lower() in _FAILED_STATUSES_TRACE:
            has_failure = True
        call_count += 1
    # legacy jobs may contribute failure info and root failure
    for j in legacy_matches:
        if str(j.status or "").strip().lower() in _FAILED_STATUSES_TRACE:
            has_failure = True

    root_call_id = None
    # determine root among calls if present
    if trace_calls:
        call_id_set = {c.id for c in trace_calls}
        root = None
        for c in sorted(trace_calls, key=lambda x: x.created_at):
            parent = parent_by_call.get(c.id)
            if not parent or parent not in call_id_set:
                root = c
                break
        if root is None:
            root = min(trace_calls, key=lambda x: x.created_at)
        root_call_id = root.id
    else:
        # fallback to first legacy job id
        root_call_id = legacy_matches[0].diagnosis_id if legacy_matches else None

    root_failure_category = None
    root_job = None
    if root_call_id:
        # try to find a linked DiagnosisJob for the root
        root_job = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                or_(DiagnosisJob.call_id == root_call_id, DiagnosisJob.diagnosis_id == root_call_id),
            )
        ).scalar_one_or_none()
        if root_job and root_job.result_json:
            result = safe_load_json(root_job.result_json)
            diagnoses = result.get("diagnoses") if result else None
            if isinstance(diagnoses, list) and diagnoses and isinstance(diagnoses[0], dict):
                root_failure_category = diagnoses[0].get("category") or None

    started_at = combined_items[0][0]
    last_seen_at = combined_items[-1][0]

    return TraceListItem(
        trace_id=trace_id,
        root_call_id=root_call_id or "",
        call_count=call_count + len(legacy_matches),
        agent_count=len(seen_agents),
        agents=seen_agents,
        providers=sorted(list(providers)),
        started_at=started_at,
        last_seen_at=last_seen_at,
        total_cost_usd=round(total_cost, 6),
        has_failure=has_failure,
        root_failure_category=root_failure_category,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
