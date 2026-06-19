"""contracts, releases, and repository runner metadata

Revision ID: 0090_contracts_releases_repository_runner
Revises: 0089_drop_legacy_teams_install
Create Date: 2026-06-19 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0090_contracts_releases_repository_runner"
down_revision = "0089_drop_legacy_teams_install"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    supports_alter_constraints = bind.dialect.name != "sqlite"

    op.create_table(
        "environments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default=sa.text("'custom'")),
        sa.Column("retention_policy_json", sa.Text(), nullable=True),
        sa.Column("capture_policy_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "type IN ('production', 'staging', 'development', 'ci', 'custom')",
            name="ck_environments_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="ux_environments_project_name"),
    )
    op.create_index("ix_environments_project_created", "environments", ["project_id", "created_at"])
    op.create_index("ix_environments_project_type", "environments", ["project_id", "type"])

    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="ux_agents_project_slug"),
    )
    op.create_index("ix_agents_project_created", "agents", ["project_id", "created_at"])

    op.create_table(
        "agent_releases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("environment_id", sa.String(length=36), nullable=False),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column("application_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("model_provider", sa.String(length=120), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("model_parameters_hash", sa.String(length=64), nullable=True),
        sa.Column("tool_schema_hash", sa.String(length=64), nullable=True),
        sa.Column("retrieval_version", sa.String(length=128), nullable=True),
        sa.Column("release_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "agent_id",
            "environment_id",
            "release_fingerprint",
            name="ux_agent_releases_project_agent_env_fp",
        ),
    )
    op.create_index("ix_agent_releases_project_created", "agent_releases", ["project_id", "created_at"])
    op.create_index("ix_agent_releases_project_fingerprint", "agent_releases", ["project_id", "release_fingerprint"])
    op.create_index("ix_agent_releases_project_git_sha", "agent_releases", ["project_id", "git_sha"])

    op.create_table(
        "regression_contracts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_issue_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("active_version_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_regression_contracts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'quarantined', 'retired')",
            name="ck_regression_contracts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="ux_regression_contracts_project_name"),
    )
    op.create_index("ix_regression_contracts_project_created", "regression_contracts", ["project_id", "created_at"])
    op.create_index("ix_regression_contracts_project_status", "regression_contracts", ["project_id", "status"])

    op.create_table(
        "regression_contract_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "spec_version",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'regression_contract_v1'"),
        ),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("fixture_set_id", sa.String(length=36), nullable=True),
        sa.Column("baseline_release_id", sa.String(length=36), nullable=True),
        sa.Column(
            "trial_policy_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{\"required_trials\":10,\"critical_violation_tolerance\":0}'"),
        ),
        sa.Column("evaluator_bundle_version", sa.String(length=64), nullable=False, server_default=sa.text("'default-v1'")),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["baseline_release_id"], ["agent_releases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["regression_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fixture_set_id"], ["golden_sets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "version_number", name="ux_regression_contract_versions_contract_version"),
    )
    op.create_index(
        "ix_regression_contract_versions_project_created",
        "regression_contract_versions",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_regression_contract_versions_project_fixture",
        "regression_contract_versions",
        ["project_id", "fixture_set_id"],
    )

    op.create_table(
        "regression_contract_run_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("replay_run_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("contract_version_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_release_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trial_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("required_trials", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("critical_violation_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("evaluator_bundle_version", sa.String(length=64), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'not_verified', 'error')",
            name="ck_regression_contract_run_results_status",
        ),
        sa.ForeignKeyConstraint(["candidate_release_id"], ["agent_releases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["regression_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_version_id"], ["regression_contract_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replay_run_id"], ["replay_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("replay_run_id", "contract_version_id", name="ux_regression_contract_run_results_run_version"),
    )
    op.create_index(
        "ix_regression_contract_run_results_project_run",
        "regression_contract_run_results",
        ["project_id", "replay_run_id"],
    )
    op.create_index(
        "ix_regression_contract_run_results_project_version",
        "regression_contract_run_results",
        ["project_id", "contract_version_id"],
    )

    for table_name in ("calls", "trace_spans"):
        op.add_column(table_name, sa.Column("environment_id", sa.String(length=36), nullable=True))
        op.add_column(table_name, sa.Column("agent_id", sa.String(length=36), nullable=True))
        op.add_column(table_name, sa.Column("agent_release_id", sa.String(length=36), nullable=True))
        if supports_alter_constraints:
            op.create_foreign_key(
                f"fk_{table_name}_environment_id_environments",
                table_name,
                "environments",
                ["environment_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_foreign_key(
                f"fk_{table_name}_agent_id_agents",
                table_name,
                "agents",
                ["agent_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_foreign_key(
                f"fk_{table_name}_agent_release_id_agent_releases",
                table_name,
                "agent_releases",
                ["agent_release_id"],
                ["id"],
                ondelete="SET NULL",
            )

    op.create_index("ix_calls_project_environment_created", "calls", ["project_id", "environment_id", "created_at"])
    op.create_index("ix_calls_project_agent_release_created", "calls", ["project_id", "agent_release_id", "created_at"])
    op.create_index("ix_trace_spans_project_environment", "trace_spans", ["project_id", "environment_id"])
    op.create_index("ix_trace_spans_project_agent_release", "trace_spans", ["project_id", "agent_release_id"])

    op.add_column("replay_runs", sa.Column("repository", sa.String(length=255), nullable=True))
    op.add_column("replay_runs", sa.Column("pull_request_number", sa.Integer(), nullable=True))
    op.add_column("replay_runs", sa.Column("head_sha", sa.String(length=64), nullable=True))
    op.add_column("replay_runs", sa.Column("base_sha", sa.String(length=64), nullable=True))
    op.add_column("replay_runs", sa.Column("workflow_run_id", sa.String(length=64), nullable=True))
    op.add_column("replay_runs", sa.Column("workflow_attempt", sa.Integer(), nullable=True))
    op.add_column("replay_runs", sa.Column("contract_version_ids_json", sa.Text(), nullable=True))
    op.add_column("replay_runs", sa.Column("runner_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("replay_runs", sa.Column("run_token_hash", sa.String(length=64), nullable=True))
    op.add_column("replay_runs", sa.Column("run_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("replay_runs", sa.Column("superseded_by_run_id", sa.String(length=36), nullable=True))
    op.add_column("replay_runs", sa.Column("candidate_release_id", sa.String(length=36), nullable=True))
    if supports_alter_constraints:
        op.create_foreign_key(
            "fk_replay_runs_candidate_release_id_agent_releases",
            "replay_runs",
            "agent_releases",
            ["candidate_release_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_replay_runs_project_head_sha", "replay_runs", ["project_id", "head_sha"])
    op.create_index(
        "ix_replay_runs_project_pr_created",
        "replay_runs",
        ["project_id", "repository", "pull_request_number", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    supports_alter_constraints = bind.dialect.name != "sqlite"

    op.drop_index("ix_replay_runs_project_pr_created", table_name="replay_runs")
    op.drop_index("ix_replay_runs_project_head_sha", table_name="replay_runs")
    if supports_alter_constraints:
        op.drop_constraint("fk_replay_runs_candidate_release_id_agent_releases", "replay_runs", type_="foreignkey")
    for column in (
        "candidate_release_id",
        "superseded_by_run_id",
        "run_token_expires_at",
        "run_token_hash",
        "runner_required",
        "contract_version_ids_json",
        "workflow_attempt",
        "workflow_run_id",
        "base_sha",
        "head_sha",
        "pull_request_number",
        "repository",
    ):
        op.drop_column("replay_runs", column)

    op.drop_index("ix_trace_spans_project_agent_release", table_name="trace_spans")
    op.drop_index("ix_trace_spans_project_environment", table_name="trace_spans")
    op.drop_index("ix_calls_project_agent_release_created", table_name="calls")
    op.drop_index("ix_calls_project_environment_created", table_name="calls")
    for table_name in ("trace_spans", "calls"):
        if supports_alter_constraints:
            op.drop_constraint(f"fk_{table_name}_agent_release_id_agent_releases", table_name, type_="foreignkey")
            op.drop_constraint(f"fk_{table_name}_agent_id_agents", table_name, type_="foreignkey")
            op.drop_constraint(f"fk_{table_name}_environment_id_environments", table_name, type_="foreignkey")
        op.drop_column(table_name, "agent_release_id")
        op.drop_column(table_name, "agent_id")
        op.drop_column(table_name, "environment_id")

    op.drop_index("ix_regression_contract_run_results_project_version", table_name="regression_contract_run_results")
    op.drop_index("ix_regression_contract_run_results_project_run", table_name="regression_contract_run_results")
    op.drop_table("regression_contract_run_results")

    op.drop_index("ix_regression_contract_versions_project_fixture", table_name="regression_contract_versions")
    op.drop_index("ix_regression_contract_versions_project_created", table_name="regression_contract_versions")
    op.drop_table("regression_contract_versions")

    op.drop_index("ix_regression_contracts_project_status", table_name="regression_contracts")
    op.drop_index("ix_regression_contracts_project_created", table_name="regression_contracts")
    op.drop_table("regression_contracts")

    op.drop_index("ix_agent_releases_project_git_sha", table_name="agent_releases")
    op.drop_index("ix_agent_releases_project_fingerprint", table_name="agent_releases")
    op.drop_index("ix_agent_releases_project_created", table_name="agent_releases")
    op.drop_table("agent_releases")

    op.drop_index("ix_agents_project_created", table_name="agents")
    op.drop_table("agents")

    op.drop_index("ix_environments_project_type", table_name="environments")
    op.drop_index("ix_environments_project_created", table_name="environments")
    op.drop_table("environments")
