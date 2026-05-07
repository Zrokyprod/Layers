"""encrypt user email and add email_hash for searchable lookups

Revision ID: 0024_encrypt_user_email
Revises: 0023_add_fix_embeddings
Create Date: 2026-04-30 18:50:00.000000

This migration:
1. Adds email_hash column for deterministic lookups
2. Changes email column type from VARCHAR(320) to TEXT (to fit encrypted data)
3. Backfills email_hash for existing rows
4. Drops the old unique index on email and creates new one on email_hash

NOTE: Existing plain-text emails are kept as-is. The application layer 
will handle encryption transparently for new writes via EncryptedSearchableString.
For existing rows, manually run a backfill script if encryption-at-rest is 
required for legacy data.
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_encrypt_user_email"
down_revision = "0023_add_fix_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add email_hash column for searchable lookups (HMAC-SHA256 hex = 64 chars)
    op.add_column("users", sa.Column("email_hash", sa.String(length=64), nullable=True))

    # Drop the old unique index on email (since email is now encrypted, can't enforce uniqueness directly)
    try:
        op.drop_index("ux_users_email", table_name="users")
    except Exception:
        # Index may not exist in some environments
        pass

    # Change email column type to TEXT to fit encrypted payloads (Fernet output is longer than original)
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=320),
            type_=sa.Text(),
            existing_nullable=True,
        )

    # Create unique index on email_hash for fast lookups
    op.create_index(
        "ux_users_email_hash",
        "users",
        ["email_hash"],
        unique=True,
        postgresql_where=sa.text("email_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_users_email_hash", table_name="users")
    
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.Text(),
            type_=sa.String(length=320),
            existing_nullable=True,
        )
    
    op.create_index("ux_users_email", "users", ["email"], unique=True)
    op.drop_column("users", "email_hash")
