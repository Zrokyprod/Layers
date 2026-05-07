"""add_fix_embeddings

Revision ID: 0023_add_fix_embeddings
Revises: 0022_convert_money_float_to_numeric
Create Date: 2026-04-30

Creates the fix_embeddings table with pgvector support for semantic search.
Includes pgvector extension setup for PostgreSQL.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0023_add_fix_embeddings"
down_revision = "0022_convert_money_float_to_numeric"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Enable pgvector extension for PostgreSQL
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create fix_embeddings table with TEXT embedding column (works on both DBs)
    op.create_table(
        "fix_embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("diagnosis_id", sa.String(64), nullable=False, index=True),
        sa.Column("fix_id", sa.String(128), nullable=False, index=True),
        sa.Column("embedding_text", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=True),
        sa.Column("embedding_model", sa.String(64), nullable=False, server_default="text-embedding-3-small"),
        sa.Column("diagnosis_type", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("project_id", "fix_id", name="ux_fix_embeddings_project_fix"),
    )

    # Create standard indexes
    op.create_index("ix_fix_embeddings_project_diagnosis", "fix_embeddings", ["project_id", "diagnosis_id"])
    op.create_index("ix_fix_embeddings_project_fix", "fix_embeddings", ["project_id", "fix_id"])
    op.create_index("ix_fix_embeddings_diagnosis_type", "fix_embeddings", ["project_id", "diagnosis_type"])

    # For PostgreSQL, convert to proper vector(1536) type and create ivfflat index
    if is_postgres:
        op.execute(
            "ALTER TABLE fix_embeddings ALTER COLUMN embedding TYPE vector(1536) USING NULL"
        )
        op.execute(
            "CREATE INDEX ix_fix_embeddings_embedding ON fix_embeddings "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
        op.execute("ALTER TABLE fix_embeddings ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY fix_embeddings_tenant_isolation ON fix_embeddings "
            "USING (project_id = current_setting('app.current_tenant')::text)"
        )

def downgrade() -> None:
    op.drop_table("fix_embeddings")
