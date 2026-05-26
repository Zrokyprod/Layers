from app.services._internal.fix_adoption_common import *
from app.services._internal.fix_adoption_events import record_fix_event
from app.services._internal.fix_adoption_resolution import (
    _decayed_resolution_truth,
    evaluate_fix_resolution,
)

def _cooldown_scan_start(
    db: Session,
    *,
    project_id: str,
    since: datetime,
    cooldown_calls: int,
    cooldown_minutes: int,
) -> datetime:
    since_utc = _as_utc(since)
    time_cutoff = since_utc + timedelta(minutes=max(0, cooldown_minutes))
    call_cutoff: datetime | None = None

    if cooldown_calls > 0:
        calls = list(
            db.execute(
                select(Call)
                .where(
                    Call.project_id == project_id,
                    Call.created_at > since_utc,
                )
                .order_by(Call.created_at.asc())
                .limit(cooldown_calls)
            )
            .scalars()
            .all()
        )
        if len(calls) >= cooldown_calls:
            call_cutoff = _as_utc(calls[-1].created_at)

    if call_cutoff is None:
        return time_cutoff
    if cooldown_minutes <= 0:
        return call_cutoff
    return min(call_cutoff, time_cutoff)


def _regression_severity(matching_jobs: list[DiagnosisJob]) -> str:
    if len(matching_jobs) >= 3:
        return "major"

    for job in matching_jobs:
        if job.error_message:
            return "major"
        if str(job.status).strip().lower() not in DIAGNOSIS_DONE_STATUSES:
            return "major"

        payload = _safe_json_object(job.result_json)
        diagnoses = payload.get("diagnoses")
        if not isinstance(diagnoses, list):
            continue
        for item in diagnoses:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or item.get("impact") or "").strip().lower()
            if severity in {"major", "high", "critical"}:
                return "major"

    return "minor"


def evaluate_fix_regressions(
    db: Session,
    *,
    project_id: str,
    cooldown_calls: int = DEFAULT_REGRESSION_COOLDOWN_CALLS,
    cooldown_minutes: int = DEFAULT_REGRESSION_COOLDOWN_MINUTES,
    max_fixes: int = 50,
) -> int:
    resolved_events = list(
        db.execute(
            select(FixEvent)
            .where(
                FixEvent.project_id == project_id,
                FixEvent.event_type == "resolved",
            )
            .order_by(FixEvent.timestamp.desc())
            .limit(max(1, max_fixes))
        )
        .scalars()
        .all()
    )

    regressed_count = 0
    seen_fix_ids: set[str] = set()
    for resolved_event in resolved_events:
        if resolved_event.fix_id in seen_fix_ids:
            continue
        seen_fix_ids.add(resolved_event.fix_id)

        existing_regression = db.execute(
            select(FixEvent).where(
                FixEvent.project_id == project_id,
                FixEvent.fix_id == resolved_event.fix_id,
                FixEvent.event_type == "regressed",
                FixEvent.timestamp > resolved_event.timestamp,
            )
        ).scalar_one_or_none()
        if existing_regression is not None:
            continue

        source_job = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == project_id,
                DiagnosisJob.diagnosis_id == resolved_event.diagnosis_id,
            )
        ).scalar_one_or_none()
        if source_job is None:
            continue

        target_categories = sorted(_extract_job_categories(source_job))
        if not target_categories:
            continue

        scan_start = _cooldown_scan_start(
            db,
            project_id=project_id,
            since=resolved_event.timestamp,
            cooldown_calls=max(0, cooldown_calls),
            cooldown_minutes=max(0, cooldown_minutes),
        )
        candidate_jobs = list(
            db.execute(
                select(DiagnosisJob)
                .where(
                    DiagnosisJob.tenant_id == project_id,
                    DiagnosisJob.diagnosis_id != resolved_event.diagnosis_id,
                    DiagnosisJob.created_at > scan_start,
                )
                .order_by(DiagnosisJob.created_at.asc())
                .limit(100)
            )
            .scalars()
            .all()
        )

        target_set = set(target_categories)
        matching_jobs = [job for job in candidate_jobs if target_set.intersection(_extract_job_categories(job))]
        if not matching_jobs:
            continue
        recurrence = matching_jobs[0]
        severity = _regression_severity(matching_jobs)

        record_fix_event(
            db,
            project_id=project_id,
            diagnosis_id=resolved_event.diagnosis_id,
            fix_id=resolved_event.fix_id,
            event_type="regressed",
            metadata={
                "regression_confidence": 0.8,
                "resolution_event_id": resolved_event.id,
                "recurrence_diagnosis_id": recurrence.diagnosis_id,
                "recurrence_count": len(matching_jobs),
                "regression_severity": severity,
                "target_categories": target_categories,
                "cooldown_window": f"{cooldown_calls}_calls_or_{cooldown_minutes}m",
            },
            idempotency_key=f"regressed:{resolved_event.id}:{recurrence.diagnosis_id}",
            source="system",
            timestamp=_as_utc(recurrence.created_at),
        )
        regressed_count += 1

    return regressed_count


