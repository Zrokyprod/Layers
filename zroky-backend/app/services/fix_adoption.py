from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob, FixEvent
from app.services.privacy import mask_metadata, mask_payload

STATEFUL_FIX_EVENT_TYPES = {"shown", "copied", "pr_generated", "pr_merged", "applied", "resolved", "regressed"}
FIX_EVENT_TYPES = {
    "shown",
    "copied",
    "pr_generated",
    "pr_merged",
    "applied",
    "resolved",
    "ignored",
    "regressed",
}
FIX_EVENT_SOURCES = {"dashboard", "sdk", "github_webhook", "api", "system"}
ADOPTION_EVENT_TYPES = {"copied", "pr_generated", "pr_merged", "applied"}
APPLIED_EVENT_TYPES = {"applied", "pr_merged"}
DIAGNOSIS_DONE_STATUSES = {"done", "completed"}
DEFAULT_RESOLUTION_WINDOW_CALLS = 50
DEFAULT_RESOLUTION_WINDOW_HOURS = 24
DEFAULT_MINIMUM_OBSERVATIONS_THRESHOLD = 10
DEFAULT_REGRESSION_COOLDOWN_CALLS = 10
DEFAULT_REGRESSION_COOLDOWN_MINUTES = 10
CORRELATION_RANK = {"low": 0, "medium": 1, "high": 2}
STATE_RANK = {
    "shown": 10,
    "copied": 20,
    "pr_generated": 30,
    "applied": 40,
    "pr_merged": 40,
    "resolved": 50,
    "regressed": 60,
}
REQUIRED_PRIOR_EVENTS = {
    "shown": set(),
    "copied": {"shown"},
    "pr_generated": {"copied"},
    "applied": {"copied", "pr_generated", "pr_merged"},
    "pr_merged": {"pr_generated"},
    "resolved": {"applied", "pr_merged"},
    "regressed": {"resolved", "applied", "pr_merged"},
}
INFERRED_PREREQUISITES = {
    "copied": ["shown"],
    "pr_generated": ["shown", "copied"],
    "applied": ["shown", "copied", "pr_generated"],
    "pr_merged": ["shown", "copied", "pr_generated"],
    "regressed": ["shown", "copied", "pr_generated", "pr_merged"],
}


@dataclass(frozen=True)
class ResolutionEvaluation:
    resolved: bool
    resolution_confidence: float
    resolution_correlation: str
    attribution_mode: str
    confidence_calibration: str
    resolution_window: str
    checked_calls: int
    recurrence_count: int
    target_categories: list[str]
    reason: str

    def to_metadata(self) -> dict[str, Any]:
        return {
            "resolution_confidence": self.resolution_confidence,
            "resolution_correlation": self.resolution_correlation,
            "attribution_mode": self.attribution_mode,
            "confidence_calibration": self.confidence_calibration,
            "resolution_window": self.resolution_window,
            "checked_calls": self.checked_calls,
            "recurrence_count": self.recurrence_count,
            "target_categories": self.target_categories,
            "reason": self.reason,
        }


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    return mask_payload(parsed) if isinstance(parsed, dict) else {}


def _json_dumps_object(value: dict[str, Any]) -> str:
    return json.dumps(mask_metadata(value), separators=(",", ":"), default=str)


def _timestamp_bucket(dt: datetime) -> str:
    return _as_utc(dt).strftime("%Y%m%d%H%M")


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized[:255] if normalized else None


def _normalize_source(value: str | None) -> str:
    if value is None:
        return "dashboard"
    normalized = value.strip().lower()
    if normalized in FIX_EVENT_SOURCES:
        return normalized
    return "api"


def _build_idempotency_key(
    *,
    diagnosis_id: str,
    fix_id: str,
    event_type: str,
    timestamp_bucket: str,
    idempotency_key: str | None,
) -> str:
    normalized = _normalize_idempotency_key(idempotency_key)
    if normalized is not None:
        return normalized

    return f"auto:{diagnosis_id.strip()}:{fix_id.strip()}:{event_type}:{timestamp_bucket}"[:255]


def _resolution_window_label(*, window_calls: int, window_hours: int) -> str:
    if window_hours <= 0:
        return f"{window_calls}_calls"
    return f"{window_calls}_calls_and_{window_hours}h"


def _normalize_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().upper().replace(" ", "_")
    return normalized or None


