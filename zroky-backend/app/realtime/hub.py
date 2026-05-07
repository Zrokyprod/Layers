"""In-process WebSocket hub for tenant-scoped realtime updates.

Topics
------
- ``diagnosis``  — emitted when a new diagnosis is produced.
- ``loop_alert`` — emitted when the loop-detection engine raises an alert.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

try:
    import websockets as _websockets_lib
except ImportError:  # pragma: no cover
    _websockets_lib = None  # type: ignore[assignment]

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# tenant_id -> { topic -> [WebSocket, ...] }
_connections: dict[str, dict[str, list[WebSocket]]] = {}

# tenant_id -> { topic -> asyncio.Queue }
_local_queues: dict[str, dict[str, asyncio.Queue]] = {}

# Background tasks so they are not garbage-collected
_task_refs: set[asyncio.Task] = set()

# Redis pub/sub bridge (shared across all tenants/topics)
_redis_pub: aioredis.Redis | None = None
_redis_sub_thread: threading.Thread | None = None
_redis_sub_stop = threading.Event()
_main_event_loop: asyncio.AbstractEventLoop | None = None


def _redis_channel(tenant_id: str, topic: str) -> str:
    return f"zroky:ws:{tenant_id}:{topic}"


async def _ensure_redis_pub() -> aioredis.Redis | None:
    """Lazy-create async Redis client for publishing."""
    global _redis_pub
    if _redis_pub is not None:
        return _redis_pub
    if aioredis is None:
        return None
    try:
        settings = get_settings()
        _redis_pub = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return _redis_pub
    except Exception as exc:
        logger.warning("Redis pub client unavailable: %s", exc)
        return None


async def _publish_to_redis(tenant_id: str, topic: str, payload: dict) -> None:
    """Publish a message to the Redis channel so other pods receive it."""
    client = await _ensure_redis_pub()
    if client is None:
        return
    try:
        await client.publish(_redis_channel(tenant_id, topic), json.dumps(payload))
    except Exception as exc:
        logger.debug("Redis publish failed (non-critical): %s", exc)


def _redis_subscriber_loop() -> None:
    """Synchronous thread that subscribes to Redis and enqueues messages locally."""
    try:
        import redis as _sync_redis

        settings = get_settings()
        client = _sync_redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=None,
        )
        pubsub = client.pubsub()
        pubsub.psubscribe("zroky:ws:*")
        for message in pubsub.listen():
            if _redis_sub_stop.is_set():
                break
            if message["type"] != "pmessage":
                continue
            try:
                channel: str = message["channel"]
                data = json.loads(message["data"])
                # channel format: zroky:ws:{tenant_id}:{topic}
                parts = channel.split(":")
                if len(parts) >= 4:
                    tenant_id = parts[2]
                    topic = ":".join(parts[3:])
                    asyncio.run_coroutine_threadsafe(
                        _publish_to_local_connections(tenant_id, topic, data),
                        _get_event_loop(),
                    )
            except Exception:
                logger.exception("Redis subscriber message handling error")
    except Exception as exc:
        logger.warning("Redis subscriber thread exiting: %s", exc)


def _get_event_loop() -> asyncio.AbstractEventLoop:
    if _main_event_loop is not None:
        return _main_event_loop
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.new_event_loop()


async def start_redis_bridge() -> None:
    """Start the background Redis subscriber thread if Redis is available."""
    global _redis_sub_thread, _main_event_loop
    _main_event_loop = asyncio.get_running_loop()
    if _redis_sub_thread is not None and _redis_sub_thread.is_alive():
        return
    if aioredis is None:
        logger.info("aioredis unavailable; skipping Redis Pub/Sub bridge")
        return
    try:
        _redis_sub_stop.clear()
        _redis_sub_thread = threading.Thread(
            target=_redis_subscriber_loop, name="zroky-redis-ws-bridge", daemon=True
        )
        _redis_sub_thread.start()
        logger.info("Redis WebSocket Pub/Sub bridge started")
    except Exception as exc:
        logger.warning("Could not start Redis WebSocket bridge: %s", exc)


async def _close_websocket(ws: WebSocket) -> None:
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass


async def _publish_to_local_connections(
    tenant_id: str,
    topic: str,
    payload: dict,
    exclude: WebSocket | None = None,
) -> None:
    """Push a JSON-serialisable payload to every WebSocket connected to the tenant/topic."""
    data = json.dumps(payload)
    topic_map = _connections.get(tenant_id, {})
    for ws in list(topic_map.get(topic, [])):
        if ws is exclude:
            continue
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(data)
        except (RuntimeError, WebSocketDisconnect) as exc:
            logger.warning("Dropping stale WebSocket for tenant %s: %s", tenant_id, exc)
            topic_map[topic].remove(ws)
            await _close_websocket(ws)


async def _broadcast_loop(tenant_id: str, topic: str) -> None:
    """Consume messages from the in-memory queue, dispatch locally, and forward to Redis."""
    q = _local_queues[tenant_id][topic]
    while True:
        payload = await q.get()
        try:
            await _publish_to_local_connections(tenant_id, topic, payload)
            await _publish_to_redis(tenant_id, topic, payload)
        except Exception:
            logger.exception("Broadcast loop error for %s/%s", tenant_id, topic)
        finally:
            q.task_done()


@dataclass
class _Subscriber:
    websocket: WebSocket
    tenant_id: str
    topics: set[str] = field(default_factory=set)


class RealtimeHub:
    """Tenant-scoped pub/sub layer over WebSocket connections."""

    def __init__(self) -> None:
        # tenant_id → list of subscribers
        self._subscribers: dict[str, list[_Subscriber]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        *,
        tenant_id: str,
        topics: Iterable[str] | None = None,
    ) -> _Subscriber:
        await websocket.accept()
        sub = _Subscriber(
            websocket=websocket,
            tenant_id=tenant_id,
            topics=set(topics or []),
        )
        async with self._lock:
            self._subscribers[tenant_id].append(sub)
        logger.info(
            "realtime: client connected (tenant=%s, topics=%s, total=%d)",
            tenant_id,
            sorted(sub.topics) or "*",
            len(self._subscribers[tenant_id]),
        )
        return sub

    async def disconnect(self, sub: _Subscriber) -> None:
        async with self._lock:
            tenant_subs = self._subscribers.get(sub.tenant_id, [])
            if sub in tenant_subs:
                tenant_subs.remove(sub)
            if not tenant_subs:
                self._subscribers.pop(sub.tenant_id, None)
        try:
            await sub.websocket.close()
        except Exception:  # noqa: BLE001
            pass

    async def publish(
        self,
        *,
        tenant_id: str,
        topic: str,
        payload: dict[str, Any],
    ) -> int:
        """Fan-out a message to all subscribers of ``tenant_id`` watching ``topic``.

        Returns the number of clients that received the message.
        """
        message = {
            "topic": topic,
            "payload": payload,
            "sent_at": datetime.now(UTC).isoformat(),
        }
        encoded = json.dumps(message, default=str)

        async with self._lock:
            subs_snapshot = list(self._subscribers.get(tenant_id, []))

        delivered = 0
        for sub in subs_snapshot:
            if sub.topics and topic not in sub.topics:
                continue
            try:
                await sub.websocket.send_text(encoded)
                delivered += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("realtime: drop subscriber after send error: %s", exc)
                await self.disconnect(sub)
        return delivered

    def stats(self) -> dict[str, int]:
        return {tid: len(subs) for tid, subs in self._subscribers.items()}


_HUB_SINGLETON: RealtimeHub | None = None


def get_hub() -> RealtimeHub:
    """Module-level singleton accessor for the realtime hub."""
    global _HUB_SINGLETON
    if _HUB_SINGLETON is None:
        _HUB_SINGLETON = RealtimeHub()
    return _HUB_SINGLETON
