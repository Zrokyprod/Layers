"""Read model for hidden Discovery status inspection.

This is intentionally a read-only projection over existing Discovery tables
and the shared `anomalies` surface. It does not change the product exposure
rules: Discovery remains default-off and customer UI/API exposure is still
blocked until the real-trace precision gate passes.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Anomaly, BehavioralBaseline, DiscoveryScanState
from app.services.discovery.sink import DISCOVERY_DETECTOR


def get_discovery_project_status(
    db: Session,
    *,
    project_id: str,
    settings: Settings | None = None,
    anomaly_limit: int = 20,
) -> dict[str, Any]:
    settings = settings or get_settings()
    baselines = _load_baselines(db, project_id=project_id)
    baseline_counts = Counter(row.status for row in baselines)
    scan_state = db.execute(
        select(DiscoveryScanState).where(DiscoveryScanState.project_id == project_id)
    ).scalar_one_or_none()
    anomalies = _load_discovery_anomalies(
        db,
        project_id=project_id,
        limit=max(1, min(int(anomaly_limit), 100)),
    )

    return {
        "project_id": project_id,
        "discovery_enabled": bool(settings.DISCOVERY_ENABLED),
        "customer_surface": {
            "enabled": False,
            "blocked_reason": "real_trace_precision_gate_required",
        },
        "baselines": {
            "total": len(baselines),
            "active": baseline_counts.get("active", 0),
            "learning": baseline_counts.get("learning", 0),
            "suspect": baseline_counts.get("suspect", 0),
            "superseded": baseline_counts.get("superseded", 0),
            "items": [_baseline_item(row) for row in baselines],
        },
        "scan_state": _scan_state_item(scan_state),
        "surfaced_anomalies": {
            "total_in_page": len(anomalies),
            "items": [_anomaly_item(row) for row in anomalies],
        },
    }


def _load_baselines(
    db: Session,
    *,
    project_id: str,
) -> list[BehavioralBaseline]:
    return list(
        db.execute(
            select(BehavioralBaseline)
            .where(BehavioralBaseline.project_id == project_id)
            .order_by(
                BehavioralBaseline.behavior_key.asc(),
                BehavioralBaseline.version.desc(),
            )
        ).scalars()
    )


def _load_discovery_anomalies(
    db: Session,
    *,
    project_id: str,
    limit: int,
) -> list[Anomaly]:
    return list(
        db.execute(
            select(Anomaly)
            .where(
                Anomaly.project_id == project_id,
                Anomaly.detector == DISCOVERY_DETECTOR,
            )
            .order_by(Anomaly.last_seen_at.desc(), Anomaly.id.desc())
            .limit(limit)
        ).scalars()
    )


def _baseline_item(row: BehavioralBaseline) -> dict[str, Any]:
    return {
        "id": row.id,
        "behavior_key": row.behavior_key,
        "agent_name": row.agent_name,
        "workflow_name": row.workflow_name,
        "specificity": row.specificity,
        "version": row.version,
        "status": row.status,
        "sample_count": row.sample_count,
        "distinct_days": row.distinct_days,
        "error_rate": float(row.error_rate or 0.0),
        "window_start_at": _iso(row.window_start_at),
        "window_end_at": _iso(row.window_end_at),
        "updated_at": _iso(row.updated_at),
    }


def _scan_state_item(row: DiscoveryScanState | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "last_scanned_call_id": row.last_scanned_call_id,
        "last_scanned_call_created_at": _iso(row.last_scanned_call_created_at),
        "updated_at": _iso(row.updated_at),
    }


def _anomaly_item(row: Anomaly) -> dict[str, Any]:
    evidence = _safe_json_object(row.evidence_json)
    return {
        "id": row.id,
        "fingerprint": row.fingerprint,
        "severity": row.severity,
        "status": row.status,
        "occurrence_count": row.occurrence_count,
        "first_seen_at": _iso(row.first_seen_at),
        "last_seen_at": _iso(row.last_seen_at),
        "sample_call_ids": _safe_json_list(row.sample_call_ids_json),
        "primary_dimension": evidence.get("primary_dimension"),
        "summary": evidence.get("summary"),
        "confidence": evidence.get("confidence"),
        "anomaly_score": evidence.get("anomaly_score"),
        "corroboration": evidence.get("corroboration") if isinstance(evidence.get("corroboration"), list) else [],
        "discovery_signature": evidence.get("discovery_signature"),
    }


def _safe_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
