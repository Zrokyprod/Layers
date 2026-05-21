"""create intel_signals table (Intel Pulse — external signal ingestion)

Revision ID: 0055_create_intel_signals
Revises: 0054_create_subscriptions_and_entitlements
Create Date: 2026-05-13 19:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 / §9):
  - Global, NOT tenant-scoped: signals are shared intelligence across all
    orgs (provider outages, model deprecations, CVEs, pricing changes).
    Hence no project_id / org_id column and no RLS policy.
  - Sources the scrapers populate:
        'openai_status'    — status.openai.com feed
        'anthropic_status' — anthropic.com/status feed
        'cve_db'           — NVD / provider CVE advisories
        'pricing_tracker'  — vendor pricing API / changelog diff
        'manual'           — ops-team override
  - `kind` enumerates the signal category:
        'outage' | 'deprecation' | 'cve' | 'pricing_change' | 'advisory'
  - `model_affected` is NULL for provider-wide signals, a single model name
    ('gpt-4o-2024-05-13'), or a glob-ish pattern ('gpt-4*').
  - `valid_from` is required; `valid_to` NULL means "still active".
    Dashboards filter by `now BETWEEN valid_from AND COALESCE(valid_to, 'infinity')`.
  - `confidence` is a 0.0–1.0 scraper-assigned score; `1.0` for first-party
    feeds, lower for heuristic scraping.
  - Dedup: no unique constraint at DB level — scrapers compute a canonical
    key in the app layer and upsert via explicit lookup; NULL-semantics on
    `url` and `model_affected` make a pure DB unique awkward.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0055_create_intel_signals"
down_revision = "0054_create_subscriptions_and_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intel_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            comment="'openai_status' | 'anthropic_status' | 'cve_db' | 'pricing_tracker' | 'manual'",
        ),
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            comment="'outage' | 'deprecation' | 'cve' | 'pricing_change' | 'advisory'",
        ),
        sa.Column(
            "url",
            sa.String(length=512),
            nullable=True,
            comment="Canonical URL for the signal (provider status page, CVE entry, ...)",
        ),
        sa.Column(
            "model_affected",
            sa.String(length=128),
            nullable=True,
            comment="Model name, glob pattern, or NULL for provider-wide",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'low'"),
            comment="'low' | 'medium' | 'high' | 'critical'",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
            comment="0.0–1.0 scraper-assigned confidence; 1.0 for first-party feeds",
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "valid_to",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL = still active",
        ),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=True,
            comment="Raw scraped payload / advisory body",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('outage', 'deprecation', 'cve', 'pricing_change', 'advisory')",
            name="ck_intel_signals_kind",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_intel_signals_severity",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_intel_signals_confidence_range",
        ),
    )

    op.create_index(
        "ix_intel_signals_source_kind",
        "intel_signals",
        ["source", "kind"],
    )
    op.create_index(
        "ix_intel_signals_model_affected",
        "intel_signals",
        ["model_affected"],
    )
    op.create_index(
        "ix_intel_signals_valid_to",
        "intel_signals",
        ["valid_to"],
    )
    op.create_index(
        "ix_intel_signals_valid_from",
        "intel_signals",
        ["valid_from"],
    )
    op.create_index(
        "ix_intel_signals_severity",
        "intel_signals",
        ["severity"],
    )
    op.create_index(
        "ix_intel_signals_created_at",
        "intel_signals",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intel_signals_created_at", table_name="intel_signals")
    op.drop_index("ix_intel_signals_severity", table_name="intel_signals")
    op.drop_index("ix_intel_signals_valid_from", table_name="intel_signals")
    op.drop_index("ix_intel_signals_valid_to", table_name="intel_signals")
    op.drop_index("ix_intel_signals_model_affected", table_name="intel_signals")
    op.drop_index("ix_intel_signals_source_kind", table_name="intel_signals")
    op.drop_table("intel_signals")
