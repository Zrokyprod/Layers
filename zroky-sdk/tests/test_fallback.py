# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for the automatic model fallback engine."""
import time

import pytest

from zroky._internal.fallback import (
    FallbackChain,
    FallbackExecutor,
    FallbackOutcome,
    ModelHealthRegistry,
    build_chain,
    resolve_provider_from_model,
)


# ---------------------------------------------------------------------------
# resolve_provider_from_model
# ---------------------------------------------------------------------------


class TestResolveProvider:
    def test_openai_gpt(self):
        assert resolve_provider_from_model("gpt-4o") == "openai"
        assert resolve_provider_from_model("gpt-4o-mini") == "openai"

    def test_openai_o_series(self):
        assert resolve_provider_from_model("o1-preview") == "openai"
        assert resolve_provider_from_model("o3-mini") == "openai"

    def test_anthropic_claude(self):
        assert resolve_provider_from_model("claude-3-5-sonnet-20241022") == "anthropic"
        assert resolve_provider_from_model("claude-3-haiku") == "anthropic"

    def test_openai_compatible(self):
        assert resolve_provider_from_model("llama-3.1-70b") == "openai"
        assert resolve_provider_from_model("mistral-large") == "openai"
        assert resolve_provider_from_model("gemini-pro") == "openai"
        assert resolve_provider_from_model("deepseek-chat") == "openai"

    def test_unknown_returns_none(self):
        assert resolve_provider_from_model("totally-unknown-model") is None

    def test_case_insensitive(self):
        assert resolve_provider_from_model("GPT-4o") == "openai"
        assert resolve_provider_from_model("Claude-3-Haiku") == "anthropic"


# ---------------------------------------------------------------------------
# ModelHealthRegistry
# ---------------------------------------------------------------------------


class TestModelHealthRegistry:
    def test_empty_score_is_1(self):
        r = ModelHealthRegistry()
        assert r.score("gpt-4o") == 1.0

    def test_empty_latency_is_none(self):
        r = ModelHealthRegistry()
        assert r.ema_latency("gpt-4o") is None

    def test_all_success(self):
        r = ModelHealthRegistry()
        for _ in range(5):
            r.record("gpt-4o", 100.0, success=True)
        assert r.score("gpt-4o") == 1.0

    def test_all_failure(self):
        r = ModelHealthRegistry()
        for _ in range(5):
            r.record("gpt-4o", 100.0, success=False)
        assert r.score("gpt-4o") == 0.0

    def test_mixed(self):
        r = ModelHealthRegistry()
        r.record("gpt-4o", 100.0, success=True)
        r.record("gpt-4o", 100.0, success=False)
        assert r.score("gpt-4o") == 0.5

    def test_ema_latency_single(self):
        r = ModelHealthRegistry()
        r.record("gpt-4o", 200.0, success=True)
        assert r.ema_latency("gpt-4o") == 200.0

    def test_ema_latency_multiple(self):
        r = ModelHealthRegistry()
        r.record("gpt-4o", 100.0, success=True)
        r.record("gpt-4o", 200.0, success=True)
        # EMA: 0.3 * 200 + 0.7 * 100 = 130
        assert abs(r.ema_latency("gpt-4o") - 130.0) < 0.01

    def test_window_expiry(self):
        r = ModelHealthRegistry(window=0.01)
        r.record("gpt-4o", 100.0, success=False)
        time.sleep(0.02)  # wait for entry to expire
        r.record("gpt-4o", 100.0, success=True)
        assert r.score("gpt-4o") == 1.0

    def test_maxlen(self):
        r = ModelHealthRegistry(maxlen=3)
        for _ in range(3):
            r.record("gpt-4o", 100.0, success=False)
        r.record("gpt-4o", 100.0, success=True)
        # deque(maxlen=3): [fail, fail, success] — 1/3
        assert abs(r.score("gpt-4o") - 1 / 3) < 0.01

    def test_circuit_open_after_consecutive_failures(self):
        r = ModelHealthRegistry()
        r.record("gpt-4o", 100.0, success=False)
        r.record("gpt-4o", 100.0, success=False)

        assert r.consecutive_failures("gpt-4o") == 2
        assert r.circuit_open(
            "gpt-4o",
            failure_threshold=2,
            reset_timeout_seconds=60.0,
        ) is True


# ---------------------------------------------------------------------------
# FallbackChain
# ---------------------------------------------------------------------------


