# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Automatic model fallback engine.

When a provider call fails (even after retries), transparently cascade
to backup models.  Captures which model actually served the response
in ``CallEvent.resolved_model``.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Model → provider auto-resolution
# ---------------------------------------------------------------------------

_PROVIDER_BY_PREFIX: dict[str, str] = {
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "claude": "anthropic",
}

_OPENAI_COMPATIBLE = frozenset({"llama", "mistral", "gemini", "deepseek"})
_NON_FALLBACKABLE_ERROR_CODES = frozenset({"AUTH_FAILURE", "TOKEN_OVERFLOW"})


def resolve_provider_from_model(model: str) -> str | None:
    """Guess provider name from model string."""
    lower = model.lower()
    for prefix, provider in _PROVIDER_BY_PREFIX.items():
        if lower.startswith(prefix):
            return provider
    for prefix in _OPENAI_COMPATIBLE:
        if lower.startswith(prefix):
            return "openai"
    return None


# ---------------------------------------------------------------------------
# Health registry
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    ts: float
    latency_ms: float
    ok: bool


class ModelHealthRegistry:
    """Sliding-window health tracker per model."""

    def __init__(self, window: float = 300.0, maxlen: int = 100) -> None:
        self._window = window
        self._maxlen = maxlen
        self._data: dict[str, deque[_Entry]] = {}

    def record(self, model: str, latency_ms: float, success: bool) -> None:
        now = time.monotonic()
        dq = self._data.setdefault(model, deque(maxlen=self._maxlen))
        dq.append(_Entry(now, latency_ms, success))
        cutoff = now - self._window
        while dq and dq[0].ts < cutoff:
            dq.popleft()

    def score(self, model: str) -> float:
        dq = self._data.get(model, deque())
        if not dq:
            return 1.0
        ok = sum(1 for e in dq if e.ok)
        return ok / len(dq)

    def ema_latency(self, model: str) -> float | None:
        dq = self._data.get(model, deque())
        if not dq:
            return None
        ema = dq[0].latency_ms
        for e in list(dq)[1:]:
            ema = 0.3 * e.latency_ms + 0.7 * ema
        return ema

    def consecutive_failures(self, model: str) -> int:
        dq = self._data.get(model, deque())
        count = 0
        for entry in reversed(dq):
            if entry.ok:
                break
            count += 1
        return count

    def circuit_open(
        self,
        model: str,
        *,
        failure_threshold: int,
        reset_timeout_seconds: float,
    ) -> bool:
        if failure_threshold <= 0:
            return False

        dq = self._data.get(model, deque())
        if not dq or dq[-1].ok:
            return False
        if self.consecutive_failures(model) < failure_threshold:
            return False

        age_seconds = time.monotonic() - dq[-1].ts
        return age_seconds < max(0.0, reset_timeout_seconds)


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FallbackChain:
    primary_model: str
    primary_provider: str
    backups: tuple[str, ...] = ()
    adaptive: bool = False
    max_fallbacks: int = 3

    def models(self) -> list[str]:
        return [self.primary_model] + list(self.backups[:self.max_fallbacks])

    def ordered(self, registry: ModelHealthRegistry | None = None) -> list[str]:
        models = self.models()
        if not self.adaptive or registry is None or len(models) <= 2:
            return models
        # keep primary first; reorder backups by health score desc, latency asc
        primary, *rest = models
        def _key(m: str) -> tuple[float, float]:
            return (-registry.score(m), registry.ema_latency(m) or float("inf"))
        return [primary] + sorted(rest, key=_key)


@dataclass
class FallbackOutcome:
    resolved_model: str | None = None
    resolved_provider: str | None = None
    fallback_attempts: int = 0
    chain: list[str] | None = None
    last_error: Exception | None = None
    last_error_code: str | None = None
    circuit_open_models: list[str] | None = None

    def merge_into_event(self, event: Any) -> None:
        if self.resolved_model:
            event.resolved_model = self.resolved_model
        if self.chain:
            event.fallback_chain = self.chain
        event.fallback_attempts = self.fallback_attempts
        if self.circuit_open_models is not None:
            event.circuit_open_models = self.circuit_open_models


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_chain(
    *,
    primary_provider: str,
    primary_model: str,
    fallback: list[str] | tuple[str, ...] | None = None,
    adaptive: bool = False,
    max_fallbacks: int = 3,
) -> FallbackChain | None:
    if not fallback:
        return None
    return FallbackChain(
        primary_model=primary_model,
        primary_provider=primary_provider,
        backups=tuple(fallback),
        adaptive=adaptive,
        max_fallbacks=max_fallbacks,
    )


# ---------------------------------------------------------------------------
# Fallback executor
# ---------------------------------------------------------------------------

