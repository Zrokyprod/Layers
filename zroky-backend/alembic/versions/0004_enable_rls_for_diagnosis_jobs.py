"""enable postgres RLS for diagnosis_jobs

Revision ID: 0004_enable_rls_for_diagnosis_jobs
Revises: 0003_create_users_and_project_memberships
Create Date: 2026-04-22 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0004_enable_rls_for_diagnosis_jobs"
down_revision = "0003_create_users_and_project_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE diagnosis_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE diagnosis_jobs FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS diagnosis_jobs_tenant_isolation ON diagnosis_jobs")
    op.execute(
        """
        CREATE POLICY diagnosis_jobs_tenant_isolation
        ON diagnosis_jobs
        USING (tenant_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP POLICY IF EXISTS diagnosis_jobs_tenant_isolation ON diagnosis_jobs")
    op.execute("ALTER TABLE diagnosis_jobs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE diagnosis_jobs DISABLE ROW LEVEL SECURITY")
