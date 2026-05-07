"""Run Postgres RLS tests with deterministic setup.

This utility replaces ad-hoc shell one-liners with a repeatable flow:
1) recreate target DB
2) apply migrations
3) run RLS tests
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _run_subprocess(command: list[str], env: dict[str, str], cwd: str) -> int:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, env=env, check=False)
    return result.returncode


def _recreate_database(admin_url: str, target_db_name: str) -> None:
    if not IDENTIFIER_RE.fullmatch(target_db_name):
        raise ValueError(
            "Invalid target database name. Use letters, numbers, and underscores only."
        )

    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {target_db_name}"))
            connection.execute(text(f"CREATE DATABASE {target_db_name}"))
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recreate a Postgres DB and run RLS tests.")
    parser.add_argument(
        "--admin-url",
        default="postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        help="Admin DB URL used to create/drop target DB.",
    )
    parser.add_argument(
        "--target-db-name",
        default="zroky_rls_ci",
        help="Target database name to recreate for the suite.",
    )
    parser.add_argument(
        "--target-db-url",
        default=None,
        help="Optional full target DB URL. If omitted, generated from localhost + target-db-name.",
    )
    args = parser.parse_args()

    target_db_url = (
        args.target_db_url
        or f"postgresql+psycopg://postgres:postgres@localhost:5432/{args.target_db_name}"
    )

    parsed_target = make_url(target_db_url)
    target_db_name = parsed_target.database or args.target_db_name

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["DATABASE_URL"] = target_db_url
    env["RUN_POSTGRES_RLS_TESTS"] = "1"
    env["PYTHONPATH"] = "."

    print(f"Target DB: {target_db_url}")
    try:
        _recreate_database(args.admin_url, target_db_name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(f"Failed to recreate database: {exc}", file=sys.stderr)
        return 2

    rc = _run_subprocess([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, cwd=repo_root)
    if rc != 0:
        print("Migration step failed.", file=sys.stderr)
        return rc

    rc = _run_subprocess(
        [sys.executable, "-m", "pytest", "-q", "-m", "postgres_rls", "tests/test_postgres_rls.py"],
        env=env,
        cwd=repo_root,
    )
    if rc != 0:
        print("Postgres RLS test step failed.", file=sys.stderr)
        return rc

    print("Postgres RLS suite passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
