from app.services._internal.fix_adoption_common import *
from app.services._internal.fix_adoption_events import record_fix_event

def _resolution_correlation(*, resolved: bool, correlation_signal: str) -> str:
    if not resolved:
        return "low"

    normalized = correlation_signal.strip().lower()
    if normalized == "pr_merged":
        return "high"
    if normalized in {"applied", "manual", "manual_applied"}:
        return "medium"
    return "low"


def _stronger_correlation(left: str, right: str) -> str:
    left_normalized = left if left in CORRELATION_RANK else "low"
    right_normalized = right if right in CORRELATION_RANK else "low"
    if CORRELATION_RANK[right_normalized] > CORRELATION_RANK[left_normalized]:
        return right_normalized
    return left_normalized


def _decayed_resolution_truth(
    *,
    since: datetime,
    now: datetime,
    base_confidence: float,
    base_correlation: str,
) -> tuple[float, str, str]:
    stable_age = _as_utc(now) - _as_utc(since)
    if stable_age >= timedelta(days=7):
        return 0.97, "high", "stable_7d"
    if stable_age >= timedelta(hours=24):
        return max(base_confidence, 0.9), _stronger_correlation(base_correlation, "medium"), "stable_24h"
    return base_confidence, base_correlation, "initial_window"


def _attribution_mode(
    db: Session,
    *,
    project_id: str,
    diagnosis_id: str,
    fix_id: str | None,
    target_categories: list[str],
    until: datetime,
) -> str:
    applied_events = list(
        db.execute(
            select(FixEvent).where(
                FixEvent.project_id == project_id,
                FixEvent.event_type.in_(APPLIED_EVENT_TYPES),
                FixEvent.timestamp <= _as_utc(until),
            )
        )
        .scalars()
        .all()
    )
    same_diagnosis_fix_ids = {event.fix_id for event in applied_events if event.diagnosis_id == diagnosis_id}
    if fix_id:
        same_diagnosis_fix_ids.add(fix_id)
    if len(same_diagnosis_fix_ids) > 1:
        return "multi"

    target_set = set(target_categories)
    for event in applied_events:
        if event.diagnosis_id == diagnosis_id:
            continue
        job = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == project_id,
                DiagnosisJob.diagnosis_id == event.diagnosis_id,
            )
        ).scalar_one_or_none()
        if job is not None and target_set.intersection(_extract_job_categories(job)):
            return "ambiguous"

    return "single"


