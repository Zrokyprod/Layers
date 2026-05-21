"""Tests for `app/services/judge_mode_resolver.py`.

Coverage:
  - No override + no run → blocking with null accuracy
  - Latest complete run sets accuracy
  - Advisory override wins over high accuracy
  - Graceful degradation on exceptions
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import JudgeCalibrationRun, JudgeModeOverride, Project
from app.services.judge_mode_resolver import resolve_mode


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "test_resolver.db"
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
    p = Project(id=str(uuid.uuid4()), name="resolver-test")
    db_session.add(p)
    db_session.commit()
    return p


class TestResolveMode:
    def test_default_blocking_no_data(self, db_session, project) -> None:
        view = resolve_mode(db_session, project_id=project.id, judge_model="m")
        assert view.mode == "blocking"
        assert view.accuracy is None
        assert view.sample_count is None

    def test_accuracy_from_latest_run(self, db_session, project) -> None:
        run = JudgeCalibrationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            judge_model="m",
            run_date=date.today(),
            status="complete",
            sample_count=100,
            agreement_count=95,
            accuracy=0.95,
            kappa=0.9,
            low_confidence_pct=0.02,
            cost_usd="0.01",
        )
        db_session.add(run)
        db_session.commit()

        view = resolve_mode(db_session, project_id=project.id, judge_model="m")
        assert view.mode == "blocking"
        assert view.accuracy == 0.95
        assert view.sample_count == 100
        assert view.last_run_date == str(date.today())

    def test_advisory_override_wins(self, db_session, project) -> None:
        run = JudgeCalibrationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            judge_model="m",
            run_date=date.today(),
            status="complete",
            sample_count=100,
            agreement_count=95,
            accuracy=0.95,
            kappa=0.9,
            low_confidence_pct=0.02,
            cost_usd="0.01",
        )
        override = JudgeModeOverride(
            id=str(uuid.uuid4()),
            project_id=project.id,
            judge_model="m",
            mode="advisory",
            reason="manual",
        )
        db_session.add_all([run, override])
        db_session.commit()

        view = resolve_mode(db_session, project_id=project.id, judge_model="m")
        assert view.mode == "advisory"
        assert view.accuracy == 0.95
        assert "manual" in (view.reason or "")

    def test_graceful_degradation_on_error(self, db_session, project, monkeypatch) -> None:
        def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "app.services.judge_mode_resolver.select",
            _boom,
        )
        view = resolve_mode(db_session, project_id=project.id, judge_model="m")
        assert view.mode == "blocking"
        assert view.accuracy is None
