#!/usr/bin/env sh
set -e

python -c "from app.core.config import get_settings, validate_runtime_settings; validate_runtime_settings(get_settings())"
mkdir -p .data
alembic upgrade head

python - <<'PYEOF'
import os
from sqlalchemy import create_engine, text
from sqlalchemy import pool

raw_url = os.environ["DATABASE_URL"]
print("[DIAG] raw DATABASE_URL prefix =", raw_url[:40])

# Use same URL alembic uses (no modification)
eng_alembic = create_engine(raw_url, poolclass=pool.NullPool)
with eng_alembic.connect() as c:
    db = c.execute(text("SELECT current_database(), current_schema()")).fetchone()
    print("[DIAG] alembic-url db/schema =", db)
    sp = c.execute(text("SHOW search_path")).fetchone()
    print("[DIAG] alembic-url search_path =", sp)
    rows = c.execute(text("SELECT schemaname,tablename FROM pg_tables WHERE tablename IN ('users','alembic_version')")).fetchall()
    print("[DIAG] alembic-url key tables =", rows)
    # try creating a test table to see if DDL works
    try:
        c.execute(text("CREATE TABLE IF NOT EXISTS _diag_test (id int)"))
        c.commit()
        rows2 = c.execute(text("SELECT tablename FROM pg_tables WHERE tablename='_diag_test'")).fetchall()
        print("[DIAG] _diag_test created =", rows2)
        c.execute(text("DROP TABLE IF EXISTS _diag_test"))
        c.commit()
    except Exception as e:
        print("[DIAG] DDL test failed:", e)

# Use modified URL (app uses)
from app.db.session import engine as app_engine
with app_engine.connect() as c:
    db2 = c.execute(text("SELECT current_database(), current_schema()")).fetchone()
    print("[DIAG] app-url db/schema =", db2)
    sp2 = c.execute(text("SHOW search_path")).fetchone()
    print("[DIAG] app-url search_path =", sp2)
PYEOF

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
