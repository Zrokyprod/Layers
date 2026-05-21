# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

# ---------------------------------------------------------------------------
# Tests for Loop Guard — Real-Time Agent Loop Detection & Kill
# ---------------------------------------------------------------------------

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure local zroky is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zroky._internal.loop_guard import (
    LoopCheckResult,
    LoopDetectedError,
    LoopGuard,
    _TraceState,
)
from zroky._internal.loop_signals import generate_output_fingerprint


class TestTraceState:
    def test_default_values(self):
        s = _TraceState()
        assert s.call_count == 0
        assert s.cumulative_cost_usd == 0.0
        assert s.last_good_response is None


class TestCheckPreCall:
    def test_allow_when_no_trace_id(self):
        g = LoopGuard(max_calls_per_trace=3)
        result = g.check_pre_call(trace_id=None)
        assert result.action == "allow"

    def test_allow_first_call(self):
        g = LoopGuard(max_calls_per_trace=3)
        result = g.check_pre_call(trace_id="t1")
        assert result.action == "allow"
        assert g._traces["t1"].call_count == 1

    def test_max_calls_blocked(self):
        g = LoopGuard(max_calls_per_trace=2, default_action="raise")
        # first call
        assert g.check_pre_call("t1").action == "allow"
        # second call
        assert g.check_pre_call("t1").action == "allow"
        # third call — exceeds max_calls=2
        result = g.check_pre_call("t1")
        assert result.action == "raise"
        assert result.loop_type == "max_calls"

    def test_max_calls_warn(self):
        g = LoopGuard(max_calls_per_trace=1, default_action="warn")
        g.check_pre_call("t1")
        result = g.check_pre_call("t1")
        assert result.action == "warn"

    def test_max_cost_blocked(self):
        g = LoopGuard(max_cost_per_trace_usd=1.0, default_action="raise")
        # first call with cost 0.6
        assert g.check_pre_call("t1", estimated_cost_usd=0.6).action == "allow"
        assert g._traces["t1"].cumulative_cost_usd == 0.6
        # second call would exceed 1.0
        result = g.check_pre_call("t1", estimated_cost_usd=0.6)
        assert result.action == "raise"
        assert result.loop_type == "max_cost"

    def test_max_cost_return_cached(self):
        g = LoopGuard(max_cost_per_trace_usd=1.0, default_action="return_cached")
        g.check_pre_call("t1", estimated_cost_usd=0.6)
        result = g.check_pre_call("t1", estimated_cost_usd=0.6)
        assert result.action == "return_cached"

    def test_different_traces_isolated(self):
        g = LoopGuard(max_calls_per_trace=2)
        g.check_pre_call("t1")
        g.check_pre_call("t1")
        g.check_pre_call("t2")
        assert g._traces["t1"].call_count == 2
        assert g._traces["t2"].call_count == 1


