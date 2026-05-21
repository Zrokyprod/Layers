# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for the intelligent response cache."""
import sqlite3
import time

import pytest

from zroky._internal.cache import (
    CacheEntry,
    CachedResponse,
    ResponseCache,
    _DiskCache,
    _MemoryLRU,
    build_cache_key,
    cached_stream_iter,
    cached_stream_iter_async,
)


def _reset_sdk():
    """Reset SDK global state between tests."""
    import zroky
    zroky._config = None
    zroky._queue = None
    zroky._async_queue = None
    zroky._response_cache = None
    zroky._recent_preflight_calls.clear()


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_is_expired_false(self):
        e = CacheEntry(content="hi", tool_calls=None, usage=None, model="gpt-4o", provider="openai", ttl=10)
        assert not e.is_expired()

    def test_is_expired_true(self):
        e = CacheEntry(content="hi", tool_calls=None, usage=None, model="gpt-4o", provider="openai", ttl=0.01)
        time.sleep(0.02)
        assert e.is_expired()

    def test_to_json_roundtrip(self):
        e = CacheEntry(
            content="hello",
            tool_calls=[{"id": "tc-1", "type": "function"}],
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model="gpt-4o",
            provider="openai",
            ttl=3600,
        )
        raw = e.to_json()
        restored = CacheEntry.from_json(raw)
        assert restored.content == "hello"
        assert restored.usage == {"prompt_tokens": 10, "completion_tokens": 5}


# ---------------------------------------------------------------------------
# CachedResponse
# ---------------------------------------------------------------------------


class TestCachedResponse:
    def test_openai_style_access(self):
        e = CacheEntry(content="cached text", tool_calls=None, usage={"prompt_tokens": 3, "completion_tokens": 2}, model="gpt-4o", provider="openai")
        r = CachedResponse(e)
        assert r.from_cache is True
        assert r.choices[0].message.content == "cached text"
        assert r.choices[0].finish_reason == "stop"
        assert r.usage.prompt_tokens == 3
        assert r.usage.total_tokens == 5  # prompt + completion

    def test_tool_calls_reconstruction(self):
        e = CacheEntry(
            content=None,
            tool_calls=[{"id": "tc-1", "type": "function", "function": {"name": "search", "arguments": "{}"}}],
            usage=None,
            model="gpt-4o",
            provider="openai",
        )
        r = CachedResponse(e)
        assert r.choices[0].message.tool_calls[0].id == "tc-1"
        assert r.choices[0].message.tool_calls[0].function.name == "search"


# ---------------------------------------------------------------------------
# build_cache_key
# ---------------------------------------------------------------------------


class TestBuildCacheKey:
    def test_prefixes_fingerprint(self):
        assert build_cache_key("abc123").startswith("zc:abc123")


# ---------------------------------------------------------------------------
# _MemoryLRU
# ---------------------------------------------------------------------------


class TestMemoryLRU:
    def test_get_put(self):
        m = _MemoryLRU(max_entries=10)
        e = CacheEntry(content="x", tool_calls=None, usage=None, model="m", provider="p")
        m.put("k", e)
        assert m.get("k") is not None
        assert m.get("k").content == "x"

    def test_miss_returns_none(self):
        m = _MemoryLRU(max_entries=10)
        assert m.get("missing") is None

    def test_expired_removed(self):
        m = _MemoryLRU(max_entries=10)
        e = CacheEntry(content="x", tool_calls=None, usage=None, model="m", provider="p", ttl=0.01)
        m.put("k", e)
        time.sleep(0.02)
        assert m.get("k") is None

    def test_lru_eviction(self):
        m = _MemoryLRU(max_entries=2)
        m.put("a", CacheEntry(content="a", tool_calls=None, usage=None, model="m", provider="p"))
        m.put("b", CacheEntry(content="b", tool_calls=None, usage=None, model="m", provider="p"))
        m.put("c", CacheEntry(content="c", tool_calls=None, usage=None, model="m", provider="p"))
        assert m.get("a") is None
        assert m.get("b") is not None
        assert m.get("c") is not None

    def test_clear_single(self):
        m = _MemoryLRU(max_entries=10)
        m.put("a", CacheEntry(content="a", tool_calls=None, usage=None, model="m", provider="p"))
        m.clear("a")
        assert m.get("a") is None

    def test_clear_all(self):
        m = _MemoryLRU(max_entries=10)
        m.put("a", CacheEntry(content="a", tool_calls=None, usage=None, model="m", provider="p"))
        m.put("b", CacheEntry(content="b", tool_calls=None, usage=None, model="m", provider="p"))
        m.clear()
        assert m.get("a") is None
        assert m.get("b") is None


