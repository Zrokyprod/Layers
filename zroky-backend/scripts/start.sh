#!/usr/bin/env sh
set -e

case "${ZROKY_PROCESS_TYPE:-api}" in
  api)
    exec sh scripts/start-api.sh
    ;;
  worker)
    exec sh scripts/start-worker.sh
    ;;
  beat)
    exec sh scripts/start-beat.sh
    ;;
  *)
    echo "Unsupported ZROKY_PROCESS_TYPE: ${ZROKY_PROCESS_TYPE}" >&2
    exit 64
    ;;
esac
