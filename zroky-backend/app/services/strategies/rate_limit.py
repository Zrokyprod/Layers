"""RATE_LIMIT template fix strategy."""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _as_int, _as_text, _clean_snippet
from app.services.strategies._diff import (
    _before_after_diff,
    _conceptual_diff,
    _first_relevant_line,
)
from app.services.strategies.ai_fix import FixTuple


def generate(request: Any) -> FixTuple:
    return _rate_limit_fix(request)


def _rate_limit_fix(request: Any) -> FixTuple:
    evidence = request.evidence
    provider = _as_text(evidence.get("provider") or request.call_context.get("provider"))
    retry_after = _as_int(evidence.get("retry_after_seconds"))
    snippet = _clean_snippet(request.code_snippet)

    if snippet:
        diff = _rate_limit_diff_from_snippet(snippet, retry_after=retry_after)
        strategy_confidence = 0.88 if "AFTER" in diff else 0.70
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Apply at the provider client initialization or request site.",
            [
                "Add exponential backoff with jitter for 429 responses.",
                (
                    f"Respect retry-after headers if provider sends them (current: {retry_after}s)."
                    if retry_after
                    else "Respect retry-after headers if provider sends them."
                ),
                "Consider circuit breaker for sustained rate limiting.",
            ],
        )
        strategy_confidence = 0.65

    explanation = (
        f"Provider {provider or 'unknown'} returned rate limit signals. "
        "The fix adds retry logic with exponential backoff to gracefully handle transient rate limits."
    )
    fix_rationale = "Exponential backoff with jitter prevents thundering herd while respecting provider limits."
    alternatives = [
        {"option": "increase_rate_limit_quota", "tradeoff": "Requires provider account upgrade; may increase costs but eliminates client-side complexity."},
        {"option": "request_batching", "tradeoff": "Reduces request count but adds latency and complexity for real-time use cases."},
        {"option": "circuit_breaker", "tradeoff": "Prevents hammering failing endpoints but requires careful tuning of thresholds."},
    ]
    review_points = [
        "Ensure max retry count and total timeout align with SLA requirements.",
        "Verify jitter prevents synchronized retries across multiple instances.",
        "Check that retry-after header parsing handles edge cases (missing, malformed, too large).",
    ]
    verification_steps = [
        "Simulate 429 responses and verify backoff behavior.",
        "Confirm retry-after header is respected when present.",
        "Measure p99 latency under rate limit conditions.",
    ]
    rollback_instructions = [
        "Remove or disable the retry wrapper.",
        "Restore original synchronous request behavior.",
        "Verify rate limit errors surface immediately again.",
    ]
    return (
        "Fix RATE_LIMIT with exponential backoff and retry logic",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _rate_limit_diff_from_snippet(snippet: str, *, retry_after: int) -> str:
    line = _first_relevant_line(snippet, ("request", "post", "get", "client", "call"))
    if line:
        return _before_after_diff(
            before=line,
            after=f"<existing_retry_wrapper>(\n    lambda: {line},\n    max_retries=3,\n    base_delay=1.0,\n)",
        )
    return _before_after_diff(
        before="# Original request code",
        after=(
            "# Add retry logic around the rate-limited request\n"
            "response = <existing_retry_wrapper>(\n"
            "    make_request,\n"
            "    max_retries=3,\n"
            "    base_delay=1.0,\n"
            ")"
        ),
    )
