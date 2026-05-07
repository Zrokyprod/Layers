"""Tests for the realtime WebSocket hub."""

from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_realtime.db")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-realtime")

import pytest

from app.realtime.hub import RealtimeHub


class _FakeWebSocket:
    """Minimal WebSocket double that captures sent messages."""

    def __init__(self) -> None:
        self.accepted = False
        self.closed = False
        self.sent: list[str] = []
        self._fail_next_send = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self._fail_next_send:
            self._fail_next_send = False
            raise RuntimeError("boom")
        self.sent.append(text)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_publish_fans_out_to_tenant_subscribers():
    hub = RealtimeHub()
    ws_a = _FakeWebSocket()
    ws_b = _FakeWebSocket()

    await hub.connect(ws_a, tenant_id="t1")
    await hub.connect(ws_b, tenant_id="t1")

    delivered = await hub.publish(
        tenant_id="t1",
        topic="diagnosis",
        payload={"call_id": "abc"},
    )
    assert delivered == 2
    assert all("diagnosis" in msg for msg in ws_a.sent)
    assert all("diagnosis" in msg for msg in ws_b.sent)


@pytest.mark.asyncio
async def test_other_tenant_is_isolated():
    hub = RealtimeHub()
    ws_a = _FakeWebSocket()
    ws_b = _FakeWebSocket()
    await hub.connect(ws_a, tenant_id="t1")
    await hub.connect(ws_b, tenant_id="t2")

    delivered = await hub.publish(tenant_id="t1", topic="diagnosis", payload={})
    assert delivered == 1
    assert ws_a.sent and not ws_b.sent


@pytest.mark.asyncio
async def test_topic_filter_skips_non_matching_subscriber():
    hub = RealtimeHub()
    ws = _FakeWebSocket()
    await hub.connect(ws, tenant_id="t1", topics={"loop_alert"})

    await hub.publish(tenant_id="t1", topic="diagnosis", payload={})
    assert not ws.sent

    await hub.publish(tenant_id="t1", topic="loop_alert", payload={"x": 1})
    assert len(ws.sent) == 1
    decoded = json.loads(ws.sent[0])
    assert decoded["topic"] == "loop_alert"


@pytest.mark.asyncio
async def test_disconnect_removes_subscriber():
    hub = RealtimeHub()
    ws = _FakeWebSocket()
    sub = await hub.connect(ws, tenant_id="t1")
    assert hub.stats() == {"t1": 1}

    await hub.disconnect(sub)
    assert hub.stats() == {}
    assert ws.closed


@pytest.mark.asyncio
async def test_failed_send_evicts_subscriber():
    hub = RealtimeHub()
    ws = _FakeWebSocket()
    ws._fail_next_send = True
    await hub.connect(ws, tenant_id="t1")

    delivered = await hub.publish(tenant_id="t1", topic="diagnosis", payload={})
    # The send raised → subscriber was evicted, so delivered count is 0.
    assert delivered == 0
    assert hub.stats() == {}


@pytest.mark.asyncio
async def test_publish_to_empty_tenant_is_safe():
    hub = RealtimeHub()
    delivered = await hub.publish(tenant_id="ghost", topic="diagnosis", payload={})
    assert delivered == 0
