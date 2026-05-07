"""Automatic retry engine for provider calls.

Error-type-aware retry with exponential backoff, Retry-After header
parsing, and per-attempt telemetry for the ZROKY diagnosis engine.

Strategy by error type:
  RATE_LIMIT     → respect Retry-After header, else exponential backoff
  TIMEOUT        → exponential backoff
  NETWORK_ERROR  → exponential backoff
  5xx server     → exponential backoff
  TOKEN_OVERFLOW → never retry (input too large)
  AUTH_FAILURE   → never retry (credentials wrong)
  4xx client     → never retry

Backoff algorithm: full jitter — uniform(0, min(cap, base × 2^attempt)).
AWS research shows full jitter is optimal for distributed retry storms.

Blueprint SLO: retry overhead ≤ backoff_time + 1ms per attempt.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Error codes that are never worth retrying.
_NON_RETRYABLE_ERROR_CODES: frozenset[str] = frozenset({
    "TOKEN_OVERFLOW",
    "AUTH_FAILURE",
})

# HTTP status codes that indicate transient server-side failure.
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# Provider exception type names (lowercase) known to be transient.
_RETRYABLE_EXCEPTION_TYPES: frozenset[str] = frozenset({
    "ratelimiterror",
    "apitimeouterror",
    "apiconnectionerror",
    "internalservererror",
    "serviceunavailableerror",
    "timeouterror",
    "timeoutexception",
    "connecterror",
    "remoteprotocolerror",
    "connectionerror",
})

# Error message fragments that signal transient failures.
_TRANSIENT_MESSAGE_PATTERNS: tuple[str, ...] = (
    "connection reset",
    "broken pipe",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "overloaded",
    "capacity",
    "engine is currently overloaded",
    "server is busy",
)

# Hard ceiling for Retry-After values to prevent absurd waits.
_RETRY_AFTER_CAP_SECONDS: float = 120.0


def _tag_error_code(exc: Exception, error_code: str) -> None:
    try:
        setattr(exc, "__zroky_error_code", error_code)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Policy & Outcome
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """Immutable retry configuration."""

    max_retries: int = 2
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 30.0

    @property
    def total_attempts(self) -> int:
        return self.max_retries + 1


NO_RETRY = RetryPolicy(max_retries=0)


@dataclass
class RetryOutcome:
    """Mutable telemetry record — pass into retry functions to capture state."""

    attempt_count: int = 1
    retry_count: int = 0
    successful: bool = True
    last_error_type: str | None = None
    last_error_message: str | None = None
    total_backoff_seconds: float = 0.0
    backoff_durations: list[float] = field(default_factory=list)
    max_steps_reached: bool = False

    def to_retry_metadata(self) -> dict[str, Any] | None:
        """Format compatible with loop_signals.normalize_retry_metadata."""
        if self.retry_count == 0:
            return None
        return {
            "retry_count": self.retry_count,
            "retry_reason": self.last_error_type or "",
            "retry_interval": round(self.total_backoff_seconds * 1000, 1),
            "backoff_pattern": ",".join(f"{d:.2f}" for d in self.backoff_durations),
            "max_steps_reached": self.max_steps_reached,
        }


# ---------------------------------------------------------------------------
# Header extraction helpers
# ---------------------------------------------------------------------------

def _extract_retry_after(exc: Exception) -> float | None:
    """Parse Retry-After / x-ratelimit-reset from provider exception headers."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    for header_name in ("retry-after", "Retry-After", "x-ratelimit-reset"):
        value = None
        try:
            value = headers.get(header_name)
        except Exception:  # noqa: BLE001
            pass
        if value is not None:
            try:
                seconds = float(value)
                return min(max(0.0, seconds), _RETRY_AFTER_CAP_SECONDS)
            except (TypeError, ValueError):
                continue
    return None


