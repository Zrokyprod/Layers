"""
Tests for `app/services/judge_calibration.py` (Module 7).

Coverage:
  - record_sample: in-memory append; bookkeeping; idempotency-not-claimed
  - compute_drift: empty / below-floor / above-threshold / at-threshold
  - alert callback fires only on breach + below-floor suppression
  - clear_all wipes state
  - missing project_id / judge_model handled as no-op
  - rolling-window prune: old samples beyond the window are dropped
"""
from __future__ import annotations

import time

import pytest

from app.core.config import get_settings
from app.services import judge_calibration
from app.services.judge_calibration import (
    DimensionDriftStatus,
    DriftStatus,
    clear_all,
    compute_dimension_drift,
    compute_drift,
    record_dimension_sample,
    record_sample,
    register_alert_callback,
)


@pytest.fixture(autouse=True)
def _isolate_calibration_state():
    """Wipe per-process state before and after each test."""
    judge_calibration._unregister_all_callbacks_for_tests()
    clear_all()
    yield
    judge_calibration._unregister_all_callbacks_for_tests()
    clear_all()


@pytest.fixture()
def calibration_settings(monkeypatch):
    """Tune calibration thresholds to small values for fast tests."""
    s = get_settings()
    snapshot = {
        "JUDGE_CALIBRATION_DRIFT_THRESHOLD": s.JUDGE_CALIBRATION_DRIFT_THRESHOLD,
        "JUDGE_CALIBRATION_WINDOW_HOURS": s.JUDGE_CALIBRATION_WINDOW_HOURS,
        "JUDGE_CALIBRATION_MIN_SAMPLES": s.JUDGE_CALIBRATION_MIN_SAMPLES,
    }
    s.JUDGE_CALIBRATION_DRIFT_THRESHOLD = 0.20  # 20% disagreement allowed
    s.JUDGE_CALIBRATION_WINDOW_HOURS = 1
    s.JUDGE_CALIBRATION_MIN_SAMPLES = 5
    yield s
    for k, v in snapshot.items():
        setattr(s, k, v)


@pytest.fixture()
def force_memory_store(monkeypatch):
    """Force the in-memory store path even if a local Redis is available.

    Tests that probe the in-memory branch should use this to avoid
    cross-contamination from a developer's local Redis.
    """
    monkeypatch.setattr(judge_calibration, "_redis_client", lambda: None)


pytestmark = pytest.mark.usefixtures("force_memory_store")


# ──────────────────────────────────────────────────────────────────────────
# record_sample + compute_drift basics
# ──────────────────────────────────────────────────────────────────────────


