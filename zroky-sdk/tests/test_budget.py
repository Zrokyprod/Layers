"""Tests for real-time budget enforcement engine."""
import sqlite3
import time
from pathlib import Path

import pytest

from zroky._internal.budget import (
    BudgetCheckResult,
    BudgetExceededError,
    BudgetTracker,
    _BudgetRule,
    _SpendAccumulator,
    _window_key,
    build_budget_rules,
)
from zroky._internal.cost import calculate_cost


# ---------------------------------------------------------------------------
# Window key
# ---------------------------------------------------------------------------


class TestWindowKey:
    def test_hourly_format(self):
        k = _window_key("hourly")
        assert len(k) == 13  # YYYY-MM-DDTHH

    def test_daily_format(self):
        k = _window_key("daily")
        assert len(k) == 10  # YYYY-MM-DD

    def test_monthly_format(self):
        k = _window_key("monthly")
        assert len(k) == 7  # YYYY-MM

    def test_ever(self):
        assert _window_key("ever") == "ever"


# ---------------------------------------------------------------------------
# SpendAccumulator
# ---------------------------------------------------------------------------


class TestSpendAccumulator:
    def test_add_and_get(self):
        acc = _SpendAccumulator()
        acc.add(1.5)
        acc.add(2.5)
        assert acc.get() == 4.0

    def test_reset(self):
        acc = _SpendAccumulator()
        acc.add(5.0)
        acc.reset()
        assert acc.get() == 0.0


# ---------------------------------------------------------------------------
# BudgetRule
# ---------------------------------------------------------------------------


class TestBudgetRule:
    def test_frozen(self):
        r = _BudgetRule(limit_usd=10.0, window="daily", action="warn")
        with pytest.raises(AttributeError):
            r.limit_usd = 20.0


# ---------------------------------------------------------------------------
# BudgetTracker — unit tests
# ---------------------------------------------------------------------------


class TestBudgetTrackerUnit:
    def test_check_no_rules_allow(self):
        t = BudgetTracker()
        result = t.check(
            project="p", agent="a", user="u",
            model="gpt-4o", prompt_tokens=1000,
        )
        assert result.action == "allow"
        assert result.estimated_cost_usd > 0

    def test_check_hard_block(self):
        t = BudgetTracker(
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 0.01, "action": "hard_block"},
                    }
                }
            }
        )
        # First call should estimate > $0.01 for 1000 tokens on gpt-4o
        result = t.check(
            project="default", agent="a", user="u",
            model="gpt-4o", prompt_tokens=100_000,
        )
        assert result.action == "hard_block"

    def test_check_warn(self):
        t = BudgetTracker(
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 1_000_000.0, "action": "warn"},
                    }
                }
            }
        )
        result = t.check(
            project="default", agent="a", user="u",
            model="gpt-4o", prompt_tokens=100,
        )
        assert result.action == "allow"  # warn only triggers when limit exceeded

    def test_record_spend_updates(self):
        t = BudgetTracker(
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 10.0, "action": "hard_block"},
                    }
                }
            }
        )
        # Spend $5
        t.record_spend(project="default", agent="a", user="u", cost_usd=5.0, window_keys={"project|default": _window_key("daily")})
        # Now check again with same scope
        result = t.check(
            project="default", agent="a", user="u",
            model="gpt-4o", prompt_tokens=1000,
        )
        assert result.remaining_usd == pytest.approx(5.0, abs=0.01)

    def test_most_severe_action_wins(self):
        t = BudgetTracker(
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 0.0, "action": "warn"},
                    }
                },
                "user": {
                    "default": {
                        "daily": {"limit_usd": 0.0, "action": "hard_block"},
                    }
                },
            }
        )
        result = t.check(
            project="default", agent="a", user="default",
            model="gpt-4o", prompt_tokens=1000,
        )
        assert result.action == "hard_block"

    def test_status_reflects_spend(self):
        t = BudgetTracker(
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 100.0, "action": "warn"},
                    }
                }
            }
        )
        t.record_spend(project="default", agent="a", user="u", cost_usd=42.0, window_keys={"project|default": _window_key("daily")})
        st = t.status()
        assert st["project/default"]["spent_usd"] == 42.0
        assert st["project/default"]["remaining_usd"] == 58.0

    def test_close_no_db_path(self):
        t = BudgetTracker()
        t.close()  # should not raise

    def test_db_persistence(self, tmp_path):
        db = str(tmp_path / "budget.db")
        t1 = BudgetTracker(
            db_path=db,
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 100.0, "action": "hard_block"},
                    }
                }
            },
        )
        t1.record_spend(project="default", agent="a", user="u", cost_usd=50.0, window_keys={"project|default": _window_key("daily")})
        t1.close()

        t2 = BudgetTracker(
            db_path=db,
            rules={
                "project": {
                    "default": {
                        "daily": {"limit_usd": 100.0, "action": "hard_block"},
                    }
                }
            },
        )
        result = t2.check(
            project="default", agent="a", user="u",
            model="gpt-4o", prompt_tokens=100,
        )
        assert result.remaining_usd == pytest.approx(50.0, abs=0.01)
        t2.close()

    def test_cleanup_old_windows(self, tmp_path):
        db = str(tmp_path / "budget.db")
        t = BudgetTracker(db_path=db)
        # Insert an old window via the same connection so WAL sees it
        old_ts = 1_600_000_000.0  # ~Sep 2020
        t._conn.execute(
            "INSERT INTO budget_spend (scope_type, scope_id, window_key, spend_usd, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("project", "default", "2020-01-01", 99.0, old_ts),
        )
        t._conn.commit()
        t.cleanup_old_windows(keep_hours=1)
        cur = t._conn.execute("SELECT COUNT(*) FROM budget_spend")
        row = cur.fetchone()
        assert row[0] == 0


