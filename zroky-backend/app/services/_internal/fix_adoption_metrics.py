from app.services._internal.fix_adoption_common import *

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


__all__ = [name for name in globals() if not name.startswith("__")]