class TestFallbackChain:
    def test_models_list(self):
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet", "gpt-4o-mini"),
        )
        assert chain.models() == ["gpt-4o", "claude-3-5-sonnet", "gpt-4o-mini"]

    def test_models_respects_max_fallbacks(self):
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("a", "b", "c", "d"),
            max_fallbacks=2,
        )
        assert chain.models() == ["gpt-4o", "a", "b"]

    def test_ordered_no_adaptive(self):
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
            adaptive=False,
        )
        assert chain.ordered() == ["gpt-4o", "claude-3-5-sonnet"]

    def test_ordered_adaptive_reorders_by_health(self):
        registry = ModelHealthRegistry()
        # Make claude healthy and gpt-4o-mini unhealthy
        for _ in range(5):
            registry.record("claude-3-5-sonnet", 50.0, success=True)
            registry.record("gpt-4o-mini", 200.0, success=False)

        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("gpt-4o-mini", "claude-3-5-sonnet"),
            adaptive=True,
        )
        ordered = chain.ordered(registry)
        # Primary stays first
        assert ordered[0] == "gpt-4o"
        # claude should be preferred over gpt-4o-mini
        assert ordered[1] == "claude-3-5-sonnet"
        assert ordered[2] == "gpt-4o-mini"

    def test_ordered_adaptive_too_few_models(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
            adaptive=True,
        )
        # With <= 2 models, no reordering
        assert chain.ordered(registry) == ["gpt-4o", "claude-3-5-sonnet"]


# ---------------------------------------------------------------------------
# FallbackOutcome
# ---------------------------------------------------------------------------


class TestFallbackOutcome:
    def test_merge_into_event(self):
        class FakeEvent:
            resolved_model = None
            fallback_chain = None
            fallback_attempts = 0

        outcome = FallbackOutcome(
            resolved_model="claude-3-5-sonnet",
            chain=["gpt-4o", "claude-3-5-sonnet"],
            fallback_attempts=1,
        )
        evt = FakeEvent()
        outcome.merge_into_event(evt)
        assert evt.resolved_model == "claude-3-5-sonnet"
        assert evt.fallback_chain == ["gpt-4o", "claude-3-5-sonnet"]
        assert evt.fallback_attempts == 1

    def test_merge_no_fallback(self):
        class FakeEvent:
            resolved_model = None
            fallback_chain = None
            fallback_attempts = 0

        outcome = FallbackOutcome()
        evt = FakeEvent()
        outcome.merge_into_event(evt)
        assert evt.resolved_model is None
        assert evt.fallback_chain is None
        assert evt.fallback_attempts == 0


# ---------------------------------------------------------------------------
# build_chain
# ---------------------------------------------------------------------------


class TestBuildChain:
    def test_none_when_no_fallback(self):
        assert build_chain(
            primary_provider="openai",
            primary_model="gpt-4o",
            fallback=None,
        ) is None

    def test_none_when_empty_fallback(self):
        assert build_chain(
            primary_provider="openai",
            primary_model="gpt-4o",
            fallback=[],
        ) is None

    def test_builds_chain(self):
        chain = build_chain(
            primary_provider="openai",
            primary_model="gpt-4o",
            fallback=["claude-3-5-sonnet", "gpt-4o-mini"],
        )
        assert chain is not None
        assert chain.primary_model == "gpt-4o"
        assert chain.primary_provider == "openai"
        assert chain.backups == ("claude-3-5-sonnet", "gpt-4o-mini")

    def test_respects_adaptive(self):
        chain = build_chain(
            primary_provider="openai",
            primary_model="gpt-4o",
            fallback=["claude-3-5-sonnet"],
            adaptive=True,
        )
        assert chain is not None
        assert chain.adaptive is True

    def test_respects_max_fallbacks(self):
        chain = build_chain(
            primary_provider="openai",
            primary_model="gpt-4o",
            fallback=["a", "b", "c", "d"],
            max_fallbacks=2,
        )
        assert chain is not None
        assert len(chain.models()) == 3  # primary + 2

    def test_tuple_input(self):
        chain = build_chain(
            primary_provider="openai",
            primary_model="gpt-4o",
            fallback=("claude-3-5-sonnet",),
        )
        assert chain is not None
        assert chain.backups == ("claude-3-5-sonnet",)


# ---------------------------------------------------------------------------
# FallbackExecutor (sync)
# ---------------------------------------------------------------------------


