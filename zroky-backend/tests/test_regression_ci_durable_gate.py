from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import GoldenSet, GoldenTrace, ReplayRun, ReplayRunTrace
from app.services.regression_ci.durable_gate import apply_golden_gate_policy
from app.services.regression_ci.models import (
    SCHEMA_VERSION,
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    RegressionCIReport,
    SampleSpec,
    StratificationCounts,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_regression_ci_durable_gate.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _report(project_id: str = "proj-1") -> RegressionCIReport:
    blast = BlastRadius(
        category=BlastRadiusCategory.SYSTEM_PROMPT,
        source=BlastRadiusSource.DECLARED,
    )
    return RegressionCIReport(
        schema_version=SCHEMA_VERSION,
        run_id="ci-run",
        project_id=project_id,
        git_sha="abc123",
        blast_radius=blast,
        sample_spec=SampleSpec(
            target_total=10,
            stratification={"pass_history": 1.0},
            blast_radius=blast,
        ),
        stratification_realised=StratificationCounts(pass_history=10),
        trace_count=10,
        regressed_count=0,
        regression_rate=0.0,
        threshold=0.02,
        verdict="pass",
    )


def _trusted_contract() -> str:
    return json.dumps({
        "golden_contract_v1": {
            "linked_proof": {
                "replay_run_id": "proof-run",
                "proof_status": "verified_fix",
            }
        }
    })


def _seed_golden(
    session,
    *,
    project_id: str = "proj-1",
    blocks_ci: bool = True,
    is_flaky: bool = False,
    trace_status: str = "fail",
    trusted: bool = True,
):
    now = datetime.now(timezone.utc)
    golden_set = GoldenSet(
        id=str(uuid4()),
        project_id=project_id,
        name=f"Golden {uuid4()}",
        blocks_ci=blocks_ci,
        is_flaky=is_flaky,
        created_at=now,
    )
    trace = GoldenTrace(
        id=str(uuid4()),
        golden_set_id=golden_set.id,
        project_id=project_id,
        status="active",
        expected_output_text="expected",
        criteria_json=_trusted_contract() if trusted else "{}",
        created_at=now,
    )
    run = ReplayRun(
        id=str(uuid4()),
        project_id=project_id,
        golden_set_id=golden_set.id,
        trigger="manual",
        status=trace_status,
        created_at=now,
        summary_json=json.dumps({
            "requested_replay_mode": "real_llm",
            "verification_status": "verified_fix",
            "verified_fix": True,
        }),
    )
    run_trace = ReplayRunTrace(
        id=str(uuid4()),
        replay_run_id=run.id,
        golden_trace_id=trace.id,
        project_id=project_id,
        status=trace_status,
        created_at=now,
    )
    session.add_all([golden_set, trace, run, run_trace])
    session.commit()


def test_no_blocking_goldens_returns_not_verified(db_session):
    report = apply_golden_gate_policy(db_session, _report())

    assert report.verdict == "not_verified"
    assert "no active blocking Goldens exist for this project" in report.not_verified_reasons


def test_blocking_golden_failure_returns_fail(db_session):
    _seed_golden(db_session, blocks_ci=True, trace_status="fail")

    report = apply_golden_gate_policy(db_session, _report())

    assert report.verdict == "fail"
    assert len(report.failed_goldens) == 1
    assert report.failed_goldens[0]["assertion"] == "replay_trace_status:fail"


def test_non_blocking_golden_failure_returns_warn(db_session):
    _seed_golden(db_session, blocks_ci=True, trace_status="pass")
    _seed_golden(db_session, blocks_ci=False, trace_status="fail")

    report = apply_golden_gate_policy(db_session, _report())

    assert report.verdict == "warn"
    assert len(report.warn_goldens) == 1
