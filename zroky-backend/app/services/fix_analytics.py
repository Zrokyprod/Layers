from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DiagnosisJob, FixEvent
from app.schemas.dashboard import (
    FixActionQueueItem,
    FixAnalyticsResponse,
    FixDiagnosisPerformanceItem,
    FixFunnelStep,
    FixHealthTrustSummary,
    FixMicroInsight,
    FixTrendPoint,
)

FUNNEL_STATES = [
    ("shown", "Shown"),
    ("copied", "Copied"),
    ("pr_generated", "PR Generated"),
    ("applied", "Merged / Applied"),
    ("resolved", "Resolved"),
    ("regressed", "Regressed"),
]
STATE_RANK = {
    "shown": 10,
    "copied": 20,
    "pr_generated": 30,
    "applied": 40,
    "pr_merged": 40,
    "resolved": 50,
    "regressed": 60,
}
ADOPTED_STATES = {"copied", "pr_generated", "applied", "pr_merged", "resolved", "regressed"}
APPLIED_STATES = {"applied", "pr_merged"}


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
    return parsed if isinstance(parsed, dict) else {}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 2)


def _delta(current: float, previous: float) -> float:
    return round(current - previous, 4)


def _delta_optional(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


def _metadata(event: FixEvent) -> dict[str, Any]:
    return _safe_json_object(event.metadata_json)


def _normalize_state(event_type: str) -> str:
    if event_type == "pr_merged":
        return "applied"
    return event_type


def _current_state(events: list[FixEvent]) -> str:
    if not events:
        return "shown"
    latest = max(events, key=lambda item: (STATE_RANK.get(item.event_type, 0), _as_utc(item.timestamp)))
    return _normalize_state(latest.event_type)


def _first_event(events: list[FixEvent], event_types: set[str]) -> FixEvent | None:
    matches = [event for event in events if event.event_type in event_types]
    if not matches:
        return None
    return min(matches, key=lambda item: _as_utc(item.timestamp))


def _last_event(events: list[FixEvent], event_types: set[str]) -> FixEvent | None:
    matches = [event for event in events if event.event_type in event_types]
    if not matches:
        return None
    return max(matches, key=lambda item: _as_utc(item.timestamp))


def _hours_between(start: datetime, end: datetime) -> float:
    seconds = max(0.0, (_as_utc(end) - _as_utc(start)).total_seconds())
    return round(seconds / 3600.0, 2)


def _category_from_job(job: DiagnosisJob | None) -> str:
    if job is None:
        return "UNKNOWN"

    for raw in (job.result_json, job.payload_json):
        payload = _safe_json_object(raw)
        diagnoses = payload.get("diagnoses")
        if isinstance(diagnoses, list):
            for item in diagnoses:
                if isinstance(item, dict) and isinstance(item.get("category"), str):
                    return item["category"].strip().upper() or "UNKNOWN"
        for key in ("category", "diagnosis_type", "error_code"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()

    return "UNKNOWN"


def _metadata_value(events: list[FixEvent], *keys: str, fallback: str | None = None) -> str | None:
    for event in sorted(events, key=lambda item: _as_utc(item.timestamp)):
        metadata = _metadata(event)
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback


def _metadata_float(events: list[FixEvent], key: str) -> float | None:
    for event in sorted(events, key=lambda item: _as_utc(item.timestamp), reverse=True):
        value = _metadata(event).get(key)
        if isinstance(value, (int, float)):
            return round(float(value), 4)
        if isinstance(value, str):
            try:
                return round(float(value), 4)
            except ValueError:
                continue
    return None


def _fix_tags(events: list[FixEvent]) -> list[str]:
    tags: list[str] = []
    for event in events:
        metadata = _metadata(event)
        raw_tags = metadata.get("fix_tags") or metadata.get("tags")
        if isinstance(raw_tags, list):
            for item in raw_tags:
                if isinstance(item, str) and item.strip() and item.strip() not in tags:
                    tags.append(item.strip())
        elif isinstance(raw_tags, str):
            for item in raw_tags.split(","):
                tag = item.strip()
                if tag and tag not in tags:
                    tags.append(tag)
    return tags


def _fix_title(events: list[FixEvent], diagnosis_type: str) -> str:
    title = _metadata_value(events, "title", "fix_title")
    if title:
        return title
    return f"Fix {diagnosis_type.replace('_', ' ').title()}"


def _status_badge(
    *,
    priority: str,
    success_status: str,
    resolution_confidence: float | None,
    attribution_mode: str | None,
    regression_severity: str | None,
    blast_radius: str | None,
    time_open_hours: float,
) -> str:
    priority_upper = priority.upper()
    if success_status == "regressed":
        return "critical"
    if priority_upper == "P0" and success_status == "unresolved":
        return "critical"
    if resolution_confidence is not None and resolution_confidence < 0.65:
        return "critical"
    if blast_radius == "high" and (resolution_confidence is None or resolution_confidence < 0.75):
        return "critical"
    if success_status == "unresolved":
        return "watch"
    if attribution_mode in {"ambiguous", "multi"}:
        return "watch"
    if resolution_confidence is None or resolution_confidence < 0.85:
        return "watch"
    if regression_severity == "minor":
        return "watch"
    if priority_upper == "P1" and success_status == "unresolved" and time_open_hours >= 24:
        return "watch"
    return "stable"


def _recommended_action(
    *,
    status_badge: str,
    success_status: str,
    current_state: str,
    regression_severity: str | None,
    attribution_mode: str | None,
    resolution_confidence: float | None,
) -> str:
    if success_status == "regressed":
        if regression_severity == "major":
            return "Reopen fix review and inspect recurrence evidence."
        return "Review regression sample before changing strategy."
    if current_state in {"shown", "copied"}:
        return "Review diff and decide whether to generate PR."
    if current_state == "pr_generated":
        return "Review PR draft and merge or reject."
    if current_state == "applied":
        return "Wait for resolution window and monitor recurrence."
    if attribution_mode in {"ambiguous", "multi"}:
        return "Verify attribution before counting this as a reliable fix."
    if resolution_confidence is not None and resolution_confidence < 0.75:
        return "Keep monitoring; confidence is below trust threshold."
    if status_badge == "stable":
        return "No immediate action."
    return "Review fix details."


def _success_status(current_state: str) -> str:
    if current_state == "regressed":
        return "regressed"
    if current_state == "resolved":
        return "resolved"
    return "unresolved"


def _health_snapshot(events: list[FixEvent]) -> dict[str, Any]:
    grouped: dict[str, list[FixEvent]] = defaultdict(list)
    for event in events:
        grouped[event.fix_id].append(event)

    shown_fix_ids = {fix_id for fix_id, rows in grouped.items() if any(row.event_type == "shown" for row in rows)}
    adopted_fix_ids = {fix_id for fix_id, rows in grouped.items() if any(row.event_type in ADOPTED_STATES for row in rows)}
    applied_fix_ids = {fix_id for fix_id, rows in grouped.items() if any(row.event_type in APPLIED_STATES for row in rows)}
    resolved_fix_ids = {fix_id for fix_id, rows in grouped.items() if any(row.event_type == "resolved" for row in rows)}
    regressed_fix_ids = {fix_id for fix_id, rows in grouped.items() if any(row.event_type == "regressed" for row in rows)}

    resolution_hours: list[float] = []
    resolution_confidences: list[float] = []
    major_regressions = 0

    for rows in grouped.values():
        rows = sorted(rows, key=lambda item: _as_utc(item.timestamp))
        resolved_event = _first_event(rows, {"resolved"})
        applied_event = _first_event(rows, APPLIED_STATES)
        if resolved_event and applied_event:
            resolution_hours.append(_hours_between(applied_event.timestamp, resolved_event.timestamp))

        confidence = _metadata_float(rows, "resolution_confidence")
        if confidence is not None:
            resolution_confidences.append(confidence)

        if _metadata_value(rows, "regression_severity") == "major":
            major_regressions += 1

    return {
        "adoption_rate": _rate(len(adopted_fix_ids), len(shown_fix_ids)),
        "success_rate": _rate(len(resolved_fix_ids), len(applied_fix_ids)),
        "regression_rate": _rate(len(regressed_fix_ids), len(resolved_fix_ids) or len(applied_fix_ids)),
        "median_time_to_resolution_hours": _median(resolution_hours),
        "average_resolution_confidence": round(sum(resolution_confidences) / len(resolution_confidences), 4)
        if resolution_confidences
        else 0.0,
        "major_regressions_count": major_regressions,
    }


def _sort_queue(item: FixActionQueueItem) -> tuple[int, float]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}.get(item.priority.upper(), 3)
    if item.success_status == "regressed" and item.regression_severity == "major":
        return (0, -item.time_open_hours)
    if item.status_badge == "critical":
        return (1 + priority_rank, -item.time_open_hours)
    if item.status_badge == "watch":
        return (5 + priority_rank, -item.time_open_hours)
    return (10 + priority_rank, -item.time_open_hours)


def build_fix_analytics(
    db: Session,
    *,
    tenant_id: str,
    window_days: int = 30,
    now: datetime | None = None,
) -> FixAnalyticsResponse:
    now_utc = _as_utc(now or datetime.now(timezone.utc))
    bounded_days = max(1, min(180, int(window_days)))
    start_time = now_utc - timedelta(days=bounded_days)
    current_delta_start = now_utc - timedelta(hours=24)
    previous_delta_start = now_utc - timedelta(hours=48)
    query_start = min(start_time, previous_delta_start)

    all_events = list(
        db.execute(
            select(FixEvent)
            .where(
                FixEvent.project_id == tenant_id,
                FixEvent.timestamp >= query_start,
                FixEvent.timestamp <= now_utc,
            )
            .order_by(FixEvent.timestamp.asc())
        )
        .scalars()
        .all()
    )
    events = [event for event in all_events if _as_utc(event.timestamp) >= start_time]
    current_delta_events = [
        event for event in all_events if current_delta_start <= _as_utc(event.timestamp) <= now_utc
    ]
    previous_delta_events = [
        event for event in all_events if previous_delta_start <= _as_utc(event.timestamp) < current_delta_start
    ]
    current_delta = _health_snapshot(current_delta_events)
    previous_delta = _health_snapshot(previous_delta_events)

    fix_events: dict[str, list[FixEvent]] = defaultdict(list)
    diagnosis_ids: set[str] = set()
    for event in events:
        fix_events[event.fix_id].append(event)
        diagnosis_ids.add(event.diagnosis_id)

    jobs_by_id: dict[str, DiagnosisJob] = {}
    if diagnosis_ids:
        jobs = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.tenant_id == tenant_id,
                DiagnosisJob.diagnosis_id.in_(diagnosis_ids),
            )
        ).scalars().all()
        jobs_by_id = {job.diagnosis_id: job for job in jobs}

    shown_fix_ids = {fix_id for fix_id, rows in fix_events.items() if any(row.event_type == "shown" for row in rows)}
    adopted_fix_ids = {
        fix_id for fix_id, rows in fix_events.items() if any(row.event_type in ADOPTED_STATES for row in rows)
    }
    applied_fix_ids = {
        fix_id for fix_id, rows in fix_events.items() if any(row.event_type in APPLIED_STATES for row in rows)
    }
    resolved_fix_ids = {fix_id for fix_id, rows in fix_events.items() if any(row.event_type == "resolved" for row in rows)}
    regressed_fix_ids = {
        fix_id for fix_id, rows in fix_events.items() if any(row.event_type == "regressed" for row in rows)
    }

    resolution_hours: list[float] = []
    resolution_confidences: list[float] = []
    major_regressions = 0
    action_rows: list[FixActionQueueItem] = []
    diagnosis_groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "fix_ids": set(),
            "shown": set(),
            "adopted": set(),
            "resolved": set(),
            "regressed": set(),
            "resolution_hours": [],
            "tags": set(),
        }
    )

    for fix_id, rows in fix_events.items():
        rows = sorted(rows, key=lambda item: _as_utc(item.timestamp))
        diagnosis_id = rows[0].diagnosis_id
        diagnosis_type = _category_from_job(jobs_by_id.get(diagnosis_id))
        current_state = _current_state(rows)
        success_status = _success_status(current_state)
        first_event = rows[0]
        resolved_event = _first_event(rows, {"resolved"})
        applied_event = _first_event(rows, APPLIED_STATES)
        tags = _fix_tags(rows)

        if resolved_event and applied_event:
            hours = _hours_between(applied_event.timestamp, resolved_event.timestamp)
            resolution_hours.append(hours)
            diagnosis_groups[diagnosis_type]["resolution_hours"].append(hours)

        confidence = _metadata_float(rows, "resolution_confidence")
        if confidence is not None:
            resolution_confidences.append(confidence)

        regression_severity = _metadata_value(rows, "regression_severity")
        if regression_severity == "major":
            major_regressions += 1

        time_open_hours = _hours_between(first_event.timestamp, now_utc)
        priority = _metadata_value(rows, "recommended_priority", "priority", fallback="P2") or "P2"
        risk_level = _metadata_value(rows, "risk_level")
        blast_radius = _metadata_value(rows, "blast_radius")
        resolution_correlation = _metadata_value(rows, "resolution_correlation")
        attribution_mode = _metadata_value(rows, "attribution_mode")
        status_badge = _status_badge(
            priority=priority,
            success_status=success_status,
            resolution_confidence=confidence,
            attribution_mode=attribution_mode,
            regression_severity=regression_severity,
            blast_radius=blast_radius,
            time_open_hours=time_open_hours,
        )

        action_rows.append(
            FixActionQueueItem(
                fix_id=fix_id,
                diagnosis_id=diagnosis_id,
                status_badge=status_badge,  # type: ignore[arg-type]
                priority=priority,
                diagnosis_type=diagnosis_type,
                fix_title=_fix_title(rows, diagnosis_type),
                current_state=current_state,
                success_status=success_status,  # type: ignore[arg-type]
                resolution_confidence=confidence,
                resolution_correlation=resolution_correlation,
                attribution_mode=attribution_mode,
                regression_severity=regression_severity,
                risk_level=risk_level,
                blast_radius=blast_radius,
                time_open_hours=time_open_hours,
                recommended_next_action=_recommended_action(
                    status_badge=status_badge,
                    success_status=success_status,
                    current_state=current_state,
                    regression_severity=regression_severity,
                    attribution_mode=attribution_mode,
                    resolution_confidence=confidence,
                ),
            )
        )

        group = diagnosis_groups[diagnosis_type]
        group["fix_ids"].add(fix_id)
        for tag in tags:
            group["tags"].add(tag)
        if fix_id in shown_fix_ids:
            group["shown"].add(fix_id)
        if fix_id in adopted_fix_ids:
            group["adopted"].add(fix_id)
        if fix_id in resolved_fix_ids:
            group["resolved"].add(fix_id)
        if fix_id in regressed_fix_ids:
            group["regressed"].add(fix_id)

    funnel: list[FixFunnelStep] = []
    previous_count = len(shown_fix_ids)
    for state, label in FUNNEL_STATES:
        if state == "applied":
            count = len(applied_fix_ids)
        elif state == "resolved":
            count = len(resolved_fix_ids)
        elif state == "regressed":
            count = len(regressed_fix_ids)
        else:
            count = len({fix_id for fix_id, rows in fix_events.items() if any(row.event_type == state for row in rows)})
        funnel.append(
            FixFunnelStep(
                state=state,
                label=label,
                count=count,
                conversion_rate=_rate(count, previous_count or count),
            )
        )
        if state != "regressed":
            previous_count = count

    trend: list[FixTrendPoint] = []
    for offset in range(bounded_days - 1, -1, -1):
        day = (now_utc - timedelta(days=offset)).date()
        day_events = [event for event in events if _as_utc(event.timestamp).date() == day]
        day_applied = {event.fix_id for event in day_events if event.event_type in APPLIED_STATES}
        day_resolved = {event.fix_id for event in day_events if event.event_type == "resolved"}
        day_regressed = {event.fix_id for event in day_events if event.event_type == "regressed"}
        denominator = len(day_applied.union(day_resolved).union(day_regressed))
        trend.append(
            FixTrendPoint(
                day=day.isoformat(),
                success_rate=_rate(len(day_resolved), denominator),
                regression_rate=_rate(len(day_regressed), denominator),
                resolved_count=len(day_resolved),
                regressed_count=len(day_regressed),
            )
        )

    diagnosis_performance = [
        FixDiagnosisPerformanceItem(
            diagnosis_type=diagnosis_type,
            fix_tags=sorted(group["tags"]),
            shown_count=len(group["shown"]),
            adopted_count=len(group["adopted"]),
            resolved_count=len(group["resolved"]),
            regressed_count=len(group["regressed"]),
            adoption_rate=_rate(len(group["adopted"]), len(group["shown"])),
            success_rate=_rate(len(group["resolved"]), len(group["adopted"])),
            regression_rate=_rate(len(group["regressed"]), len(group["resolved"]) or len(group["adopted"])),
            median_resolution_hours=_median(group["resolution_hours"]),
        )
        for diagnosis_type, group in diagnosis_groups.items()
    ]
    diagnosis_performance.sort(key=lambda item: (item.regression_rate, item.shown_count), reverse=True)

    action_rows.sort(key=_sort_queue)

    severity_indicator = "stable"
    if major_regressions > 0 or _rate(len(regressed_fix_ids), len(resolved_fix_ids) or len(applied_fix_ids)) >= 0.2:
        severity_indicator = "critical"
    elif any(item.status_badge == "watch" for item in action_rows[:5]):
        severity_indicator = "watch"

    micro_insight = _build_micro_insight(diagnosis_performance)

    return FixAnalyticsResponse(
        generated_at=now_utc,
        window_days=bounded_days,
        health=FixHealthTrustSummary(
            adoption_rate=_rate(len(adopted_fix_ids), len(shown_fix_ids)),
            adoption_rate_delta=_delta(
                current_delta["adoption_rate"],
                previous_delta["adoption_rate"],
            ),
            success_rate=_rate(len(resolved_fix_ids), len(applied_fix_ids)),
            success_rate_delta=_delta(
                current_delta["success_rate"],
                previous_delta["success_rate"],
            ),
            regression_rate=_rate(len(regressed_fix_ids), len(resolved_fix_ids) or len(applied_fix_ids)),
            regression_rate_delta=_delta(
                current_delta["regression_rate"],
                previous_delta["regression_rate"],
            ),
            median_time_to_resolution_hours=_median(resolution_hours),
            median_time_to_resolution_hours_delta=_delta_optional(
                current_delta["median_time_to_resolution_hours"],
                previous_delta["median_time_to_resolution_hours"],
            ),
            average_resolution_confidence=round(sum(resolution_confidences) / len(resolution_confidences), 4)
            if resolution_confidences
            else 0.0,
            average_resolution_confidence_delta=_delta(
                current_delta["average_resolution_confidence"],
                previous_delta["average_resolution_confidence"],
            ),
            major_regressions_count=major_regressions,
            major_regressions_count_delta=int(current_delta["major_regressions_count"])
            - int(previous_delta["major_regressions_count"]),
            severity_indicator=severity_indicator,  # type: ignore[arg-type]
        ),
        funnel=funnel,
        trend=trend,
        diagnosis_performance=diagnosis_performance,
        action_queue=action_rows[:25],
        micro_insight=micro_insight,
    )


