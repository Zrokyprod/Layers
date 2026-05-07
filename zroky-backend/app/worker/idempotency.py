from contextlib import contextmanager

from app.core.config import get_settings
from app.services.redis_client import get_redis_client


@contextmanager
def idempotency_guard(task_key: str):
    settings = get_settings()
    redis_client = get_redis_client()
    lock_key = f"idempotency:{task_key}"

    acquired = bool(
        redis_client.set(lock_key, "1", nx=True, ex=settings.IDEMPOTENCY_TTL_SECONDS)
    )
    completed_without_error = False
    try:
        yield acquired
        completed_without_error = True
    finally:
        if acquired and not completed_without_error:
            redis_client.delete(lock_key)
