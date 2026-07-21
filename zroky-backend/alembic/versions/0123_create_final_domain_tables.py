"""create final domain tables

Revision ID: 0123_create_final_domain_tables
Revises: 0122_mcp_interception
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0123_create_final_domain_tables"
down_revision = "0122_mcp_interception"
branch_labels = None
depends_on = None


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


def upgrade() -> None:
    op.create_table(
        "final_workflow_intents",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("agent_ref", sa.String(length=255), nullable=True),
        sa.Column("intent_digest", sa.String(length=80), nullable=False),
        sa.Column("intent_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'received'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('received','policy_denied','approval_required','authorized','expired')",
            name="ck_final_workflow_intents_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "idempotency_key", name="ux_final_intents_scope_idempotency"),
    )
    op.create_index(
        "ix_final_intents_scope_status",
        "final_workflow_intents",
        ["project_id", "environment", "status", "created_at"],
    )

    op.create_table(
        "final_policy_decisions",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("policy_digest", sa.String(length=80), nullable=False),
        sa.Column("decision_json", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('allow','deny','approval_required','observe_only')",
            name="ck_final_policy_decisions_decision",
        ),
        sa.ForeignKeyConstraint(["intent_id"], ["final_workflow_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_final_policy_scope_intent", "final_policy_decisions", ["project_id", "environment", "intent_id"])

    op.create_table(
        "final_assurance_packs",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("workflow_key", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("pack_digest", sa.String(length=80), nullable=False),
        sa.Column("pack_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_final_assurance_packs_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "workflow_key", "version", name="ux_final_assurance_packs_scope_version"),
    )
    op.create_index("ix_final_assurance_packs_scope_status", "final_assurance_packs", ["project_id", "environment", "status"])

    op.create_table(
        "final_observations",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("intent_id", sa.String(length=36), nullable=True),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("observed_object_ref", sa.String(length=255), nullable=False),
        sa.Column("observation_digest", sa.String(length=80), nullable=False),
        sa.Column("observation_json", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["intent_id"], ["final_workflow_intents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_final_observations_scope_object", "final_observations", ["project_id", "environment", "observed_object_ref", "observed_at"])
    op.create_index("ix_final_observations_scope_intent", "final_observations", ["project_id", "environment", "intent_id"])

    op.create_table(
        "final_outcome_graphs",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("graph_digest", sa.String(length=80), nullable=False),
        sa.Column("graph_json", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "verification_status IN ('pending','verified','failed','inconclusive')",
            name="ck_final_outcome_graphs_verification_status",
        ),
        sa.ForeignKeyConstraint(["intent_id"], ["final_workflow_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_final_outcome_graphs_scope_status", "final_outcome_graphs", ["project_id", "environment", "verification_status", "created_at"])

    op.create_table(
        "final_outcome_incidents",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("outcome_graph_id", sa.String(length=36), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'open'"), nullable=False),
        sa.Column("incident_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_final_outcome_incidents_severity"),
        sa.CheckConstraint("status IN ('open','recovering','resolved','unresolved')", name="ck_final_outcome_incidents_status"),
        sa.ForeignKeyConstraint(["outcome_graph_id"], ["final_outcome_graphs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_final_incidents_scope_status", "final_outcome_incidents", ["project_id", "environment", "status", "created_at"])

    op.create_table(
        "final_recovery_plans",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("plan_digest", sa.String(length=80), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("approval_status", sa.String(length=32), server_default=sa.text("'not_required'"), nullable=False),
        sa.Column("execution_status", sa.String(length=32), server_default=sa.text("'not_started'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "approval_status IN ('not_required','required','approved','denied')",
            name="ck_final_recovery_plans_approval_status",
        ),
        sa.CheckConstraint(
            "execution_status IN ('not_started','dispatched','succeeded','failed','ambiguous')",
            name="ck_final_recovery_plans_execution_status",
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["final_outcome_incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_final_recovery_plans_scope_status", "final_recovery_plans", ["project_id", "environment", "execution_status", "created_at"])

    op.create_table(
        "final_evidence_bundles",
        _id_column(),
        _project_column(),
        _environment_column(),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("bundle_digest", sa.String(length=80), nullable=False),
        sa.Column("bundle_json", sa.Text(), nullable=False),
        sa.Column("signature_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "environment", "bundle_digest", name="ux_final_evidence_bundles_scope_digest"),
    )
    op.create_index("ix_final_evidence_bundles_scope_subject", "final_evidence_bundles", ["project_id", "environment", "subject_type", "subject_id"])

    for table_name in FINAL_DOMAIN_TABLES:
        _enable_project_rls(table_name)


def downgrade() -> None:
    for table_name in reversed(FINAL_DOMAIN_TABLES):
        _disable_project_rls(table_name)

    op.drop_index("ix_final_evidence_bundles_scope_subject", table_name="final_evidence_bundles")
    op.drop_table("final_evidence_bundles")
    op.drop_index("ix_final_recovery_plans_scope_status", table_name="final_recovery_plans")
    op.drop_table("final_recovery_plans")
    op.drop_index("ix_final_incidents_scope_status", table_name="final_outcome_incidents")
    op.drop_table("final_outcome_incidents")
    op.drop_index("ix_final_outcome_graphs_scope_status", table_name="final_outcome_graphs")
    op.drop_table("final_outcome_graphs")
    op.drop_index("ix_final_observations_scope_intent", table_name="final_observations")
    op.drop_index("ix_final_observations_scope_object", table_name="final_observations")
    op.drop_table("final_observations")
    op.drop_index("ix_final_assurance_packs_scope_status", table_name="final_assurance_packs")
    op.drop_table("final_assurance_packs")
    op.drop_index("ix_final_policy_scope_intent", table_name="final_policy_decisions")
    op.drop_table("final_policy_decisions")
    op.drop_index("ix_final_intents_scope_status", table_name="final_workflow_intents")
    op.drop_table("final_workflow_intents")


def _id_column() -> sa.Column[str]:
    return sa.Column("id", sa.String(length=36), nullable=False)


def _project_column() -> sa.Column[str]:
    return sa.Column("project_id", sa.String(length=64), nullable=False)


def _environment_column() -> sa.Column[str]:
    return sa.Column("environment", sa.String(length=64), nullable=False)


def _enable_project_rls(table_name: str) -> None:
    policy_name = f"{table_name}_project_isolation"
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {policy_name}
        ON {table_name}
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def _disable_project_rls(table_name: str) -> None:
    policy_name = f"{table_name}_project_isolation"
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