def evaluate_fix_resolution(
    db: Session,
    *,
    project_id: str,
    diagnosis_id: str,
    since: datetime,
    window_calls: int = DEFAULT_RESOLUTION_WINDOW_CALLS,
    window_hours: int = DEFAULT_RESOLUTION_WINDOW_HOURS,
    minimum_observations_threshold: int = DEFAULT_MINIMUM_OBSERVATIONS_THRESHOLD,
    fix_id: str | None = None,
    correlation_signal: str = "unknown",
    now: datetime | None = None,
) -> ResolutionEvaluation:
    bounded_window = max(1, int(window_calls))
    bounded_hours = max(0, int(window_hours))
    minimum_observations = max(1, int(minimum_observations_threshold))
    resolution_window = _resolution_window_label(window_calls=bounded_window, window_hours=bounded_hours)
    source_job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == project_id,
            DiagnosisJob.diagnosis_id == diagnosis_id,
        )
    ).scalar_one_or_none()
    if source_job is None:
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=0.0,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=0,
            recurrence_count=0,
            target_categories=[],
            reason="source_diagnosis_not_found",
        )

    target_categories = sorted(_extract_job_categories(source_job))
    if not target_categories:
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=0.0,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=0,
            recurrence_count=0,
            target_categories=[],
            reason="source_diagnosis_category_unknown",
        )

    since_utc = _as_utc(since)
    calls = list(
        db.execute(
            select(Call)
            .where(
                Call.project_id == project_id,
                Call.created_at > since_utc,
            )
            .order_by(Call.created_at.asc())
            .limit(bounded_window)
        )
        .scalars()
        .all()
    )
    checked_calls = len(calls)
    if checked_calls < minimum_observations:
        confidence = round(min(0.5, 0.1 + (checked_calls / minimum_observations) * 0.4), 2)
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=confidence,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=checked_calls,
            recurrence_count=0,
            target_categories=target_categories,
            reason="insufficient_observations",
        )

    if checked_calls < bounded_window:
        confidence = round(min(0.6, 0.2 + (checked_calls / bounded_window) * 0.4), 2)
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=confidence,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=checked_calls,
            recurrence_count=0,
            target_categories=target_categories,
            reason="insufficient_call_window",
        )

    call_ids = [call.id for call in calls]
    window_jobs = list(
        db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == project_id,
                DiagnosisJob.call_id.in_(call_ids),
            )
        )
        .scalars()
        .all()
    )
    jobs_by_call_id = {job.call_id: job for job in window_jobs if job.call_id}
    if any(
        call_id not in jobs_by_call_id
        or str(jobs_by_call_id[call_id].status).strip().lower() not in DIAGNOSIS_DONE_STATUSES
        for call_id in call_ids
    ):
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=0.4,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=checked_calls,
            recurrence_count=0,
            target_categories=target_categories,
            reason="diagnosis_window_not_complete",
        )

    target_set = set(target_categories)
    recurrence_count = 0
    for job in window_jobs:
        if job.diagnosis_id == diagnosis_id:
            continue
        if target_set.intersection(_extract_job_categories(job)):
            recurrence_count += 1

    if recurrence_count > 0:
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=0.1,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=checked_calls,
            recurrence_count=recurrence_count,
            target_categories=target_categories,
            reason="recurrence_detected",
        )

    now_utc = _as_utc(now or datetime.now(timezone.utc))
    if bounded_hours > 0 and now_utc < since_utc + timedelta(hours=bounded_hours):
        return ResolutionEvaluation(
            resolved=False,
            resolution_confidence=0.6,
            resolution_correlation="low",
            attribution_mode="ambiguous",
            confidence_calibration="not_resolved",
            resolution_window=resolution_window,
            checked_calls=checked_calls,
            recurrence_count=0,
            target_categories=target_categories,
            reason="insufficient_time_window",
        )

    correlation = _resolution_correlation(resolved=True, correlation_signal=correlation_signal)
    confidence, correlation, confidence_calibration = _decayed_resolution_truth(
        since=since_utc,
        now=now_utc,
        base_confidence=0.85,
        base_correlation=correlation,
    )
    attribution_mode = _attribution_mode(
        db,
        project_id=project_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        target_categories=target_categories,
        until=now_utc,
    )
    return ResolutionEvaluation(
        resolved=True,
        resolution_confidence=confidence,
        resolution_correlation=correlation,
        attribution_mode=attribution_mode,
        confidence_calibration=confidence_calibration,
        resolution_window=resolution_window,
        checked_calls=checked_calls,
        recurrence_count=0,
        target_categories=target_categories,
        reason="no_recurrence_in_window",
    )


def mark_resolved_if_no_recurrence(
    db: Session,
    *,
    project_id: str,
    diagnosis_id: str,
    fix_id: str,
    since: datetime,
    window_calls: int = DEFAULT_RESOLUTION_WINDOW_CALLS,
    window_hours: int = DEFAULT_RESOLUTION_WINDOW_HOURS,
    minimum_observations_threshold: int = DEFAULT_MINIMUM_OBSERVATIONS_THRESHOLD,
    correlation_signal: str = "unknown",
    now: datetime | None = None,
) -> tuple[ResolutionEvaluation, FixEvent | None]:
    evaluation = evaluate_fix_resolution(
        db,
        project_id=project_id,
        diagnosis_id=diagnosis_id,
        since=since,
        window_calls=window_calls,
        window_hours=window_hours,
        minimum_observations_threshold=minimum_observations_threshold,
        fix_id=fix_id,
        correlation_signal=correlation_signal,
        now=now,
    )
    if not evaluation.resolved:
        return evaluation, None

    existing = db.execute(
        select(FixEvent).where(
            FixEvent.project_id == project_id,
            FixEvent.fix_id == fix_id,
            FixEvent.event_type == "resolved",
        )
    ).scalar_one_or_none()
    if existing is not None:
        return evaluation, None

    event = record_fix_event(
        db,
        project_id=project_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        event_type="resolved",
        metadata={**evaluation.to_metadata(), "applied_signal": correlation_signal},
        source="system",
    )
    return evaluation, event


__all__ = [name for name in globals() if not name.startswith("__")]
