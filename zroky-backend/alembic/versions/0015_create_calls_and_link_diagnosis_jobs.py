"""create calls table and link diagnosis jobs

Revision ID: 0015_create_calls_and_link_diagnosis_jobs
Revises: 0014_add_pricing_and_rollback_config_fields
Create Date: 2026-04-26 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_create_calls_and_link_diagnosis_jobs"
down_revision = "0014_add_pricing_and_rollback_config_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=120), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("model", sa.String(length=120), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_total", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "event_id", name="ux_calls_project_event"),
    )
    op.create_index("ix_calls_project_created", "calls", ["project_id", "created_at"], unique=False)
    op.create_index("ix_calls_project_status", "calls", ["project_id", "status"], unique=False)
    op.create_index(
        "ix_calls_project_status_created",
        "calls",
        ["project_id", "status", "created_at"],
        unique=False,
    )
    op.create_index("ix_calls_project_provider", "calls", ["project_id", "provider"], unique=False)
    op.create_index(
        "ix_calls_project_provider_model_created",
        "calls",
        ["project_id", "provider", "model", "created_at"],
        unique=False,
    )

    with op.batch_alter_table("diagnosis_jobs") as batch_op:
        batch_op.add_column(sa.Column("call_id", sa.String(length=64), nullable=True))
        batch_op.create_index(
            "ix_diagnosis_jobs_tenant_call",
            ["tenant_id", "call_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_diagnosis_jobs_call_id_calls",
            "calls",
            ["call_id"],
            ["id"],
            ondelete="SET NULL",
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE calls ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE calls FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS calls_project_isolation ON calls")
        op.execute(
            """
            CREATE POLICY calls_project_isolation
            ON calls
            USING (project_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS calls_project_isolation ON calls")
        op.execute("ALTER TABLE calls NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE calls DISABLE ROW LEVEL SECURITY")

    with op.batch_alter_table("diagnosis_jobs") as batch_op:
        batch_op.drop_constraint("fk_diagnosis_jobs_call_id_calls", type_="foreignkey")
        batch_op.drop_index("ix_diagnosis_jobs_tenant_call")
        batch_op.drop_column("call_id")
    op.drop_index("ix_calls_project_provider_model_created", table_name="calls")
    op.drop_index("ix_calls_project_provider", table_name="calls")
    op.drop_index("ix_calls_project_status_created", table_name="calls")
    op.drop_index("ix_calls_project_status", table_name="calls")
    op.drop_index("ix_calls_project_created", table_name="calls")
    op.drop_table("calls")
