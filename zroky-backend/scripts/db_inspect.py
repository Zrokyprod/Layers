"""Safe database inspection utility for local troubleshooting.

This script avoids shell-quoting issues from ad-hoc one-liners by keeping SQL
inside Python and using parameterized execution paths.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


def _resolve_database_url(cli_database_url: str | None) -> str:
    if cli_database_url:
        return cli_database_url
    return get_settings().DATABASE_URL


def _redact_url(database_url: str) -> str:
    try:
        parsed: URL = make_url(database_url)
    except Exception:
        return database_url
    if parsed.password is None:
        return parsed.render_as_string(hide_password=False)
    return parsed.render_as_string(hide_password=True)


def _print_rows(title: str, rows: Sequence[tuple]) -> None:
    print(f"\n[{title}]")
    if not rows:
        print("(none)")
        return
    for row in rows:
        print(" - " + ", ".join(str(item) for item in row))


def run(database_url: str) -> int:
    print(f"Database: {_redact_url(database_url)}")

    try:
        engine = create_engine(database_url, future=True)
    except Exception as exc:
        print(f"Failed to create engine: {exc}", file=sys.stderr)
        return 2

    try:
        with engine.connect() as connection:
            backend = connection.dialect.name
            print(f"Backend: {backend}")

            if backend == "postgresql":
                tables = connection.execute(
                    text(
                        """
                        SELECT table_schema, table_name
                        FROM information_schema.tables
                        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                        ORDER BY table_schema, table_name
                        """
                    )
                ).fetchall()
            else:
                tables = connection.execute(
                    text(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                        ORDER BY name
                        """
                    )
                ).fetchall()

            version_exists = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar_one_or_none() if backend == "postgresql" else None

            if backend == "postgresql":
                if version_exists:
                    versions = connection.execute(
                        text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
                    ).fetchall()
                else:
                    versions = []
            else:
                # SQLite: table may not exist, so query safely.
                has_alembic = connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM sqlite_master
                        WHERE type = 'table' AND name = 'alembic_version'
                        """
                    )
                ).scalar_one()
                versions = (
                    connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).fetchall()
                    if has_alembic
                    else []
                )

            _print_rows("User Tables", tables)
            _print_rows("Alembic Versions", versions)

    except SQLAlchemyError as exc:
        print(f"Database query failed: {exc}", file=sys.stderr)
        return 3
    finally:
        engine.dispose()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect DB tables and Alembic version safely.")
    parser.add_argument("--database-url", dest="database_url", default=None)
    args = parser.parse_args()
    return run(_resolve_database_url(args.database_url))


if __name__ == "__main__":
    raise SystemExit(main())
