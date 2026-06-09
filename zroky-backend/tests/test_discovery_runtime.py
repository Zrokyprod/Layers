from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Anomaly, BehavioralBaseline, Call, DiscoveryScanState
from app.services.discovery.runtime import refresh_baselines, scan_and_surface
from app.services.discovery.sink import DISCOVERY_DETECTOR


PROJECT_ID = "runtime-project"
AGENT_NAME = "refund-agent"
WORKFLOW_NAME = "refund-status"


def _settings(*, enabled: bool) -> Settings:
    return Settings(
        DISCOVERY_ENABLED=enabled,
        DISCOVERY_WARMUP_MIN_TRACES=20,
        DISCOVERY_WARMUP_MIN_DAYS=2,
        DISCOVERY_BASELINE_WINDOW_DAYS=30,
        DISCOVERY_SCAN_LIMIT=500,
    )


def test_discovery_config_is_disabled_by_default() -> None:
    assert Settings().DISCOVERY_ENABLED is False


def _session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'runtime.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, factory()


def _seed_call(
    db,
    index: int,
    *,
    call_id: str | None = None,
    latency_ms: float | None = None,
    cost_total: float = 0.002,
    payload_extra: dict | None = None,
) -> None:
    output = {
        "status": "pending",
        "eta_days": 3,
        "message": "Refund is pending.",
        "next_step": "wait",
    }
    payload = {
        "call_id": call_id or f"call-{index}",
        "workflow_name": WORKFLOW_NAME,
        "tool_calls": [
            {"name": "lookup_order"},
            {"name": "get_refund_status"},
            {"name": "render_refund_answer"},
        ],
        "output_content": json.dumps(output, separators=(",", ":")),
        "finish_reason": "stop",
        "outcome": {"success": True},
    }
    if payload_extra:
        payload.update(payload_extra)
    db.add(
        Call(
            id=call_id or f"call-{index}",
            project_id=PROJECT_ID,
            event_id=f"event-{index}",
            created_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=index * 3),
            agent_name=AGENT_NAME,
            provider="openai",
            model="gpt-test",
            status="completed",
            latency_ms=latency_ms if latency_ms is not None else 600 + (index % 10),
            cost_total=cost_total,
            is_production=True,
            payload_json=json.dumps(payload, separators=(",", ":")),
        )
    )


def test_refresh_baselines_disabled_by_default_does_not_read_or_write(tmp_path: Path) -> None:
    engine, db = _session(tmp_path)
    try:
        _seed_call(db, 1)
        db.commit()

        result = refresh_baselines(
            db,
            project_id=PROJECT_ID,
            settings=_settings(enabled=False),
            now=datetime(2026, 6, 10, tzinfo=UTC),
        )

        assert result.enabled is False
        assert result.skipped_reason == "DISCOVERY_ENABLED=false"
        assert result.calls_loaded == 0
        assert db.execute(select(BehavioralBaseline)).scalars().all() == []
    finally:
        db.close()
        engine.dispose()


def test_scan_and_surface_disabled_does_not_write_anomalies(tmp_path: Path) -> None:
    engine, db = _session(tmp_path)
    try:
        db.add(
            BehavioralBaseline(
                id="baseline-1",
                project_id=PROJECT_ID,
                agent_name=AGENT_NAME,
                workflow_name=WORKFLOW_NAME,
                behavior_key=(
                    f"project={PROJECT_ID}|agent={AGENT_NAME}|workflow={WORKFLOW_NAME}"
                ),
                specificity="exact",
                version=1,
                status="active",
                sample_count=20,
                distinct_days=2,
                error_rate=0,
                features_json=json.dumps({"status": "active"}),
            )
        )
        _seed_call(db, 1)
        db.commit()

        result = scan_and_surface(
            db,
            project_id=PROJECT_ID,
            settings=_settings(enabled=False),
            now=datetime(2026, 6, 10, tzinfo=UTC),
        )

        assert result.enabled is False
        assert result.skipped_reason == "DISCOVERY_ENABLED=false"
        assert result.traces_scored == 0
        assert db.execute(select(Anomaly)).scalars().all() == []
        assert db.execute(select(DiscoveryScanState)).scalars().all() == []
    finally:
        db.close()
        engine.dispose()


def test_refresh_baselines_enabled_writes_baseline_versions(tmp_path: Path) -> None:
    engine, db = _session(tmp_path)
    try:
        for index in range(24):
            _seed_call(db, index)
        db.commit()

        result = refresh_baselines(
            db,
            project_id=PROJECT_ID,
            settings=_settings(enabled=True),
            now=datetime(2026, 6, 10, tzinfo=UTC),
        )

        rows = db.execute(select(BehavioralBaseline)).scalars().all()
        assert result.enabled is True
        assert result.calls_loaded == 24
        assert result.baselines_written == 1
        assert len(rows) == 1
        assert rows[0].status == "active"
    finally:
        db.close()
        engine.dispose()


def test_enabled_scan_surfaces_structural_failure_and_reuses_existing_anomaly(
    tmp_path: Path,
) -> None:
    engine, db = _session(tmp_path)
    settings = _settings(enabled=True)
    try:
        for index in range(24):
            _seed_call(db, index)
        db.commit()
        refresh = refresh_baselines(
            db,
            project_id=PROJECT_ID,
            settings=settings,
            now=datetime(2026, 6, 10, tzinfo=UTC),
        )
        assert refresh.baselines_written == 1

        for index in range(3):
            _seed_call(
                db,
                100 + index,
                call_id=f"missing-tool-{index}",
                payload_extra={
                    "tool_calls": [{"name": "lookup_order"}],
                    "output_content": "Refund looks complete.",
                },
            )
        for index in range(8):
            _seed_call(
                db,
                120 + index,
                call_id=f"slow-call-{index}",
                latency_ms=5000 + index,
            )
        db.commit()

        first = scan_and_surface(
            db,
            project_id=PROJECT_ID,
            settings=settings,
            now=datetime(2026, 6, 25, tzinfo=UTC),
        )

        rows = db.execute(select(Anomaly).where(Anomaly.project_id == PROJECT_ID)).scalars().all()
        assert first.enabled is True
        assert first.calls_loaded == 35
        assert first.candidates_found == 11
        assert first.anomalies_written == 1
        assert first.watermark_advanced is True
        assert len(rows) == 1
        assert rows[0].detector == DISCOVERY_DETECTOR
        evidence = json.loads(rows[0].evidence_json or "{}")
        assert evidence["primary_dimension"] == "missing_critical_tool"
        first_occurrence_count = rows[0].occurrence_count
        state = db.execute(
            select(DiscoveryScanState).where(DiscoveryScanState.project_id == PROJECT_ID)
        ).scalar_one()
        assert state.last_scanned_call_id == "slow-call-7"

        second = scan_and_surface(
            db,
            project_id=PROJECT_ID,
            settings=settings,
            now=datetime(2026, 6, 25, tzinfo=UTC),
        )

        rows = db.execute(select(Anomaly).where(Anomaly.project_id == PROJECT_ID)).scalars().all()
        assert second.calls_loaded == 0
        assert second.candidates_found == 0
        assert second.anomalies_written == 0
        assert second.watermark_advanced is False
        assert len(rows) == 1
        assert rows[0].occurrence_count == first_occurrence_count
    finally:
        db.close()
        engine.dispose()
