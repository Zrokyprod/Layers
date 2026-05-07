#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
celery -A app.worker.celery_app.celery_app beat \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}"
