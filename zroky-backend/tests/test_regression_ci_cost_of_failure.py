"""Tests for `app.services.regression_ci.cost_of_failure.compute_pr_savings`.

The function is the Wedge 4 bridge between the regression-CI gate and
the cost-of-failure attribution surface. It must:

  * Return None when the project has zero outcome cost in the lookback.
  * Return None on DB error (never raise — the regression-CI run must
    never crash because of an attribution side query).
  * Compute cost_per_failed_call from attached outcome cost / failed
    call count, falling back to total outcome cost when no attached
    cost is available.
  * Cap the displayed risk at RISK_CEILING_USD.
  * Emit a stable schema dict the PR-comment formatter can render.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.regression_ci.cost_of_failure import (
    LOOKBACK_DAYS,
    RISK_CEILING_USD,
    compute_pr_savings,
)


def _db_with_scalars(values: list[float | int]) -> MagicMock:
    """Return a MagicMock db whose `execute(...).scalar()` calls
    return the given values in order — one per query in compute_pr_savings."""
    db = MagicMock()
    results = [MagicMock(**{"scalar.return_value": v}) for v in values]
    db.execute.side_effect = results
    return db


class TestEdgeCases:
    def test_blank_project_returns_none(self):
        db = MagicMock()
        assert compute_pr_savings(db, project_id="", regressed_count=5) is None
        assert compute_pr_savings(db, project_id="   ", regressed_count=5) is None
        # No DB queries should have been issued for a blank project.
        assert db.execute.call_count == 0

    def test_negative_regressed_count_clamped_to_zero(self):
        # Total cost = 100, attached cost = 80, failed_calls = 10.
        # cost_per_failed_call = 80/10 = 8.0; risk = 0 * 8 = 0.
        db = _db_with_scalars([100.0, 80.0, 10])
        snap = compute_pr_savings(
            db, project_id="proj-1", regressed_count=-3,
        )
        assert snap is not None
        assert snap["regressed_in_pr"] == 0
        assert snap["estimated_monthly_risk_usd"] == 0.0

    def test_zero_total_outcome_cost_returns_none(self):
        # Project has no outcome data → no signal → return None so the
        # PR comment doesn't render a misleading "$0 risk" tag.
        db = _db_with_scalars([0.0])
        assert compute_pr_savings(
            db, project_id="proj-1", regressed_count=5
        ) is None

    def test_db_error_returns_none(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("connection lost")
        assert compute_pr_savings(
            db, project_id="proj-1", regressed_count=5
        ) is None


class TestComputation:
    def test_typical_case(self):
        # Project: $11,840 / 30d cost, $9,500 attached to failed calls,
        # 247 failed calls → $38.46/call. PR has 12 regressions →
        # estimated risk = 12 × 38.46 = $461.51/mo.
        db = _db_with_scalars([11_840.0, 9_500.0, 247])
        snap = compute_pr_savings(
            db, project_id="proj-1", regressed_count=12,
        )
        assert snap is not None
        assert snap["outcome_cost_30d_usd"] == pytest.approx(11_840.0)
        assert snap["failed_call_count_30d"] == 247
        assert snap["regressed_in_pr"] == 12
        assert snap["cost_per_failed_call_usd"] == pytest.approx(
            9_500.0 / 247, rel=1e-3,
        )
        expected_risk = 12 * (9_500.0 / 247)
        assert snap["estimated_monthly_risk_usd"] == pytest.approx(
            expected_risk, rel=1e-3,
        )
        assert snap["method"] == "linear_extrapolation"

    def test_falls_back_to_total_when_no_attached_cost(self):
        # Some projects post outcome events without call_id. We still
        # produce a useful risk number using total / failed_call_count.
        db = _db_with_scalars([1000.0, 0.0, 10])
        snap = compute_pr_savings(
            db, project_id="proj-1", regressed_count=2,
        )
        assert snap is not None
        # cost_per_failed_call = 1000/10 = 100; risk = 2 * 100 = 200
        assert snap["cost_per_failed_call_usd"] == pytest.approx(100.0)
        assert snap["estimated_monthly_risk_usd"] == pytest.approx(200.0)

    def test_zero_failed_calls_yields_zero_per_call_cost(self):
        # Outcomes exist but no diagnosed failed calls — we don't have
        # a meaningful per-call basis, so cost_per_failed_call = 0
        # and the risk is naturally 0 even with regressions.
        db = _db_with_scalars([500.0, 0.0, 0])
        snap = compute_pr_savings(
            db, project_id="proj-1", regressed_count=4,
        )
        assert snap is not None
        assert snap["cost_per_failed_call_usd"] == 0.0
        assert snap["estimated_monthly_risk_usd"] == 0.0

    def test_risk_ceiling_caps_pathological_value(self):
        # $1B total, $1B attached, 1 failed call = $1B/call.
        # Times 5 regressions = $5B, capped at RISK_CEILING_USD.
        db = _db_with_scalars([1_000_000_000.0, 1_000_000_000.0, 1])
        snap = compute_pr_savings(
            db, project_id="proj-1", regressed_count=5,
        )
        assert snap is not None
        assert snap["estimated_monthly_risk_usd"] == RISK_CEILING_USD


class TestSchemaContract:
    def test_keys_match_pr_comment_expectations(self):
        db = _db_with_scalars([100.0, 50.0, 5])
        snap = compute_pr_savings(
            db, project_id="proj-1", regressed_count=1,
        )
        assert snap is not None
        # The PR-comment formatter reads exactly these keys.
        for key in (
            "outcome_cost_30d_usd",
            "failed_call_count_30d",
            "regressed_in_pr",
            "cost_per_failed_call_usd",
            "estimated_monthly_risk_usd",
            "method",
        ):
            assert key in snap, f"missing required key: {key!r}"

    def test_lookback_default_is_30_days(self):
        # Sanity assertion so future refactors don't accidentally drift
        # from the dashboard's 30-day window.
        assert LOOKBACK_DAYS == 30
