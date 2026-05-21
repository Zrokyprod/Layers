"""Benchmark: per-detector evaluation latency (Rule 4 — ZROKY-004).

Measures wall-clock time for each detector to evaluate a worst-case payload.
All detectors must be callable with no external dependencies (no DB, no network).

Target: p95 < 5 ms per detector (see README: BENCH_TAG:detector_p95_latency).

Run locally:
    cd zroky-backend
    python -m pytest benchmarks/bench_detector_latency.py -v --benchmark-autosave

CI comparison:
    python -m pytest benchmarks/bench_detector_latency.py --benchmark-compare
    --benchmark-compare-fail=mean:10%
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Worst-case payloads per detector
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)

_PAYLOADS: dict[str, dict[str, Any]] = {
    "token_overflow": {
        "error_code": "context_length_exceeded",
        "model": "gpt-4",
        "prompt_tokens": 8200,
        "context_limit": 8192,
        "error_message": "This model's maximum context length is 8192 tokens. You have 8200 tokens.",
        "usage": {"prompt_tokens": 8200, "completion_tokens": 0},
        "estimated_prompt_tokens": 8200,
        "system_prompt_tokens": 4096,
        "user_message_tokens": 4104,
    },
    "rate_limit": {
        "status_code": 429,
        "error_code": "rate_limit_exceeded",
        "model": "gpt-4",
        "retry_after": 30,
        "error_message": "Rate limit reached for model gpt-4 on tokens per minute.",
    },
    "auth_failure": {
        "status_code": 401,
        "error_code": "invalid_api_key",
        "error_message": "Incorrect API key provided: sk-****",
        "model": "gpt-4",
    },
    "provider_error": {
        "status_code": 503,
        "error_code": "service_unavailable",
        "error_message": "The model is currently overloaded. Please try again later.",
        "model": "gpt-4",
    },
    "loop_detected": {
        "loop": {
            "repeat_count": 8,
            "window_seconds": 90,
            "tool_chain_repeat_cycles": 5,
            "tool_window_seconds": 120,
            "no_progress": True,
            "no_progress_reasons": ["no_new_information", "repeated_tool_call", "same_decision"],
            "loop_window_size": 10,
            "sample_timestamps": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:01:00Z",
                "2024-01-01T00:02:00Z",
            ],
        },
        "agent_name": "planner",
        "prompt_fingerprint": "fp_abcdef123456",
    },
    "cost_spike": {
        "cost_usd": 3.50,
        "total_tokens": 350_000,
        "model": "gpt-4",
        "agent_name": "bulk_document_processor",
        "per_session_cost_usd": 14.00,
        "reasoning_tokens": 50000,
        "cache_savings_total": 0.25,
        "status": "success",
    },
}


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

@pytest.mark.benchmark(group="detector_latency")
def test_token_overflow_detector_latency(benchmark) -> None:
    """BENCH_TAG:detector_p95_latency — TOKEN_OVERFLOW p95 < 5 ms."""
    from app.services.detectors.token_overflow import detect
    payload = _PAYLOADS["token_overflow"]
    result = benchmark(detect, payload)
    assert result is not None


@pytest.mark.benchmark(group="detector_latency")
def test_rate_limit_detector_latency(benchmark) -> None:
    """BENCH_TAG:detector_p95_latency — RATE_LIMIT p95 < 5 ms."""
    from app.services.detectors.rate_limit import detect
    payload = _PAYLOADS["rate_limit"]
    result = benchmark(detect, payload)
    assert result is not None


@pytest.mark.benchmark(group="detector_latency")
def test_auth_failure_detector_latency(benchmark) -> None:
    """BENCH_TAG:detector_p95_latency — AUTH_FAILURE p95 < 5 ms."""
    from app.services.detectors.auth_failure import detect
    payload = _PAYLOADS["auth_failure"]
    result = benchmark(detect, payload)
    assert result is not None


@pytest.mark.benchmark(group="detector_latency")
def test_provider_error_detector_latency(benchmark) -> None:
    """BENCH_TAG:detector_p95_latency — PROVIDER_ERROR p95 < 5 ms."""
    from app.services.detectors.provider_error import detect
    payload = _PAYLOADS["provider_error"]
    result = benchmark(detect, payload)
    assert result is not None


@pytest.mark.benchmark(group="detector_latency")
def test_loop_detected_detector_latency(benchmark) -> None:
    """BENCH_TAG:detector_p95_latency — LOOP_DETECTED p95 < 5 ms."""
    from app.services.detectors.loop import detect_entry
    payload = _PAYLOADS["loop_detected"]
    result = benchmark(detect_entry, payload, now=_NOW)
    assert result is not None


@pytest.mark.benchmark(group="detector_latency")
def test_cost_spike_detector_latency(benchmark) -> None:
    """BENCH_TAG:detector_p95_latency — COST_SPIKE p95 < 5 ms."""
    from app.services.detectors.cost_spike import detect_entry
    payload = _PAYLOADS["cost_spike"]
    result = benchmark(detect_entry, payload)
    assert result is not None


@pytest.mark.benchmark(group="detector_latency")
def test_registry_load_latency(benchmark) -> None:
    """BENCH_TAG:detector_registry_load — cold registry load < 50 ms."""
    from app.services.detectors._registry import _builtin_detectors
    detectors = benchmark(_builtin_detectors)
    assert len(detectors) == 6


# Rule 4 threshold registry
RULE4_LIMITS_MS = {
    "detector_p95_latency": 5.0,
    "detector_registry_load": 50.0,
}