class TestFallbackExecutorSync:
    def test_no_chain_calls_primary(self):
        registry = ModelHealthRegistry()
        executor = FallbackExecutor(chain=None, registry=registry)
        result, outcome = executor.execute_sync(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=lambda m, p, i: {"model": m, "provider": p},
        )
        assert result == {"model": "gpt-4o", "provider": "openai"}
        assert outcome.resolved_model == "gpt-4o"
        assert outcome.fallback_attempts == 0

    def test_success_on_primary(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)
        result, outcome = executor.execute_sync(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=lambda m, p, i: {"model": m},
        )
        assert result == {"model": "gpt-4o"}
        assert outcome.fallback_attempts == 0
        assert outcome.resolved_model == "gpt-4o"

    def test_fallback_to_backup(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet", "gpt-4o-mini"),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)
        calls = []

        def _call(m, p, i):
            calls.append((m, p, i))
            if m == "gpt-4o":
                raise RuntimeError("primary failed")
            return {"model": m}

        result, outcome = executor.execute_sync(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=_call,
        )
        assert result == {"model": "claude-3-5-sonnet"}
        assert outcome.fallback_attempts == 1
        assert outcome.resolved_model == "claude-3-5-sonnet"
        assert outcome.last_error is not None
        assert len(calls) == 2

    def test_exhausted_raises_last_error(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)

        def _call(m, p, i):
            raise RuntimeError(f"fail {m}")

        with pytest.raises(RuntimeError, match="fail claude-3-5-sonnet"):
            executor.execute_sync(
                primary_model="gpt-4o",
                primary_provider="openai",
                call_fn=_call,
            )

    def test_unresolvable_provider_skipped(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("unknown-model-xyz",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)

        def _call(m, p, i):
            if m == "gpt-4o":
                raise RuntimeError("primary failed")
            if p is None:
                raise RuntimeError("no provider")
            return {"model": m}

        with pytest.raises(RuntimeError, match="primary failed"):
            executor.execute_sync(
                primary_model="gpt-4o",
                primary_provider="openai",
                call_fn=_call,
            )

    def test_non_fallbackable_error_stops_chain(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)
        calls = []

        def _call(m, p, i):
            calls.append(m)
            exc = RuntimeError("bad credentials")
            setattr(exc, "__zroky_error_code", "AUTH_FAILURE")
            raise exc

        with pytest.raises(RuntimeError, match="bad credentials"):
            executor.execute_sync(
                primary_model="gpt-4o",
                primary_provider="openai",
                call_fn=_call,
            )

        assert calls == ["gpt-4o"]

    def test_circuit_open_primary_skips_to_backup(self):
        registry = ModelHealthRegistry()
        registry.record("gpt-4o", 100.0, success=False)
        registry.record("gpt-4o", 100.0, success=False)
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("gpt-4o-mini",),
        )
        executor = FallbackExecutor(
            chain=chain,
            registry=registry,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_reset_timeout_seconds=60.0,
        )
        calls = []

        def _call(m, p, i):
            calls.append(m)
            return {"model": m}

        result, outcome = executor.execute_sync(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=_call,
        )

        assert result == {"model": "gpt-4o-mini"}
        assert calls == ["gpt-4o-mini"]
        assert outcome.fallback_attempts == 1
        assert outcome.circuit_open_models == ["gpt-4o"]


# ---------------------------------------------------------------------------
# FallbackExecutor (async)
# ---------------------------------------------------------------------------


class TestFallbackExecutorAsync:
    @pytest.mark.asyncio
    async def test_no_chain_calls_primary(self):
        registry = ModelHealthRegistry()
        executor = FallbackExecutor(chain=None, registry=registry)
        async def _call(m, p, i):
            return {"model": m, "provider": p}

        result, outcome = await executor.execute_async(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=_call,
        )
        assert result == {"model": "gpt-4o", "provider": "openai"}
        assert outcome.resolved_model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_success_on_primary(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)

        async def _call(m, p, i):
            return {"model": m}

        result, outcome = await executor.execute_async(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=_call,
        )
        assert result == {"model": "gpt-4o"}
        assert outcome.fallback_attempts == 0

    @pytest.mark.asyncio
    async def test_fallback_to_backup(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)

        async def _call(m, p, i):
            if m == "gpt-4o":
                raise RuntimeError("primary failed")
            return {"model": m}

        result, outcome = await executor.execute_async(
            primary_model="gpt-4o",
            primary_provider="openai",
            call_fn=_call,
        )
        assert result == {"model": "claude-3-5-sonnet"}
        assert outcome.fallback_attempts == 1

    @pytest.mark.asyncio
    async def test_exhausted_raises_last_error(self):
        registry = ModelHealthRegistry()
        chain = FallbackChain(
            primary_model="gpt-4o",
            primary_provider="openai",
            backups=("claude-3-5-sonnet",),
        )
        executor = FallbackExecutor(chain=chain, registry=registry)

        async def _call(m, p, i):
            raise RuntimeError(f"fail {m}")

        with pytest.raises(RuntimeError, match="fail claude-3-5-sonnet"):
            await executor.execute_async(
                primary_model="gpt-4o",
                primary_provider="openai",
                call_fn=_call,
            )
