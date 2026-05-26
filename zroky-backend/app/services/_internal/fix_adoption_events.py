from app.services._internal.fix_adoption_common import *

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


__all__ = [name for name in globals() if not name.startswith("__")]
