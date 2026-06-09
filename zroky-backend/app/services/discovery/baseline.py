"""Behavioral baseline persistence for the Discovery engine (DB layer).

The pure baseline math lives in `baseline_core.py` (no ORM) so the offline
harness and production share one source of truth. This module only adds the
DB read/write around that shared math.

Warmup discipline + suspect detection are decided in `baseline_core`; here we
just persist the versioned result. Prior versions are kept (`superseded`) so a
poisoning regression can be reconstructed and large shifts reviewed.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BehavioralBaseline
# Re-export the pure API so existing imports of these names keep working.
from app.services.discovery.baseline_core import (  # noqa: F401
    DEFAULT_CRITICAL_TOOL_PCT,
    DEFAULT_WARMUP_MIN_DAYS,
    DEFAULT_WARMUP_MIN_TRACES,
    SUSPECT_ERROR_RATE,
    BaselineConfig,
    NumericStats,
    build_baselines_in_memory,
    build_features_payload,
)


def get_active_baseline(
    db: Session, *, project_id: str, behavior_key_value: str
) -> BehavioralBaseline | None:
    """Return the newest active/suspect baseline for a key (None if learning/absent)."""
    return db.execute(
        select(BehavioralBaseline)
        .where(
            BehavioralBaseline.project_id == project_id,
            BehavioralBaseline.behavior_key == behavior_key_value,
            BehavioralBaseline.status.in_(("active", "suspect")),
        )
        .order_by(BehavioralBaseline.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def upsert_baseline(
    db: Session,
    *,
    project_id: str,
    behavior_key_value: str,
    agent_name: str | None,
    workflow_name: str | None,
    payload: Mapping,
) -> BehavioralBaseline:
    """Persist a new baseline version, superseding the prior one."""
    now = datetime.now(timezone.utc)
    prior = db.execute(
        select(BehavioralBaseline)
        .where(
            BehavioralBaseline.project_id == project_id,
            BehavioralBaseline.behavior_key == behavior_key_value,
        )
        .order_by(BehavioralBaseline.version.desc())
    ).scalars().all()
    next_version = (prior[0].version + 1) if prior else 1
    for row in prior:
        if row.status != "superseded":
            row.status = "superseded"
            row.updated_at = now
            db.add(row)

    baseline = BehavioralBaseline(
        id=str(uuid4()),
        project_id=project_id,
        agent_name=agent_name,
        workflow_name=workflow_name,
        behavior_key=behavior_key_value,
        specificity=str(payload.get("specificity", "exact")),
        version=next_version,
        status=str(payload.get("status", "learning")),
        sample_count=int(payload.get("sample_count", 0) or 0),
        distinct_days=int(payload.get("distinct_days", 0) or 0),
        error_rate=float(payload.get("error_rate", 0.0) or 0.0),
        window_start_at=_parse_iso(payload.get("window_start_at")),
        window_end_at=_parse_iso(payload.get("window_end_at")),
        features_json=json.dumps(payload, separators=(",", ":"), default=str),
        created_at=now,
        updated_at=now,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline


def load_features(baseline: BehavioralBaseline) -> dict:
    """Decode a persisted baseline's features_json into the scorer dict."""
    raw = baseline.features_json
    if not raw:
        return {"status": baseline.status}
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {"status": baseline.status}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"status": baseline.status}


def _parse_iso(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
