from datetime import datetime, timedelta, timezone

import pytest

from app.services import loop_pattern_cache


class _FakeRedis:
    def __init__(self) -> None:
        self._zsets: dict[str, dict[str, float]] = {}
        self._values: dict[str, str] = {}

    def zadd(self, key: str, members: dict[str, float]) -> int:
        target = self._zsets.setdefault(key, {})
        added = 0
        for member, score in members.items():
            if member not in target:
                added += 1
            target[member] = float(score)
        return added

    def zremrangebyscore(self, key: str, min_score, max_score) -> int:
        target = self._zsets.get(key, {})
        min_value = float("-inf") if min_score == "-inf" else float(min_score)
        max_value = float("inf") if max_score == "+inf" else float(max_score)
        to_remove = [member for member, score in target.items() if min_value <= score <= max_value]
        for member in to_remove:
            target.pop(member, None)
        return len(to_remove)

    def zrangebyscore(self, key: str, min_score, max_score, withscores: bool = False):
        target = self._zsets.get(key, {})
        min_value = float("-inf") if min_score == "-inf" else float(min_score)
        max_value = float("inf") if max_score == "+inf" else float(max_score)
        filtered = [
            (member, score)
            for member, score in target.items()
            if min_value <= score <= max_value
        ]
        filtered.sort(key=lambda item: item[1])

        if withscores:
            return filtered
        return [member for member, _ in filtered]

    def zcount(self, key: str, min_score, max_score) -> int:
        return len(self.zrangebyscore(key, min_score, max_score))

    def expire(self, _key: str, _ttl: int) -> bool:
        return True

    def get(self, key: str):
        return self._values.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> bool:
        self._values[key] = value
        return True


def test_loop_cache_summarizes_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(loop_pattern_cache, "get_redis_client", lambda: fake_redis)

    base_time = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
    summary = None
    for idx in range(3):
        summary = loop_pattern_cache.summarize_loop_from_cache(
            tenant_id="proj-1",
            agent_name="agent-a",
            prompt_fingerprint="fp-a",
            now=base_time + timedelta(seconds=idx * 5),
            is_retry=False,
            failure_signature="code:rate_limit_exceeded",
            useless_output=False,
            output_signature="",
            repeat_window_seconds=90,
            progress_window_seconds=120,
            progress_min_events=3,
            evidence_sample_limit=5,
            cooldown_seconds=600,
        )

    assert summary is not None
    assert summary["repeat_count"] == 3
    assert summary["no_progress"] is True
    assert "repeated_failures" in summary["no_progress_reasons"]
    assert summary["error_pattern"]["failure_count"] == 3


def test_loop_cache_excludes_retries_from_repeat_count(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(loop_pattern_cache, "get_redis_client", lambda: fake_redis)

    now = datetime(2026, 4, 25, 11, 0, tzinfo=timezone.utc)
    loop_pattern_cache.summarize_loop_from_cache(
        tenant_id="proj-2",
        agent_name="agent-a",
        prompt_fingerprint="fp-b",
        now=now,
        is_retry=True,
        failure_signature="",
        useless_output=False,
        output_signature="",
        repeat_window_seconds=90,
        progress_window_seconds=120,
        progress_min_events=3,
        evidence_sample_limit=5,
        cooldown_seconds=600,
    )
    summary = loop_pattern_cache.summarize_loop_from_cache(
        tenant_id="proj-2",
        agent_name="agent-a",
        prompt_fingerprint="fp-b",
        now=now + timedelta(seconds=2),
        is_retry=False,
        failure_signature="code:timeout",
        useless_output=False,
        output_signature="",
        repeat_window_seconds=90,
        progress_window_seconds=120,
        progress_min_events=3,
        evidence_sample_limit=5,
        cooldown_seconds=600,
    )

    assert summary is not None
    assert summary["repeat_count"] == 1
    assert summary["retry_excluded_count"] >= 1


def test_loop_cache_mark_fired_updates_last_fired(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(loop_pattern_cache, "get_redis_client", lambda: fake_redis)

    fired_at = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    marked = loop_pattern_cache.mark_loop_detected_fired(
        tenant_id="proj-3",
        agent_name="agent-a",
        prompt_fingerprint="fp-c",
        fired_at=fired_at,
        cooldown_seconds=600,
    )
    assert marked is True

    summary = loop_pattern_cache.summarize_loop_from_cache(
        tenant_id="proj-3",
        agent_name="agent-a",
        prompt_fingerprint="fp-c",
        now=fired_at + timedelta(seconds=5),
        is_retry=False,
        failure_signature="",
        useless_output=False,
        output_signature="",
        repeat_window_seconds=90,
        progress_window_seconds=120,
        progress_min_events=3,
        evidence_sample_limit=5,
        cooldown_seconds=600,
    )

    assert summary is not None
    assert summary["last_fired_at"] is not None
