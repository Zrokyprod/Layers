"""
Metrics and telemetry hooks for the ZROKY SDK.

This module provides hooks for custom metrics collection and monitoring.
Users can register callbacks to receive SDK events for custom metrics.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from zroky._internal.models import CallEvent

_logger = logging.getLogger(__name__)

# Callback registry
_event_callbacks: list[Callable[[CallEvent], None]] = []
_error_callbacks: list[Callable[[CallEvent, Exception], None]] = []
_flush_callbacks: list[Callable[[int, int], None]] = []  # (success_count, fail_count)


def register_event_callback(callback: Callable[[CallEvent], None]) -> None:
    """
    Register a callback to be called for every captured event.
    
    The callback receives the CallEvent after it's been enqueued.
    
    Example:
        def on_event(event):
            print(f"Captured: {event.provider}/{event.model}")
        
        zroky.register_event_callback(on_event)
    """
    _event_callbacks.append(callback)


def unregister_event_callback(callback: Callable[[CallEvent], None]) -> None:
    """Remove a previously registered event callback."""
    if callback in _event_callbacks:
        _event_callbacks.remove(callback)


def register_error_callback(callback: Callable[[CallEvent, Exception], None]) -> None:
    """
    Register a callback to be called when an error is captured.
    
    The callback receives the CallEvent and the original exception.
    
    Example:
        def on_error(event, exc):
            if event.error_code == "RATE_LIMIT":
                alert_ops_team("Rate limit hit!")
        
        zroky.register_error_callback(on_error)
    """
    _error_callbacks.append(callback)


def unregister_error_callback(callback: Callable[[CallEvent, Exception], None]) -> None:
    """Remove a previously registered error callback."""
    if callback in _error_callbacks:
        _error_callbacks.remove(callback)


def register_flush_callback(callback: Callable[[int, int], None]) -> None:
    """
    Register a callback to be called after batch flush.
    
    The callback receives (success_count, fail_count) for the batch.
    
    Example:
        def on_flush(success, fail):
            metrics.gauge("zroky.flush.success", success)
            metrics.gauge("zroky.flush.fail", fail)
        
        zroky.register_flush_callback(on_flush)
    """
    _flush_callbacks.append(callback)


def unregister_flush_callback(callback: Callable[[int, int], None]) -> None:
    """Remove a previously registered flush callback."""
    if callback in _flush_callbacks:
        _flush_callbacks.remove(callback)


def notify_event(event: "CallEvent") -> None:
    """Notify all registered event callbacks."""
    for callback in _event_callbacks:
        try:
            callback(event)
        except Exception as exc:
            _logger.debug("Event callback failed: %s", exc)


def notify_error(event: "CallEvent", exc: Exception) -> None:
    """Notify all registered error callbacks."""
    for callback in _error_callbacks:
        try:
            callback(event, exc)
        except Exception as inner_exc:
            _logger.debug("Error callback failed: %s", inner_exc)


def notify_flush(success_count: int, fail_count: int) -> None:
    """Notify all registered flush callbacks."""
    for callback in _flush_callbacks:
        try:
            callback(success_count, fail_count)
        except Exception as exc:
            _logger.debug("Flush callback failed: %s", exc)


def clear_all_callbacks() -> None:
    """Clear all registered callbacks. Useful for testing."""
    _event_callbacks.clear()
    _error_callbacks.clear()
    _flush_callbacks.clear()
