"""create policy_documents table

Revision ID: 0044_create_policy_documents
Revises: 0043_create_issues
Create Date: 2026-05-12 01:30:00.000000

Schema notes:
  - One active policy per project (only one row with active=true per project_id).
  - `body` is application-layer encrypted (same pattern as users.email).
  - Judge reads the single active policy body (≤ 2 KB) into its system prompt.
  - `version` is a monotonic counter bumped on every update.
  - RLS mirrors other tenant tables.
"""

from alembic import op
import sqlalchemy as sa


revision = "0044_create_policy_documents"
down_revision = "0043_create_issues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
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
    )

    # ── indexes ───────────────────────────────────────────────────────────────
    op.create_index(
        "ix_policy_documents_project_active",
        "policy_documents",
        ["project_id", "active"],
    )
    op.create_index(
        "ix_policy_documents_project_created",
        "policy_documents",
        ["project_id", "created_at"],
    )
    # Partial unique index: only one active policy per project at a time.
    # Enforced at DB level on PostgreSQL; SQLite/other DBs fall back to app logic.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX ux_policy_documents_one_active_per_project
            ON policy_documents (project_id)
            WHERE active = true
            """
        )

        op.execute("ALTER TABLE policy_documents ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE policy_documents FORCE ROW LEVEL SECURITY")
        op.execute(
            "DROP POLICY IF EXISTS policy_documents_tenant_isolation ON policy_documents"
        )
        op.execute(
            """
            CREATE POLICY policy_documents_tenant_isolation
            ON policy_documents
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS policy_documents_tenant_isolation ON policy_documents"
        )
        op.execute("ALTER TABLE policy_documents NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE policy_documents DISABLE ROW LEVEL SECURITY")
        op.execute(
            "DROP INDEX IF EXISTS ux_policy_documents_one_active_per_project"
        )

    op.drop_index("ix_policy_documents_project_created", table_name="policy_documents")
    op.drop_index("ix_policy_documents_project_active", table_name="policy_documents")
    op.drop_table("policy_documents")
