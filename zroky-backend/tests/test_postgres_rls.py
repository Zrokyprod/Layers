import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


pytestmark = pytest.mark.postgres_rls

RLS_TEST_ROLE = "zroky_rls_tester"
RLS_TEST_ROLE_PASSWORD = "zroky_rls_tester"


def _apply_migrations(database_url: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "Failed to apply migrations for postgres RLS tests. "
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def _bootstrap_rls_table(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.diagnosis_jobs (
                id VARCHAR(36) PRIMARY KEY,
                tenant_id VARCHAR(64) NOT NULL,
                diagnosis_id VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NULL,
                error_message TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_diagnosis_jobs_tenant_diagnosis
            ON public.diagnosis_jobs (tenant_id, diagnosis_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_diagnosis_jobs_tenant_status
            ON public.diagnosis_jobs (tenant_id, status)
            """
        )
    )
    connection.execute(text("ALTER TABLE public.diagnosis_jobs ENABLE ROW LEVEL SECURITY"))
    connection.execute(text("ALTER TABLE public.diagnosis_jobs FORCE ROW LEVEL SECURITY"))
    connection.execute(text("DROP POLICY IF EXISTS diagnosis_jobs_tenant_isolation ON public.diagnosis_jobs"))
    connection.execute(
        text(
            """
            CREATE POLICY diagnosis_jobs_tenant_isolation
            ON public.diagnosis_jobs
            USING (tenant_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))
            """
        )
    )


@pytest.fixture(scope="module")
def postgres_engine():
    if os.getenv("RUN_POSTGRES_RLS_TESTS") != "1":
        pytest.skip("Postgres RLS tests are disabled. Set RUN_POSTGRES_RLS_TESTS=1 to enable.")

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("Postgres RLS tests require DATABASE_URL pointing to PostgreSQL.")

    _apply_migrations(database_url)

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        _bootstrap_rls_table(connection)

        connection.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RLS_TEST_ROLE}') THEN
                        CREATE ROLE {RLS_TEST_ROLE}
                        LOGIN
                        PASSWORD '{RLS_TEST_ROLE_PASSWORD}'
                        NOSUPERUSER
                        NOCREATEDB
                        NOCREATEROLE
                        NOINHERIT;
                    END IF;
                END
                $$;
                """
            )
        )
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.diagnosis_jobs TO {RLS_TEST_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.project_alerts TO {RLS_TEST_ROLE}"))

    try:
        yield engine
    finally:
        engine.dispose()


def _set_tenant(connection, tenant_id: str) -> None:
    connection.execute(text("SET LOCAL search_path TO public"))
    connection.execute(text(f"SET LOCAL ROLE {RLS_TEST_ROLE}"))
    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def test_rls_blocks_cross_tenant_insert(postgres_engine) -> None:
    tenant_allowed = f"proj_rls_allow_{uuid4().hex[:8]}"
    tenant_denied = f"proj_rls_deny_{uuid4().hex[:8]}"

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_allowed)
        connection.execute(
            text(
                """
                INSERT INTO public.diagnosis_jobs (id, tenant_id, diagnosis_id, status, payload_json)
                VALUES (:id, :tenant_id, :diagnosis_id, 'queued', '{}'::text)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_allowed,
                "diagnosis_id": f"diag_rls_allow_{uuid4().hex[:8]}",
            },
        )

    with pytest.raises(DBAPIError):
        with postgres_engine.begin() as connection:
            _set_tenant(connection, tenant_allowed)
            connection.execute(
                text(
                    """
                    INSERT INTO public.diagnosis_jobs (id, tenant_id, diagnosis_id, status, payload_json)
                    VALUES (:id, :tenant_id, :diagnosis_id, 'queued', '{}'::text)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "tenant_id": tenant_denied,
                    "diagnosis_id": f"diag_rls_deny_{uuid4().hex[:8]}",
                },
            )


def test_rls_filters_reads_by_current_tenant(postgres_engine) -> None:
    tenant_a = f"proj_rls_a_{uuid4().hex[:8]}"
    tenant_b = f"proj_rls_b_{uuid4().hex[:8]}"
    diagnosis_a = f"diag_rls_a_{uuid4().hex[:8]}"
    diagnosis_b = f"diag_rls_b_{uuid4().hex[:8]}"

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_a)
        connection.execute(
            text(
                """
                INSERT INTO public.diagnosis_jobs (id, tenant_id, diagnosis_id, status, payload_json)
                VALUES (:id, :tenant_id, :diagnosis_id, 'queued', '{}'::text)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_a,
                "diagnosis_id": diagnosis_a,
            },
        )

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_b)
        connection.execute(
            text(
                """
                INSERT INTO public.diagnosis_jobs (id, tenant_id, diagnosis_id, status, payload_json)
                VALUES (:id, :tenant_id, :diagnosis_id, 'queued', '{}'::text)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_b,
                "diagnosis_id": diagnosis_b,
            },
        )

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_a)
        rows = connection.execute(
            text(
                """
                SELECT diagnosis_id
                FROM public.diagnosis_jobs
                WHERE diagnosis_id IN (:diag_a, :diag_b)
                ORDER BY diagnosis_id
                """
            ),
            {
                "diag_a": diagnosis_a,
                "diag_b": diagnosis_b,
            },
        ).scalars().all()

    assert rows == [diagnosis_a]

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_b)
        rows = connection.execute(
            text(
                """
                SELECT diagnosis_id
                FROM public.diagnosis_jobs
                WHERE diagnosis_id IN (:diag_a, :diag_b)
                ORDER BY diagnosis_id
                """
            ),
            {
                "diag_a": diagnosis_a,
                "diag_b": diagnosis_b,
            },
        ).scalars().all()

    assert rows == [diagnosis_b]


