#!/usr/bin/env sh
set -e

echo "[startup] step 1: validating settings..."
python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())" && echo "[startup] settings OK" || { echo "[startup] SETTINGS VALIDATION FAILED"; exit 1; }
echo "[startup] step 2: mkdir .data"
mkdir -p .data
echo "[startup] step 3: alembic upgrade head"
alembic upgrade head
echo "[startup] step 4: starting uvicorn on port ${PORT:-8000}"
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
