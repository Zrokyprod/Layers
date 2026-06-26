from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActionTimelineEvent


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256_digest(canonical_payload: str) -> str:
    return f"sha256:{hashlib.sha256(canonical_payload.encode('utf-8')).hexdigest()}"


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def record_action_timeline_event(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    actor: str | None = None,
) -> ActionTimelineEvent:
    event_payload = {
        "project_id": project_id,
        "action_id": action_id,
        "event_type": event_type,
        "actor": actor,
        "payload": dict(payload),
    }
    event_canonical = _canonical_json(event_payload)
    row = ActionTimelineEvent(
        project_id=project_id,
        action_intent_id=action_id,
        event_type=event_type,
        event_digest=_sha256_digest(event_canonical),
        event_payload_json=event_canonical,
        actor=actor,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def list_action_timeline(
    db: Session,
    *,
    project_id: str,
    action_id: str,
) -> list[ActionTimelineEvent]:
    return list(
        db.execute(
            select(ActionTimelineEvent)
            .where(
                ActionTimelineEvent.project_id == project_id,
                ActionTimelineEvent.action_intent_id == action_id,
            )
            .order_by(ActionTimelineEvent.created_at.asc(), ActionTimelineEvent.id.asc())
        ).scalars()
    )


def action_timeline_event_payload(row: ActionTimelineEvent) -> dict[str, Any]:
    value = _json_loads(row.event_payload_json, {})
    return value if isinstance(value, dict) else {}
