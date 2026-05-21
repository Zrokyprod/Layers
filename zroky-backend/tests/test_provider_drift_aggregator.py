"""Layer 5 tests for the aggregator."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    ProviderDriftAlert,
    ProviderDriftModel,
    ProviderDriftProbe,
    ProviderDriftPrompt,
    ProviderDriftRun,
)
from app.services.provider_drift.aggregator import (
    build_alert_spec,
    run_aggregator,
)
from app.services.provider_drift.drift_detector import (
    DEFAULT_BASELINE_DAYS,
    ProbeRow,
)
from app.services.provider_drift.models import DriftMetric

CURRENT = date(2026, 5, 18)


@pytest.fixture()
def session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pdw.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ── helpers ─────────────────────────────────────────────────────────────────


def _seed_model(session, *, model_id: str = "openai_gpt_4o_mini") -> ProviderDriftModel:
    row = ProviderDriftModel(
        id=model_id,
        provider="openai",
        model_id="gpt-4o-mini",
        display_name="GPT-4o mini",
        family="gpt-4o",
        active=True,
    )
    session.add(row)
    session.flush()
    return row


def _seed_prompts(
    session,
    *,
    category: str = "math",
    prompt_ids: Iterable[str] = ("p1", "p2", "p3", "p4", "p5"),
) -> None:
    for pid in prompt_ids:
        session.add(
            ProviderDriftPrompt(
                id=pid,
                category=category,
                prompt_text="x",
                expected_signal=json.dumps({"kind": "must_contain", "value": "x"}),
                version=1,
                active=True,
            )
        )
    session.flush()


def _seed_run_and_probes(
    session,
    *,
    model_id: str,
    run_date: date,
    prompt_ids: Iterable[str],
    pass_rate: float,
    embedding=(1.0, 0.0, 0.0),
    category: str = "math",
) -> None:
    run = ProviderDriftRun(
        id=str(uuid4()),
        model_id=model_id,
        run_date=run_date,
        status="complete",
    )
    session.add(run)
    session.flush()
    pids = list(prompt_ids)
    n_pass = int(round(pass_rate * len(pids)))
    for i, pid in enumerate(pids):
        session.add(
            ProviderDriftProbe(
                id=str(uuid4()),
                run_id=run.id,
                prompt_id=pid,
                model_id=model_id,
                run_date=run_date,
                category=category,
                output_text="x",
                output_embedding=json.dumps(list(embedding)),
                embedding_model="stub",
                judge_pass=(i < n_pass),
                outcome="ok",
                cost_usd=0.0,
            )
        )
    session.flush()


# ── build_alert_spec ────────────────────────────────────────────────────────


class TestBuildAlertSpec:
    def _metric(self, **kw) -> DriftMetric:
        defaults = dict(
            model_id="m1",
            category="math",
            current_date=CURRENT,
            baseline_start=CURRENT - timedelta(days=7),
            baseline_end=CURRENT - timedelta(days=1),
            pass_rate_current=0.5,
            pass_rate_baseline=0.8,
            pass_rate_stddev=0.05,
            judge_z=-6.0,
            embedding_z=-3.0,
            coverage_current=0.95,
            coverage_baseline_min=0.9,
            sample_size_current=20,
            sample_size_baseline=140,
        )
        defaults.update(kw)
        return DriftMetric(**defaults)

    def test_regressed_headline(self) -> None:
        spec = build_alert_spec(
            metric=self._metric(),
            model_display_name="GPT-4o mini",
            severity="critical",
            is_candidate=False,
        )
        assert "GPT-4o mini regressed on math" in spec.headline
        assert "−30.0pp" in spec.headline
        assert "2026-05-18" in spec.headline
        ev = spec.evidence
        assert ev["delta_pp"] == pytest.approx(-30.0)
        assert ev["judge_z"] == pytest.approx(-6.0)

    def test_improved_headline(self) -> None:
        spec = build_alert_spec(
            metric=self._metric(pass_rate_current=0.9, pass_rate_baseline=0.7),
            model_display_name="Claude Sonnet 4",
            severity="info",
            is_candidate=False,
        )
        assert "improved on math" in spec.headline
        assert "20.0pp" in spec.headline


# ── run_aggregator ──────────────────────────────────────────────────────────


class TestRunAggregatorIdempotency:
    def test_no_models_returns_empty(self, session) -> None:
        out = run_aggregator(db=session, current_date=CURRENT)
        assert out.alerts_published == 0
        assert out.metrics_evaluated == 0

    def test_no_drift_no_alert(self, session) -> None:
        model = _seed_model(session)
        prompts = ("p1", "p2", "p3", "p4", "p5")
        _seed_prompts(session, prompt_ids=prompts)

        # Steady 80% pass-rate every day for 8 days (7 baseline + today).
        for offset in range(DEFAULT_BASELINE_DAYS + 1):
            d = CURRENT - timedelta(days=DEFAULT_BASELINE_DAYS - offset)
            _seed_run_and_probes(
                session,
                model_id=model.id,
                run_date=d,
                prompt_ids=prompts,
                pass_rate=0.8,
            )
        session.commit()

        out = run_aggregator(db=session, current_date=CURRENT)
        assert out.metrics_evaluated >= 1
        assert out.alerts_published == 0

        alerts = session.execute(select(ProviderDriftAlert)).scalars().all()
        assert alerts == []

    def test_drift_publishes_alert(self, session) -> None:
        model = _seed_model(session)
        prompts = ("p1", "p2", "p3", "p4", "p5")
        _seed_prompts(session, prompt_ids=prompts)

        # 7 baseline days at 100% pass-rate, embedding (1, 0, 0).
        for offset in range(DEFAULT_BASELINE_DAYS):
            d = CURRENT - timedelta(days=DEFAULT_BASELINE_DAYS - offset)
            _seed_run_and_probes(
                session,
                model_id=model.id,
                run_date=d,
                prompt_ids=prompts,
                pass_rate=1.0,
                embedding=(1.0, 0.0, 0.0),
            )
        # Today: 0% pass-rate, orthogonal embedding.
        _seed_run_and_probes(
            session,
            model_id=model.id,
            run_date=CURRENT,
            prompt_ids=prompts,
            pass_rate=0.0,
            embedding=(0.0, 1.0, 0.0),
        )
        session.commit()

        out = run_aggregator(db=session, current_date=CURRENT)
        assert out.alerts_published >= 1

        rows = session.execute(select(ProviderDriftAlert)).scalars().all()
        assert any(a.is_candidate is False for a in rows)
        critical = [a for a in rows if a.severity == "critical"]
        assert len(critical) == 1

    def test_idempotent_rerun_overwrites(self, session) -> None:
        model = _seed_model(session)
        prompts = ("p1", "p2", "p3", "p4", "p5")
        _seed_prompts(session, prompt_ids=prompts)
        for offset in range(DEFAULT_BASELINE_DAYS):
            d = CURRENT - timedelta(days=DEFAULT_BASELINE_DAYS - offset)
            _seed_run_and_probes(
                session,
                model_id=model.id,
                run_date=d,
                prompt_ids=prompts,
                pass_rate=1.0,
            )
        _seed_run_and_probes(
            session,
            model_id=model.id,
            run_date=CURRENT,
            prompt_ids=prompts,
            pass_rate=0.0,
            embedding=(0.0, 1.0, 0.0),
        )
        session.commit()

        run_aggregator(db=session, current_date=CURRENT)
        n_before = session.execute(select(ProviderDriftAlert)).scalars().all()
        assert len(n_before) == 1

        # Re-run on same date — should NOT duplicate.
        run_aggregator(db=session, current_date=CURRENT)
        n_after = session.execute(select(ProviderDriftAlert)).scalars().all()
        assert len(n_after) == 1
        assert n_after[0].id == n_before[0].id

    def test_low_coverage_skipped(self, session) -> None:
        model = _seed_model(session)
        prompts = ("p1", "p2", "p3", "p4", "p5")
        _seed_prompts(session, prompt_ids=prompts)
        # Today: only 1/5 OK (others are rate_limited).
        run = ProviderDriftRun(
            id=str(uuid4()),
            model_id=model.id,
            run_date=CURRENT,
            status="partial",
        )
        session.add(run)
        session.flush()
        session.add(
            ProviderDriftProbe(
                id=str(uuid4()),
                run_id=run.id,
                prompt_id="p1",
                model_id=model.id,
                run_date=CURRENT,
                category="math",
                outcome="ok",
                judge_pass=True,
                cost_usd=0.0,
            )
        )
        for pid in prompts[1:]:
            session.add(
                ProviderDriftProbe(
                    id=str(uuid4()),
                    run_id=run.id,
                    prompt_id=pid,
                    model_id=model.id,
                    run_date=CURRENT,
                    category="math",
                    outcome="rate_limited",
                    cost_usd=0.0,
                )
            )
        session.commit()

        out = run_aggregator(db=session, current_date=CURRENT)
        assert out.alerts_published == 0
        assert out.skipped_for_coverage >= 1
