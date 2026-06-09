from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.internal import discovery_status_internal
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Anomaly, BehavioralBaseline, DiscoveryScanState, Project
from app.services.discovery.read_model import get_discovery_project_status
from app.services.discovery.sink import DISCOVERY_DETECTOR


PROJECT_ID = "discovery-read-project"


def _session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'discovery_read.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, factory()


def _seed_rows(db) -> None:
    now = datetime(2026, 6, 6, tzinfo=UTC)
    db.add(Project(id=PROJECT_ID, name="Discovery Read", is_active=True))
    db.add(
        BehavioralBaseline(
            id="baseline-active",
            project_id=PROJECT_ID,
            agent_name="refund-agent",
            workflow_name="refund-status",
            behavior_key=f"project={PROJECT_ID}|agent=refund-agent|workflow=refund-status",
            specificity="exact",
            version=2,
            status="active",
            sample_count=300,
            distinct_days=4,
            error_rate=0,
            window_start_at=now,
            window_end_at=now,
            features_json=json.dumps({"status": "active"}),
        )
    )
    db.add(
        BehavioralBaseline(
            id="baseline-learning",
            project_id=PROJECT_ID,
            agent_name="billing-agent",
            workflow_name="invoice-question",
            behavior_key=f"project={PROJECT_ID}|agent=billing-agent|workflow=invoice-question",
            specificity="exact",
            version=1,
            status="learning",
            sample_count=25,
            distinct_days=1,
            error_rate=0,
            features_json=json.dumps({"status": "learning"}),
        )
    )
    db.add(
        DiscoveryScanState(
            id="scan-state",
            project_id=PROJECT_ID,
            last_scanned_call_created_at=now,
            last_scanned_call_id="call-300",
        )
    )
    db.add(
        Anomaly(
            id="disc-anomaly",
            project_id=PROJECT_ID,
            fingerprint="disc-fingerprint",
            detector=DISCOVERY_DETECTOR,
            severity="medium",
            status="open",
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=3,
            sample_call_ids_json=json.dumps(["call-1", "call-2"]),
            evidence_json=json.dumps(
                {
                    "primary_dimension": "missing_critical_tool",
                    "summary": "Missing critical tool",
                    "confidence": 0.97,
                    "anomaly_score": 0.99,
                    "corroboration": ["missing critical tool"],
                    "discovery_signature": "sig-1",
                }
            ),
        )
    )
    db.add(
        Anomaly(
            id="other-anomaly",
            project_id=PROJECT_ID,
            fingerprint="other-fingerprint",
            detector="LATENCY_DRIFT",
            severity="low",
            status="open",
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            evidence_json=json.dumps({"summary": "not discovery"}),
        )
    )
    db.commit()


def test_discovery_read_model_summarizes_hidden_status(tmp_path: Path) -> None:
    engine, db = _session(tmp_path)
    try:
        _seed_rows(db)

        status = get_discovery_project_status(
            db,
            project_id=PROJECT_ID,
            settings=Settings(DISCOVERY_ENABLED=False),
        )

        assert status["discovery_enabled"] is False
        assert status["customer_surface"] == {
            "enabled": False,
            "blocked_reason": "real_trace_precision_gate_required",
        }
        assert status["baselines"]["total"] == 2
        assert status["baselines"]["active"] == 1
        assert status["baselines"]["learning"] == 1
        assert status["scan_state"]["last_scanned_call_id"] == "call-300"
        assert status["surfaced_anomalies"]["total_in_page"] == 1
        anomaly = status["surfaced_anomalies"]["items"][0]
        assert anomaly["id"] == "disc-anomaly"
        assert anomaly["primary_dimension"] == "missing_critical_tool"
        assert anomaly["sample_call_ids"] == ["call-1", "call-2"]
    finally:
        db.close()
        engine.dispose()


def test_internal_discovery_status_endpoint_is_provisioning_only_read_model(
    tmp_path: Path,
) -> None:
    engine, db = _session(tmp_path)
    try:
        _seed_rows(db)

        status = discovery_status_internal(
            project_id=PROJECT_ID,
            limit=5,
            _=None,
            db=db,
        )

        assert status["project_id"] == PROJECT_ID
        assert status["baselines"]["active"] == 1
        assert len(status["surfaced_anomalies"]["items"]) == 1

        with pytest.raises(HTTPException) as exc_info:
            discovery_status_internal(
                project_id="missing-project",
                limit=5,
                _=None,
                db=db,
            )
        assert exc_info.value.status_code == 404
    finally:
        db.close()
        engine.dispose()
