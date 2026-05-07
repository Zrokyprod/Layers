#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
celery -A app.worker.celery_app.celery_app worker \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
  --concurrency="${CELERY_CONCURRENCY:-2}"
