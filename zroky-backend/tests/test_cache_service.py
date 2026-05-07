"""Tests for unified cache service with Redis and in-process backends."""
import os


os.environ["TESTING"] = "true"

from app.services.cache_service import CacheService, cached, clear_cache, get_cache


def test_get_set_round_trip():
    cache = CacheService("test")
    cache.set("key1", "value1", ttl_seconds=60)
    assert cache.get("key1") == "value1"


def test_get_missing_returns_none():
    cache = CacheService("test")
    assert cache.get("nonexistent_key_123") is None


def test_delete_removes_value():
    cache = CacheService("test")
    cache.set("delete_me", "data", ttl_seconds=60)
    assert cache.get("delete_me") == "data"
    cache.delete("delete_me")
    assert cache.get("delete_me") is None


def test_ttl_on_expired_key():
    cache = CacheService("test")
    cache.set("ttl_key", "data", ttl_seconds=1)
    assert cache.exists("ttl_key")
    # TTL is returned as integer seconds
    assert cache.ttl("ttl_key") >= 0


def test_exists_on_missing():
    cache = CacheService("test")
    assert not cache.exists("no_such_key")


def test_json_round_trip():
    cache = CacheService("test")
    data = {"nested": {"value": 42}, "list": [1, 2, 3]}
    cache.set_json("json_key", data, ttl_seconds=60)
    assert cache.get_json("json_key") == data


def test_json_invalid_returns_none():
    cache = CacheService("test")
    cache.set("bad_json", "not-json", ttl_seconds=60)
    assert cache.get_json("bad_json") is None


def test_incr_creates_key():
    cache = CacheService("test")
    result = cache.incr("counter", 1, ttl_seconds=60)
    assert result == 1


def test_incr_increments():
    cache = CacheService("test")
    cache.incr("counter2", 5, ttl_seconds=60)
    result = cache.incr("counter2", 3, ttl_seconds=60)
    assert result == 8


def test_namespace_isolation():
    cache_a = CacheService("ns_a")
    cache_b = CacheService("ns_b")
    cache_a.set("shared_key", "A", ttl_seconds=60)
    cache_b.set("shared_key", "B", ttl_seconds=60)
    assert cache_a.get("shared_key") == "A"
    assert cache_b.get("shared_key") == "B"


def test_mget_and_mset():
    cache = CacheService("test")
    cache.mset({"k1": "v1", "k2": "v2"}, ttl_seconds=60)
    results = cache.mget(["k1", "k2", "k3"])
    assert results == ["v1", "v2", None]


def test_mset_json():
    cache = CacheService("test")
    cache.mset_json({"jk1": {"a": 1}, "jk2": {"b": 2}}, ttl_seconds=60)
    results = cache.mget_json(["jk1", "jk2", "jk3"])
    assert results == [{"a": 1}, {"b": 2}, None]


def test_cached_decorator_hits_cache():
    call_count = 0

    @cached(namespace="decorator_test", ttl_seconds=60)
    def compute(x: int):
        nonlocal call_count
        call_count += 1
        return x * 2

    clear_cache("decorator_test")
    compute(5)
    assert call_count == 1
    compute(5)
    assert call_count == 1  # second call should hit cache


def test_cached_decorator_different_args():
    call_count = 0

    @cached(namespace="decorator_test2", ttl_seconds=60)
    def compute(x: int):
        nonlocal call_count
        call_count += 1
        return x * 2

    clear_cache("decorator_test2")
    compute(5)
    compute(7)
    assert call_count == 2  # different args, so two calls


def test_cached_decorator_none_skipped_by_default():
    call_count = 0

    @cached(namespace="decorator_test3", ttl_seconds=60)
    def maybe_none(x: int):
        nonlocal call_count
        call_count += 1
        return None if x < 0 else x

    clear_cache("decorator_test3")
    maybe_none(-5)
    assert call_count == 1
    maybe_none(-5)
    assert call_count == 2  # None not cached


def test_factory_returns_same_instance_type():
    cache = get_cache("factory")
    assert isinstance(cache, CacheService)
