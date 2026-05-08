#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
mkdir -p .data
alembic upgrade head

python - <<'PYEOF'
from app.db.session import engine
from sqlalchemy import text
with engine.connect() as c:
    sp = c.execute(text("SHOW search_path")).fetchone()
    print("[DIAG] search_path =", sp)
    rows = c.execute(text("SELECT schemaname, tablename FROM pg_tables WHERE tablename IN ('users','alembic_version') ORDER BY schemaname, tablename")).fetchall()
    print("[DIAG] key tables =", rows)
    all_schemas = c.execute(text("SELECT DISTINCT schemaname FROM pg_tables ORDER BY schemaname")).fetchall()
    print("[DIAG] all schemas =", all_schemas)
PYEOF

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
