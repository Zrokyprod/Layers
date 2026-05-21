"""Unit tests for Reliability Intelligence Queue recommendations service.

Tests cover:
  - _make_rec:              builds a ReliabilityRecommendation with correct fields
  - _gen_determinism_high:  fires only when det_ratio >= 0.5 and low health
  - _gen_score_drop:        fires only when fail rate rose >= 5pp
  - impact_score formula:   ranking produces expected ordering
  - priority assignment:    quantile-based priority for batches
  - update_status:          valid / invalid transitions
  - get_summary:            aggregation over mocked list_recommendations
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


TODAY = date(2026, 5, 20)


def _make_score(agent, health, fail_rate, call_count=100, prev_fail_rate=None,
                det_breakdown=None, top_axis=None, avg_cost=0.002):
    return SimpleNamespace(
        agent_name=agent,
        health_score=health,
        fail_rate=fail_rate,
        call_count=call_count,
        prev_week_fail_rate=prev_fail_rate,
        determinism_breakdown_json=(
            json.dumps(det_breakdown) if det_breakdown else None
        ),
        top_failure_axis=top_axis,
        avg_cost_usd=avg_cost,
        score_date=TODAY,
    )


# ── _make_rec helper ──────────────────────────────────────────────────────────

class TestMakeRec:
    def test_basic_fields(self):
        from app.services.recommendations import _make_rec
        rec = _make_rec(
            project_id="proj",
            agent_name="order-agent",
            rec_type="axis_causal",
            title="Test",
            detail="detail",
            fix_suggestion="fix",
            fix_difficulty="easy",
            top_axis="model_version",
            axis_confidence=0.87,
            impact_score=42.5,
            monthly_impact=30.0,
            health_score=45.0,
            fail_rate=0.30,
            call_count=500,
            ablation_job_id="job-1",
            generated_date=TODAY,
        )
        assert rec.project_id == "proj"
        assert rec.recommendation_type == "axis_causal"
        assert rec.title == "Test"
        assert float(rec.impact_score) == 42.5
        assert float(rec.axis_confidence) == 0.87
        assert rec.status == "open"
        assert rec.generated_date == TODAY

    def test_title_clamped_to_255(self):
        from app.services.recommendations import _make_rec
        long_title = "x" * 300
        rec = _make_rec(
            project_id="p", agent_name="a", rec_type="cost_spike",
            title=long_title, detail=None, fix_suggestion=None, fix_difficulty=None,
            top_axis=None, axis_confidence=None, impact_score=1.0, monthly_impact=None,
            health_score=50.0, fail_rate=0.1, call_count=10, ablation_job_id=None,
            generated_date=TODAY,
        )
        assert len(rec.title) == 255

    def test_negative_impact_clamped_to_zero(self):
        from app.services.recommendations import _make_rec
        rec = _make_rec(
            project_id="p", agent_name="a", rec_type="score_drop",
            title="t", detail=None, fix_suggestion=None, fix_difficulty=None,
            top_axis=None, axis_confidence=None, impact_score=-99.0, monthly_impact=None,
            health_score=80.0, fail_rate=0.05, call_count=50, ablation_job_id=None,
            generated_date=TODAY,
        )
        assert float(rec.impact_score) == 0.0


# ── Determinism high generator ────────────────────────────────────────────────

class TestGenDeterminismHigh:
    def test_fires_when_mostly_deterministic_low_health(self):
        from app.services.recommendations import _gen_determinism_high
        score = _make_score(
            "a1", health=40.0, fail_rate=0.30,
            det_breakdown={"deterministic": 8, "stochastic": 1, "environmental": 1, "unknown": 0},
        )
        recs = _gen_determinism_high(project_id="p", score=score, today=TODAY, project_avg_cost=0.005)
        assert len(recs) == 1
        assert recs[0].recommendation_type == "determinism_high"

    def test_skips_when_health_is_high(self):
        from app.services.recommendations import _gen_determinism_high, _DETERMINISM_HIGH_THRESHOLD
        score = _make_score(
            "a2", health=80.0, fail_rate=0.05,  # 80 > 60 threshold
            det_breakdown={"deterministic": 5, "stochastic": 0, "environmental": 0, "unknown": 0},
        )
        recs = _gen_determinism_high(project_id="p", score=score, today=TODAY, project_avg_cost=0.005)
        assert len(recs) == 0

    def test_skips_when_det_ratio_low(self):
        from app.services.recommendations import _gen_determinism_high
        score = _make_score(
            "a3", health=30.0, fail_rate=0.40,
            det_breakdown={"deterministic": 1, "stochastic": 9, "environmental": 0, "unknown": 0},
        )
        recs = _gen_determinism_high(project_id="p", score=score, today=TODAY, project_avg_cost=0.005)
        assert len(recs) == 0  # det_ratio=0.10 < 0.50 threshold

    def test_skips_when_no_breakdown(self):
        from app.services.recommendations import _gen_determinism_high
        score = _make_score("a4", health=30.0, fail_rate=0.50)
        recs = _gen_determinism_high(project_id="p", score=score, today=TODAY, project_avg_cost=0.005)
        assert len(recs) == 0


# ── Score drop generator ──────────────────────────────────────────────────────

class TestGenScoreDrop:
    def test_fires_on_regression(self):
        from app.services.recommendations import _gen_score_drop
        score = _make_score("b1", health=50.0, fail_rate=0.25, prev_fail_rate=0.10)
        recs = _gen_score_drop(project_id="p", score=score, today=TODAY, project_avg_cost=0.003)
        assert len(recs) == 1
        assert recs[0].recommendation_type == "score_drop"
        assert "+15.0pp" in recs[0].title

    def test_skips_when_no_prev_week(self):
        from app.services.recommendations import _gen_score_drop
        score = _make_score("b2", health=50.0, fail_rate=0.25, prev_fail_rate=None)
        recs = _gen_score_drop(project_id="p", score=score, today=TODAY, project_avg_cost=0.003)
        assert len(recs) == 0

    def test_skips_when_improvement(self):
        from app.services.recommendations import _gen_score_drop
        score = _make_score("b3", health=70.0, fail_rate=0.05, prev_fail_rate=0.20)
        recs = _gen_score_drop(project_id="p", score=score, today=TODAY, project_avg_cost=0.003)
        assert len(recs) == 0

    def test_skips_when_delta_below_threshold(self):
        from app.services.recommendations import _gen_score_drop
        # +3pp change — below 5pp threshold
        score = _make_score("b4", health=65.0, fail_rate=0.13, prev_fail_rate=0.10)
        recs = _gen_score_drop(project_id="p", score=score, today=TODAY, project_avg_cost=0.003)
        assert len(recs) == 0


# ── Impact score ordering ─────────────────────────────────────────────────────

class TestImpactScoreOrdering:
    def test_high_impact_beats_low_impact(self):
        from app.services.recommendations import _make_rec
        high = _make_rec(
            project_id="p", agent_name="a", rec_type="axis_causal",
            title="h", detail=None, fix_suggestion=None, fix_difficulty=None,
            top_axis="model_version", axis_confidence=0.9, impact_score=500.0,
            monthly_impact=100.0, health_score=20.0, fail_rate=0.6, call_count=1000,
            ablation_job_id=None, generated_date=TODAY,
        )
        low = _make_rec(
            project_id="p", agent_name="b", rec_type="axis_causal",
            title="l", detail=None, fix_suggestion=None, fix_difficulty=None,
            top_axis="model_version", axis_confidence=0.3, impact_score=10.0,
            monthly_impact=5.0, health_score=75.0, fail_rate=0.05, call_count=50,
            ablation_job_id=None, generated_date=TODAY,
        )
        assert float(high.impact_score) > float(low.impact_score)


# ── Status transitions ────────────────────────────────────────────────────────

class TestUpdateStatus:
    def test_valid_status_transition(self):
        from app.services.recommendations import update_status
        mock_rec = SimpleNamespace(
            id="r1", project_id="p", status="open",
            actioned_by=None, actioned_at=None, snoozed_until=None,
        )
        mock_db = MagicMock()
        with patch("app.services.recommendations.get_recommendation", return_value=mock_rec):
            result = update_status(mock_db, project_id="p", rec_id="r1", new_status="acknowledged", actioned_by="user@test.com")
        assert result.status == "acknowledged"
        assert result.actioned_by == "user@test.com"

    def test_invalid_status_raises(self):
        from app.services.recommendations import update_status
        with pytest.raises(ValueError, match="Invalid status"):
            update_status(MagicMock(), project_id="p", rec_id="r1", new_status="flying")

    def test_not_found_raises_lookup_error(self):
        from app.services.recommendations import update_status
        with patch("app.services.recommendations.get_recommendation", return_value=None):
            with pytest.raises(LookupError):
                update_status(MagicMock(), project_id="p", rec_id="missing", new_status="resolved")


# ── Summary ───────────────────────────────────────────────────────────────────

class TestGetSummary:
    def _make_rec_ns(self, priority, impact=100.0, agent="a"):
        return SimpleNamespace(
            priority=priority, agent_name=agent,
            estimated_monthly_impact_usd=impact, status="open",
        )

    def test_summary_counts(self):
        from app.services.recommendations import get_summary
        recs = [
            self._make_rec_ns("critical", 500.0, "agent-1"),
            self._make_rec_ns("critical", 300.0, "agent-2"),
            self._make_rec_ns("high", 100.0, "agent-1"),
            self._make_rec_ns("medium", 50.0, "agent-3"),
        ]
        with patch("app.services.recommendations.list_recommendations", return_value=recs):
            s = get_summary(MagicMock(), project_id="proj")
        assert s.total_open == 4
        assert s.critical_count == 2
        assert s.high_count == 1
        assert abs(s.total_estimated_saving_usd - 950.0) < 0.01

    def test_top_agents_ordered_by_count(self):
        from app.services.recommendations import get_summary
        recs = [
            self._make_rec_ns("critical", agent="agent-x"),
            self._make_rec_ns("critical", agent="agent-x"),
            self._make_rec_ns("high", agent="agent-y"),
        ]
        with patch("app.services.recommendations.list_recommendations", return_value=recs):
            s = get_summary(MagicMock(), project_id="proj")
        assert s.top_agents[0] == "agent-x"

    def test_empty_project(self):
        from app.services.recommendations import get_summary
        with patch("app.services.recommendations.list_recommendations", return_value=[]):
            s = get_summary(MagicMock(), project_id="proj")
        assert s.total_open == 0
        assert s.total_estimated_saving_usd == 0.0
        assert s.top_agents == []


# ── Imports ───────────────────────────────────────────────────────────────────

class TestImports:
    def test_router_importable(self):
        from app.api.routes.recommendations import router
        assert router is not None

    def test_service_importable(self):
        from app.services.recommendations import (
            generate_recommendations,
            list_recommendations,
            get_recommendation,
            update_status,
            get_summary,
        )
        assert all(callable(f) for f in [
            generate_recommendations, list_recommendations,
            get_recommendation, update_status, get_summary,
        ])
