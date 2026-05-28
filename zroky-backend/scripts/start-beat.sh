#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
python -m app.worker.healthcheck_server &
healthcheck_pid="$!"
trap 'kill "$healthcheck_pid" 2>/dev/null || true' EXIT

celery -A app.worker.celery_app.celery_app beat \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}"
