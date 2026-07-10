#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
python -m app.worker.healthcheck_server &
healthcheck_pid="$!"
control_pid=""
fetch_pid=""
watchdog_pid=""

cleanup() {
  [ -n "$watchdog_pid" ] && kill "$watchdog_pid" 2>/dev/null || true
  [ -n "$control_pid" ] && kill "$control_pid" 2>/dev/null || true
  [ -n "$fetch_pid" ] && kill "$fetch_pid" 2>/dev/null || true
  kill "$healthcheck_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Keep control-plane work responsive even while a slow customer SOR occupies
# every fetch slot. The fetch worker consumes only verification_fetch; the
# control worker owns all existing diagnosis queues plus verification control
# and sweep queues so this is backwards-compatible with the current service.
celery -A app.worker.celery_app.celery_app worker \
  --hostname="zroky-control@%h" \
  --queues="${CELERY_CONTROL_QUEUES:-diagnosis_fast,diagnosis_pattern,verification_control,verification_sweep}" \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
  --concurrency="${CELERY_CONCURRENCY:-2}" &
control_pid="$!"

celery -A app.worker.celery_app.celery_app worker \
  --hostname="zroky-verification-fetch@%h" \
  --queues="verification_fetch" \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
  --concurrency="${VERIFICATION_FETCH_CONCURRENCY:-1}" &
fetch_pid="$!"

# A failure in either logical lane should restart the container. Without the
# watchdog, a dead control worker could leave the fetch process masking it.
(
  while kill -0 "$control_pid" 2>/dev/null && kill -0 "$fetch_pid" 2>/dev/null; do
    sleep 5
  done
  kill "$control_pid" "$fetch_pid" 2>/dev/null || true
) &
watchdog_pid="$!"

wait "$fetch_pid"