# ---------------------------------------------------------------------------
# _DiskCache
# ---------------------------------------------------------------------------


class TestDiskCache:
    def test_get_put(self, tmp_path):
        db = _DiskCache(str(tmp_path / "cache.db"))
        e = CacheEntry(content="disk", tool_calls=None, usage=None, model="m", provider="p")
        db.put("k", e)
        got = db.get("k")
        assert got is not None
        assert got.content == "disk"
        db.close()

    def test_expired_not_returned(self, tmp_path):
        db = _DiskCache(str(tmp_path / "cache.db"))
        e = CacheEntry(content="old", tool_calls=None, usage=None, model="m", provider="p", ttl=0.01)
        db.put("k", e)
        time.sleep(0.02)
        assert db.get("k") is None
        db.close()

    def test_clear_all(self, tmp_path):
        db = _DiskCache(str(tmp_path / "cache.db"))
        db.put("a", CacheEntry(content="a", tool_calls=None, usage=None, model="m", provider="p"))
        db.clear()
        assert db.get("a") is None
        db.close()

    def test_clear_single(self, tmp_path):
        db = _DiskCache(str(tmp_path / "cache.db"))
        db.put("a", CacheEntry(content="a", tool_calls=None, usage=None, model="m", provider="p"))
        db.put("b", CacheEntry(content="b", tool_calls=None, usage=None, model="m", provider="p"))
        db.clear("a")
        assert db.get("a") is None
        assert db.get("b") is not None
        db.close()

    def test_hit_count_increments(self, tmp_path):
        db = _DiskCache(str(tmp_path / "cache.db"))
        db.put("k", CacheEntry(content="x", tool_calls=None, usage=None, model="m", provider="p"))
        db.get("k")
        db.get("k")
        # Internal verification via raw query
        conn = sqlite3.connect(str(tmp_path / "cache.db"))
        row = conn.execute("SELECT hit_count FROM response_cache WHERE cache_key = 'k'").fetchone()
        conn.close()
        assert row[0] == 2
        db.close()


# ---------------------------------------------------------------------------
# ResponseCache (two-tier)
# ---------------------------------------------------------------------------


class TestResponseCache:
    def test_memory_hit_no_disk(self):
        c = ResponseCache(max_memory=10, default_ttl=3600)
        e = CacheEntry(content="mem", tool_calls=None, usage=None, model="m", provider="p")
        c.put("k", e)
        got = c.get("k")
        assert got is not None
        assert got.content == "mem"

    def test_memory_miss_disk_hit(self, tmp_path):
        db = str(tmp_path / "cache.db")
        c = ResponseCache(max_memory=10, default_ttl=3600, db_path=db)
        e = CacheEntry(content="tier2", tool_calls=None, usage=None, model="m", provider="p")
        c.put("k", e)
        # Simulate cold memory by creating a new cache pointing at same DB
        c2 = ResponseCache(max_memory=10, default_ttl=3600, db_path=db)
        got = c2.get("k")
        assert got is not None
        assert got.content == "tier2"
        # Promoted to L1
        assert c2.get("k") is not None

    def test_stats(self):
        c = ResponseCache(max_memory=10, default_ttl=3600)
        c.get("missing")
        e = CacheEntry(content="x", tool_calls=None, usage=None, model="m", provider="p")
        c.put("k", e)
        c.get("k")
        s = c.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["hit_rate"] == 0.5
        assert s["memory_entries"] == 1

    def test_configure_ttl(self):
        c = ResponseCache(max_memory=10, default_ttl=3600)
        c.configure_ttl("gpt-4o", 7200)
        assert c.ttl_for("gpt-4o") == 7200
        assert c.ttl_for("other") == 3600

    def test_clear_all(self):
        c = ResponseCache(max_memory=10, default_ttl=3600)
        c.put("a", CacheEntry(content="a", tool_calls=None, usage=None, model="m", provider="p"))
        c.clear()
        assert c.get("a") is None

    def test_disk_graceful_degradation(self, tmp_path):
        # Use a directory path as db_path to force sqlite error on write
        bad_path = str(tmp_path / "not_a_dir" / "cache.db")
        c = ResponseCache(max_memory=10, default_ttl=3600, db_path=bad_path)
        # Should not raise; falls back to memory-only
        e = CacheEntry(content="x", tool_calls=None, usage=None, model="m", provider="p")
        c.put("k", e)
        assert c.get("k") is not None