class TestRecordSample:
    def test_first_record_returns_status(self, calibration_settings) -> None:
        st = record_sample(
            project_id="p1",
            judge_model="m1",
            judge_verdict="pass",
            truth_verdict="pass",
        )
        assert isinstance(st, DriftStatus)
        assert st.project_id == "p1"
        assert st.judge_model == "m1"
        assert st.sample_count == 1
        assert st.disagreement_count == 0
        assert st.disagreement_rate == 0.0

    def test_disagreement_counted(self, calibration_settings) -> None:
        record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        st = record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="fail",
        )
        assert st.sample_count == 2
        assert st.disagreement_count == 1
        assert st.disagreement_rate == 0.5

    def test_below_floor_does_not_breach(self, calibration_settings) -> None:
        # Threshold 20%, min_samples 5. 1/4 disagreement = 25% but only 4
        # samples → no breach.
        for jv, tv in [("pass", "pass"), ("pass", "pass"),
                       ("pass", "pass"), ("pass", "fail")]:
            st = record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert st.sample_count == 4
        assert st.disagreement_rate == 0.25
        assert st.breached is False  # below MIN_SAMPLES floor

    def test_above_floor_and_threshold_breaches(self, calibration_settings) -> None:
        # 5 samples, 2 disagreements = 40% > 20%
        for jv, tv in [("pass", "pass"), ("pass", "pass"), ("pass", "pass"),
                       ("pass", "fail"), ("fail", "pass")]:
            st = record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert st.sample_count == 5
        assert st.disagreement_count == 2
        assert st.disagreement_rate == 0.4
        assert st.breached is True

    def test_exactly_at_threshold_does_not_breach(self, calibration_settings) -> None:
        # Threshold 20%; 5 samples 1 disagreement = 20% (not strictly > 20%)
        for jv, tv in [("pass", "pass")] * 4 + [("pass", "fail")]:
            st = record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert st.disagreement_rate == 0.2
        assert st.breached is False

    def test_empty_project_id_is_noop(self, calibration_settings) -> None:
        st = record_sample(
            project_id="", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        assert st.sample_count == 0
        assert st.breached is False

    def test_empty_judge_model_is_noop(self, calibration_settings) -> None:
        st = record_sample(
            project_id="p1", judge_model="",
            judge_verdict="pass", truth_verdict="pass",
        )
        assert st.sample_count == 0

    def test_isolation_across_models(self, calibration_settings) -> None:
        record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        st = record_sample(
            project_id="p1", judge_model="m2",
            judge_verdict="fail", truth_verdict="pass",
        )
        # m2's window is independent of m1.
        assert st.sample_count == 1
        assert st.disagreement_count == 1

    def test_isolation_across_projects(self, calibration_settings) -> None:
        record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        st = record_sample(
            project_id="p2", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        assert st.sample_count == 1  # p2's first sample


# ──────────────────────────────────────────────────────────────────────────
# compute_drift (read-only)
# ──────────────────────────────────────────────────────────────────────────


class TestComputeDrift:
    def test_empty_window_returns_zero(self, calibration_settings) -> None:
        st = compute_drift("p-nonexistent", "m-nonexistent")
        assert st.sample_count == 0
        assert st.disagreement_count == 0
        assert st.disagreement_rate == 0.0
        assert st.breached is False

    def test_reflects_recorded_samples(self, calibration_settings) -> None:
        for jv, tv in [("pass", "pass"), ("pass", "pass"),
                       ("pass", "fail"), ("fail", "pass")]:
            record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        st = compute_drift("p1", "m1")
        assert st.sample_count == 4
        assert st.disagreement_count == 2

    def test_threshold_inherited_from_settings(self, calibration_settings) -> None:
        st = compute_drift("p1", "m1")
        assert st.threshold == 0.20


# ──────────────────────────────────────────────────────────────────────────
# alert callbacks
# ──────────────────────────────────────────────────────────────────────────


class TestAlertCallbacks:
    def test_callback_fires_on_breach(self, calibration_settings) -> None:
        received: list[DriftStatus] = []
        register_alert_callback(lambda st: received.append(st))
        for jv, tv in [("pass", "pass"), ("pass", "pass"), ("pass", "pass"),
                       ("pass", "fail"), ("fail", "pass")]:
            record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert len(received) == 1
        assert received[0].breached is True
        assert received[0].project_id == "p1"

    def test_callback_does_not_fire_below_floor(self, calibration_settings) -> None:
        received: list[DriftStatus] = []
        register_alert_callback(lambda st: received.append(st))
        # 4 samples, 2 disagreements = 50% but below floor of 5.
        for jv, tv in [("pass", "pass"), ("pass", "pass"),
                       ("pass", "fail"), ("fail", "pass")]:
            record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert received == []

    def test_callback_does_not_fire_below_threshold(
        self, calibration_settings
    ) -> None:
        received: list[DriftStatus] = []
        register_alert_callback(lambda st: received.append(st))
        # 10 samples, 1 disagreement = 10% < 20% threshold.
        samples = [("pass", "pass")] * 9 + [("pass", "fail")]
        for jv, tv in samples:
            record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert received == []

    def test_callback_exception_does_not_propagate(self, calibration_settings) -> None:
        def boom(_st: DriftStatus) -> None:
            raise RuntimeError("alert sink down")

        register_alert_callback(boom)
        # Make the next sample breach the threshold.
        for jv, tv in [("pass", "pass"), ("pass", "pass"), ("pass", "pass"),
                       ("pass", "fail"), ("fail", "pass")]:
            # Should not raise even though the callback throws.
            record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )

    def test_register_non_callable_rejected(self) -> None:
        with pytest.raises(TypeError):
            register_alert_callback("not callable")  # type: ignore[arg-type]

    def test_multiple_callbacks_all_fire(self, calibration_settings) -> None:
        a: list[DriftStatus] = []
        b: list[DriftStatus] = []
        register_alert_callback(lambda st: a.append(st))
        register_alert_callback(lambda st: b.append(st))
        for jv, tv in [("pass", "pass"), ("pass", "pass"), ("pass", "pass"),
                       ("pass", "fail"), ("fail", "pass")]:
            record_sample(
                project_id="p1", judge_model="m1",
                judge_verdict=jv, truth_verdict=tv,
            )
        assert len(a) == 1
        assert len(b) == 1


# ──────────────────────────────────────────────────────────────────────────
# rolling-window prune
# ──────────────────────────────────────────────────────────────────────────


class TestWindowPrune:
    def test_old_samples_dropped_by_window(
        self, calibration_settings, monkeypatch
    ) -> None:
        # Set window to 1 hour; manually inject ancient samples into the
        # memory store then record a fresh one and confirm prune.
        old_ts = time.time() - 7200  # 2 hours ago, outside 1h window
        judge_calibration._memory_store[("p1", "m1")] = [
            (old_ts, "pass", "fail"),
            (old_ts, "pass", "fail"),
        ]
        st = record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        # Only the fresh sample survives.
        assert st.sample_count == 1
        assert st.disagreement_count == 0


# ──────────────────────────────────────────────────────────────────────────
# clear_all
# ──────────────────────────────────────────────────────────────────────────


class TestClearAll:
    def test_wipes_in_memory_state(self, calibration_settings) -> None:
        record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="fail",
        )
        assert compute_drift("p1", "m1").sample_count == 1
        clear_all()
        assert compute_drift("p1", "m1").sample_count == 0


