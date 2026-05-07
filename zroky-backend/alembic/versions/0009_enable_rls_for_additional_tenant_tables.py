"""enable postgres RLS for additional tenant tables

Revision ID: 0009_enable_rls_for_additional_tenant_tables
Revises: 0008_create_diagnosis_fix_watches
Create Date: 2026-04-24 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0009_enable_rls_for_additional_tenant_tables"
down_revision = "0008_create_diagnosis_fix_watches"
branch_labels = None
depends_on = None


TENANT_TABLE_POLICIES: tuple[tuple[str, str], ...] = (
    ("diagnosis_feedback", "diagnosis_feedback_tenant_isolation"),
    ("diagnosis_share_tokens", "diagnosis_share_tokens_tenant_isolation"),
    ("project_alerts", "project_alerts_tenant_isolation"),
    ("project_dashboard_configs", "project_dashboard_configs_tenant_isolation"),
    ("diagnosis_fix_watches", "diagnosis_fix_watches_tenant_isolation"),
)


def _enable_rls_with_policy(table_name: str, policy_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
    op.execute(
        f"""
        CREATE POLICY {policy_name}
        ON {table_name}
        USING (tenant_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))
        """
    )


def _disable_rls_with_policy(table_name: str, policy_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name, policy_name in TENANT_TABLE_POLICIES:
        _enable_rls_with_policy(table_name, policy_name)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name, policy_name in TENANT_TABLE_POLICIES:
        _disable_rls_with_policy(table_name, policy_name)