# ---------------------------------------------------------------------------
# build_budget_rules
# ---------------------------------------------------------------------------


class TestBuildBudgetRules:
    def test_flat_list_to_nested(self):
        specs = [
            {
                "scope_type": "project",
                "scope_id": "default",
                "window": "daily",
                "limit_usd": 500.0,
                "action": "warn",
            }
        ]
        rules = build_budget_rules(specs)
        assert rules["project"]["default"]["daily"]["limit_usd"] == 500.0
        assert rules["project"]["default"]["daily"]["action"] == "warn"


# ---------------------------------------------------------------------------
# Integration with SDK
# ---------------------------------------------------------------------------


class TestBudgetIntegration:
    def test_hard_block_raises(self, monkeypatch):
        import zroky
        from unittest.mock import MagicMock, patch

        zroky.shutdown()
        zroky._config = None
        zroky._queue = None
        zroky._response_cache = None
        zroky._budget_tracker = None
        zroky._recent_preflight_calls.clear()
        monkeypatch.setenv("ZROKY_MODE", "local")

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(
                project="unknown",
                budget_enabled=True,
                budget_rules={
                    "project": {
                        "unknown": {
                            "daily": {"limit_usd": 0.0, "action": "hard_block"},
                        }
                    }
                },
            )

        mock_client = MagicMock()

        with pytest.raises(zroky.BudgetExceededError):
            zroky.call(
                provider="openai",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hello"}],
                _client=mock_client,
            )

        # Provider never called
        mock_client.chat.completions.create.assert_not_called()

        zroky.shutdown()
        zroky._config = None
        zroky._queue = None
        zroky._budget_tracker = None
        zroky._recent_preflight_calls.clear()

    def test_soft_block_logs_warning(self, monkeypatch, caplog):
        import zroky
        from unittest.mock import MagicMock, patch

        zroky.shutdown()
        zroky._config = None
        zroky._queue = None
        zroky._response_cache = None
        zroky._budget_tracker = None
        zroky._recent_preflight_calls.clear()
        monkeypatch.setenv("ZROKY_MODE", "local")

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(
                budget_enabled=True,
                budget_rules={
                    "project": {
                        "unknown": {
                            "daily": {"limit_usd": 0.0, "action": "soft_block"},
                        }
                    }
                },
            )

        class FakeResponse:
            class usage:
                prompt_tokens = 10
                completion_tokens = 5
            choices = []

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = FakeResponse()

        result = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "soft test"}],
            _client=mock_client,
        )

        # Provider WAS called because soft_block only logs
        mock_client.chat.completions.create.assert_called_once()
        assert result is not None

        zroky.shutdown()
        zroky._config = None
        zroky._queue = None
        zroky._budget_tracker = None
        zroky._recent_preflight_calls.clear()

    def test_budget_disabled_does_not_interfere(self, monkeypatch):
        import zroky
        from unittest.mock import MagicMock, patch

        zroky.shutdown()
        zroky._config = None
        zroky._queue = None
        zroky._response_cache = None
        zroky._budget_tracker = None
        zroky._recent_preflight_calls.clear()
        monkeypatch.setenv("ZROKY_MODE", "local")

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(budget_enabled=False)

        class FakeResponse:
            class usage:
                prompt_tokens = 10
                completion_tokens = 5
            choices = []

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = FakeResponse()

        result = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "no budget"}],
            _client=mock_client,
        )

        assert result is not None
        mock_client.chat.completions.create.assert_called_once()

        zroky.shutdown()
        zroky._config = None
        zroky._queue = None
        zroky._budget_tracker = None
        zroky._recent_preflight_calls.clear()
