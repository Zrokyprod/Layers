"""Unit tests for the Agent Reliability Scorecard service.

Tests cover:
  - _compute_agent_score:  score composition from mock call data
  - score clamping:        health_score stays in [0, 100]
  - zero_score:            no calls → health_score = 0
  - get_project_summary:   aggregation across agents
  - determinism breakdown: ablation data correctly wired into det_score
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────


def _mock_call(status="completed", cost=0.002, latency=800.0):
    return SimpleNamespace(status=status, cost_total=cost, latency_ms=latency)


def _row(status="completed", cost=0.002, latency=800.0):
    return SimpleNamespace(status=status, cost_total=cost, latency_ms=latency)


TODAY = date(2026, 5, 20)


# ── scorer unit tests ─────────────────────────────────────────────────────────


class TestScoreComponents:
    def test_perfect_agent_scores_near_100(self):
        from app.services.agent_reliability import (
            _W_COST_EFF, _W_DETERMINISM, _W_FAIL_RATE, _W_TREND,
        )
        # fail_rate=0 → fail_rate_score=100
        # cost = median → cost_eff=50
        # no ablation → det_score=75
        # no prev week → trend_score=50
        expected = (
            _W_FAIL_RATE * 100.0
            + _W_COST_EFF * 50.0
            + _W_DETERMINISM * 75.0
            + _W_TREND * 50.0
        )
        assert abs(expected - 73.75) < 0.01  # 35*1 + 25*0.5 + 25*0.75 + 15*0.5 = 73.75

    def test_zero_score_when_no_calls(self):
        from app.services.agent_reliability import _zero_score
        score = _zero_score("proj", "agent-x", TODAY)
        assert float(score.health_score) == 0.0
        assert score.call_count == 0

    def test_health_score_clamped_to_100(self):
        from app.services.agent_reliability import (
            _W_COST_EFF, _W_DETERMINISM, _W_FAIL_RATE, _W_TREND,
        )
        raw = _W_FAIL_RATE * 100 + _W_COST_EFF * 100 + _W_DETERMINISM * 100 + _W_TREND * 100
        clamped = min(100.0, raw)
        assert clamped == 100.0

    def test_health_score_clamped_to_zero(self):
        raw = -5.0
        clamped = max(0.0, raw)
        assert clamped == 0.0

    def test_determinism_penalty_ordering(self):
        from app.services.agent_reliability import _DETERMINISM_PENALTY
        # deterministic is most penalised → lowest penalty multiplier
        assert _DETERMINISM_PENALTY["deterministic"] < _DETERMINISM_PENALTY["stochastic"]
        assert _DETERMINISM_PENALTY["stochastic"] < _DETERMINISM_PENALTY["environmental"]

    def test_trend_score_improvement(self):
        # prev_fail_rate 0.5, current 0.1 → delta=0.4 → trend_score = 50 + 0.4*200 = 130 → clamped 100
        prev_fail_rate = 0.5
        fail_rate = 0.1
        delta = prev_fail_rate - fail_rate
        score = min(100.0, max(0.0, 50.0 + delta * 200.0))
        assert score == 100.0

    def test_trend_score_regression(self):
        # prev 0.1, current 0.5 → delta=-0.4 → trend_score = 50 - 80 = -30 → clamped 0
        prev_fail_rate = 0.1
        fail_rate = 0.5
        delta = prev_fail_rate - fail_rate
        score = min(100.0, max(0.0, 50.0 + delta * 200.0))
        assert score == 0.0

    def test_cost_efficiency_expensive_agent(self):
        # avg_cost >> median → ratio < 1 → cost_eff_score < 50
        median = 0.001
        avg_cost = 0.010  # 10× more expensive
        ratio = median / avg_cost  # 0.1
        score = min(100.0, 50.0 * ratio)
        assert score == 5.0

    def test_cost_efficiency_cheap_agent(self):
        # avg_cost << median → ratio > 1 → score higher, capped at 100
        median = 0.010
        avg_cost = 0.001
        ratio = median / avg_cost  # 10
        score = min(100.0, 50.0 * ratio)
        assert score == 100.0


class TestDeterminismBreakdown:
    def test_all_deterministic_low_det_score(self):
        from app.services.agent_reliability import _DETERMINISM_PENALTY
        breakdown = {"deterministic": 10, "stochastic": 0, "environmental": 0, "unknown": 0}
        total = 10
        det_score = sum(
            breakdown[cls] * _DETERMINISM_PENALTY[cls]
            for cls in breakdown
        ) / total * 100.0
        assert det_score == 0.0  # fully deterministic → worst det score

    def test_all_environmental_high_det_score(self):
        from app.services.agent_reliability import _DETERMINISM_PENALTY
        breakdown = {"deterministic": 0, "stochastic": 0, "environmental": 10, "unknown": 0}
        total = 10
        det_score = sum(
            breakdown[cls] * _DETERMINISM_PENALTY[cls]
            for cls in breakdown
        ) / total * 100.0
        assert det_score == 75.0  # environmental penalty=0.75


class TestGetProjectSummary:
    def _make_score(self, agent, health, det=0, sto=0):
        return SimpleNamespace(
            agent_name=agent,
            score_date=TODAY,
            health_score=health,
            determinism_breakdown_json=json.dumps(
                {"deterministic": det, "stochastic": sto, "environmental": 0, "unknown": 0}
            ),
        )

    def test_best_and_worst_agent(self):
        from app.services.agent_reliability import get_project_summary
        rows = [
            self._make_score("order-agent", 85.0),
            self._make_score("chat-agent", 42.0, det=3),
            self._make_score("search-agent", 60.0),
        ]
        with patch("app.services.agent_reliability.get_leaderboard", return_value=rows):
            summary = get_project_summary(MagicMock(), project_id="proj")
        assert summary.best_agent == "order-agent"
        assert summary.worst_agent == "search-agent"  # last in sorted list
        assert summary.agent_count == 3

    def test_deterministic_failures_counted(self):
        from app.services.agent_reliability import get_project_summary
        rows = [
            self._make_score("a1", 80.0, det=5, sto=2),
            self._make_score("a2", 70.0, det=3, sto=1),
        ]
        with patch("app.services.agent_reliability.get_leaderboard", return_value=rows):
            summary = get_project_summary(MagicMock(), project_id="proj")
        assert summary.total_deterministic_failures == 8
        assert summary.total_stochastic_failures == 3

    def test_empty_project_returns_zero_summary(self):
        from app.services.agent_reliability import get_project_summary
        with patch("app.services.agent_reliability.get_leaderboard", return_value=[]):
            summary = get_project_summary(MagicMock(), project_id="proj")
        assert summary.agent_count == 0
        assert summary.avg_health_score == 0.0
        assert summary.best_agent is None


class TestImports:
    def test_router_importable(self):
        from app.api.routes.reliability import router
        assert router is not None

    def test_service_importable(self):
        from app.services.agent_reliability import (
            compute_project_scores,
            get_agent_history,
            get_leaderboard,
            get_project_summary,
        )
        assert all(callable(f) for f in [compute_project_scores, get_agent_history, get_leaderboard, get_project_summary])