def _extract_status_code(exc: Exception) -> int | None:
    """Extract HTTP status code from a provider exception."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


# ---------------------------------------------------------------------------
# Retry classification
# ---------------------------------------------------------------------------

def is_retryable(exc: Exception, error_code: str) -> bool:
    """Decide if *exc* is worth retrying given its classified *error_code*."""
    if error_code in _NON_RETRYABLE_ERROR_CODES:
        return False

    status = _extract_status_code(exc)
    if status is not None:
        if status in _RETRYABLE_STATUS_CODES:
            return True
        if 400 <= status < 500:
            return False

    exc_type = type(exc).__name__.lower()
    if exc_type in _RETRYABLE_EXCEPTION_TYPES:
        return True

    if error_code in ("RATE_LIMIT", "TIMEOUT", "NETWORK_ERROR"):
        return True

    msg = str(exc).lower()
    return any(p in msg for p in _TRANSIENT_MESSAGE_PATTERNS)


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------

def _calculate_backoff(
    attempt: int,
    base: float,
    maximum: float,
    retry_after: float | None,
) -> float:
    """Full-jitter exponential backoff, overridden by Retry-After when present."""
    if retry_after is not None and retry_after > 0:
        return min(retry_after + random.uniform(0, 0.5), maximum)

    exponential = base * (2 ** attempt)
    capped = min(exponential, maximum)
    return random.uniform(0, capped)


# ---------------------------------------------------------------------------
# Sync retry
# ---------------------------------------------------------------------------

def retry_sync(
    fn: Callable[..., Any],
    *,
    policy: RetryPolicy,
    classify_error: Callable[[Exception], str],
    verbose: bool = False,
    call_kwargs: dict[str, Any],
    outcome: RetryOutcome,
) -> Any:
    """Execute *fn(**call_kwargs)* with automatic retry on transient failures.

    Mutates *outcome* in-place so the caller always has telemetry,
    even when an exception propagates.

    Returns the provider response on success.
    Raises the last exception when all attempts are exhausted or the
    error is non-retryable.
    """
    last_exc: Exception | None = None

    for attempt in range(policy.total_attempts):
        try:
            result = fn(**call_kwargs)
            outcome.attempt_count = attempt + 1
            outcome.retry_count = attempt
            outcome.successful = True
            return result
        except Exception as exc:
            error_code = classify_error(exc)
            _tag_error_code(exc, error_code)
            last_exc = exc

            outcome.attempt_count = attempt + 1
            outcome.retry_count = attempt
            outcome.last_error_type = error_code
            outcome.last_error_message = str(exc)[:200]
            outcome.successful = False

            if not is_retryable(exc, error_code):
                raise

            if attempt >= policy.max_retries:
                outcome.max_steps_reached = True
                raise

            retry_after = _extract_retry_after(exc)
            backoff = _calculate_backoff(
                attempt=attempt,
                base=policy.base_backoff_seconds,
                maximum=policy.max_backoff_seconds,
                retry_after=retry_after,
            )

            outcome.backoff_durations.append(round(backoff, 3))
            outcome.total_backoff_seconds += backoff

            if verbose:
                source = (
                    f"Retry-After={retry_after:.1f}s"
                    if retry_after is not None
                    else f"backoff={backoff:.2f}s"
                )
                print(
                    f"[ZROKY] {error_code} on attempt {attempt + 1}/{policy.total_attempts}"
                    f", retrying in {backoff:.2f}s ({source})"
                )

            time.sleep(backoff)

    # Unreachable under normal flow, but defensive.
    outcome.successful = False
    outcome.max_steps_reached = True
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("[ZROKY] Retry exhausted with no exception captured")


# ---------------------------------------------------------------------------
# Async retry
# ---------------------------------------------------------------------------

async def retry_async(
    fn: Callable[..., Any],
    *,
    policy: RetryPolicy,
    classify_error: Callable[[Exception], str],
    verbose: bool = False,
    call_kwargs: dict[str, Any],
    outcome: RetryOutcome,
    is_coroutine: bool = True,
) -> Any:
    """Async equivalent of :func:`retry_sync`.

    When *is_coroutine* is True (default), ``fn`` is awaited directly.
    Otherwise it is dispatched to the default executor.
    """
    import asyncio  # noqa: PLC0415

    last_exc: Exception | None = None

    for attempt in range(policy.total_attempts):
        try:
            if is_coroutine:
                result = await fn(**call_kwargs)
            else:
                loop = asyncio.get_event_loop()
                _kw = call_kwargs

                def _run() -> Any:
                    return fn(**_kw)

                result = await loop.run_in_executor(None, _run)

            outcome.attempt_count = attempt + 1
            outcome.retry_count = attempt
            outcome.successful = True
            return result
        except Exception as exc:
            error_code = classify_error(exc)
            _tag_error_code(exc, error_code)
            last_exc = exc

            outcome.attempt_count = attempt + 1
            outcome.retry_count = attempt
            outcome.last_error_type = error_code
            outcome.last_error_message = str(exc)[:200]
            outcome.successful = False

            if not is_retryable(exc, error_code):
                raise

            if attempt >= policy.max_retries:
                outcome.max_steps_reached = True
                raise

            retry_after = _extract_retry_after(exc)
            backoff = _calculate_backoff(
                attempt=attempt,
                base=policy.base_backoff_seconds,
                maximum=policy.max_backoff_seconds,
                retry_after=retry_after,
            )

            outcome.backoff_durations.append(round(backoff, 3))
            outcome.total_backoff_seconds += backoff

            if verbose:
                source = (
                    f"Retry-After={retry_after:.1f}s"
                    if retry_after is not None
                    else f"backoff={backoff:.2f}s"
                )
                print(
                    f"[ZROKY] {error_code} on attempt {attempt + 1}/{policy.total_attempts}"
                    f", retrying in {backoff:.2f}s ({source})"
                )

            await asyncio.sleep(backoff)

    outcome.successful = False
    outcome.max_steps_reached = True
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("[ZROKY] Retry exhausted with no exception captured")