def test_rls_blocks_cross_tenant_project_alert_insert(postgres_engine) -> None:
    tenant_allowed = f"proj_alert_allow_{uuid4().hex[:8]}"
    tenant_denied = f"proj_alert_deny_{uuid4().hex[:8]}"

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_allowed)
        connection.execute(
            text(
                """
                INSERT INTO public.project_alerts (id, tenant_id, diagnosis_id, category, title)
                VALUES (:id, :tenant_id, :diagnosis_id, :category, :title)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_allowed,
                "diagnosis_id": f"diag_alert_allow_{uuid4().hex[:8]}",
                "category": "RATE_LIMIT",
                "title": "Allowed tenant alert",
            },
        )

    with pytest.raises(DBAPIError):
        with postgres_engine.begin() as connection:
            _set_tenant(connection, tenant_allowed)
            connection.execute(
                text(
                    """
                    INSERT INTO public.project_alerts (id, tenant_id, diagnosis_id, category, title)
                    VALUES (:id, :tenant_id, :diagnosis_id, :category, :title)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "tenant_id": tenant_denied,
                    "diagnosis_id": f"diag_alert_deny_{uuid4().hex[:8]}",
                    "category": "AUTH_FAILURE",
                    "title": "Denied tenant alert",
                },
            )


def test_rls_filters_project_alert_reads_by_current_tenant(postgres_engine) -> None:
    tenant_a = f"proj_alert_a_{uuid4().hex[:8]}"
    tenant_b = f"proj_alert_b_{uuid4().hex[:8]}"
    diagnosis_a = f"diag_alert_a_{uuid4().hex[:8]}"
    diagnosis_b = f"diag_alert_b_{uuid4().hex[:8]}"

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_a)
        connection.execute(
            text(
                """
                INSERT INTO public.project_alerts (id, tenant_id, diagnosis_id, category, title)
                VALUES (:id, :tenant_id, :diagnosis_id, :category, :title)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_a,
                "diagnosis_id": diagnosis_a,
                "category": "TOKEN_OVERFLOW",
                "title": "Tenant A alert",
            },
        )

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_b)
        connection.execute(
            text(
                """
                INSERT INTO public.project_alerts (id, tenant_id, diagnosis_id, category, title)
                VALUES (:id, :tenant_id, :diagnosis_id, :category, :title)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_b,
                "diagnosis_id": diagnosis_b,
                "category": "COST_SPIKE",
                "title": "Tenant B alert",
            },
        )

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_a)
        rows = connection.execute(
            text(
                """
                SELECT diagnosis_id
                FROM public.project_alerts
                WHERE diagnosis_id IN (:diag_a, :diag_b)
                ORDER BY diagnosis_id
                """
            ),
            {
                "diag_a": diagnosis_a,
                "diag_b": diagnosis_b,
            },
        ).scalars().all()

    assert rows == [diagnosis_a]

    with postgres_engine.begin() as connection:
        _set_tenant(connection, tenant_b)
        rows = connection.execute(
            text(
                """
                SELECT diagnosis_id
                FROM public.project_alerts
                WHERE diagnosis_id IN (:diag_a, :diag_b)
                ORDER BY diagnosis_id
                """
            ),
            {
                "diag_a": diagnosis_a,
                "diag_b": diagnosis_b,
            },
        ).scalars().all()

    assert rows == [diagnosis_b]
