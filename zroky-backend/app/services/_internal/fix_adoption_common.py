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
    ordered_events.sort(key=lambda item: (item[0], item[1], STATE_RANK[item[3]], item[2]))

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


__all__ = [name for name in globals() if not name.startswith("__")]
