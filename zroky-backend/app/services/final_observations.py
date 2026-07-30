from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FinalObservation


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def observation_payload(
    *,
    run_id: str | None,
    intent_id: str | None,
    source_kind: str,
    observed_object_ref: str,
    observed_state: dict[str, Any] | None,
    provenance: dict[str, Any],
    observed_at: datetime,
    read_at: datetime | None,
    max_freshness_seconds: int,
) -> dict[str, Any]:
    read_time = read_at or datetime.now(UTC)
    return {
        "schema_version": "zroky.observation.v1",
        "run_id": run_id,
        "intent_id": intent_id,
        "source_kind": source_kind,
        "observed_object_ref": observed_object_ref,
        "observed_state": observed_state,
        "provenance": provenance,
        "observed_at": observed_at,
        "read_at": read_time,
        "freshness": _freshness(observed_at, read_time, max_freshness_seconds),
    }


def create_final_observation_row(
    db: Session,
    *,
    project_id: str,
    environment: str,
    run_id: str | None,
    intent_id: str | None,
    source_kind: str,
    observed_object_ref: str,
    observed_state: dict[str, Any] | None,
    provenance: dict[str, Any],
    observed_at: datetime,
    read_at: datetime | None = None,
    max_freshness_seconds: int = 300,
    commit: bool = True,
) -> FinalObservation:
    payload = observation_payload(
        run_id=run_id,
        intent_id=intent_id,
        source_kind=source_kind,
        observed_object_ref=observed_object_ref,
        observed_state=observed_state,
        provenance=provenance,
        observed_at=observed_at,
        read_at=read_at,
        max_freshness_seconds=max_freshness_seconds,
    )
    digest = observation_digest(payload)
    existing = db.execute(
        select(FinalObservation).where(
            FinalObservation.project_id == project_id,
            FinalObservation.environment == environment,
            FinalObservation.observation_digest == digest,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = FinalObservation(
        project_id=project_id,
        environment=environment,
        intent_id=intent_id,
        source_kind=source_kind,
        observed_object_ref=observed_object_ref,
        observation_digest=digest,
        observation_json=json.dumps(payload, sort_keys=True, separators=(",", ":"), default=json_default),
        observed_at=observed_at,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def observation_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=json_default).encode("utf-8")).hexdigest()


def _freshness(observed_at: datetime, read_at: datetime, max_seconds: int) -> dict[str, Any]:
    observed = observed_at.astimezone(UTC)
    read = read_at.astimezone(UTC)
    age = max(0, int((read - observed).total_seconds()))
    return {"age_seconds": age, "max_freshness_seconds": max_seconds, "fresh": age <= max_seconds}