# ──────────────────────────────────────────────────────────────────────────
# DriftStatus shape
# ──────────────────────────────────────────────────────────────────────────


class TestDriftStatus:
    def test_to_dict_is_json_serializable(self, calibration_settings) -> None:
        import json as _json

        st = record_sample(
            project_id="p1", judge_model="m1",
            judge_verdict="pass", truth_verdict="pass",
        )
        d = st.to_dict()
        _json.dumps(d)  # must not raise
        assert d["project_id"] == "p1"
        assert d["judge_model"] == "m1"


# ──────────────────────────────────────────────────────────────────────────
# Per-dimension drift (Layer 3 extension)
# ──────────────────────────────────────────────────────────────────────────


class TestPerDimensionDrift:
    """`record_dimension_sample` + `compute_dimension_drift` smoke tests.

    The threshold/min-samples values come from module constants
    (_DIMENSION_DRIFT_THRESHOLD=0.10, _DIMENSION_MIN_SAMPLES_PER_HALF=10).
    These tests assume those defaults — if they ever change, update here.
    """

    def test_first_sample_returns_zero_drift(self) -> None:
        st = record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="groundedness", score=0.85,
        )
        assert isinstance(st, DimensionDriftStatus)
        assert st.sample_count == 1
        assert st.older_mean == 0.85
        assert st.recent_mean == 0.85
        assert st.drift == 0.0
        assert st.breached is False

    def test_below_minimum_samples_does_not_breach(self) -> None:
        # 6 older + 6 recent samples (n=12, half=6). Below min-10 floor → no breach
        # even with a huge drift.
        for _ in range(6):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.95,
            )
        for _ in range(6):
            st = record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.30,
            )
        assert st.sample_count == 12
        assert st.drift >= 0.6  # massive degradation
        assert st.breached is False  # but min-samples gate suppresses

    def test_above_min_with_meaningful_drift_breaches(self) -> None:
        # 10 older at 0.90, 10 recent at 0.65 → drift 0.25 > threshold 0.10.
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.90,
            )
        for _ in range(10):
            st = record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.65,
            )
        assert st.sample_count == 20
        assert st.older_mean == 0.90
        assert st.recent_mean == 0.65
        assert st.drift == 0.25
        assert st.breached is True

    def test_score_improvement_does_not_breach(self) -> None:
        # Negative drift (improvement) should never breach.
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="accuracy", score=0.60,
            )
        for _ in range(10):
            st = record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="accuracy", score=0.90,
            )
        assert st.drift < 0  # negative drift = improvement
        assert st.breached is False

    def test_drift_below_threshold_does_not_breach(self) -> None:
        # 0.85 -> 0.80 = 0.05 drift, under 0.10 threshold.
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="relevance", score=0.85,
            )
        for _ in range(10):
            st = record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="relevance", score=0.80,
            )
        assert st.drift == 0.05
        assert st.breached is False

    def test_scores_are_clamped_to_unit_interval(self) -> None:
        st = record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="relevance", score=1.7,  # invalid input
        )
        assert st.older_mean == 1.0  # clamped to upper bound

        st2 = record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="coherence", score=-0.4,  # invalid input
        )
        assert st2.older_mean == 0.0  # clamped to lower bound

    def test_invalid_score_returns_zero_status(self) -> None:
        st = record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="relevance", score="not_a_number",  # type: ignore[arg-type]
        )
        assert st.sample_count == 0
        assert st.breached is False

    def test_empty_project_or_model_or_dim_is_noop(self) -> None:
        for pid, model, dim in [("", "m1", "g"), ("p1", "", "g"), ("p1", "m1", "")]:
            st = record_dimension_sample(
                project_id=pid, judge_model=model, dimension=dim, score=0.5,
            )
            assert st.sample_count == 0
            assert st.breached is False

    def test_isolation_across_dimensions(self) -> None:
        # Drift on `groundedness` should not affect `accuracy` calibration.
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.90,
            )
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.50,
            )
        record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="accuracy", score=0.85,
        )

        groundedness_status = compute_dimension_drift("p1", "m1", "groundedness")
        accuracy_status = compute_dimension_drift("p1", "m1", "accuracy")

        assert groundedness_status.sample_count == 20
        assert groundedness_status.breached is True
        assert accuracy_status.sample_count == 1
        assert accuracy_status.breached is False

    def test_isolation_across_models(self) -> None:
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="haiku",
                dimension="groundedness", score=0.90,
            )
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="haiku",
                dimension="groundedness", score=0.50,
            )

        gpt_status = compute_dimension_drift("p1", "gpt-4o-mini", "groundedness")
        assert gpt_status.sample_count == 0
        assert gpt_status.breached is False

    def test_alert_callback_fires_on_dimension_breach(self) -> None:
        captured: list[object] = []
        register_alert_callback(lambda st: captured.append(st))

        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.90,
            )
        for _ in range(10):
            record_dimension_sample(
                project_id="p1", judge_model="m1",
                dimension="groundedness", score=0.50,
            )

        # At least one callback invocation with a breaching DimensionDriftStatus.
        breaches = [c for c in captured if isinstance(c, DimensionDriftStatus) and c.breached]
        assert len(breaches) >= 1
        assert breaches[-1].dimension == "groundedness"

    def test_compute_dimension_drift_without_recording(self) -> None:
        st = compute_dimension_drift("nobody", "nothing", "groundedness")
        assert st.sample_count == 0
        assert st.breached is False

    def test_dimension_status_to_dict_is_json_serializable(self) -> None:
        import json as _json

        st = record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="groundedness", score=0.8,
        )
        d = st.to_dict()
        _json.dumps(d)  # must not raise
        assert d["dimension"] == "groundedness"
        assert d["older_mean"] == 0.8

    def test_clear_all_wipes_dimension_state(self) -> None:
        record_dimension_sample(
            project_id="p1", judge_model="m1",
            dimension="groundedness", score=0.8,
        )
        assert compute_dimension_drift("p1", "m1", "groundedness").sample_count == 1
        clear_all()
        assert compute_dimension_drift("p1", "m1", "groundedness").sample_count == 0
