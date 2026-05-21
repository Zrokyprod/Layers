# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for metrics and callback functionality."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import zroky
from zroky._internal.metrics import clear_all_callbacks
from zroky._internal.models import CallEvent, ErrorCode


def _reset_sdk():
    """Reset SDK global state."""
    zroky._config = None
    zroky._queue = None
    zroky._recent_preflight_calls.clear()
    clear_all_callbacks()


@pytest.fixture(autouse=True)
def cleanup():
    """Cleanup after each test."""
    yield
    clear_all_callbacks()


def test_error_classification_timeout():
    """Timeout errors are correctly classified."""
    timeout_errors = [
        Exception("Request timed out after 30 seconds"),
        Exception("Connection timeout"),
        Exception("Read timeout"),
        Exception("deadline exceeded"),
        Exception("The operation timed out"),
    ]
    for exc in timeout_errors:
        assert zroky._classify_error(exc) == ErrorCode.TIMEOUT


def test_error_classification_network():
    """Network errors are correctly classified."""
    network_errors = [
        Exception("Connection refused"),
        Exception("Network unreachable"),
        Exception("DNS resolution failed"),
        Exception("Connection reset by peer"),
        Exception("Name resolution error"),
    ]
    for exc in network_errors:
        assert zroky._classify_error(exc) == ErrorCode.NETWORK_ERROR


def test_error_classification_comprehensive_rate_limit():
    """Comprehensive rate limit patterns are detected."""
    rate_limit_errors = [
        Exception("429 Too Many Requests"),
        Exception("Rate limit exceeded: 1000 requests per minute"),
        Exception("Throttling error"),
        Exception("Quota exceeded for quota metric"),
        Exception("Capacity exceeded"),
        Exception("Over quota"),
        Exception("RPM limit exceeded"),
        Exception("TPM limit exceeded"),
    ]
    for exc in rate_limit_errors:
        assert zroky._classify_error(exc) == ErrorCode.RATE_LIMIT


def test_error_classification_comprehensive_auth():
    """Comprehensive auth failure patterns are detected."""
    auth_errors = [
        Exception("401 Unauthorized"),
        Exception("403 Forbidden"),
        Exception("Invalid API key provided"),
        Exception("Authentication failed"),
        Exception("Access denied"),
        Exception("Permission denied"),
        Exception("Invalid token"),
        Exception("Expired token"),
        Exception("API key not found"),
    ]
    for exc in auth_errors:
        assert zroky._classify_error(exc) == ErrorCode.AUTH_FAILURE


def test_unknown_error_returns_unknown_code():
    """Unknown errors return UNKNOWN_ERROR code."""
    exc = Exception("Some random unexpected error")
    assert zroky._classify_error(exc) == ErrorCode.UNKNOWN_ERROR


def test_event_callback_is_called(monkeypatch):
    """Event callbacks are invoked when events are captured."""
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")

    captured_events = []

    def on_event(event):
        captured_events.append(event)

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()
        zroky.on_event(on_event)

    # Simulate recording an event
    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        latency_ms=100.0,
    )

    # Flush and shutdown
    zroky.flush()

    assert len(captured_events) == 1
    assert captured_events[0].provider == "openai"

    zroky.shutdown()
    _reset_sdk()


def test_error_callback_is_called(monkeypatch):
    """Error callbacks are invoked when errors are captured."""
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")

    captured_errors = []

    def on_error(event, exc):
        captured_errors.append((event, exc))

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()
        zroky.on_error(on_error)

    # Simulate recording an error
    test_exc = Exception("429 Rate limit exceeded")
    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        error=test_exc,
        latency_ms=100.0,
    )

    zroky.flush()

    assert len(captured_errors) == 1
    event, exc = captured_errors[0]
    assert event.provider == "openai"
    assert event.error_code == ErrorCode.RATE_LIMIT

    zroky.shutdown()
    _reset_sdk()


def test_callback_registration_and_unregistration():
    """Callbacks can be registered and unregistered."""
    from zroky._internal import metrics

    events = []

    def handler(event):
        events.append(event)

    # Register
    zroky.on_event(handler)
    assert len(metrics._event_callbacks) == 1

    # Unregister
    zroky.unregister_event_callback(handler)
    assert len(metrics._event_callbacks) == 0