def _build_micro_insight(items: list[FixDiagnosisPerformanceItem]) -> FixMicroInsight:
    if not items:
        return FixMicroInsight(
            message="No active issues. Recent fixes are stable.",
            severity="stable",
            action_label="No action",
        )

    risky = [item for item in items if item.regressed_count > 0]
    if risky:
        top = max(risky, key=lambda item: (item.regression_rate, item.regressed_count))
        priority = "P0" if top.regression_rate >= 0.35 else "P1"
        return FixMicroInsight(
            message=(
                f"{top.diagnosis_type} fixes show {round(top.regression_rate * 100)}% regression. "
                f"Review guard strategy ({priority})."
            ),
            severity="critical" if priority == "P0" else "watch",
            diagnosis_type=top.diagnosis_type,
            priority_hint=priority,
            action_label="Review strategy",
        )

    weak = [item for item in items if item.shown_count >= 3 and item.adoption_rate < 0.35]
    if weak:
        top = min(weak, key=lambda item: item.adoption_rate)
        return FixMicroInsight(
            message=(
                f"{top.diagnosis_type} fixes have low adoption. Improve diff clarity and PR handoff (P2)."
            ),
            severity="watch",
            diagnosis_type=top.diagnosis_type,
            priority_hint="P2",
            action_label="Improve handoff",
        )

    return FixMicroInsight(
        message="No active issues. Recent fixes are stable.",
        severity="stable",
        action_label="No action",
    )