def calibrate_resolved_fix_confidence(
    db: Session,
    *,
    project_id: str,
    now: datetime | None = None,
    max_fixes: int = 50,
) -> int:
    now_utc = _as_utc(now or datetime.now(timezone.utc))
    resolved_events = list(
        db.execute(
            select(FixEvent)
            .where(
                FixEvent.project_id == project_id,
                FixEvent.event_type == "resolved",
            )
            .order_by(FixEvent.timestamp.desc())
            .limit(max(1, max_fixes))
        )
        .scalars()
        .all()
    )

    updated_count = 0
    seen_fix_ids: set[str] = set()
    for event in resolved_events:
        if event.fix_id in seen_fix_ids:
            continue
        seen_fix_ids.add(event.fix_id)

        regression = db.execute(
            select(FixEvent).where(
                FixEvent.project_id == project_id,
                FixEvent.fix_id == event.fix_id,
                FixEvent.event_type == "regressed",
                FixEvent.timestamp > event.timestamp,
            )
        ).scalar_one_or_none()
        if regression is not None:
            continue

        metadata = fix_event_metadata(event)
        current_confidence = float(metadata.get("resolution_confidence") or 0.0)
        current_correlation = str(metadata.get("resolution_correlation") or "low")
        confidence, correlation, calibration = _decayed_resolution_truth(
            since=event.timestamp,
            now=now_utc,
            base_confidence=current_confidence,
            base_correlation=current_correlation,
        )
        if calibration == "initial_window":
            continue
        if (
            confidence <= current_confidence
            and CORRELATION_RANK.get(correlation, 0) <= CORRELATION_RANK.get(current_correlation, 0)
            and metadata.get("confidence_calibration") == calibration
        ):
            continue

        metadata["resolution_confidence"] = confidence
        metadata["resolution_correlation"] = correlation
        metadata["confidence_calibration"] = calibration
        metadata["confidence_calibrated_at"] = now_utc.isoformat()
        event.metadata_json = _json_dumps_object(metadata)
        db.add(event)
        updated_count += 1

    if updated_count:
        db.commit()

    return updated_count


def evaluate_pending_fix_resolutions(
    db: Session,
    *,
    project_id: str,
    window_calls: int = DEFAULT_RESOLUTION_WINDOW_CALLS,
    window_hours: int = DEFAULT_RESOLUTION_WINDOW_HOURS,
    minimum_observations_threshold: int = DEFAULT_MINIMUM_OBSERVATIONS_THRESHOLD,
    max_fixes: int = 50,
) -> int:
    applied_events = list(
        db.execute(
            select(FixEvent)
            .where(
                FixEvent.project_id == project_id,
                FixEvent.event_type.in_(APPLIED_EVENT_TYPES),
            )
            .order_by(FixEvent.timestamp.desc())
            .limit(max(1, max_fixes))
        )
        .scalars()
        .all()
    )

    resolved_count = 0
    preferred_by_fix_id: dict[str, FixEvent] = {}
    for event in applied_events:
        current = preferred_by_fix_id.get(event.fix_id)
        if current is None:
            preferred_by_fix_id[event.fix_id] = event
            continue
        if event.event_type == "pr_merged" and current.event_type != "pr_merged":
            preferred_by_fix_id[event.fix_id] = event
            continue
        if event.event_type == current.event_type and _as_utc(event.timestamp) > _as_utc(current.timestamp):
            preferred_by_fix_id[event.fix_id] = event

    for event in preferred_by_fix_id.values():
        existing_resolved = db.execute(
            select(FixEvent).where(
                FixEvent.project_id == project_id,
                FixEvent.fix_id == event.fix_id,
                FixEvent.event_type == "resolved",
            )
        ).scalar_one_or_none()
        if existing_resolved is not None:
            continue

        _, resolved_event = mark_resolved_if_no_recurrence(
            db,
            project_id=project_id,
            diagnosis_id=event.diagnosis_id,
            fix_id=event.fix_id,
            since=event.timestamp,
            window_calls=window_calls,
            window_hours=window_hours,
            minimum_observations_threshold=minimum_observations_threshold,
            correlation_signal=event.event_type,
        )
        if resolved_event is not None:
            resolved_count += 1

    return resolved_count


__all__ = [name for name in globals() if not name.startswith("__")]
