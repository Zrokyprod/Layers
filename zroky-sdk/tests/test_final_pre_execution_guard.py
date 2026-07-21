from __future__ import annotations

from unittest.mock import patch

import pytest

import zroky
from zroky._errors import ZrokyRuntimePolicyBlocked


def _reset_sdk() -> None:
    zroky._config = None
    zroky._queue = None


def test_pre_execution_guard_calls_intent_then_policy_and_blocks_observe_only(monkeypatch) -> None:
    _reset_sdk()
    monkeypatch.setenv("ZROKY_API_KEY", "zk_test")
    monkeypatch.setenv("ZROKY_PROJECT_ID", "proj_test")
    monkeypatch.setenv("ZROKY_API_URL", "https://api.example")

    calls = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/v1/intents"):
            return Response({"id": "intent_1"})
        return Response({"id": "decision_1", "decision": "observe_only"})

    with patch("zroky._internal.queue.IngestClient"), patch("httpx.post", fake_post):
        with pytest.raises(ZrokyRuntimePolicyBlocked):
            zroky.pre_execution_guard(intent={"action": "refund"}, idempotency_key="intent-key")

    assert [call[0] for call in calls] == [
        "https://api.example/v1/intents",
        "https://api.example/v1/policy/check",
    ]
    assert calls[0][1]["headers"]["Idempotency-Key"] == "intent-key"