# ---------------------------------------------------------------------------
# cached_stream_iter
# ---------------------------------------------------------------------------


class TestCachedStreamIter:
    def test_yields_content_and_final_chunk(self):
        e = CacheEntry(content="streamed", tool_calls=None, usage={"prompt_tokens": 1, "completion_tokens": 2}, model="m", provider="p")
        chunks = list(cached_stream_iter(e))
        assert len(chunks) == 2
        assert chunks[0].choices[0].delta.content == "streamed"
        assert chunks[0].from_cache is True
        assert chunks[1].choices[0].finish_reason == "stop"
        assert chunks[1].usage.prompt_tokens == 1

    @pytest.mark.asyncio
    async def test_async_yields_same(self):
        e = CacheEntry(content="async", tool_calls=None, usage=None, model="m", provider="p")
        chunks = []
        async for chunk in cached_stream_iter_async(e):
            chunks.append(chunk)
        assert len(chunks) == 2
        assert chunks[0].choices[0].delta.content == "async"


# ---------------------------------------------------------------------------
# Integration with SDK
# ---------------------------------------------------------------------------


class TestCacheIntegration:
    def test_cache_hit_bypasses_provider_call(self, monkeypatch):
        import zroky
        from unittest.mock import MagicMock, patch

        zroky.shutdown()
        _reset_sdk()
        monkeypatch.setenv("ZROKY_MODE", "local")

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(cache_enabled=True, cache_default_ttl=3600)

        # Pre-populate cache
        fp = zroky.generate_prompt_fingerprint(
            messages=[{"role": "user", "content": "say hi"}],
            tools=None,
            model="gpt-4o",
        )
        key = build_cache_key(fp)
        zroky._response_cache.put(key, CacheEntry(
            content="cached hello",
            tool_calls=None,
            usage={"prompt_tokens": 2, "completion_tokens": 3},
            model="gpt-4o",
            provider="openai",
        ))

        mock_client = MagicMock()
        result = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "say hi"}],
            _client=mock_client,
        )

        # Provider was never called
        mock_client.chat.completions.create.assert_not_called()
        assert result.from_cache is True
        assert result.choices[0].message.content == "cached hello"

        zroky.shutdown()
        _reset_sdk()

    def test_no_cache_kwarg_bypasses_cache(self, monkeypatch):
        import zroky
        from unittest.mock import MagicMock, patch

        zroky.shutdown()
        _reset_sdk()
        monkeypatch.setenv("ZROKY_MODE", "local")

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(cache_enabled=True)

        fp = zroky.generate_prompt_fingerprint(
            messages=[{"role": "user", "content": "force fresh"}],
            tools=None,
            model="gpt-4o",
        )
        key = build_cache_key(fp)
        zroky._response_cache.put(key, CacheEntry(
            content="cached",
            tool_calls=None,
            usage=None,
            model="gpt-4o",
            provider="openai",
        ))

        class FakeResponse:
            class usage:
                prompt_tokens = 5
                completion_tokens = 3
            choices = []

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = FakeResponse()

        result = zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "force fresh"}],
            _client=mock_client,
            no_cache=True,
        )

        # Provider WAS called because no_cache=True
        mock_client.chat.completions.create.assert_called_once()
        assert not hasattr(result, "from_cache")

        zroky.shutdown()
        _reset_sdk()

    def test_cache_disabled_init(self, monkeypatch):
        import zroky
        from unittest.mock import MagicMock, patch

        zroky.shutdown()
        _reset_sdk()
        monkeypatch.setenv("ZROKY_MODE", "local")

        with patch("zroky._internal.queue.LocalWriter"):
            zroky.init(cache_enabled=False)

        class FakeResponse:
            class usage:
                prompt_tokens = 1
                completion_tokens = 1
            choices = []

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = FakeResponse()

        # Call twice with same message
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            _client=mock_client,
        )
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            _client=mock_client,
        )

        # Both hit provider because cache is disabled
        assert mock_client.chat.completions.create.call_count == 2

        zroky.shutdown()
        _reset_sdk()
