# ---------------------------------------------------------------------------
# Integration tests for zroky.call() / zroky.acall()
#
# These tests exercise the full call path (fallback, retry, timeout,
# telemetry, health-recording) with mock provider clients — no real
# API keys or network calls required.
# ---------------------------------------------------------------------------
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import zroky


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_sdk():
    """Reset SDK global state between tests."""
    zroky._config = None
    zroky._queue = None
    zroky._response_cache = None
    zroky._budget_tracker = None
    zroky._loop_guard = None
    zroky._timeout_manager = None
    zroky._model_health_registry = zroky.ModelHealthRegistry()
    zroky._recent_preflight_calls.clear()
    zroky._payload_guard_logged_call_ids.clear()
    zroky._payload_guard_log_order.clear()


def _init_local(monkeypatch, **overrides):
    """Init the SDK in local mode with no real backend."""
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_API_KEY", "test-key")
    for k, v in overrides.items():
        monkeypatch.setenv(k, str(v))
    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()


def _fake_response(*, prompt_tokens=10, completion_tokens=5, content="hello"):
    """Build a minimal fake provider response object."""
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        input_tokens=None,
        output_tokens=None,
        completion_tokens_details=None,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=None),
        finish_reason="stop",
    )
    return SimpleNamespace(usage=usage, choices=[choice], model="gpt-4o")


def _fake_client(side_effect=None, return_value=None):
    """Build a mock client whose .chat.completions.create is controllable."""
    client = MagicMock()
    create = client.chat.completions.create
    if side_effect is not None:
        create.side_effect = side_effect
    elif return_value is not None:
        create.return_value = return_value
    else:
        create.return_value = _fake_response()
    return client


# ---------------------------------------------------------------------------
# Sync call() integration tests
# ---------------------------------------------------------------------------


class TestCallIntegration:
    """Smoke tests for the full synchronous call() path."""

    def test_basic_call_returns_response(self, monkeypatch):
        _reset_sdk()
        _init_local(monkeypatch)
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        resp = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            _client=_fake_client(),
        )

        assert resp is not None
        assert len(captured) == 1
        event = captured[0]
        assert event.status == "success"
        assert event.provider == "openai"
        assert event.model == "gpt-4o"
        assert event.prompt_tokens == 10
        assert event.completion_tokens == 5
        assert event.latency_ms > 0
        zroky.shutdown()
        _reset_sdk()

    def test_call_error_sets_failed_status(self, monkeypatch):
        _reset_sdk()
        _init_local(monkeypatch)
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        client = _fake_client(side_effect=RuntimeError("provider exploded"))

        with pytest.raises(RuntimeError, match="provider exploded"):
            zroky.call(
                provider="openai",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                _client=client,
            )

        assert len(captured) == 1
        event = captured[0]
        assert event.status == "failed"
        assert event.latency_ms > 0
        zroky.shutdown()
        _reset_sdk()

    def test_fallback_to_backup_model(self, monkeypatch):
        _reset_sdk()
        _init_local(monkeypatch)
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        call_log: list[str] = []

        def _create(**kwargs):
            model = kwargs.get("model", "")
            call_log.append(model)
            if model == "gpt-4o":
                raise RuntimeError("primary down")
            return _fake_response(content="from backup")

        client = _fake_client(side_effect=_create)

        resp = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            fallback=["claude-3-5-sonnet"],
            _client=client,
        )

        assert resp is not None
        assert "gpt-4o" in call_log
        assert len(captured) == 1
        event = captured[0]
        assert event.status == "success"
        assert event.resolved_model == "claude-3-5-sonnet"
        assert event.fallback_attempts == 1
        zroky.shutdown()
        _reset_sdk()

    def test_global_fallback_policy_applies_without_per_call_fallback(self, monkeypatch):
        _reset_sdk()
        monkeypatch.setenv("ZROKY_MODE", "local")
        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(fallback_models=["gpt-4o-mini"])
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        call_log: list[str] = []

        def _create(**kwargs):
            model = kwargs.get("model", "")
            call_log.append(model)
            if model == "gpt-4o":
                raise RuntimeError("primary down")
            return _fake_response(content="from global fallback")

        client = _fake_client(side_effect=_create)

        resp = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            _client=client,
        )

        assert resp is not None
        assert call_log == ["gpt-4o", "gpt-4o-mini"]
        assert captured[0].resolved_model == "gpt-4o-mini"
        assert captured[0].fallback_chain == ["gpt-4o", "gpt-4o-mini"]
        zroky.shutdown()
        _reset_sdk()

    def test_fallback_exhausted_raises(self, monkeypatch):
        _reset_sdk()
        _init_local(monkeypatch)
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        client = _fake_client(side_effect=RuntimeError("all models down"))

        with pytest.raises(RuntimeError, match="all models down"):
            zroky.call(
                provider="openai",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                fallback=["claude-3-5-sonnet"],
                _client=client,
            )

        assert len(captured) == 1
        assert captured[0].status == "failed"
        zroky.shutdown()
        _reset_sdk()

    def test_adaptive_timeout_records_latency(self, monkeypatch):
        _reset_sdk()
        _init_local(monkeypatch)
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            _client=_fake_client(),
        )

        # Check the timeout manager got a latency observation
        if zroky._timeout_manager is not None:
            count = zroky._timeout_manager.latency_tracker.count("gpt-4o")
            assert count >= 1, "Expected at least 1 latency observation recorded"

        zroky.shutdown()
        _reset_sdk()

    def test_health_registry_records_success(self, monkeypatch):
        _reset_sdk()
        _init_local(monkeypatch)
        captured = []
        zroky._queue.enqueue = lambda e: captured.append(e)

        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            _client=_fake_client(),
        )

        score = zroky._model_health_registry.score("gpt-4o")
        assert score == 1.0, "Expected health score 1.0 after successful call"
        zroky.shutdown()
        _reset_sdk()


