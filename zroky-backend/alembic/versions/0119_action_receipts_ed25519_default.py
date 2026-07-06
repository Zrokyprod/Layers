"""Use Ed25519 as the default action receipt signature algorithm.

Revision ID: 0119_action_receipts_ed25519_default
Revises: 0118_add_commerce_connector_types
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0119_action_receipts_ed25519_default"
down_revision = "0118_add_commerce_connector_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("action_receipts") as batch_op:
        batch_op.alter_column(
            "signature_algorithm",
            existing_type=sa.String(length=32),
            server_default=sa.text("'Ed25519'"),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("action_receipts") as batch_op:
        batch_op.alter_column(
            "signature_algorithm",
            existing_type=sa.String(length=32),
            server_default=sa.text("'HMAC-SHA256'"),
            existing_nullable=False,
        )
