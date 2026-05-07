"""convert_money_float_to_numeric

Revision ID: 0022_convert_money_float_to_numeric
Revises: 0021_add_github_repo_oauth_user_fields
Create Date: 2026-04-30

Converts floating-point money columns to NUMERIC for precision:
- calls.cost_total, calls.reasoning_cost_total, calls.cache_savings_total
- tenant_settings.monthly_budget_usd, tenant_settings.budget_threshold_percentage

SQLite does not support ALTER COLUMN TYPE, so for SQLite we use a table-copy
approach via batch mode. PostgreSQL (production) gets a direct USING cast.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0022_convert_money_float_to_numeric"
down_revision = "0021_add_github_repo_oauth_user_fields"
branch_labels = None
depends_on = None

_NUMERIC_18_8 = sa.Numeric(18, 8)
_NUMERIC_6_3 = sa.Numeric(6, 3)


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        # SQLite: use batch_alter_table to rebuild columns
        with op.batch_alter_table("calls") as batch_op:
            batch_op.alter_column("cost_total", type_=_NUMERIC_18_8, existing_type=sa.Float(), existing_nullable=False)
            batch_op.alter_column("reasoning_cost_total", type_=_NUMERIC_18_8, existing_type=sa.Float(), existing_nullable=False)
            batch_op.alter_column("cache_savings_total", type_=_NUMERIC_18_8, existing_type=sa.Float(), existing_nullable=False)

        with op.batch_alter_table("tenant_settings") as batch_op:
            batch_op.alter_column("monthly_budget_usd", type_=_NUMERIC_18_8, existing_type=sa.Float(), existing_nullable=True)
            batch_op.alter_column("budget_threshold_percentage", type_=_NUMERIC_6_3, existing_type=sa.Float(), existing_nullable=False)
    else:
        # PostgreSQL: direct ALTER COLUMN with USING cast
        for col in ("cost_total", "reasoning_cost_total", "cache_savings_total"):
            op.alter_column(
                "calls",
                col,
                type_=_NUMERIC_18_8,
                existing_type=sa.Float(),
                postgresql_using=f"{col}::numeric",
                existing_nullable=False,
            )

        op.alter_column(
            "tenant_settings",
            "monthly_budget_usd",
            type_=_NUMERIC_18_8,
            existing_type=sa.Float(),
            postgresql_using="monthly_budget_usd::numeric",
            existing_nullable=True,
        )
        op.alter_column(
            "tenant_settings",
            "budget_threshold_percentage",
            type_=_NUMERIC_6_3,
            existing_type=sa.Float(),
            postgresql_using="budget_threshold_percentage::numeric",
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("calls") as batch_op:
            batch_op.alter_column("cost_total", type_=sa.Float(), existing_type=_NUMERIC_18_8, existing_nullable=False)
            batch_op.alter_column("reasoning_cost_total", type_=sa.Float(), existing_type=_NUMERIC_18_8, existing_nullable=False)
            batch_op.alter_column("cache_savings_total", type_=sa.Float(), existing_type=_NUMERIC_18_8, existing_nullable=False)

        with op.batch_alter_table("tenant_settings") as batch_op:
            batch_op.alter_column("monthly_budget_usd", type_=sa.Float(), existing_type=_NUMERIC_18_8, existing_nullable=True)
            batch_op.alter_column("budget_threshold_percentage", type_=sa.Float(), existing_type=_NUMERIC_6_3, existing_nullable=False)
    else:
        for col in ("cost_total", "reasoning_cost_total", "cache_savings_total"):
            op.alter_column(
                "calls",
                col,
                type_=sa.Float(),
                existing_type=_NUMERIC_18_8,
                postgresql_using=f"{col}::double precision",
                existing_nullable=False,
            )
        op.alter_column(
            "tenant_settings",
            "monthly_budget_usd",
            type_=sa.Float(),
            existing_type=_NUMERIC_18_8,
            postgresql_using="monthly_budget_usd::double precision",
            existing_nullable=True,
        )
        op.alter_column(
            "tenant_settings",
            "budget_threshold_percentage",
            type_=sa.Float(),
            existing_type=_NUMERIC_6_3,
            postgresql_using="budget_threshold_percentage::double precision",
            existing_nullable=False,
        )