# ---------------------------------------------------------------------------
# Async acall() integration tests
# ---------------------------------------------------------------------------


class TestAcallIntegration:
    """Smoke tests for the full asynchronous acall() path."""

    @staticmethod
    async def _ainit_local(monkeypatch):
        """Set up SDK for async tests with a mock async queue."""
        _reset_sdk()
        _init_local(monkeypatch)
        # Create a mock async queue so acall() doesn't call ainit()
        mock_async_queue = MagicMock()
        mock_async_queue.enqueue = MagicMock()
        mock_async_queue.flush = AsyncMock()
        mock_async_queue.shutdown = AsyncMock()
        zroky._async_queue = mock_async_queue

    @pytest.mark.asyncio
    async def test_basic_acall_returns_response(self, monkeypatch):
        await self._ainit_local(monkeypatch)
        captured = []
        zroky._async_queue.enqueue = lambda e: captured.append(e)

        client = MagicMock()
        client.chat.completions.create = MagicMock(return_value=_fake_response())

        resp = await zroky.acall(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            _client=client,
        )

        assert resp is not None
        assert len(captured) == 1
        event = captured[0]
        assert event.status == "success"
        assert event.provider == "openai"
        zroky.shutdown()
        _reset_sdk()

    @pytest.mark.asyncio
    async def test_acall_error_sets_failed(self, monkeypatch):
        await self._ainit_local(monkeypatch)
        captured = []
        zroky._async_queue.enqueue = lambda e: captured.append(e)

        client = MagicMock()
        client.chat.completions.create = MagicMock(
            side_effect=RuntimeError("async provider fail"),
        )

        with pytest.raises(RuntimeError, match="async provider fail"):
            await zroky.acall(
                provider="openai",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                _client=client,
            )

        assert len(captured) == 1
        assert captured[0].status == "failed"
        zroky.shutdown()
        _reset_sdk()
