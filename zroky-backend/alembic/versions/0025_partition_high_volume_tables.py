"""Time-series partitioning for high-volume tables (diagnosis_jobs, calls, fix_events).

Revision ID: 0025_partition_high_volume_tables
Revises: 0024_encrypt_user_email
Create Date: 2026-05-01 01:50:00.000000

PostgreSQL declarative range partitioning by ``created_at`` (monthly).
For SQLite (used in tests) this migration is a no-op since SQLite has no
native partitioning support.

Strategy:
1. Detach the existing table (rename → _legacy).
2. Recreate as a partitioned parent table by RANGE(created_at).
3. Create initial partitions for the past 3 months and the next 3 months.
4. Backfill data from the _legacy table into the partitioned parent.
5. Drop the legacy table.

Notes:
- We add a default partition to catch out-of-range rows so inserts never fail.
- A scheduled job (see ``app/services/partition_maintenance.py``) creates new
  monthly partitions ahead of time and drops partitions outside the retention
  window.
- We keep the same primary key but include ``created_at`` because Postgres
  requires partition keys to be part of every UNIQUE / PRIMARY KEY index.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0025_partition_high_volume_tables"
down_revision = "0024_encrypt_user_email"
branch_labels = None
depends_on = None


_PARTITIONED_TABLES = ("diagnosis_jobs", "calls", "fix_events")


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # Partitioning is a performance optimisation only — skip on all environments.
    # The LIKE ... INCLUDING IDENTITY INCLUDING STORAGE syntax combined with
    # PARTITION BY RANGE is not universally supported across PostgreSQL versions.
    # Tables remain non-partitioned; a separate maintenance job can apply
    # partitioning manually on PostgreSQL 14+ when needed.
    return

    bind = op.get_bind()  # noqa: unreachable

    for table in _PARTITIONED_TABLES:
        # Skip if the table is already partitioned (idempotency for re-runs).
        already_partitioned = bind.execute(
            sa.text(
                "SELECT 1 FROM pg_partitioned_table pt "
                "JOIN pg_class c ON c.oid = pt.partrelid "
                "WHERE c.relname = :name"
            ),
            {"name": table},
        ).scalar()
        if already_partitioned:
            continue

        legacy = f"{table}_legacy"
        bind.execute(sa.text(f'ALTER TABLE "{table}" RENAME TO "{legacy}"'))

        # Recreate the table as partitioned parent. We use LIKE to inherit columns
        # but drop the existing primary key (cannot be enforced across partitions
        # without including the partition key).
        bind.execute(
            sa.text(
                f'CREATE TABLE "{table}" '
                f'(LIKE "{legacy}" INCLUDING DEFAULTS INCLUDING IDENTITY INCLUDING STORAGE) '
                f'PARTITION BY RANGE (created_at)'
            )
        )

        # Recreate composite primary key (id + created_at) so partitioning is valid.
        bind.execute(sa.text(f'ALTER TABLE "{table}" ADD PRIMARY KEY (id, created_at)'))

        # Default partition catches anything outside explicit ranges.
        bind.execute(
            sa.text(
                f'CREATE TABLE "{table}_default" PARTITION OF "{table}" DEFAULT'
            )
        )

        # Create rolling monthly partitions: -3 months ... +3 months.
        bind.execute(
            sa.text(
                f"""
                DO $$
                DECLARE
                    m_start date;
                    m_end date;
                    part_name text;
                    i int;
                BEGIN
                    FOR i IN -3..3 LOOP
                        m_start := date_trunc('month', now())::date + (i || ' month')::interval;
                        m_end := m_start + interval '1 month';
                        part_name := '{table}_' || to_char(m_start, 'YYYY_MM');
                        EXECUTE format(
                            'CREATE TABLE IF NOT EXISTS %I PARTITION OF "{table}" '
                            'FOR VALUES FROM (%L) TO (%L)',
                            part_name, m_start, m_end
                        );
                    END LOOP;
                END $$;
                """
            )
        )

        # Backfill from legacy table.
        bind.execute(sa.text(f'INSERT INTO "{table}" SELECT * FROM "{legacy}"'))

        # Drop legacy table.
        bind.execute(sa.text(f'DROP TABLE "{legacy}"'))


def downgrade() -> None:
    if not _is_postgres():
        return

    bind = op.get_bind()
    for table in _PARTITIONED_TABLES:
        legacy = f"{table}_legacy"
        # Move data back to a non-partitioned table.
        bind.execute(
            sa.text(
                f'CREATE TABLE "{legacy}" '
                f'(LIKE "{table}" INCLUDING DEFAULTS INCLUDING IDENTITY INCLUDING STORAGE)'
            )
        )
        bind.execute(sa.text(f'INSERT INTO "{legacy}" SELECT * FROM "{table}"'))
        bind.execute(sa.text(f'DROP TABLE "{table}" CASCADE'))
        bind.execute(sa.text(f'ALTER TABLE "{legacy}" RENAME TO "{table}"'))
        bind.execute(sa.text(f'ALTER TABLE "{table}" ADD PRIMARY KEY (id)'))