def _extract_categories_from_payload(payload: dict[str, Any]) -> set[str]:
    categories: set[str] = set()
    for key in ("category", "diagnosis_type", "error_code", "expected_category", "failure_category"):
        normalized = _normalize_category(payload.get(key))
        if normalized:
            categories.add(normalized)

    diagnoses = payload.get("diagnoses")
    if isinstance(diagnoses, list):
        for item in diagnoses:
            if not isinstance(item, dict):
                continue
            for key in ("category", "diagnosis_type", "error_code"):
                normalized = _normalize_category(item.get(key))
                if normalized:
                    categories.add(normalized)

    return categories


def _extract_job_categories(job: DiagnosisJob) -> set[str]:
    result_categories = _extract_categories_from_payload(_safe_json_object(job.result_json))
    if result_categories:
        return result_categories
    return _extract_categories_from_payload(_safe_json_object(job.payload_json))


def fix_event_metadata(event: FixEvent) -> dict[str, Any]:
    return _safe_json_object(event.metadata_json)


def _event_metadata_with_signal(event_type: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    enriched = mask_metadata(metadata)
    if event_type == "pr_merged":
        enriched.setdefault("inferred_applied", True)
        enriched.setdefault("applied_signal", "pr_merged")
    elif event_type == "applied":
        enriched.setdefault("applied_signal", "manual")
    return enriched


def _latest_event_for_fix(
    db: Session,
    *,
    project_id: str,
    fix_id: str,
) -> FixEvent | None:
    return db.execute(
        select(FixEvent)
        .where(
            FixEvent.project_id == project_id,
            FixEvent.fix_id == fix_id,
        )
        .order_by(FixEvent.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()


def _events_for_fix(
    db: Session,
    *,
    project_id: str,
    fix_id: str,
) -> list[FixEvent]:
    return list(
        db.execute(
            select(FixEvent)
            .where(
                FixEvent.project_id == project_id,
                FixEvent.fix_id == fix_id,
            )
            .order_by(FixEvent.timestamp.asc(), FixEvent.id.asc())
        )
        .scalars()
        .all()
    )


def _event_tuple(
    *,
    event_type: str,
    timestamp: datetime,
    event_id: str,
    is_candidate: bool = False,
) -> tuple[datetime, int, str, str, bool]:
    # Candidate sorts after persisted rows with the same timestamp so retries
    # and synchronous UI events do not accidentally invert existing order.
    return (_as_utc(timestamp), 1 if is_candidate else 0, event_id, event_type, is_candidate)


def _validate_state_transition(
    db: Session,
    *,
    project_id: str,
    fix_id: str,
    event_type: str,
    timestamp: datetime,
) -> None:
    if event_type not in STATEFUL_FIX_EVENT_TYPES:
        return

    persisted_events = _events_for_fix(db, project_id=project_id, fix_id=fix_id)
    ordered_events = [
        _event_tuple(
            event_type=row.event_type,
            timestamp=row.timestamp,
            event_id=row.id,
        )
        for row in persisted_events
        if row.event_type in STATEFUL_FIX_EVENT_TYPES
    ]
    ordered_events.append(
        _event_tuple(
            event_type=event_type,
            timestamp=timestamp,
            event_id="candidate",
            is_candidate=True,
        )
    )
    ordered_events.sort(key=lambda item: (item[0], item[1], item[2]))

    seen_events: set[str] = set()
    highest_rank = 0
    regressed_seen = False
    for _, _, _, current_type, _ in ordered_events:
        if regressed_seen and current_type != "regressed":
            raise ValueError("Invalid fix event transition: no events may follow regressed for the same fix_id")

        current_rank = STATE_RANK[current_type]
        if current_rank < highest_rank and not (
            current_type in APPLIED_EVENT_TYPES and "resolved" in seen_events
        ):
            raise ValueError(
                f"Invalid fix event transition: {current_type} cannot occur after a later fix state"
            )

        required_prior = REQUIRED_PRIOR_EVENTS[current_type]
        if required_prior and not required_prior.intersection(seen_events):
            required = ", ".join(sorted(required_prior))
            raise ValueError(f"Invalid fix event transition: {current_type} requires prior {required}")

        if current_type == "shown" and any(item in seen_events for item in STATEFUL_FIX_EVENT_TYPES):
            raise ValueError("Invalid fix event transition: shown must be the first state for a fix_id")

        seen_events.add(current_type)
        highest_rank = max(highest_rank, current_rank)
        if current_type == "regressed":
            regressed_seen = True


def _fetch_duplicate_event(
    db: Session,
    *,
    project_id: str,
    idempotency_key: str,
    fix_id: str,
    event_type: str,
    timestamp_bucket: str,
) -> FixEvent | None:
    duplicate = db.execute(
        select(FixEvent).where(
            FixEvent.project_id == project_id,
            FixEvent.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        return duplicate

    return db.execute(
        select(FixEvent).where(
            FixEvent.project_id == project_id,
            FixEvent.fix_id == fix_id,
            FixEvent.event_type == event_type,
            FixEvent.timestamp_bucket == timestamp_bucket,
        )
    ).scalar_one_or_none()


def _repair_late_resolution_correlation(
    db: Session,
    *,
    signal_event: FixEvent,
) -> None:
    if signal_event.event_type not in APPLIED_EVENT_TYPES:
        return

    new_correlation = _resolution_correlation(resolved=True, correlation_signal=signal_event.event_type)
    new_rank = CORRELATION_RANK.get(new_correlation, 0)
    if new_rank <= 0:
        return

    resolved_events = list(
        db.execute(
            select(FixEvent)
            .where(
                FixEvent.project_id == signal_event.project_id,
                FixEvent.fix_id == signal_event.fix_id,
                FixEvent.event_type == "resolved",
            )
            .order_by(FixEvent.timestamp.asc())
        )
        .scalars()
        .all()
    )
    changed = False
    for resolved_event in resolved_events:
        metadata = fix_event_metadata(resolved_event)
        current_rank = CORRELATION_RANK.get(str(metadata.get("resolution_correlation") or "low"), 0)
        if current_rank >= new_rank:
            continue
        metadata["resolution_correlation"] = new_correlation
        metadata["applied_signal"] = signal_event.event_type
        metadata["late_signal_event_id"] = signal_event.id
        metadata["correlation_repaired_at"] = datetime.now(timezone.utc).isoformat()
        resolved_event.metadata_json = _json_dumps_object(metadata)
        db.add(resolved_event)
        changed = True

    if changed:
        db.commit()


def _distinct_fix_ids(
    db: Session,
    *,
    project_id: str,
    event_types: set[str],
    since: datetime | None = None,
    until: datetime | None = None,
) -> set[str]:
    query = select(func.distinct(FixEvent.fix_id)).where(
        FixEvent.project_id == project_id,
        FixEvent.event_type.in_(event_types),
    )
    if since is not None:
        query = query.where(FixEvent.timestamp >= _as_utc(since))
    if until is not None:
        query = query.where(FixEvent.timestamp <= _as_utc(until))
    return {str(row[0]) for row in db.execute(query).all() if row[0]}


def _events_in_window(
    db: Session,
    *,
    project_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[FixEvent]:
    query = select(FixEvent).where(FixEvent.project_id == project_id)
    if since is not None:
        query = query.where(FixEvent.timestamp >= _as_utc(since))
    if until is not None:
        query = query.where(FixEvent.timestamp <= _as_utc(until))
    return list(db.execute(query.order_by(FixEvent.timestamp.asc())).scalars().all())


def _metadata_by_fix_id(events: list[FixEvent]) -> dict[str, dict[str, Any]]:
    by_fix_id: dict[str, dict[str, Any]] = {}
    for event in events:
        current = by_fix_id.setdefault(event.fix_id, {})
        metadata = fix_event_metadata(event)
        for key, value in metadata.items():
            if key not in current and value not in (None, "", []):
                current[key] = value
    return by_fix_id


def _metadata_tags(metadata: dict[str, Any]) -> list[str]:
    raw_tags = metadata.get("fix_tags")
    if raw_tags is None:
        raw_tags = metadata.get("tags")

    tags: list[str] = []
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if not isinstance(item, str):
                continue
            tag = item.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
    elif isinstance(raw_tags, str):
        for item in raw_tags.split(","):
            tag = item.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)

    return tags or ["unknown"]


def _metadata_priority(metadata: dict[str, Any]) -> str:
    raw_priority = metadata.get("recommended_priority") or metadata.get("priority")
    if not isinstance(raw_priority, str):
        return "unknown"

    normalized = raw_priority.strip().upper().replace(" ", "_")
    priority_aliases = {
        "HIGH_PRIORITY": "P0",
        "HIGH": "P0",
        "MEDIUM_PRIORITY": "P1",
        "MEDIUM": "P1",
        "LOW_PRIORITY": "P2",
        "LOW": "P2",
    }
    if normalized in {"P0", "P1", "P2", "P3"}:
        return normalized
    return priority_aliases.get(normalized, "unknown")


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def record_fix_event(
    db: Session,
    *,
    project_id: str,
    diagnosis_id: str,
    fix_id: str,
    event_type: str,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    source: str | None = None,
    timestamp: datetime | None = None,
) -> FixEvent:
    normalized_event_type = event_type.strip().lower()
    if normalized_event_type not in FIX_EVENT_TYPES:
        raise ValueError(f"Unsupported fix event type: {event_type}")

    event_time = _as_utc(timestamp or datetime.now(timezone.utc))
    bucket = _timestamp_bucket(event_time)
    normalized_diagnosis_id = diagnosis_id.strip()
    normalized_fix_id = fix_id.strip()
    normalized_source = _normalize_source(source)
    resolved_idempotency_key = _build_idempotency_key(
        diagnosis_id=normalized_diagnosis_id,
        fix_id=normalized_fix_id,
        event_type=normalized_event_type,
        timestamp_bucket=bucket,
        idempotency_key=idempotency_key,
    )
    duplicate = _fetch_duplicate_event(
        db,
        project_id=project_id,
        idempotency_key=resolved_idempotency_key,
        fix_id=normalized_fix_id,
        event_type=normalized_event_type,
        timestamp_bucket=bucket,
    )
    if duplicate is not None:
        _repair_late_resolution_correlation(db, signal_event=duplicate)
        return duplicate

    _validate_state_transition(
        db,
        project_id=project_id,
        fix_id=normalized_fix_id,
        event_type=normalized_event_type,
        timestamp=event_time,
    )

    enriched_metadata = _event_metadata_with_signal(normalized_event_type, metadata)
    enriched_metadata.setdefault("source", normalized_source)

    latest_event = _latest_event_for_fix(db, project_id=project_id, fix_id=normalized_fix_id)
    if latest_event is not None and event_time < _as_utc(latest_event.timestamp):
        enriched_metadata.setdefault("out_of_order", True)
        enriched_metadata.setdefault("latest_event_type_at_ingest", latest_event.event_type)
        enriched_metadata.setdefault("latest_event_timestamp_at_ingest", _as_utc(latest_event.timestamp).isoformat())

    event = FixEvent(
        project_id=project_id,
        diagnosis_id=normalized_diagnosis_id,
        fix_id=normalized_fix_id,
        event_type=normalized_event_type,
        source=normalized_source,
        idempotency_key=resolved_idempotency_key,
        timestamp_bucket=bucket,
        timestamp=event_time,
        metadata_json=_json_dumps_object(enriched_metadata),
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
        _repair_late_resolution_correlation(db, signal_event=event)
        return event
    except IntegrityError:
        db.rollback()
        duplicate = _fetch_duplicate_event(
            db,
            project_id=project_id,
            idempotency_key=resolved_idempotency_key,
            fix_id=normalized_fix_id,
            event_type=normalized_event_type,
            timestamp_bucket=bucket,
        )
        if duplicate is None:
            raise
        _repair_late_resolution_correlation(db, signal_event=duplicate)
        return duplicate


def ensure_fix_event_prerequisites(
    db: Session,
    *,
    project_id: str,
    diagnosis_id: str,
    fix_id: str,
    event_type: str,
    anchor_time: datetime | None = None,
    source: str = "system",
    inferred_from: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[FixEvent]:
    normalized_event_type = event_type.strip().lower()
    sequence = INFERRED_PREREQUISITES.get(normalized_event_type, [])
    if not sequence:
        return []

    existing_events = _events_for_fix(db, project_id=project_id, fix_id=fix_id)
    existing_types = {event.event_type for event in existing_events}
    missing_types = [item for item in sequence if item not in existing_types]
    if not missing_types:
        return []

    anchor_candidates = [_as_utc(anchor_time or datetime.now(timezone.utc))]
    anchor_candidates.extend(_as_utc(event.timestamp) for event in existing_events if event.event_type in STATEFUL_FIX_EVENT_TYPES)
    anchor = min(anchor_candidates)

    created: list[FixEvent] = []
    base_metadata = mask_metadata(metadata)
    for index, missing_type in enumerate(missing_types):
        inferred_metadata = {
            **base_metadata,
            "inferred": True,
            "inferred_from": inferred_from or normalized_event_type,
            "inference_reason": "missing_required_fix_lifecycle_prerequisite",
        }
        event_time = anchor - timedelta(seconds=len(missing_types) - index)
        event = record_fix_event(
            db,
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            event_type=missing_type,
            metadata=inferred_metadata,
            idempotency_key=f"inferred:{diagnosis_id}:{fix_id}:{missing_type}:{normalized_event_type}"[:255],
            source=source,
            timestamp=event_time,
        )
        created.append(event)

    return created


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


def get_fix_adoption_rate(
    db: Session,
    *,
    project_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    shown_fix_ids = _distinct_fix_ids(
        db,
        project_id=project_id,
        event_types={"shown"},
        since=since,
        until=until,
    )
    adopted_fix_ids = _distinct_fix_ids(
        db,
        project_id=project_id,
        event_types=ADOPTION_EVENT_TYPES,
        since=since,
        until=until,
    )
    shown = len(shown_fix_ids)
    adopted = len(shown_fix_ids.intersection(adopted_fix_ids))
    return {"numerator": adopted, "denominator": shown, "rate": _rate(adopted, shown)}


def get_fix_success_rate(
    db: Session,
    *,
    project_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    applied_fix_ids = _distinct_fix_ids(
        db,
        project_id=project_id,
        event_types=APPLIED_EVENT_TYPES,
        since=since,
        until=until,
    )
    resolved_fix_ids = _distinct_fix_ids(
        db,
        project_id=project_id,
        event_types={"resolved"},
        since=since,
        until=until,
    )
    applied = len(applied_fix_ids)
    resolved = len(applied_fix_ids.intersection(resolved_fix_ids))
    return {"numerator": resolved, "denominator": applied, "rate": _rate(resolved, applied)}


def get_pr_conversion_rate(
    db: Session,
    *,
    project_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    shown_fix_ids = _distinct_fix_ids(
        db,
        project_id=project_id,
        event_types={"shown"},
        since=since,
        until=until,
    )
    generated_fix_ids = _distinct_fix_ids(
        db,
        project_id=project_id,
        event_types={"pr_generated"},
        since=since,
        until=until,
    )
    shown = len(shown_fix_ids)
    generated = len(shown_fix_ids.intersection(generated_fix_ids))
    return {"numerator": generated, "denominator": shown, "rate": _rate(generated, shown)}


def get_fix_success_rate_by_tag(
    db: Session,
    *,
    project_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    events = _events_in_window(db, project_id=project_id, since=since, until=until)
    metadata_by_fix = _metadata_by_fix_id(events)
    applied_fix_ids = {event.fix_id for event in events if event.event_type in APPLIED_EVENT_TYPES}
    resolved_fix_ids = {event.fix_id for event in events if event.event_type == "resolved"}

    grouped: dict[str, dict[str, int]] = {}
    for fix_id in applied_fix_ids:
        for tag in _metadata_tags(metadata_by_fix.get(fix_id, {})):
            bucket = grouped.setdefault(tag, {"numerator": 0, "denominator": 0})
            bucket["denominator"] += 1
            if fix_id in resolved_fix_ids:
                bucket["numerator"] += 1

    return {
        tag: {
            "numerator": values["numerator"],
            "denominator": values["denominator"],
            "rate": _rate(values["numerator"], values["denominator"]),
        }
        for tag, values in sorted(grouped.items())
    }


def get_fix_adoption_rate_by_priority(
    db: Session,
    *,
    project_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    events = _events_in_window(db, project_id=project_id, since=since, until=until)
    metadata_by_fix = _metadata_by_fix_id(events)
    shown_fix_ids = {event.fix_id for event in events if event.event_type == "shown"}
    adopted_fix_ids = {event.fix_id for event in events if event.event_type in ADOPTION_EVENT_TYPES}

    grouped: dict[str, dict[str, int]] = {}
    for fix_id in shown_fix_ids:
        priority = _metadata_priority(metadata_by_fix.get(fix_id, {}))
        bucket = grouped.setdefault(priority, {"numerator": 0, "denominator": 0})
        bucket["denominator"] += 1
        if fix_id in adopted_fix_ids:
            bucket["numerator"] += 1

    return {
        priority: {
            "numerator": values["numerator"],
            "denominator": values["denominator"],
            "rate": _rate(values["numerator"], values["denominator"]),
        }
        for priority, values in sorted(grouped.items())
    }
