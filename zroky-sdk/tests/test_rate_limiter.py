"""Tests for the client-side rate limiter."""
import asyncio
import time
import threading

import pytest

from zroky._internal.rate_limiter import (
    BucketPair,
    RateLimiter,
    _TokenBucket,
    _parse_rate_headers,
    rate_limit_key,
)


# ---------------------------------------------------------------------------
# _TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_starts_full(self):
        b = _TokenBucket(10.0, 60.0)
        assert b.tokens == 10.0

    def test_consume_reduces_tokens(self):
        b = _TokenBucket(10.0, 60.0)
        b.consume(3)
        assert b.tokens < 10.0

    def test_wait_time_zero_when_available(self):
        b = _TokenBucket(10.0, 60.0)
        assert b.wait_time(5) == 0.0

    def test_wait_time_positive_when_depleted(self):
        b = _TokenBucket(10.0, 60.0)
        b.consume(10)
        wait = b.wait_time(1)
        assert wait > 0.0

    def test_consume_can_go_negative(self):
        b = _TokenBucket(2.0, 60.0)
        b.consume(5)
        assert b.tokens < 0.0

    def test_refill_recovers_tokens(self):
        b = _TokenBucket(100.0, 1.0)  # 100 per second
        b.consume(50)
        before = b.tokens
        time.sleep(0.05)
        b._refill()
        assert b.tokens > before

    def test_refill_caps_at_capacity(self):
        b = _TokenBucket(10.0, 60.0)
        time.sleep(0.01)
        b._refill()
        assert b.tokens <= 10.0

    def test_update_capacity(self):
        b = _TokenBucket(10.0, 60.0)
        b.consume(5)
        b.update_capacity(20.0)
        assert b.capacity == 20.0
        assert b.tokens <= 20.0

    def test_update_capacity_clamps_tokens(self):
        b = _TokenBucket(100.0, 60.0)
        b.update_capacity(5.0)
        assert b.tokens <= 5.0

    def test_set_remaining(self):
        b = _TokenBucket(100.0, 60.0)
        b.set_remaining(42.0)
        assert abs(b.tokens - 42.0) < 1.0

    def test_set_remaining_capped_at_capacity(self):
        b = _TokenBucket(10.0, 60.0)
        b.set_remaining(999.0)
        assert b.tokens <= 10.0

    def test_infinite_capacity_passthrough(self):
        b = _TokenBucket(float("inf"), 60.0)
        assert b.wait_time(1_000_000) == 0.0
        b.consume(1_000_000)
        assert b.wait_time(1) == 0.0


# ---------------------------------------------------------------------------
# BucketPair
# ---------------------------------------------------------------------------


class TestBucketPair:
    def test_from_limits_with_values(self):
        pair = BucketPair.from_limits(rpm=100, tpm=50000)
        assert pair.rpm.capacity == 100.0
        assert pair.tpm.capacity == 50000.0

    def test_from_limits_none_is_infinite(self):
        pair = BucketPair.from_limits()
        assert pair.rpm.capacity == float("inf")
        assert pair.tpm.capacity == float("inf")

    def test_has_lock(self):
        pair = BucketPair.from_limits()
        assert isinstance(pair.lock, type(threading.Lock()))


# ---------------------------------------------------------------------------
# rate_limit_key
# ---------------------------------------------------------------------------


class TestRateLimitKey:
    def test_format(self):
        assert rate_limit_key("openai", "gpt-4o") == "openai/gpt-4o"


# ---------------------------------------------------------------------------
# _parse_rate_headers
# ---------------------------------------------------------------------------


