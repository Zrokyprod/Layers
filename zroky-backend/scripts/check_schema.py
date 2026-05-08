"""One-off diagnostic: print search_path and where the users table lives."""
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as c:
    sp = c.execute(text("SHOW search_path")).fetchone()
    print("search_path:", sp)

    rows = c.execute(
        text("SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'users'")
    ).fetchall()
    print("users table location:", rows)

    all_schemas = c.execute(
        text("SELECT DISTINCT schemaname FROM pg_tables ORDER BY schemaname")
    ).fetchall()
    print("all schemas:", all_schemas)
