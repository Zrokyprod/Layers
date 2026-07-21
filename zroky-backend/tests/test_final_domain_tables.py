from __future__ import annotations

from pathlib import Path

from app.db.base import Base


FINAL_DOMAIN_TABLES = (
    "final_workflow_intents",
    "final_policy_decisions",
    "final_assurance_packs",
    "final_observations",
    "final_outcome_graphs",
    "final_outcome_incidents",
    "final_recovery_plans",
    "final_evidence_bundles",
)

FINAL_OUTBOX_TABLES = ("final_domain_outbox_jobs",)
FINAL_APPROVAL_TABLES = ("final_approval_requirements",)
FINAL_RUN_TABLES = ("final_agent_runs",)
FINAL_CAPABILITY_TABLES = ("final_connector_capability_drafts",)


def test_final_domain_models_are_project_and_environment_scoped() -> None:
    import app.db.models  # noqa: F401

    for table_name in FINAL_DOMAIN_TABLES + FINAL_OUTBOX_TABLES + FINAL_APPROVAL_TABLES + FINAL_RUN_TABLES + FINAL_CAPABILITY_TABLES:
        table = Base.metadata.tables[table_name]
        assert "project_id" in table.c
        assert "environment" in table.c
        assert table.c.project_id.nullable is False
        assert table.c.environment.nullable is False


def test_final_domain_migration_forces_project_rls() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0123_create_final_domain_tables.py"
    ).read_text(encoding="utf-8")

    for table_name in FINAL_DOMAIN_TABLES:
        assert f'"{table_name}"' in migration

    assert 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY' in migration
    assert "WITH CHECK (project_id = current_setting('app.current_tenant_id', true))" in migration


def test_final_domain_outbox_supports_required_jobs() -> None:
    import app.db.models  # noqa: F401

    table = Base.metadata.tables["final_domain_outbox_jobs"]
    for column_name in (
        "job_type",
        "aggregate_type",
        "aggregate_id",
        "idempotency_key",
        "claimed_by",
        "lease_expires_at",
        "available_at",
    ):
        assert column_name in table.c

    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0124_create_final_domain_outbox_jobs.py"
    ).read_text(encoding="utf-8")
    for job_type in ("verify_outcome", "plan_recovery", "execute_recovery", "generate_evidence"):
        assert job_type in migration
    assert 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY' in migration


def test_final_approval_requirements_are_digest_bound_and_rls_scoped() -> None:
    import app.db.models  # noqa: F401

    table = Base.metadata.tables["final_approval_requirements"]
    for column_name in ("intent_id", "policy_decision_id", "required_role", "binding_digest", "status"):
        assert column_name in table.c

    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0125_create_final_approval_requirements.py"
    ).read_text(encoding="utf-8")
    assert "final_approval_requirements" in migration
    assert "binding_digest" in migration
    assert 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY' in migration


def test_final_agent_runs_are_external_declarations_and_rls_scoped() -> None:
    import app.db.models  # noqa: F401

    table = Base.metadata.tables["final_agent_runs"]
    for column_name in ("external_run_id", "intent_id", "workflow_key", "agent_ref", "run_digest", "run_json"):
        assert column_name in table.c

    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0126_create_final_agent_runs.py"
    ).read_text(encoding="utf-8")
    assert "final_agent_runs" in migration
    assert "execution" not in migration.lower()
    assert 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY' in migration


def test_final_capability_drafts_are_not_recovery_trusted() -> None:
    import app.db.models  # noqa: F401

    table = Base.metadata.tables["final_connector_capability_drafts"]
    for column_name in ("source_kind", "capability_key", "schema_digest", "schema_json", "trusted_for_recovery"):
        assert column_name in table.c

    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0127_create_final_connector_capability_drafts.py"
    ).read_text(encoding="utf-8")
    assert "trusted_for_recovery = false" in migration
    assert 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY' in migration
