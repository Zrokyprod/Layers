# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

# ---------------------------------------------------------------------------
# Loop Guard — Real-Time Agent Loop Detection & Kill
# ---------------------------------------------------------------------------

"""
Detects agent loops IN REAL-TIME and kills the agent before damage is done.

- Tracks output fingerprints per trace_id in sliding window
- Detects repeated outputs → loop confirmed
- Detects call count per trace exceeding max depth → runaway agent
- Detects cumulative cost per trace exceeding threshold → cost runaway
- Actions: warn, raise LoopDetectedError, return_cached_last_good_response
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .loop_signals import generate_output_fingerprint


class LoopDetectedError(Exception):
    """Raised when a loop is detected and action is 'raise'."""

    def __init__(self, message: str, loop_type: str | None = None) -> None:
        super().__init__(message)
        self.loop_type = loop_type


@dataclass(frozen=True)
class LoopCheckResult:
    action: str  # "allow", "warn", "raise", "return_cached"
    message: str = ""
    loop_type: str | None = None
    trace_id: str | None = None
    loop_call_count: int = 0


@dataclass
class _TraceState:
    call_count: int = 0
    cumulative_cost_usd: float = 0.0
    output_fingerprints: deque = field(default_factory=lambda: deque(maxlen=100))
    fingerprint_counts: dict[str, int] = field(default_factory=dict)
    last_good_response: Any = None
    last_good_timestamp: float = 0.0
    created_at: float = field(default_factory=time.time)


class LoopGuard:
    """
    Thread-safe in-memory loop detector per trace_id.
    No external I/O — works in every runtime condition.
    """

    def __init__(
        self,
        *,
        max_calls_per_trace: int = 50,
        max_repeated_outputs: int = 3,
        max_cost_per_trace_usd: float = 10.0,
        default_action: str = "raise",
        window_size: int = 20,
        trace_ttl_seconds: float = 3600.0,
    ) -> None:
        self._max_calls = max(1, max_calls_per_trace)
        self._max_repeated = max(1, max_repeated_outputs)
        self._max_cost = max(0.0, max_cost_per_trace_usd)
        self._default_action = default_action
        self._window_size = max(1, window_size)
        self._trace_ttl = trace_ttl_seconds
        self._lock = threading.Lock()
        self._traces: dict[str, _TraceState] = {}

    # ------------------------------------------------------------------
    # Pre-call check: max_calls, max_cost
    # ------------------------------------------------------------------

    def check_pre_call(
        self,
        trace_id: str | None,
        estimated_cost_usd: float = 0.0,
    ) -> LoopCheckResult:
        if not trace_id:
            return LoopCheckResult(action="allow")

        try:
            with self._lock:
                state = self._get_or_create_trace(trace_id)

                # Max calls
                if state.call_count >= self._max_calls:
                    return self._make_result(
                        f"Trace {trace_id}: call count {state.call_count} >= max {self._max_calls}",
                        "max_calls",
                        state.call_count,
                    )

                # Max cost
                if state.cumulative_cost_usd + estimated_cost_usd >= self._max_cost:
                    return self._make_result(
                        f"Trace {trace_id}: cumulative cost ${state.cumulative_cost_usd:.4f} + "
                        f"estimated ${estimated_cost_usd:.4f} >= max ${self._max_cost:.2f}",
                        "max_cost",
                        state.call_count,
                    )

                # Pre-increment call count & cost (will be adjusted post-call)
                state.call_count += 1
                state.cumulative_cost_usd += estimated_cost_usd

                return LoopCheckResult(action="allow", loop_call_count=state.call_count)
        except Exception:
            # Graceful degradation — never break a call because loop guard failed
            return LoopCheckResult(action="allow")

    # ------------------------------------------------------------------
    # Post-call check: repeated output fingerprints
    # ------------------------------------------------------------------

    def check_post_call(
        self,
        trace_id: str | None,
        output_content: str | None,
        provider: str,
        model: str,
        actual_cost_usd: float = 0.0,
        estimated_cost_usd: float = 0.0,
    ) -> LoopCheckResult:
        if not trace_id or not output_content:
            # Still adjust cost bookkeeping
            if trace_id and actual_cost_usd != estimated_cost_usd:
                try:
                    with self._lock:
                        state = self._traces.get(trace_id)
                        if state:
                            state.cumulative_cost_usd += actual_cost_usd - estimated_cost_usd
                except Exception:
                    pass
            return LoopCheckResult(action="allow")

        try:
            fp = generate_output_fingerprint(output_content, provider, model)

            with self._lock:
                state = self._get_or_create_trace(trace_id)

                # Adjust cost (replace estimated with actual delta)
                if actual_cost_usd != estimated_cost_usd:
                    state.cumulative_cost_usd += actual_cost_usd - estimated_cost_usd

                # Record output fingerprint in sliding window (skip None = short/static)
                if fp is not None:
                    state.output_fingerprints.append(fp)
                    state.fingerprint_counts[fp] = state.fingerprint_counts.get(fp, 0) + 1
                    count = state.fingerprint_counts[fp]

                    # Trim counts that fell out of the sliding window
                    if len(state.output_fingerprints) == state.output_fingerprints.maxlen:
                        self._rebuild_fingerprint_counts(state)

                    if count > self._max_repeated:
                        return self._make_result(
                            f"Trace {trace_id}: output fingerprint repeated {count} times "
                            f"> max {self._max_repeated}",
                            "repeated_output",
                            state.call_count,
                        )

                # Not looping — cache this as last good response
                state.last_good_response = output_content
                state.last_good_timestamp = time.time()

                return LoopCheckResult(action="allow", loop_call_count=state.call_count)
        except Exception:
            return LoopCheckResult(action="allow")

    # ------------------------------------------------------------------
    # Retrieve last good response for return_cached action
    # ------------------------------------------------------------------

    def get_last_good_response(self, trace_id: str | None) -> Any | None:
        if not trace_id:
            return None
        try:
            with self._lock:
                state = self._traces.get(trace_id)
                return state.last_good_response if state else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # House-keeping
    # ------------------------------------------------------------------

    def cleanup_old_traces(self, max_age_seconds: float | None = None) -> int:
        """Remove trace states older than max_age_seconds. Returns count removed."""
        ttl = max_age_seconds or self._trace_ttl
        cutoff = time.time() - ttl
        removed = 0
        try:
            with self._lock:
                stale = [tid for tid, s in self._traces.items() if s.created_at < cutoff]
                for tid in stale:
                    del self._traces[tid]
                    removed += 1
        except Exception:
            pass
        return removed

    def reset_trace(self, trace_id: str | None) -> None:
        if not trace_id:
            return
        with self._lock:
            self._traces.pop(trace_id, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_trace(self, trace_id: str) -> _TraceState:
        if trace_id not in self._traces:
            self._traces[trace_id] = _TraceState()
        return self._traces[trace_id]

    def _make_result(self, message: str, loop_type: str, loop_call_count: int = 0) -> LoopCheckResult:
        return LoopCheckResult(
            action=self._default_action,
            message=message,
            loop_type=loop_type,
            loop_call_count=loop_call_count,
        )

    @staticmethod
    def _rebuild_fingerprint_counts(state: _TraceState) -> None:
        """Rebuild fingerprint counts from the sliding window deque."""
        counts: dict[str, int] = {}
        for fp in state.output_fingerprints:
            counts[fp] = counts.get(fp, 0) + 1
        state.fingerprint_counts = counts
