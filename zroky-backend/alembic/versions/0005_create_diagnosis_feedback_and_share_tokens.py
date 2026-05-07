"""create diagnosis feedback and share token tables

Revision ID: 0005_create_diagnosis_feedback_and_share_tokens
Revises: 0004_enable_rls_for_diagnosis_jobs
Create Date: 2026-04-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_create_diagnosis_feedback_and_share_tokens"
down_revision = "0004_enable_rls_for_diagnosis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("was_helpful", sa.Boolean(), nullable=False),
        sa.Column("developer_note", sa.Text(), nullable=True),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_feedback_tenant_diagnosis",
        "diagnosis_feedback",
        ["tenant_id", "diagnosis_id"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_feedback_created_at",
        "diagnosis_feedback",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "diagnosis_share_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_diagnosis_share_tokens_hash",
        "diagnosis_share_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_diagnosis_share_tokens_tenant_diagnosis",
        "diagnosis_share_tokens",
        ["tenant_id", "diagnosis_id"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_share_tokens_tenant_revoked",
        "diagnosis_share_tokens",
        ["tenant_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_diagnosis_share_tokens_expires",
        "diagnosis_share_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_share_tokens_expires", table_name="diagnosis_share_tokens")
    op.drop_index("ix_diagnosis_share_tokens_tenant_revoked", table_name="diagnosis_share_tokens")
    op.drop_index("ix_diagnosis_share_tokens_tenant_diagnosis", table_name="diagnosis_share_tokens")
    op.drop_index("ux_diagnosis_share_tokens_hash", table_name="diagnosis_share_tokens")
    op.drop_table("diagnosis_share_tokens")

    op.drop_index("ix_diagnosis_feedback_created_at", table_name="diagnosis_feedback")
    op.drop_index("ix_diagnosis_feedback_tenant_diagnosis", table_name="diagnosis_feedback")
    op.drop_table("diagnosis_feedback")