class TestCheckPostCall:
    def test_allow_when_no_trace_id(self):
        g = LoopGuard(max_repeated_outputs=2)
        result = g.check_post_call(trace_id=None, output_content="hello", provider="o", model="m")
        assert result.action == "allow"

    def test_allow_when_no_output(self):
        g = LoopGuard(max_repeated_outputs=2)
        result = g.check_post_call(trace_id="t1", output_content=None, provider="o", model="m")
        assert result.action == "allow"

    def test_repeated_output_warn(self):
        g = LoopGuard(max_repeated_outputs=2, default_action="warn")
        g.check_pre_call("t1")
        g.check_post_call("t1", "this is a hello world output", "o", "m")
        g.check_pre_call("t1")
        g.check_post_call("t1", "this is a hello world output", "o", "m")
        # third time same output
        result = g.check_post_call("t1", "this is a hello world output", "o", "m")
        assert result.action == "warn"
        assert result.loop_type == "repeated_output"

    def test_repeated_output_raise(self):
        g = LoopGuard(max_repeated_outputs=2, default_action="raise")
        g.check_pre_call("t1")
        g.check_post_call("t1", "this is a duplicate output text", "o", "m")
        g.check_pre_call("t1")
        g.check_post_call("t1", "this is a duplicate output text", "o", "m")
        with pytest.raises(LoopDetectedError):
            g.check_post_call("t1", "this is a duplicate output text", "o", "m")

    def test_different_outputs_no_loop(self):
        g = LoopGuard(max_repeated_outputs=2, default_action="raise")
        for i in range(5):
            g.check_pre_call("t1")
            result = g.check_post_call("t1", f"this is a longer unique output number {i}", "o", "m")
            assert result.action == "allow"

    def test_last_good_response_updated(self):
        g = LoopGuard(max_repeated_outputs=3)
        g.check_pre_call("t1")
        g.check_post_call("t1", "good", "o", "m")
        assert g.get_last_good_response("t1") == "good"

    def test_last_good_response_not_updated_on_loop(self):
        g = LoopGuard(max_repeated_outputs=2, default_action="warn")
        g.check_pre_call("t1")
        g.check_post_call("t1", "good", "o", "m")
        g.check_pre_call("t1")
        g.check_post_call("t1", "good", "o", "m")
        g.check_pre_call("t1")
        g.check_post_call("t1", "good", "o", "m")  # loop
        # last_good_response should still be "good" from first successful call
        assert g.get_last_good_response("t1") == "good"

    def test_cost_adjusted_post_call(self):
        g = LoopGuard(max_cost_per_trace_usd=10.0)
        g.check_pre_call("t1", estimated_cost_usd=1.0)
        assert g._traces["t1"].cumulative_cost_usd == 1.0
        g.check_post_call("t1", "hi", "o", "m", actual_cost_usd=2.0, estimated_cost_usd=1.0)
        assert g._traces["t1"].cumulative_cost_usd == 2.0


class TestCleanup:
    def test_cleanup_old_traces(self):
        g = LoopGuard()
        import time

        # Manually create an old trace
        old_state = _TraceState()
        old_state.created_at = time.time() - 7200  # 2 hours old
        g._traces["old"] = old_state

        new_state = _TraceState()
        new_state.created_at = time.time() - 60  # 1 minute old
        g._traces["new"] = new_state

        removed = g.cleanup_old_traces(max_age_seconds=3600)
        assert removed == 1
        assert "old" not in g._traces
        assert "new" in g._traces

    def test_reset_trace(self):
        g = LoopGuard()
        g.check_pre_call("t1")
        assert "t1" in g._traces
        g.reset_trace("t1")
        assert "t1" not in g._traces


def _reset_sdk():
    """Reset SDK global state between tests."""
    import zroky
    zroky._config = None
    zroky._queue = None
    zroky._async_queue = None
    zroky._response_cache = None
    zroky._budget_tracker = None
    zroky._loop_guard = None
    zroky._recent_preflight_calls.clear()


class TestIntegrationWithZrokyCall:
    """Minimal integration tests via the SDK call() path."""

    def test_pre_call_max_calls_raises(self, tmp_path):
        import zroky
        from unittest.mock import MagicMock, patch

        _reset_sdk()

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(
                loop_guard_enabled=True,
                loop_guard_max_calls_per_trace=1,
                loop_guard_action="raise",
            )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="hello", role="assistant"))
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=5, completion_tokens=3, total_tokens=8
        )
        mock_client.chat.completions.create.return_value = mock_response

        # First call should succeed
        result = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            trace_id="trace-1",
            _client=mock_client,
        )
        assert result is not None

        # Second call should raise LoopDetectedError
        with pytest.raises(zroky.LoopDetectedError):
            zroky.call(
                provider="openai",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi again"}],
                trace_id="trace-1",
                _client=mock_client,
            )

    def test_post_call_repeated_output_warn(self, tmp_path):
        import zroky
        from unittest.mock import MagicMock, patch

        _reset_sdk()

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(
                loop_guard_enabled=True,
                loop_guard_max_repeated_outputs=2,
                loop_guard_action="warn",
            )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="same", role="assistant"))
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=5, completion_tokens=1, total_tokens=6
        )
        mock_client.chat.completions.create.return_value = mock_response

        # Two calls with same output should be fine
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            trace_id="trace-2",
            _client=mock_client,
        )
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            trace_id="trace-2",
            _client=mock_client,
        )
        # Third call with same output should trigger warning but continue
        result = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            trace_id="trace-2",
            _client=mock_client,
        )
        assert result is not None
