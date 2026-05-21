"""Layer 4 tests for `app.services.provider_drift.drift_detector`."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

import pytest

from app.services.provider_drift.drift_detector import (
    CRITICAL_DELTA_PP,
    DEFAULT_BASELINE_DAYS,
    Z_INFO,
    ProbeRow,
    classify,
    compute_drift,
)
from app.services.provider_drift.models import DriftMetric

CURRENT = date(2026, 5, 18)


def _baseline_dates(n: int = DEFAULT_BASELINE_DAYS) -> list[date]:
    return [CURRENT - timedelta(days=n - i) for i in range(n)]


def _make_probes(
    *,
    prompt_ids: Sequence[str],
    days: Sequence[date],
    pass_rate: float = 1.0,
    embedding_provider=lambda pid, d: (1.0, 0.0, 0.0),
) -> list[ProbeRow]:
    """Generate probes for each (prompt_id, day) with a given pass rate."""
    rows: list[ProbeRow] = []
    n_prompts = len(prompt_ids)
    n_pass = int(round(pass_rate * n_prompts))
    for d in days:
        passes = set(prompt_ids[:n_pass])
        for pid in prompt_ids:
            rows.append(
                ProbeRow(
                    prompt_id=pid,
                    run_date=d,
                    outcome="ok",
                    judge_pass=(pid in passes),
                    embedding=embedding_provider(pid, d),
                )
            )
    return rows


# ── compute_drift ───────────────────────────────────────────────────────────


class TestComputeDriftHappyPath:
    def test_no_drift_returns_zero_z(self) -> None:
        prompts = ["p1", "p2", "p3", "p4", "p5"]
        days = _baseline_dates() + [CURRENT]
        probes = _make_probes(prompt_ids=prompts, days=days, pass_rate=0.8)
        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is not None
        assert m.pass_rate_current == pytest.approx(0.8)
        assert m.pass_rate_baseline == pytest.approx(0.8)
        assert m.judge_z == pytest.approx(0.0)

    def test_pass_rate_drop_produces_negative_z(self) -> None:
        prompts = ["p1", "p2", "p3", "p4", "p5"]
        baseline = _baseline_dates()

        # Baseline: 80% pass-rate every day.
        probes = _make_probes(prompt_ids=prompts, days=baseline, pass_rate=0.8)
        # Today: 20% pass-rate.
        probes += _make_probes(prompt_ids=prompts, days=[CURRENT], pass_rate=0.2)

        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is not None
        assert m.pass_rate_current == pytest.approx(0.2)
        assert m.pass_rate_baseline == pytest.approx(0.8)
        assert m.judge_z < 0  # drop ⇒ negative
        # Magnitude bounded by stddev floor: |z| ≈ |Δ|/floor = 0.6/0.02 = 30.
        assert abs(m.judge_z) >= 20.0


class TestComputeDriftCoverageGate:
    def test_low_today_coverage_returns_none(self) -> None:
        prompts = ["p1", "p2", "p3", "p4", "p5"]
        baseline = _baseline_dates()
        probes = _make_probes(prompt_ids=prompts, days=baseline, pass_rate=0.8)
        # Today: only 1/5 = 20% coverage.
        probes.append(ProbeRow("p1", CURRENT, "ok", True, (1.0, 0.0, 0.0)))
        for pid in prompts[1:]:
            probes.append(ProbeRow(pid, CURRENT, "rate_limited", None, None))

        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is None

    def test_low_baseline_day_coverage_returns_none(self) -> None:
        prompts = ["p1", "p2", "p3", "p4", "p5"]
        baseline = _baseline_dates()
        probes = _make_probes(prompt_ids=prompts, days=baseline, pass_rate=0.8)
        # Knock out coverage on the FIRST baseline day to <80%.
        broken_day = baseline[0]
        probes = [p for p in probes if not (p.run_date == broken_day and p.prompt_id in prompts[:2])]
        probes.append(ProbeRow("p1", broken_day, "error", None, None))
        probes.append(ProbeRow("p2", broken_day, "error", None, None))
        probes += _make_probes(prompt_ids=prompts, days=[CURRENT], pass_rate=0.8)

        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is None

    def test_no_probes_today_returns_none(self) -> None:
        prompts = ["p1", "p2", "p3"]
        probes = _make_probes(
            prompt_ids=prompts, days=_baseline_dates(), pass_rate=1.0
        )
        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is None

    def test_zero_category_size_returns_none(self) -> None:
        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=[],
            category_size=0,
        )
        assert m is None


class TestEmbeddingDrift:
    def test_consistent_embeddings_zero_z(self) -> None:
        prompts = ["p1", "p2", "p3", "p4", "p5"]
        days = _baseline_dates() + [CURRENT]
        probes = _make_probes(
            prompt_ids=prompts,
            days=days,
            pass_rate=1.0,
            embedding_provider=lambda pid, d: (1.0, 0.0, 0.0),
        )
        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is not None
        assert abs(m.embedding_z) < 0.5

    def test_today_orthogonal_embeddings_negative_z(self) -> None:
        prompts = ["p1", "p2", "p3", "p4", "p5"]
        baseline = _baseline_dates()

        def baseline_emb(pid, d):
            return (1.0, 0.0, 0.0)

        def today_emb(pid, d):
            return (0.0, 1.0, 0.0)  # orthogonal → cosine = 0

        probes = _make_probes(
            prompt_ids=prompts,
            days=baseline,
            pass_rate=1.0,
            embedding_provider=baseline_emb,
        )
        probes += _make_probes(
            prompt_ids=prompts,
            days=[CURRENT],
            pass_rate=1.0,
            embedding_provider=today_emb,
        )
        m = compute_drift(
            model_id="m",
            category="math",
            current_date=CURRENT,
            probes=probes,
            category_size=len(prompts),
        )
        assert m is not None
        assert m.embedding_z < 0  # cosine fell


# ── classify ────────────────────────────────────────────────────────────────


def _metric(**kw) -> DriftMetric:
    defaults = dict(
        model_id="m",
        category="math",
        current_date=CURRENT,
        baseline_start=CURRENT - timedelta(days=7),
        baseline_end=CURRENT - timedelta(days=1),
        pass_rate_current=0.5,
        pass_rate_baseline=0.5,
        pass_rate_stddev=0.05,
        judge_z=0.0,
        embedding_z=0.0,
        coverage_current=1.0,
        coverage_baseline_min=1.0,
        sample_size_current=10,
        sample_size_baseline=70,
    )
    defaults.update(kw)
    return DriftMetric(**defaults)


class TestClassify:
    def test_no_drift_returns_none(self) -> None:
        assert classify(_metric()) is None

    def test_single_metric_trip_is_candidate(self) -> None:
        v = classify(_metric(judge_z=-3.0, embedding_z=0.0))
        assert v is not None
        assert v.publish is False
        assert v.is_candidate is True

    def test_both_metrics_same_sign_publishes(self) -> None:
        v = classify(_metric(judge_z=-3.0, embedding_z=-2.5))
        assert v is not None
        assert v.publish is True
        assert v.is_candidate is False

    def test_disagreeing_signs_is_candidate(self) -> None:
        v = classify(_metric(judge_z=-3.0, embedding_z=2.5))
        assert v is not None
        assert v.publish is False
        assert v.is_candidate is True

    def test_critical_severity_via_z(self) -> None:
        v = classify(_metric(judge_z=-5.0, embedding_z=-4.5))
        assert v is not None
        assert v.severity == "critical"

    def test_critical_severity_via_delta(self) -> None:
        v = classify(_metric(
            pass_rate_current=0.5, pass_rate_baseline=0.7,
            judge_z=-2.5, embedding_z=-2.5,
        ))
        # |delta_pp| = 20 ≥ 15 → critical
        assert v is not None
        assert v.severity == "critical"

    def test_warn_severity(self) -> None:
        v = classify(_metric(judge_z=-3.2, embedding_z=-3.1))
        assert v is not None
        assert v.severity == "warn"

    def test_info_severity(self) -> None:
        v = classify(_metric(judge_z=-2.1, embedding_z=-2.05))
        assert v is not None
        assert v.severity == "info"
