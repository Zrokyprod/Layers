"""Synchronous helpers that schedule realtime hub publishes from worker code.

Worker tasks (Celery / RQ / sync code paths) cannot ``await`` directly, so we
schedule the publish on the running event loop if one exists and silently
no-op otherwise. This keeps the realtime layer optional — code that emits
events never fails if no event loop / no subscribers are attached.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.realtime import get_hub

logger = logging.getLogger(__name__)


def publish_event(*, tenant_id: str, topic: str, payload: dict[str, Any]) -> None:
    """Best-effort fire-and-forget realtime broadcast.

    Safe to call from sync code and worker tasks. Never raises.
    """
    if not tenant_id or not topic:
        return

    hub = get_hub()
    coro = hub.publish(tenant_id=tenant_id, topic=topic, payload=payload)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (typical for Celery workers). Spin up a short-lived
        # loop just for this publish.
        try:
            asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            logger.debug("realtime publish (fresh loop) failed: %s", exc)
        return

    try:
        loop.create_task(coro)
    except Exception as exc:  # noqa: BLE001
        logger.debug("realtime publish (existing loop) failed: %s", exc)


def publish_diagnosis(*, tenant_id: str, diagnosis: dict[str, Any]) -> None:
    publish_event(tenant_id=tenant_id, topic="diagnosis", payload=diagnosis)


def publish_loop_alert(*, tenant_id: str, alert: dict[str, Any]) -> None:
    publish_event(tenant_id=tenant_id, topic="loop_alert", payload=alert)


def publish_cost_spike(*, tenant_id: str, spike: dict[str, Any]) -> None:
    publish_event(tenant_id=tenant_id, topic="cost_spike", payload=spike)


def publish_auth_failure_alert(*, tenant_id: str, alert: dict[str, Any]) -> None:
    publish_event(tenant_id=tenant_id, topic="auth_failure_alert", payload=alert)


def publish_rate_limit_alert(*, tenant_id: str, alert: dict[str, Any]) -> None:
    publish_event(tenant_id=tenant_id, topic="rate_limit_alert", payload=alert)
