from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.base import Base

# Import models so they are registered on Base metadata.
from app.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()


def ensure_sqlite_parent_dir(db_url: str) -> None:
    try:
        parsed = make_url(db_url)
    except Exception:
        return

    if parsed.get_backend_name() != "sqlite":
        return

    database = parsed.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return

    Path(database).parent.mkdir(parents=True, exist_ok=True)


resolved_database_url = (
    os.getenv("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
    or settings.DATABASE_URL
)

ensure_sqlite_parent_dir(resolved_database_url)
config.set_main_option("sqlalchemy.url", resolved_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Use begin() so the outer context manager COMMITS on normal exit.
    # connect() in SQLAlchemy 2.0 rolls back uncommitted work on exit,
    # which silently discarded all migration DDL.
    with connectable.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET search_path TO public"))

            # Long descriptive revision IDs can exceed Alembic's default VARCHAR(32).
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS alembic_version (
                        version_num VARCHAR(255) NOT NULL PRIMARY KEY
                    )
                    """
                )
            )
            connection.execute(
                text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
            )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
