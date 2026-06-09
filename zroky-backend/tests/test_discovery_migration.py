from __future__ import annotations

import json
import importlib.util
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Anomaly, BehavioralBaseline, DiscoveryScanState
from app.services.anomalies import upsert_anomaly
from app.services.discovery.sink import DISCOVERY_DETECTOR


def test_metadata_contains_behavioral_baselines_and_behavioral_drift(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'metadata.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with factory() as db:
        baseline = BehavioralBaseline(
            id="baseline-1",
            project_id="project-1",
            agent_name="agent",
            workflow_name="workflow",
            behavior_key="project=project-1|agent=agent|workflow=workflow",
            specificity="exact",
            version=1,
            status="active",
            sample_count=200,
            distinct_days=3,
            error_rate=0,
            features_json=json.dumps({"status": "active"}),
        )
        db.add(baseline)
        db.add(
            DiscoveryScanState(
                id="scan-state-1",
                project_id="project-1",
                last_scanned_call_id="call-1",
                last_scanned_call_created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        anomaly = upsert_anomaly(
            db,
            project_id="project-1",
            detector=DISCOVERY_DETECTOR,
            call_id="call-1",
            occurred_at=datetime.now(timezone.utc),
            evidence={"source": "discovery"},
            fingerprint_extra="sig-1",
        )

        rows = db.execute(select(Anomaly).where(Anomaly.project_id == "project-1")).scalars().all()
        assert anomaly is not None
        assert rows[0].detector == DISCOVERY_DETECTOR

    engine.dispose()


def test_0077_sqlite_upgrade_creates_discovery_table(tmp_path: Path) -> None:
    db_path = tmp_path / "alembic_discovery.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0077_create_discovery_tables.py"
    )
    spec = importlib.util.spec_from_file_location("discovery_migration_0077", migration_path)
    assert spec is not None and spec.loader is not None
    discovery_migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discovery_migration)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = discovery_migration.op
        discovery_migration.op = operations
        try:
            # Isolate the discovery migration. Full SQLite upgrade-to-head is
            # blocked by older migration-chain constraint debt before 0077.
            discovery_migration.upgrade()
        finally:
            discovery_migration.op = original_op
    engine.dispose()

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "behavioral_baselines" in tables
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(behavioral_baselines)").fetchall()
        }
        assert {"project_id", "behavior_key", "features_json", "status"} <= columns
    finally:
        conn.close()


def test_0078_sqlite_upgrade_creates_discovery_scan_state_table(tmp_path: Path) -> None:
    db_path = tmp_path / "alembic_discovery_scan_state.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0078_create_discovery_scan_state.py"
    )
    spec = importlib.util.spec_from_file_location("discovery_migration_0078", migration_path)
    assert spec is not None and spec.loader is not None
    discovery_migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discovery_migration)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = discovery_migration.op
        discovery_migration.op = operations
        try:
            discovery_migration.upgrade()
        finally:
            discovery_migration.op = original_op
    engine.dispose()

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "discovery_scan_state" in tables
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(discovery_scan_state)").fetchall()
        }
        assert {
            "project_id",
            "last_scanned_call_created_at",
            "last_scanned_call_id",
        } <= columns
    finally:
        conn.close()