class TestParseHeaders:
    def test_openai_headers(self):
        class FakeResponse:
            headers = {
                "x-ratelimit-limit-requests": "500",
                "x-ratelimit-remaining-requests": "499",
                "x-ratelimit-limit-tokens": "30000",
                "x-ratelimit-remaining-tokens": "29500",
            }

        parsed = _parse_rate_headers(FakeResponse())
        assert parsed.req_limit == 500.0
        assert parsed.req_remaining == 499.0
        assert parsed.tok_limit == 30000.0
        assert parsed.tok_remaining == 29500.0

    def test_anthropic_headers(self):
        class FakeResponse:
            headers = {
                "anthropic-ratelimit-requests-limit": "1000",
                "anthropic-ratelimit-requests-remaining": "999",
                "anthropic-ratelimit-tokens-limit": "100000",
                "anthropic-ratelimit-tokens-remaining": "99500",
            }

        parsed = _parse_rate_headers(FakeResponse())
        assert parsed.req_limit == 1000.0
        assert parsed.req_remaining == 999.0
        assert parsed.tok_limit == 100000.0
        assert parsed.tok_remaining == 99500.0

    def test_no_headers(self):
        class FakeResponse:
            pass

        parsed = _parse_rate_headers(FakeResponse())
        assert parsed.req_limit is None
        assert parsed.tok_limit is None

    def test_nested_response(self):
        class Inner:
            headers = {"x-ratelimit-limit-requests": "100"}

        class FakeResponse:
            response = Inner()

        parsed = _parse_rate_headers(FakeResponse())
        assert parsed.req_limit == 100.0

    def test_non_numeric_header_ignored(self):
        class FakeResponse:
            headers = {"x-ratelimit-limit-requests": "not-a-number"}

        parsed = _parse_rate_headers(FakeResponse())
        assert parsed.req_limit is None


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_passthrough_no_config(self):
        rl = RateLimiter()
        waited = rl.acquire("openai/gpt-4o")
        assert waited == 0.0

    def test_configure_and_status(self):
        rl = RateLimiter()
        rl.configure("openai/gpt-4o", rpm=500, tpm=30000)
        s = rl.status("openai/gpt-4o")
        assert s["configured"] is True
        assert s["rpm_capacity"] == 500.0
        assert s["tpm_capacity"] == 30000.0

    def test_configure_all(self):
        rl = RateLimiter()
        rl.configure_all({
            "openai/gpt-4o": {"rpm": 500, "tpm": 30000},
            "anthropic/claude-3-5-sonnet": {"rpm": 100},
        })
        assert rl.status("openai/gpt-4o")["rpm_capacity"] == 500.0
        assert rl.status("anthropic/claude-3-5-sonnet")["rpm_capacity"] == 100.0

    def test_acquire_consumes_tokens(self):
        rl = RateLimiter()
        rl.configure("k", rpm=10)
        rl.acquire("k")
        s = rl.status("k")
        assert s["rpm_remaining"] < 10.0

    def test_acquire_consumes_estimated_tokens(self):
        rl = RateLimiter()
        rl.configure("k", tpm=1000)
        rl.acquire("k", estimated_tokens=500)
        s = rl.status("k")
        assert s["tpm_remaining"] < 1000.0

    def test_acquire_waits_when_exhausted(self):
        rl = RateLimiter()
        rl.configure("k", rpm=2)
        rl.acquire("k")
        rl.acquire("k")
        # Third call should need to wait
        start = time.monotonic()
        rl.acquire("k", timeout=2.0)
        elapsed = time.monotonic() - start
        assert elapsed > 0.01  # had to wait

    def test_acquire_timeout_sends_anyway(self):
        rl = RateLimiter()
        rl.configure("k", rpm=1)
        rl.acquire("k")
        start = time.monotonic()
        waited = rl.acquire("k", timeout=0.01)
        elapsed = time.monotonic() - start
        # Should return within ~timeout
        assert elapsed < 0.1

    def test_update_from_response_adjusts_remaining(self):
        rl = RateLimiter()
        rl.configure("k", rpm=500, tpm=30000)

        class FakeResponse:
            headers = {
                "x-ratelimit-remaining-requests": "490",
                "x-ratelimit-remaining-tokens": "28000",
            }

        rl.update_from_response("k", FakeResponse())
        s = rl.status("k")
        assert abs(s["rpm_remaining"] - 490.0) < 1.0
        assert abs(s["tpm_remaining"] - 28000.0) < 100.0

    def test_update_from_response_adjusts_capacity(self):
        rl = RateLimiter()
        rl.configure("k", rpm=100)

        class FakeResponse:
            headers = {"x-ratelimit-limit-requests": "200"}

        rl.update_from_response("k", FakeResponse())
        s = rl.status("k")
        assert s["rpm_capacity"] == 200.0

    def test_update_consumes_token_delta(self):
        rl = RateLimiter()
        rl.configure("k", tpm=10000)
        rl.acquire("k", estimated_tokens=500)
        before = rl.status("k")["tpm_remaining"]

        class FakeResponse:
            headers = {}

        rl.update_from_response(
            "k", FakeResponse(), actual_tokens=800, estimated_tokens=500,
        )
        after = rl.status("k")["tpm_remaining"]
        # Should have consumed the extra 300
        delta = before - after
        assert abs(delta - 300.0) < 10.0

    def test_reset_key(self):
        rl = RateLimiter()
        rl.configure("k", rpm=10)
        rl.acquire("k")
        rl.reset("k")
        assert rl.status("k")["configured"] is False

    def test_reset_all(self):
        rl = RateLimiter()
        rl.configure("a", rpm=10)
        rl.configure("b", rpm=20)
        rl.reset()
        assert rl.status("a")["configured"] is False
        assert rl.status("b")["configured"] is False

    def test_thread_safety(self):
        rl = RateLimiter()
        rl.configure("k", rpm=10000, tpm=1000000)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    rl.acquire("k", estimated_tokens=10)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_status_unconfigured_key(self):
        rl = RateLimiter()
        s = rl.status("nonexistent")
        assert s["configured"] is False


# ---------------------------------------------------------------------------
# Async acquire
# ---------------------------------------------------------------------------


class TestRateLimiterAsync:
    @pytest.mark.asyncio
    async def test_async_passthrough(self):
        rl = RateLimiter()
        waited = await rl.acquire_async("openai/gpt-4o")
        assert waited == 0.0

    @pytest.mark.asyncio
    async def test_async_acquire_consumes(self):
        rl = RateLimiter()
        rl.configure("k", rpm=10)
        await rl.acquire_async("k")
        s = rl.status("k")
        assert s["rpm_remaining"] < 10.0

    @pytest.mark.asyncio
    async def test_async_acquire_waits_when_exhausted(self):
        rl = RateLimiter()
        rl.configure("k", rpm=2)
        await rl.acquire_async("k")
        await rl.acquire_async("k")
        start = time.monotonic()
        await rl.acquire_async("k", timeout=2.0)
        elapsed = time.monotonic() - start
        assert elapsed > 0.01

    @pytest.mark.asyncio
    async def test_async_timeout_sends_anyway(self):
        rl = RateLimiter()
        rl.configure("k", rpm=1)
        await rl.acquire_async("k")
        start = time.monotonic()
        await rl.acquire_async("k", timeout=0.01)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
