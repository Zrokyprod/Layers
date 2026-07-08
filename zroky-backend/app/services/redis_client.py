from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=0.25,
        socket_timeout=1,
    )


def redis_healthcheck() -> bool:
    try:
        return bool(get_redis_client().ping())
    except redis.RedisError:
        return False
