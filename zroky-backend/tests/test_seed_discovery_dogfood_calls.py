from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Anomaly, BehavioralBaseline, Call, DiscoveryScanState, Project


def _load_script(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_seed_discovery_dogfood_calls_creates_exportable_calls(tmp_path: Path) -> None:
    seed_script = _load_script("seed_discovery_dogfood_calls")
    export_script = _load_script("export_discovery_traces")
    db_path = tmp_path / "dogfood.db"
    database_url = f"sqlite:///{db_path}"
    summary_path = tmp_path / "seed-summary.json"

    result = seed_script.main(
        [
            "--database-url",
            database_url,
            "--project-id",
            "dogfood-project",
            "--normal-primary",
            "30",
            "--normal-low-volume",
            "5",
            "--missing-tool-failures",
            "2",
            "--schema-break-failures",
            "2",
            "--outcome-mismatch-failures",
            "2",
            "--latency-cost-failures",
            "1",
            "--reset",
            "--summary-out",
            str(summary_path),
        ]
    )

    assert result == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["rows_seeded"] == 42
    assert summary["injected_failures"] == 7
    assert summary["dogfood_only"] is True

    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with session_factory() as db:
            project = db.execute(
                select(Project).where(Project.id == "dogfood-project")
            ).scalar_one()
            calls = db.execute(
                select(Call).where(Call.project_id == "dogfood-project")
            ).scalars().all()
            assert project.is_active is True
            assert len(calls) == 42
            assert all(call.is_production for call in calls)
            assert any("injected_failure_type" in (call.metadata_json or "") for call in calls)
    finally:
        engine.dispose()

    out_path = tmp_path / "exported.jsonl"
    export_result = export_script.main(
        [
            "--database-url",
            database_url,
            "--project-id",
            "dogfood-project",
            "--out",
            str(out_path),
            "--min-rows",
            "42",
        ]
    )

    assert export_result == 0
    exported = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert len(exported) == 42
    first_payload = json.loads(exported[0]["payload_json"])
    assert "workflow_name" in first_payload
    assert "tool_calls" in first_payload


def test_seed_discovery_dogfood_reset_clears_stale_discovery_rows(
    tmp_path: Path,
) -> None:
    seed_script = _load_script("seed_discovery_dogfood_calls")
    db_path = tmp_path / "dogfood-reset.db"
    database_url = f"sqlite:///{db_path}"
    project_id = "dogfood-reset-project"

    assert seed_script.main(
        [
            "--database-url",
            database_url,
            "--project-id",
            project_id,
            "--normal-primary",
            "2",
            "--normal-low-volume",
            "0",
            "--missing-tool-failures",
            "0",
            "--schema-break-failures",
            "0",
            "--outcome-mismatch-failures",
            "0",
            "--latency-cost-failures",
            "0",
            "--reset",
        ]
    ) == 0

    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with session_factory() as db:
            now = db.execute(select(Call.created_at).limit(1)).scalar_one()
            db.add(
                BehavioralBaseline(
                    id="stale-baseline",
                    project_id=project_id,
                    behavior_key="project=dogfood-reset-project|agent=a|workflow=w",
                    specificity="exact",
                    version=1,
                    status="active",
                    sample_count=200,
                    distinct_days=3,
                    error_rate=0,
                    features_json="{}",
                )
            )
            db.add(
                DiscoveryScanState(
                    id="stale-scan-state",
                    project_id=project_id,
                    last_scanned_call_created_at=now,
                    last_scanned_call_id="old-call",
                )
            )
            db.add(
                Anomaly(
                    id="stale-anomaly",
                    project_id=project_id,
                    fingerprint="stale-fingerprint",
                    detector="BEHAVIORAL_DRIFT",
                    severity="low",
                    status="open",
                    first_seen_at=now,
                    last_seen_at=now,
                    occurrence_count=1,
                )
            )
            db.commit()
    finally:
        engine.dispose()

    assert seed_script.main(
        [
            "--database-url",
            database_url,
            "--project-id",
            project_id,
            "--normal-primary",
            "1",
            "--normal-low-volume",
            "0",
            "--missing-tool-failures",
            "0",
            "--schema-break-failures",
            "0",
            "--outcome-mismatch-failures",
            "0",
            "--latency-cost-failures",
            "0",
            "--reset",
        ]
    ) == 0

    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with session_factory() as db:
            assert len(db.execute(select(Call)).scalars().all()) == 1
            assert db.execute(select(BehavioralBaseline)).scalars().all() == []
            assert db.execute(select(DiscoveryScanState)).scalars().all() == []
            assert db.execute(select(Anomaly)).scalars().all() == []
    finally:
        engine.dispose()
