"""Tests for `app/services/judge_calibration_runner.py`.

Coverage:
  - run_calibration: idempotent when complete row exists
  - insufficient labeled traces → status='skipped'
  - auto-downgrade hysteresis: blocking→advisory when accuracy < 90%
  - restore to blocking when accuracy ≥ 93%
  - error path persists status='error'
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    GoldenLabel,
    GoldenSet,
    GoldenTrace,
    JudgeCalibrationRun,
    JudgeModeOverride,
    Project,
)
from app.services.judge_calibration_runner import (
    REASON_DOWNGRADE,
    REASON_RESTORED,
    run_calibration,
)


# ── stub evaluator ────────────────────────────────────────────────────────────


def _stub_factory(always_verdict: str, confidence: float = 0.8):
    """Return a judge_factory that always emits the given verdict."""
    class _Verdict:
        def __init__(self):
            self.verdict = always_verdict
            self.confidence = confidence
            self.metadata = {}
            self.latency_ms = 0

    class _Stub:
        def evaluate(self, actual, expected, *, context=None):
            return _Verdict()

    def factory(model: str):
        return _Stub()

    return factory


def _raising_factory(msg: str):
    """Return a judge_factory that raises on construction."""
    def factory(model: str):
        raise RuntimeError(msg)
    return factory


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "test_runner.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def project(db_session):
    p = Project(id=str(uuid.uuid4()), name="cal-runner-test")
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def golden_set(db_session, project):
    gs = GoldenSet(
        id=str(uuid.uuid4()),
        project_id=project.id,
        name="test-set",
    )
    db_session.add(gs)
    db_session.commit()
    return gs


@pytest.fixture()
def golden_trace(db_session, project, golden_set):
    gt = GoldenTrace(
        id=str(uuid.uuid4()),
        project_id=project.id,
        golden_set_id=golden_set.id,
        expected_output_text="World",
    )
    db_session.add(gt)
    db_session.commit()
    return gt


def _add_label(db_session, trace, verdict: str):
    lbl = GoldenLabel(
        id=str(uuid.uuid4()),
        golden_trace_id=trace.id,
        project_id=trace.project_id,
        verdict=verdict,
        version=1,
        active=True,
    )
    db_session.add(lbl)
    db_session.commit()
    return lbl


# ── tests ─────────────────────────────────────────────────────────────────────


class TestRunCalibration:
    def test_idempotent_when_complete_exists(self, db_session, project) -> None:
        today = date.today()
        existing = JudgeCalibrationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            judge_model="m",
            run_date=today,
            status="complete",
            sample_count=10,
            agreement_count=9,
            accuracy=0.9,
            kappa=0.8,
            low_confidence_pct=0.1,
            cost_usd=0.01,
        )
        db_session.add(existing)
        db_session.commit()

        run = run_calibration(db_session, project_id=project.id, judge_model="m")
        assert run.id == existing.id
        assert run.status == "complete"

    def test_insufficient_samples_skipped(self, db_session, project) -> None:
        # No labeled traces at all → should skip
        run = run_calibration(
            db_session,
            project_id=project.id,
            judge_model="m",
            min_samples_to_run=1,
        )
        assert run.status == "skipped"
        assert "below minimum" in (run.per_class_metrics_json or "")

    def test_auto_downgrade_hysteresis(
        self, db_session, project, golden_trace
    ) -> None:
        # Two labeled rows for same trace (different human verdicts)
        # Judge always says "pass" → accuracy = 0.5 (< 0.90) → advisory
        _add_label(db_session, golden_trace, "pass")
        _add_label(db_session, golden_trace, "fail")

        run = run_calibration(
            db_session,
            project_id=project.id,
            judge_model="m",
            judge_factory=_stub_factory("pass"),
            downgrade_threshold=0.90,
            restore_threshold=0.93,
            min_samples_for_downgrade=2,
            min_samples_to_run=1,
        )
        assert run.status == "complete"
        assert run.sample_count == 2
        assert run.accuracy == pytest.approx(0.5)

        mode = db_session.execute(
            select(JudgeModeOverride).where(
                JudgeModeOverride.project_id == project.id,
                JudgeModeOverride.judge_model == "m",
            )
        ).scalar_one_or_none()
        assert mode is not None
        assert mode.mode == "advisory"
        assert mode.reason == REASON_DOWNGRADE

    def test_restore_to_blocking(
        self, db_session, project, golden_trace
    ) -> None:
        # Pre-existing advisory override (runner-owned)
        override = JudgeModeOverride(
            id=str(uuid.uuid4()),
            project_id=project.id,
            judge_model="m",
            mode="advisory",
            reason=REASON_DOWNGRADE,
        )
        db_session.add(override)
        db_session.commit()

        # One label, judge agrees → accuracy=1.0 ≥ 0.93 → restore
        _add_label(db_session, golden_trace, "pass")

        run = run_calibration(
            db_session,
            project_id=project.id,
            judge_model="m",
            judge_factory=_stub_factory("pass", confidence=0.99),
            downgrade_threshold=0.90,
            restore_threshold=0.93,
            min_samples_for_downgrade=1,
            min_samples_to_run=1,
        )
        assert run.status == "complete"
        assert run.accuracy == pytest.approx(1.0)

        mode = db_session.execute(
            select(JudgeModeOverride).where(
                JudgeModeOverride.project_id == project.id,
                JudgeModeOverride.judge_model == "m",
            )
        ).scalar_one()
        assert mode.mode == "blocking"
        assert mode.reason == REASON_RESTORED

    def test_error_persists_failed_run(
        self, db_session, project, golden_trace
    ) -> None:
        _add_label(db_session, golden_trace, "pass")

        run = run_calibration(
            db_session,
            project_id=project.id,
            judge_model="m",
            judge_factory=_raising_factory("judge down"),
            min_samples_to_run=1,
        )
        assert run.status == "error"
        assert "judge down" in (run.per_class_metrics_json or "")
