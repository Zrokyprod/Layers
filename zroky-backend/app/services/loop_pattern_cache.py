from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any

import redis

from app.services.redis_client import get_redis_client

_LOOP_CACHE_PREFIX = "zroky:loop:v1"


def _cache_suffix(*, tenant_id: str, agent_name: str, prompt_fingerprint: str) -> str:
    raw = f"{tenant_id}|{agent_name}|{prompt_fingerprint}".encode("utf-8")
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()


def _events_key(suffix: str) -> str:
    return f"{_LOOP_CACHE_PREFIX}:events:{suffix}"


def _retries_key(suffix: str) -> str:
    return f"{_LOOP_CACHE_PREFIX}:retries:{suffix}"


def _last_fired_key(suffix: str) -> str:
    return f"{_LOOP_CACHE_PREFIX}:last_fired:{suffix}"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def summarize_loop_from_cache(
    *,
    tenant_id: str,
    agent_name: str,
    prompt_fingerprint: str,
    now: datetime,
    is_retry: bool,
    failure_signature: str,
    useless_output: bool,
    output_signature: str,
    repeat_window_seconds: int,
    progress_window_seconds: int,
    progress_min_events: int,
    evidence_sample_limit: int,
    cooldown_seconds: int,
) -> dict[str, Any] | None:
    suffix = _cache_suffix(
        tenant_id=tenant_id,
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
    )
    events_key = _events_key(suffix)
    retries_key = _retries_key(suffix)
    last_fired_key = _last_fired_key(suffix)

    now_ts = now.timestamp()
    repeat_start = now_ts - max(1, repeat_window_seconds)
    progress_start = now_ts - max(1, progress_window_seconds)
    ttl_seconds = max(progress_window_seconds, cooldown_seconds) + 120

    unique_member = f"{now_ts:.6f}:{time.time_ns()}"

    try:
        client = get_redis_client()

        if is_retry:
            client.zadd(retries_key, {unique_member: now_ts})
        else:
            payload = {
                "t": now.isoformat(),
                "f": failure_signature[:200],
                "u": bool(useless_output),
                "o": output_signature[:240],
            }
            client.zadd(events_key, {json.dumps(payload, separators=(",", ":")): now_ts})

        client.zremrangebyscore(events_key, "-inf", progress_start)
        client.zremrangebyscore(retries_key, "-inf", progress_start)

        client.expire(events_key, ttl_seconds)
        client.expire(retries_key, ttl_seconds)

        repeat_events = client.zrangebyscore(events_key, repeat_start, now_ts)
        progress_events = client.zrangebyscore(events_key, progress_start, now_ts, withscores=True)
        retry_count = int(client.zcount(retries_key, progress_start, now_ts))
        last_fired_at = _parse_datetime(client.get(last_fired_key))

        failure_count = 0
        useless_output_count = 0
        error_counter: dict[str, int] = {}
        output_counter: dict[str, int] = {}
        sample_timestamps: list[str] = []

        for item, score in progress_events:
            try:
                event = json.loads(item)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            if not isinstance(event, dict):
                continue

            ts_text = event.get("t")
            if isinstance(ts_text, str) and ts_text.strip():
                sample_timestamps.append(ts_text.strip())
            else:
                sample_timestamps.append(datetime.fromtimestamp(score).isoformat())

            failure_sig = event.get("f")
            if isinstance(failure_sig, str) and failure_sig.strip():
                failure_count += 1
                normalized_failure = failure_sig.strip()
                error_counter[normalized_failure] = error_counter.get(normalized_failure, 0) + 1

            if bool(event.get("u")):
                useless_output_count += 1

            output_sig = event.get("o")
            if isinstance(output_sig, str) and output_sig.strip():
                normalized_output = output_sig.strip()
                output_counter[normalized_output] = output_counter.get(normalized_output, 0) + 1

        dominant_error: str | None = None
        dominant_error_count = 0
        if error_counter:
            dominant_error, dominant_error_count = max(error_counter.items(), key=lambda item: item[1])

        stagnant_output = False
        if output_counter:
            _, top_output_count = max(output_counter.items(), key=lambda item: item[1])
            stagnant_output = top_output_count >= progress_min_events

        repeated_failures = failure_count >= progress_min_events
        repeated_useless_output = useless_output_count >= progress_min_events or stagnant_output
        no_progress = repeated_failures or repeated_useless_output

        no_progress_reasons: list[str] = []
        if repeated_failures:
            no_progress_reasons.append("repeated_failures")
        if repeated_useless_output:
            no_progress_reasons.append("repeated_useless_output")
        if stagnant_output and "stagnant_output" not in no_progress_reasons:
            no_progress_reasons.append("stagnant_output")

        return {
            "repeat_count": len(repeat_events),
            "retry_excluded_count": retry_count,
            "no_progress": no_progress,
            "no_progress_reasons": no_progress_reasons,
            "sample_timestamps": sample_timestamps[-max(1, evidence_sample_limit):],
            "error_pattern": {
                "dominant_error": dominant_error,
                "dominant_error_count": dominant_error_count,
                "failure_count": failure_count,
                "useless_output_count": useless_output_count,
                "stagnant_output": stagnant_output,
            },
            "last_fired_at": last_fired_at,
        }
    except redis.RedisError:
        return None


def mark_loop_detected_fired(
    *,
    tenant_id: str,
    agent_name: str,
    prompt_fingerprint: str,
    fired_at: datetime,
    cooldown_seconds: int,
) -> bool:
    suffix = _cache_suffix(
        tenant_id=tenant_id,
        agent_name=agent_name,
        prompt_fingerprint=prompt_fingerprint,
    )
    key = _last_fired_key(suffix)

    try:
        client = get_redis_client()
        client.setex(key, max(1, cooldown_seconds), fired_at.isoformat())
        return True
    except redis.RedisError:
        return False
