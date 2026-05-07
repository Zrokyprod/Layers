"""Tests for the automatic retry engine."""
import asyncio
import time
from unittest.mock import MagicMock

import pytest

from zroky._internal.retry import (
    NO_RETRY,
    RetryOutcome,
    RetryPolicy,
    _calculate_backoff,
    _extract_retry_after,
    _extract_status_code,
    is_retryable,
    retry_async,
    retry_sync,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_error(exc: Exception) -> str:
    """Minimal error classifier for testing."""
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "429" in str(exc):
        return "RATE_LIMIT"
    if "timeout" in name:
        return "TIMEOUT"
    if "connection" in name:
        return "NETWORK_ERROR"
    if "auth" in name or "401" in str(exc):
        return "AUTH_FAILURE"
    if "overflow" in name:
        return "TOKEN_OVERFLOW"
    return "UNKNOWN_ERROR"


class FakeRateLimitError(Exception):
    """Simulates a 429 with Retry-After header."""
    def __init__(self, retry_after: float | None = None):
        super().__init__("Rate limit exceeded")
        self.status_code = 429
        self.response = MagicMock()
        if retry_after is not None:
            self.response.headers = {"retry-after": str(retry_after)}
        else:
            self.response.headers = {}


class FakeServerError(Exception):
    """Simulates a 500."""
    def __init__(self):
        super().__init__("Internal server error")
        self.status_code = 500


class FakeAuthError(Exception):
    """Simulates a 401."""
    def __init__(self):
        super().__init__("401 unauthorized")
        self.status_code = 401


class FakeTimeoutError(Exception):
    """Simulates a timeout."""
    pass


class FakeTokenOverflowError(Exception):
    pass


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------

def test_policy_defaults():
    p = RetryPolicy()
    assert p.max_retries == 2
    assert p.total_attempts == 3
    assert p.base_backoff_seconds == 0.5
    assert p.max_backoff_seconds == 30.0


def test_no_retry_policy():
    assert NO_RETRY.max_retries == 0
    assert NO_RETRY.total_attempts == 1


# ---------------------------------------------------------------------------
# RetryOutcome
# ---------------------------------------------------------------------------

def test_outcome_no_retries():
    o = RetryOutcome()
    assert o.to_retry_metadata() is None


def test_outcome_with_retries():
    o = RetryOutcome(
        retry_count=2,
        last_error_type="RATE_LIMIT",
        total_backoff_seconds=1.5,
        backoff_durations=[0.5, 1.0],
        max_steps_reached=True,
    )
    meta = o.to_retry_metadata()
    assert meta is not None
    assert meta["retry_count"] == 2
    assert meta["retry_reason"] == "RATE_LIMIT"
    assert meta["retry_interval"] == 1500.0
    assert meta["backoff_pattern"] == "0.50,1.00"
    assert meta["max_steps_reached"] is True


# ---------------------------------------------------------------------------
# Header extraction
# ---------------------------------------------------------------------------

def test_extract_retry_after():
    exc = FakeRateLimitError(retry_after=2.5)
    assert _extract_retry_after(exc) == 2.5


def test_extract_retry_after_missing():
    exc = FakeServerError()
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_capped():
    exc = FakeRateLimitError(retry_after=999.0)
    result = _extract_retry_after(exc)
    assert result is not None
    assert result <= 120.0


def test_extract_status_code():
    exc = FakeRateLimitError()
    assert _extract_status_code(exc) == 429

    exc2 = FakeServerError()
    assert _extract_status_code(exc2) == 500

    exc3 = Exception("plain")
    assert _extract_status_code(exc3) is None


# ---------------------------------------------------------------------------
# is_retryable classification
# ---------------------------------------------------------------------------

def test_retryable_rate_limit():
    assert is_retryable(FakeRateLimitError(), "RATE_LIMIT") is True


def test_retryable_server_error():
    assert is_retryable(FakeServerError(), "UNKNOWN_ERROR") is True


def test_retryable_timeout():
    assert is_retryable(FakeTimeoutError(), "TIMEOUT") is True


def test_not_retryable_auth():
    assert is_retryable(FakeAuthError(), "AUTH_FAILURE") is False


def test_not_retryable_token_overflow():
    assert is_retryable(FakeTokenOverflowError(), "TOKEN_OVERFLOW") is False


def test_not_retryable_client_400():
    exc = Exception("bad request")
    exc.status_code = 400  # type: ignore[attr-defined]
    assert is_retryable(exc, "UNKNOWN_ERROR") is False


def test_retryable_connection_error_message():
    exc = Exception("connection reset by peer")
    assert is_retryable(exc, "NETWORK_ERROR") is True


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------

def test_backoff_respects_retry_after():
    backoff = _calculate_backoff(attempt=0, base=0.5, maximum=30.0, retry_after=5.0)
    assert 5.0 <= backoff <= 5.5  # retry_after + up to 0.5s jitter


def test_backoff_without_retry_after():
    backoff = _calculate_backoff(attempt=0, base=1.0, maximum=30.0, retry_after=None)
    assert 0.0 <= backoff <= 1.0  # full jitter over [0, base * 2^0]


def test_backoff_caps_at_maximum():
    backoff = _calculate_backoff(attempt=10, base=1.0, maximum=5.0, retry_after=None)
    assert 0.0 <= backoff <= 5.0


# ---------------------------------------------------------------------------
# retry_sync — success paths
# ---------------------------------------------------------------------------

def test_sync_success_no_retry_needed():
    fn = MagicMock(return_value="ok")
    outcome = RetryOutcome()

    result = retry_sync(
        fn, policy=RetryPolicy(max_retries=2),
        classify_error=_classify_error, call_kwargs={}, outcome=outcome,
    )

    assert result == "ok"
    assert fn.call_count == 1
    assert outcome.retry_count == 0
    assert outcome.successful is True
    assert outcome.to_retry_metadata() is None


def test_sync_success_after_transient_failure():
    fn = MagicMock(side_effect=[FakeServerError(), "ok"])
    outcome = RetryOutcome()

    result = retry_sync(
        fn, policy=RetryPolicy(max_retries=2, base_backoff_seconds=0.01),
        classify_error=_classify_error, call_kwargs={}, outcome=outcome,
    )

    assert result == "ok"
    assert fn.call_count == 2
    assert outcome.retry_count == 1
    assert outcome.successful is True
    meta = outcome.to_retry_metadata()
    assert meta is not None
    assert meta["retry_count"] == 1


def test_sync_success_after_rate_limit():
    fn = MagicMock(side_effect=[FakeRateLimitError(retry_after=0.01), "ok"])
    outcome = RetryOutcome()

    result = retry_sync(
        fn, policy=RetryPolicy(max_retries=2),
        classify_error=_classify_error, call_kwargs={}, outcome=outcome,
    )

    assert result == "ok"
    assert fn.call_count == 2
    assert outcome.retry_count == 1


# ---------------------------------------------------------------------------
# retry_sync — failure paths
# ---------------------------------------------------------------------------

def test_sync_exhausts_retries():
    fn = MagicMock(side_effect=FakeServerError())
    outcome = RetryOutcome()

    with pytest.raises(FakeServerError):
        retry_sync(
            fn, policy=RetryPolicy(max_retries=2, base_backoff_seconds=0.01),
            classify_error=_classify_error, call_kwargs={}, outcome=outcome,
        )

    assert fn.call_count == 3  # 1 initial + 2 retries
    assert outcome.retry_count == 2
    assert outcome.max_steps_reached is True
    assert outcome.successful is False


def test_sync_non_retryable_fails_immediately():
    fn = MagicMock(side_effect=FakeAuthError())
    outcome = RetryOutcome()

    with pytest.raises(FakeAuthError) as raised:
        retry_sync(
            fn, policy=RetryPolicy(max_retries=5),
            classify_error=_classify_error, call_kwargs={}, outcome=outcome,
        )

    assert fn.call_count == 1  # no retry attempted
    assert outcome.retry_count == 0
    assert outcome.successful is False
    assert getattr(raised.value, "__zroky_error_code") == "AUTH_FAILURE"


def test_sync_token_overflow_fails_immediately():
    fn = MagicMock(side_effect=FakeTokenOverflowError())
    outcome = RetryOutcome()

    with pytest.raises(FakeTokenOverflowError):
        retry_sync(
            fn, policy=RetryPolicy(max_retries=3),
            classify_error=_classify_error, call_kwargs={}, outcome=outcome,
        )

    assert fn.call_count == 1


def test_sync_no_retry_policy():
    fn = MagicMock(side_effect=FakeServerError())
    outcome = RetryOutcome()

    with pytest.raises(FakeServerError):
        retry_sync(
            fn, policy=NO_RETRY,
            classify_error=_classify_error, call_kwargs={}, outcome=outcome,
        )

    assert fn.call_count == 1
    assert outcome.max_steps_reached is True


# ---------------------------------------------------------------------------
# retry_sync — kwargs forwarding
# ---------------------------------------------------------------------------

def test_sync_forwards_kwargs():
    fn = MagicMock(return_value="ok")
    outcome = RetryOutcome()

    retry_sync(
        fn, policy=RetryPolicy(max_retries=0),
        classify_error=_classify_error,
        call_kwargs={"model": "gpt-4o", "messages": []},
        outcome=outcome,
    )

    fn.assert_called_once_with(model="gpt-4o", messages=[])


# ---------------------------------------------------------------------------
# retry_sync — verbose logging
# ---------------------------------------------------------------------------

def test_sync_verbose_prints(capsys):
    fn = MagicMock(side_effect=[FakeServerError(), "ok"])
    outcome = RetryOutcome()

    retry_sync(
        fn, policy=RetryPolicy(max_retries=2, base_backoff_seconds=0.01),
        classify_error=_classify_error, verbose=True,
        call_kwargs={}, outcome=outcome,
    )

    captured = capsys.readouterr()
    assert "[ZROKY]" in captured.out
    assert "UNKNOWN_ERROR" in captured.out
    assert "attempt 1/3" in captured.out


# ---------------------------------------------------------------------------
# retry_async
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_success_no_retry():
    async def fn():
        return "ok"

    outcome = RetryOutcome()
    result = await retry_async(
        fn, policy=RetryPolicy(max_retries=2),
        classify_error=_classify_error, call_kwargs={}, outcome=outcome,
    )

    assert result == "ok"
    assert outcome.retry_count == 0
    assert outcome.successful is True


@pytest.mark.asyncio
async def test_async_success_after_transient_failure():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise FakeServerError()
        return "ok"

    outcome = RetryOutcome()
    result = await retry_async(
        fn, policy=RetryPolicy(max_retries=2, base_backoff_seconds=0.01),
        classify_error=_classify_error, call_kwargs={}, outcome=outcome,
    )

    assert result == "ok"
    assert call_count == 2
    assert outcome.retry_count == 1


@pytest.mark.asyncio
async def test_async_exhausts_retries():
    async def fn():
        raise FakeServerError()

    outcome = RetryOutcome()
    with pytest.raises(FakeServerError):
        await retry_async(
            fn, policy=RetryPolicy(max_retries=1, base_backoff_seconds=0.01),
            classify_error=_classify_error, call_kwargs={}, outcome=outcome,
        )

    assert outcome.retry_count == 1
    assert outcome.max_steps_reached is True


@pytest.mark.asyncio
async def test_async_non_retryable_fails_immediately():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        raise FakeAuthError()

    outcome = RetryOutcome()
    with pytest.raises(FakeAuthError):
        await retry_async(
            fn, policy=RetryPolicy(max_retries=3),
            classify_error=_classify_error, call_kwargs={}, outcome=outcome,
        )

    assert call_count == 1
    assert outcome.retry_count == 0


# ---------------------------------------------------------------------------
# Timing sanity — retries should not take forever
# ---------------------------------------------------------------------------

def test_sync_retry_timing_reasonable():
    fn = MagicMock(side_effect=[FakeServerError(), FakeServerError(), "ok"])
    outcome = RetryOutcome()
    start = time.monotonic()

    retry_sync(
        fn, policy=RetryPolicy(max_retries=2, base_backoff_seconds=0.01, max_backoff_seconds=0.05),
        classify_error=_classify_error, call_kwargs={}, outcome=outcome,
    )

    elapsed = time.monotonic() - start
    assert elapsed < 1.0  # should finish well under 1s with tiny backoffs
    assert outcome.successful is True