class FallbackExecutor:
    """Orchestrates fallback model execution and tracks outcomes."""

    def __init__(
        self,
        chain: FallbackChain | None,
        registry: ModelHealthRegistry,
        *,
        verbose: bool = False,
        circuit_breaker_failure_threshold: int = 5,
        circuit_breaker_reset_timeout_seconds: float = 60.0,
    ) -> None:
        self._chain = chain
        self._registry = registry
        self._verbose = verbose
        self._circuit_breaker_failure_threshold = circuit_breaker_failure_threshold
        self._circuit_breaker_reset_timeout_seconds = circuit_breaker_reset_timeout_seconds

    def _models(self) -> list[str]:
        if self._chain is None:
            return []
        return self._chain.ordered(self._registry)

    def _candidate_models(self) -> tuple[list[tuple[int, str]], list[str]]:
        models = self._models()
        if len(models) <= 1:
            return list(enumerate(models)), []

        candidates: list[tuple[int, str]] = []
        circuit_open_models: list[str] = []
        for idx, model in enumerate(models):
            if self._registry.circuit_open(
                model,
                failure_threshold=self._circuit_breaker_failure_threshold,
                reset_timeout_seconds=self._circuit_breaker_reset_timeout_seconds,
            ):
                circuit_open_models.append(model)
                continue
            candidates.append((idx, model))

        if candidates:
            return candidates, circuit_open_models
        return list(enumerate(models)), []

    @staticmethod
    def _error_code(exc: Exception) -> str | None:
        value = getattr(exc, "__zroky_error_code", None)
        return str(value) if value else None

    @staticmethod
    def _should_try_next_model(error_code: str | None) -> bool:
        return error_code not in _NON_FALLBACKABLE_ERROR_CODES

    def execute_sync(
        self,
        *,
        primary_model: str,
        primary_provider: str,
        call_fn: Any,
    ) -> tuple[Any, FallbackOutcome]:
        """Try each model in chain until one succeeds.

        *call_fn* receives ``(model: str, provider: str, attempt_idx: int)`` and
        must return the provider response on success or raise on failure.
        """
        if self._chain is None:
            result = call_fn(primary_model, primary_provider, 0)
            return result, FallbackOutcome(
                resolved_model=primary_model,
                resolved_provider=primary_provider,
                fallback_attempts=0,
                chain=[primary_model],
            )

        models = self._models()
        candidate_models, circuit_open_models = self._candidate_models()
        last_exc: Exception | None = None
        last_error_code: str | None = None

        for idx, try_model in candidate_models:
            try_provider = primary_provider if idx == 0 else resolve_provider_from_model(try_model)
            if try_provider is None:
                continue

            _t0 = time.perf_counter()
            try:
                result = call_fn(try_model, try_provider, idx)
                _latency_ms = (time.perf_counter() - _t0) * 1000.0
                self._registry.record(try_model, _latency_ms, success=True)
                return result, FallbackOutcome(
                    resolved_model=try_model,
                    resolved_provider=try_provider,
                    fallback_attempts=idx,
                    chain=models,
                    last_error=last_exc,
                    last_error_code=last_error_code,
                    circuit_open_models=circuit_open_models or None,
                )
            except Exception as exc:
                _latency_ms = (time.perf_counter() - _t0) * 1000.0
                self._registry.record(try_model, _latency_ms, success=False)
                last_exc = exc
                # Attempt to read a ZROKY error code if the caller stashed one
                last_error_code = self._error_code(exc)
                if not self._should_try_next_model(last_error_code):
                    raise
                if idx < len(models) - 1 and self._verbose:
                    print(
                        f"[ZROKY] Fallback from {models[idx]} to {models[idx + 1]} "
                        f"({type(exc).__name__})"
                    )

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("[ZROKY] Fallback exhausted with no exception captured")

    async def execute_async(
        self,
        *,
        primary_model: str,
        primary_provider: str,
        call_fn: Any,
    ) -> tuple[Any, FallbackOutcome]:
        """Async version of :meth:`execute_sync`."""
        if self._chain is None:
            result = await call_fn(primary_model, primary_provider, 0)
            return result, FallbackOutcome(
                resolved_model=primary_model,
                resolved_provider=primary_provider,
                fallback_attempts=0,
                chain=[primary_model],
            )

        models = self._models()
        candidate_models, circuit_open_models = self._candidate_models()
        last_exc: Exception | None = None
        last_error_code: str | None = None

        for idx, try_model in candidate_models:
            try_provider = primary_provider if idx == 0 else resolve_provider_from_model(try_model)
            if try_provider is None:
                continue

            _t0 = time.perf_counter()
            try:
                result = await call_fn(try_model, try_provider, idx)
                _latency_ms = (time.perf_counter() - _t0) * 1000.0
                self._registry.record(try_model, _latency_ms, success=True)
                return result, FallbackOutcome(
                    resolved_model=try_model,
                    resolved_provider=try_provider,
                    fallback_attempts=idx,
                    chain=models,
                    last_error=last_exc,
                    last_error_code=last_error_code,
                    circuit_open_models=circuit_open_models or None,
                )
            except Exception as exc:
                _latency_ms = (time.perf_counter() - _t0) * 1000.0
                self._registry.record(try_model, _latency_ms, success=False)
                last_exc = exc
                last_error_code = self._error_code(exc)
                if not self._should_try_next_model(last_error_code):
                    raise
                if idx < len(models) - 1 and self._verbose:
                    print(
                        f"[ZROKY] Fallback from {models[idx]} to {models[idx + 1]} "
                        f"({type(exc).__name__})"
                    )

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("[ZROKY] Fallback exhausted with no exception captured")
