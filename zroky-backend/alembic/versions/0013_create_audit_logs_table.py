"""create audit logs table

Revision ID: 0013_create_audit_logs_table
Revises: 0012_add_diagnosis_pull_requests
Create Date: 2026-04-25 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_create_audit_logs_table"
down_revision = "0012_add_diagnosis_pull_requests"
branch_labels = None
depends_on = None


def _enable_rls() -> None:
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_isolation ON audit_logs")
    op.execute(
        """
        CREATE POLICY audit_logs_tenant_isolation
        ON audit_logs
        USING (tenant_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))
        """
    )


def _disable_rls() -> None:
    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_isolation ON audit_logs")
    op.execute("ALTER TABLE audit_logs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_tenant_created", "audit_logs", ["tenant_id", "created_at"], unique=False)
    op.create_index(
        "ix_audit_logs_tenant_action_created",
        "audit_logs",
        ["tenant_id", "action", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_tenant_diagnosis_created",
        "audit_logs",
        ["tenant_id", "diagnosis_id", "created_at"],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _enable_rls()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _disable_rls()

    op.drop_index("ix_audit_logs_tenant_diagnosis_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_created", table_name="audit_logs")
    op.drop_table("audit_logs")
