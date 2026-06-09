"""Disabled-by-default Discovery runtime orchestration.

This module is the first production-shaped shell around the shared pure
Discovery engine. It is intentionally not wired to Celery, APIs, or UI yet.
When DISCOVERY_ENABLED is false, every public function returns before reading
or writing any discovery/anomaly state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import BehavioralBaseline, Call, DiscoveryScanState
from app.services.discovery.baseline import load_features, upsert_baseline
from app.services.discovery.baseline_core import BaselineConfig, build_baselines_in_memory
from app.services.discovery.features import behavior_key, extract_features
from app.services.discovery.scorer import AnomalyCandidate, score
from app.services.discovery.sink import sink_candidates


@dataclass(frozen=True)
class DiscoveryRuntimeResult:
    enabled: bool
    skipped_reason: str | None = None
    calls_loaded: int = 0
    baselines_written: int = 0
    traces_scored: int = 0
    candidates_found: int = 0
    anomalies_written: int = 0
    watermark_advanced: bool = False


def refresh_baselines(
    db: Session,
    *,
    project_id: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> DiscoveryRuntimeResult:
    """Build and persist behavior baselines for one project.

    Disabled mode is a hard no-op: no reads, no writes, no commits.
    """
    settings = settings or get_settings()
    if not settings.DISCOVERY_ENABLED:
        return DiscoveryRuntimeResult(
            enabled=False,
            skipped_reason="DISCOVERY_ENABLED=false",
        )

    now = now or datetime.now(timezone.utc)
    calls = _load_recent_calls(
        db,
        project_id=project_id,
        since=now - timedelta(days=max(1, settings.DISCOVERY_BASELINE_WINDOW_DAYS)),
        limit=max(1, settings.DISCOVERY_SCAN_LIMIT),
        ascending=True,
    )
    stream: list[tuple[Any, datetime | None]] = []
    meta_by_key: dict[str, tuple[str, str | None, str | None]] = {}
    for call in calls:
        features = extract_features(_call_record(call))
        key, _ = behavior_key(features)
        meta_by_key.setdefault(
            key,
            (features.project_id, features.agent_name, features.workflow_name),
        )
        stream.append((features, call.created_at))

    payloads = build_baselines_in_memory(
        stream,
        BaselineConfig(
            warmup_min_traces=max(1, settings.DISCOVERY_WARMUP_MIN_TRACES),
            warmup_min_days=max(1, settings.DISCOVERY_WARMUP_MIN_DAYS),
            critical_tool_pct=min(1.0, max(0.0, settings.DISCOVERY_CRITICAL_TOOL_PCT)),
        ),
    )
    written = 0
    for key, payload in payloads.items():
        baseline_project_id, agent_name, workflow_name = meta_by_key[key]
        upsert_baseline(
            db,
            project_id=baseline_project_id,
            behavior_key_value=key,
            agent_name=agent_name,
            workflow_name=workflow_name,
            payload=payload,
        )
        written += 1

    return DiscoveryRuntimeResult(
        enabled=True,
        calls_loaded=len(calls),
        baselines_written=written,
    )


def scan_and_surface(
    db: Session,
    *,
    project_id: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> DiscoveryRuntimeResult:
    """Score recent project calls and write surfaced clusters to anomalies.

    Disabled mode is a hard no-op: no reads, no writes, no commits.
    """
    settings = settings or get_settings()
    if not settings.DISCOVERY_ENABLED:
        return DiscoveryRuntimeResult(
            enabled=False,
            skipped_reason="DISCOVERY_ENABLED=false",
        )

    now = now or datetime.now(timezone.utc)
    baselines = _latest_baselines_by_key(db, project_id=project_id)
    if not baselines:
        return DiscoveryRuntimeResult(enabled=True)

    scan_state = _get_scan_state(db, project_id=project_id)
    calls = _load_recent_calls(
        db,
        project_id=project_id,
        since=now - timedelta(days=max(1, settings.DISCOVERY_BASELINE_WINDOW_DAYS)),
        limit=max(1, settings.DISCOVERY_SCAN_LIMIT),
        ascending=True,
        after_created_at=(
            scan_state.last_scanned_call_created_at if scan_state is not None else None
        ),
        after_call_id=scan_state.last_scanned_call_id if scan_state is not None else None,
    )
    candidates: list[AnomalyCandidate] = []
    suspect_signatures: set[str] = set()
    scored = 0
    for call in calls:
        features = extract_features(_call_record(call))
        key, _ = behavior_key(features)
        baseline = baselines.get(key)
        if baseline is None:
            continue
        scored += 1
        candidate = score(
            features,
            load_features(baseline),
            behavior_key=key,
            z_weak=max(0.1, settings.DISCOVERY_Z_WEAK),
        )
        if candidate is None:
            continue
        candidates.append(candidate)
        if baseline.status == "suspect":
            suspect_signatures.add(candidate.signature)

    written = sink_candidates(
        db,
        project_id=project_id,
        candidates=candidates,
        suspect_signatures=suspect_signatures,
        surface_min_confidence=min(1.0, max(0.0, settings.DISCOVERY_SURFACE_MIN_CONFIDENCE)),
        recurrence_k=max(1, settings.DISCOVERY_RECURRENCE_K),
        now=now,
    )
    watermark_advanced = _advance_scan_state(
        db,
        project_id=project_id,
        calls=calls,
        now=now,
    )
    return DiscoveryRuntimeResult(
        enabled=True,
        calls_loaded=len(calls),
        traces_scored=scored,
        candidates_found=len(candidates),
        anomalies_written=len(written),
        watermark_advanced=watermark_advanced,
    )


def _load_recent_calls(
    db: Session,
    *,
    project_id: str,
    since: datetime,
    limit: int,
    ascending: bool,
    after_created_at: datetime | None = None,
    after_call_id: str | None = None,
) -> list[Call]:
    order = (Call.created_at.asc(), Call.id.asc()) if ascending else (
        Call.created_at.desc(),
        Call.id.desc(),
    )
    predicates = [
        Call.project_id == project_id,
        Call.is_production.is_(True),
        Call.created_at >= since,
    ]
    if after_created_at is not None:
        predicates.append(
            or_(
                Call.created_at > after_created_at,
                and_(
                    Call.created_at == after_created_at,
                    Call.id > (after_call_id or ""),
                ),
            )
        )
    return list(
        db.execute(
            select(Call)
            .where(*predicates)
            .order_by(*order)
            .limit(limit)
        ).scalars()
    )


def _get_scan_state(
    db: Session,
    *,
    project_id: str,
) -> DiscoveryScanState | None:
    return db.execute(
        select(DiscoveryScanState).where(DiscoveryScanState.project_id == project_id)
    ).scalar_one_or_none()


def _advance_scan_state(
    db: Session,
    *,
    project_id: str,
    calls: list[Call],
    now: datetime,
) -> bool:
    if not calls:
        return False

    last_call = calls[-1]
    state = _get_scan_state(db, project_id=project_id)
    if state is None:
        state = DiscoveryScanState(project_id=project_id)
    state.last_scanned_call_created_at = last_call.created_at
    state.last_scanned_call_id = last_call.id
    state.updated_at = now
    db.add(state)
    db.commit()
    return True


def _latest_baselines_by_key(
    db: Session,
    *,
    project_id: str,
) -> dict[str, BehavioralBaseline]:
    rows = db.execute(
        select(BehavioralBaseline)
        .where(
            BehavioralBaseline.project_id == project_id,
            BehavioralBaseline.status.in_(("active", "suspect")),
        )
        .order_by(BehavioralBaseline.behavior_key.asc(), BehavioralBaseline.version.desc())
    ).scalars()
    latest: dict[str, BehavioralBaseline] = {}
    for row in rows:
        latest.setdefault(row.behavior_key, row)
    return latest


def _call_record(call: Call) -> dict[str, Any]:
    return {
        "id": call.id,
        "project_id": call.project_id,
        "event_id": call.event_id,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "agent_name": call.agent_name,
        "provider": call.provider,
        "model": call.model,
        "status": call.status,
        "error_code": call.error_code,
        "latency_ms": call.latency_ms,
        "cost_total": float(call.cost_total or 0.0),
        "output_fingerprint": call.output_fingerprint,
        "tool_lifecycle_summary_json": call.tool_lifecycle_summary_json,
        "payload_json": call.payload_json,
        "metadata": call.metadata_json,
    }
