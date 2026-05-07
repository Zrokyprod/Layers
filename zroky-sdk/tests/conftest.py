"""conftest.py for SDK tests."""
import pytest


@pytest.fixture(autouse=True)
def reset_sdk_state():
    """Reset SDK global state before every test."""
    import zroky
    zroky._config = None
    zroky._recent_preflight_calls.clear()
    zroky._payload_guard_logged_call_ids.clear()
    zroky._payload_guard_log_order.clear()
    if zroky._queue is not None:
        try:
            zroky._queue.shutdown()
        except Exception:
            pass
        zroky._queue = None
    # Reset async state
    if hasattr(zroky, '_async_queue') and zroky._async_queue is not None:
        try:
            import asyncio
            asyncio.run(zroky._async_queue.shutdown())
        except Exception:
            pass
        zroky._async_queue = None
    yield
    if zroky._queue is not None:
        try:
            zroky._queue.shutdown()
        except Exception:
            pass
    zroky._config = None
    zroky._queue = None
    zroky._recent_preflight_calls.clear()
    zroky._payload_guard_logged_call_ids.clear()
    zroky._payload_guard_log_order.clear()
    # Cleanup async state
    if hasattr(zroky, '_async_queue') and zroky._async_queue is not None:
        try:
            import asyncio
            asyncio.run(zroky._async_queue.shutdown())
        except Exception:
            pass
        zroky._async_queue = None
