from app.api.routes._internal.analytics_common import *

def _extract_loop_evidence(result_json: str | None) -> dict[str, Any] | None:
    """Return the first LOOP_DETECTED diagnosis evidence dict, or None."""
    payload = safe_load_json(result_json)
    diagnoses = payload.get("diagnoses", [])
    if not isinstance(diagnoses, list):
        return None
    for diag in diagnoses:
        if isinstance(diag, dict) and str(diag.get("category", "")).upper() == "LOOP_DETECTED":
            ev = diag.get("evidence")
            return ev if isinstance(ev, dict) else {}
    return None


@router.get("/loops/summary", response_model=LoopSummaryResponse)
def get_loop_summary(
    days: int = Query(default=7, ge=1, le=90),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> LoopSummaryResponse:
    now = utc_now()
    start_time = now - timedelta(days=days)

    jobs = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.status.in_(["completed", "done"]),
                DiagnosisJob.created_at >= _as_utc(start_time),
            ).order_by(DiagnosisJob.created_at.desc())
        ).scalars().all()
    )

    # Collect call costs in a single query for all linked call_ids
    call_ids = [j.call_id for j in jobs if j.call_id]
    call_cost_map: dict[str, float] = {}
    if call_ids:
        for call in db.execute(
            select(Call).where(Call.id.in_(call_ids))
        ).scalars().all():
            call_cost_map[call.id] = _stored_cost(call)

    total_loop_count = 0
    estimated_waste_usd = 0.0
    agent_counter: dict[str, int] = defaultdict(int)
    pattern_counter: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)

    for job in jobs:
        evidence = _extract_loop_evidence(job.result_json)
        if evidence is None:
            continue
        total_loop_count += 1
        day_key = _as_utc(job.created_at).date().isoformat()
        by_day[day_key] += 1

        agent = str(evidence.get("agent_name") or job.agent_name or "unknown")
        agent_counter[agent] += 1

        pattern = str(evidence.get("dominant_pattern") or evidence.get("detected_by") or "unknown")
        pattern_counter[pattern] += 1

        if job.call_id:
            estimated_waste_usd += call_cost_map.get(job.call_id, 0.0)

    top_looping_agent = max(agent_counter, key=lambda k: agent_counter[k]) if agent_counter else None
    most_common_pattern = max(pattern_counter, key=lambda k: pattern_counter[k]) if pattern_counter else None

    loop_count_by_day = [
        LoopDayPoint(day=day, count=count)
        for day, count in sorted(by_day.items())
    ]

    return LoopSummaryResponse(
        window_days=days,
        total_loop_count=total_loop_count,
        estimated_waste_usd=round(estimated_waste_usd, 6),
        top_looping_agent=top_looping_agent,
        most_common_pattern=most_common_pattern,
        loop_count_by_day=loop_count_by_day,
    )


@router.get("/loops/incidents", response_model=LoopIncidentsResponse)
def get_loop_incidents(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> LoopIncidentsResponse:
    now = utc_now()
    start_time = now - timedelta(days=days)

    all_jobs = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.status.in_(["completed", "done"]),
                DiagnosisJob.created_at >= _as_utc(start_time),
            ).order_by(DiagnosisJob.created_at.desc())
        ).scalars().all()
    )

    # Filter to LOOP_DETECTED jobs and extract evidence
    loop_jobs: list[tuple[DiagnosisJob, dict[str, Any]]] = []
    for job in all_jobs:
        evidence = _extract_loop_evidence(job.result_json)
        if evidence is not None:
            loop_jobs.append((job, evidence))

    total = len(loop_jobs)
    page_jobs = loop_jobs[offset : offset + limit]

    call_ids = [j.call_id for j, _ in page_jobs if j.call_id]
    call_cost_map: dict[str, float] = {}
    if call_ids:
        for call in db.execute(
            select(Call).where(Call.id.in_(call_ids))
        ).scalars().all():
            call_cost_map[call.id] = _stored_cost(call)

    items: list[LoopIncidentItem] = []
    for job, evidence in page_jobs:
        items.append(
            LoopIncidentItem(
                diagnosis_id=job.diagnosis_id,
                agent_name=str(evidence.get("agent_name") or job.agent_name or "") or None,
                created_at=_as_utc(job.created_at),
                loop_score=round(float(evidence.get("loop_score") or 0.0), 3),
                dominant_pattern=str(evidence.get("dominant_pattern") or evidence.get("detected_by") or "") or None,
                repeat_count=int(evidence.get("repeat_count") or 0),
                no_progress=bool(evidence.get("no_progress", False)),
                estimated_cost_usd=round(call_cost_map.get(job.call_id or "", 0.0), 6),
                retry_suppression_applied=bool(evidence.get("retry_suppression_applied", False)),
            )
        )

    return LoopIncidentsResponse(
        total=total,
        limit=limit,
        offset=offset,
        window_days=days,
        items=items,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
