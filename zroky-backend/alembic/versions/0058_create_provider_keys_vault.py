"""create provider_keys_vault (per-project encrypted provider API keys)

Revision ID: 0058_create_provider_keys_vault
Revises: 0057_create_audit_log_admin
Create Date: 2026-05-13 21:00:00.000000

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 + §14.2 + §6.4 + §13 risk #5):
  - Stores customer provider keys (OpenAI / Anthropic / etc.) so the replay
    worker (`app/services/replay_runner.py`, plan §6.4) can reconstruct a
    provider client and issue real calls during pre-action verification.
  - **Encryption envelope**: AES-256-GCM with a per-org KEK held in the KMS
    (plan §14.2). The application layer concatenates `nonce || ciphertext ||
    tag` into a single binary blob and writes it to `ciphertext`. We do NOT
    split the envelope into separate columns — keeping it opaque at the DB
    level prevents accidental partial reads and simplifies KEK rotation.
  - `key_fingerprint` = SHA-256(plaintext key) hex digest. Used to:
        (a) deduplicate "same key re-uploaded" cases at the app layer,
        (b) display the last-4 / fingerprint in the UI without ever
            decrypting,
        (c) cross-reference audit-log entries.
  - `kms_key_id` records WHICH KEK encrypted this row, so periodic
    re-wrap rotation can find rows still encrypted under the old KEK.
  - `is_active` + `revoked_at` model rotation: a project may keep historical
    rows for audit, but only one row per (project_id, provider) is the
    active one. App layer enforces this on insert (sets the previous row
    inactive); a partial unique index would also enforce it at the DB level
    on Postgres but is omitted here to keep SQLite parity simple — the app
    holds the invariant.
  - `last_used_at` is updated by the replay worker on every successful key
    fetch, providing the "vault read access logged" telemetry the threat
    model demands (§13 risk #5).
  - **Tenant isolation**: RLS enabled + forced on Postgres with the same
    `current_setting('app.current_tenant_id', true)` convention as every
    other tenant-scoped table. The replay worker sets the GUC before issuing
    a SELECT, so a misconfigured worker cannot read another tenant's keys.
  - Foreign keys:
        provider_keys_vault.created_by_user_id → users.id   ON DELETE SET NULL
    No FK on project_id by convention (matches 0049/0050/0052/0053/0054).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0058_create_provider_keys_vault"
down_revision = "0057_create_audit_log_admin"
branch_labels = None
depends_on = None


# Allowed provider identifiers — kept in sync with app/services/provider_registry.py
_ALLOWED_PROVIDERS = (
    "openai",
    "anthropic",
    "gemini",
    "azure_openai",
    "vertex",
    "cohere",
    "mistral",
    "deepseek",
    "bedrock",
    "openrouter",
    "groq",
    "custom",
)


def upgrade() -> None:
    providers_in = ", ".join(f"'{p}'" for p in _ALLOWED_PROVIDERS)

    op.create_table(
        "provider_keys_vault",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment=(
                "Provider identifier — must match app/services/provider_registry.py"
            ),
        ),
        sa.Column(
            "ciphertext",
            sa.LargeBinary(),
            nullable=False,
            comment=(
                "AES-256-GCM envelope: nonce(12) || ciphertext || tag(16). "
                "Encrypted under the project's per-org KEK from KMS."
            ),
        ),
        sa.Column(
            "key_fingerprint",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hex digest of plaintext key — for dedup + UI display",
        ),
        sa.Column(
            "key_last4",
            sa.String(length=8),
            nullable=True,
            comment="Last 4 chars of plaintext key — UI-only convenience",
        ),
        sa.Column(
            "kms_key_id",
            sa.String(length=128),
            nullable=True,
            comment="Identifier of the KMS KEK that encrypted this row (for rotation)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="App-enforced: at most one active row per (project_id, provider)",
        ),
        sa.Column(
            "label",
            sa.String(length=128),
            nullable=True,
            comment="Optional human-readable label e.g. 'prod', 'staging'",
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            nullable=True,
            comment="User who uploaded the key — NULL after user deletion",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Updated by replay worker on every successful fetch",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL = active; non-NULL = retained for audit only",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_provider_keys_vault_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"provider IN ({providers_in})",
            name="ck_provider_keys_vault_provider",
        ),
        sa.UniqueConstraint(
            "project_id", "provider", "key_fingerprint",
            name="ux_provider_keys_vault_project_provider_fp",
        ),
    )

    op.create_index(
        "ix_provider_keys_vault_project_provider_active",
        "provider_keys_vault",
        ["project_id", "provider", "is_active"],
    )
    op.create_index(
        "ix_provider_keys_vault_project_created",
        "provider_keys_vault",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_provider_keys_vault_created_by_user_id",
        "provider_keys_vault",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_provider_keys_vault_key_fingerprint",
        "provider_keys_vault",
        ["key_fingerprint"],
    )

    # ── RLS (Postgres only) ──────────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE provider_keys_vault ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_keys_vault FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS provider_keys_vault_tenant_isolation ON provider_keys_vault"
    )
    op.execute(
        """
        CREATE POLICY provider_keys_vault_tenant_isolation
        ON provider_keys_vault
        USING (project_id = current_setting('app.current_tenant_id', true))
        WITH CHECK (project_id = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS provider_keys_vault_tenant_isolation ON provider_keys_vault"
        )
        op.execute("ALTER TABLE provider_keys_vault NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE provider_keys_vault DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        "ix_provider_keys_vault_key_fingerprint", table_name="provider_keys_vault"
    )
    op.drop_index(
        "ix_provider_keys_vault_created_by_user_id", table_name="provider_keys_vault"
    )
    op.drop_index(
        "ix_provider_keys_vault_project_created", table_name="provider_keys_vault"
    )
    op.drop_index(
        "ix_provider_keys_vault_project_provider_active",
        table_name="provider_keys_vault",
    )
    op.drop_table("provider_keys_vault")
