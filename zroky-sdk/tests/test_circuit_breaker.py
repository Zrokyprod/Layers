# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for circuit breaker state machine."""
import time

import pytest

from zroky._internal.circuit_breaker import CircuitBreaker, CircuitState


def test_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.call_allowed() is True


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=60.0)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.call_allowed() is False


def test_resets_to_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.15)
    assert cb.call_allowed() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0.05, success_threshold=2)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.1)
    cb.call_allowed()  # transition to HALF_OPEN
    cb.record_success()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens_circuit():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.1)
    cb.call_allowed()  # transition to HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_success_clears_failure_count_in_closed():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()  # should reset counter
    cb.record_failure()
    # only 1 failure after reset — still closed
    assert cb.state == CircuitState.CLOSED


def test_does_not_trip_below_threshold():
    cb = CircuitBreaker(failure_threshold=5)
    for _ in range(4):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.call_allowed() is True
