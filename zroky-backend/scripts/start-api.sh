#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
mkdir -p .data
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
