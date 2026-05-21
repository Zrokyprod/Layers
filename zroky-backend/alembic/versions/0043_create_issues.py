"""create issues table (denormalized fast-read, grouped by failure_code+fingerprint+agent)

Revision ID: 0043_create_issues
Revises: 0035_add_email_verification_to_users
Create Date: 2026-05-12 01:00:00.000000

Schema notes:
  - One row per unique (project_id, failure_code, prompt_fingerprint, agent_name) group.
  - Built and maintained by the incremental issues worker from the `calls` table.
  - `status`  = 'open' | 'resolved' | 'ignored'
  - `occurrence_count` is incremented on every new matching call.
  - `sample_*` columns hold the most recent representative call/diagnosis.
  - RLS mirrors the `calls` table tenant-isolation policy.
"""

from alembic import op
import sqlalchemy as sa


revision = "0043_create_issues"
down_revision = "0035_add_email_verification_to_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=False),
        sa.Column("prompt_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_call_id", sa.String(length=64), nullable=True),
        sa.Column("sample_diagnosis_id", sa.String(length=64), nullable=True),
        sa.Column("sample_evidence_json", sa.Text(), nullable=True),
        sa.Column("last_fix_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_source", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "failure_code",
            "prompt_fingerprint",
            "agent_name",
            name="ux_issues_group_key",
        ),
    )

    # ── lookup indexes ────────────────────────────────────────────────────────
    op.create_index("ix_issues_project_status", "issues", ["project_id", "status"])
    op.create_index(
        "ix_issues_project_status_last_seen",
        "issues",
        ["project_id", "status", "last_seen_at"],
    )
    op.create_index(
        "ix_issues_project_failure_code",
        "issues",
        ["project_id", "failure_code"],
    )
    op.create_index(
        "ix_issues_project_agent",
        "issues",
        ["project_id", "agent_name"],
    )
    op.create_index("ix_issues_project_created", "issues", ["project_id", "created_at"])

    # ── RLS ───────────────────────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE issues ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE issues FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS issues_tenant_isolation ON issues")
    op.execute(
        """
        CREATE POLICY issues_tenant_isolation
        ON issues
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS issues_tenant_isolation ON issues")
        op.execute("ALTER TABLE issues NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE issues DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_issues_project_created", table_name="issues")
    op.drop_index("ix_issues_project_agent", table_name="issues")
    op.drop_index("ix_issues_project_failure_code", table_name="issues")
    op.drop_index("ix_issues_project_status_last_seen", table_name="issues")
    op.drop_index("ix_issues_project_status", table_name="issues")
    op.drop_table("issues")
