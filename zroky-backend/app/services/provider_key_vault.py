"""
Vault service for `provider_keys_vault` (Module 4.5; plan §6.4 + §14.2).

Responsibilities:
  - Validate provider identifiers against the migration's CHECK vocab.
  - Encrypt plaintext keys via `services.provider_key_cipher` before
    persistence — plaintext NEVER touches the DB or any log line.
  - Enforce "at most one active row per (project_id, provider)" by
    revoking the previous active row whenever a new one is added.
  - Provide a `get_active_provider_key` / `decrypt_active_provider_key`
    pair for the replay worker (plan §6.4) and bump `last_used_at` on
    fetch so the threat-model audit trail (§13 risk #5) is honoured.
  - All reads are tenant-scoped — no decrypt path takes plaintext from
    a row whose `project_id` doesn't match the calling tenant.

Errors mapped by the route layer:
  - InvalidProviderError       → HTTP 422
  - InvalidKeyPlaintextError   → HTTP 422
  - DuplicateKeyError          → HTTP 409
  - VaultCipherUnavailable     → HTTP 503  (re-raised from the cipher)

Module 4.5 ships only the routes + service. The replay worker that
calls `decrypt_active_provider_key()` lands in a later module.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ProviderKeyVault
from app.services.provider_key_cipher import (
    EnvelopeBundle,
    EnvelopeFormatError,
    VaultCipherUnavailable,
    compute_fingerprint,
    decrypt_provider_key,
    encrypt_provider_key,
)

logger = logging.getLogger(__name__)


# ── vocab (must match migration 0058 CHECK constraint) ──────────────────────


VALID_PROVIDERS: frozenset[str] = frozenset(
    {
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
    }
)


# ── exceptions ──────────────────────────────────────────────────────────────


class InvalidProviderError(ValueError):
    """`provider` field is not in VALID_PROVIDERS."""


class InvalidKeyPlaintextError(ValueError):
    """The `plaintext_key` failed shape validation (empty / too short)."""


class DuplicateKeyError(ValueError):
    """The (project_id, provider, fingerprint) tuple already has an
    active row — i.e. this exact key was uploaded for this provider
    before. The route layer surfaces this as HTTP 409."""


# ── helpers ─────────────────────────────────────────────────────────────────


def _normalize_provider(provider: str) -> str:
    if not isinstance(provider, str):
        raise InvalidProviderError("provider must be a string")
    norm = provider.strip().lower()
    if norm not in VALID_PROVIDERS:
        raise InvalidProviderError(
            f"provider {provider!r} is not in: {sorted(VALID_PROVIDERS)}"
        )
    return norm


def _validate_plaintext(plaintext: str) -> str:
    if not isinstance(plaintext, str):
        raise InvalidKeyPlaintextError("plaintext must be a string")
    cleaned = plaintext.strip()
    if not cleaned:
        raise InvalidKeyPlaintextError("plaintext key must not be empty")
    if len(cleaned) < 8:
        # Defensive — every real provider key is much longer than this.
        # Anything shorter is almost certainly an accidental paste.
        raise InvalidKeyPlaintextError(
            "plaintext key must be at least 8 characters"
        )
    return cleaned


# ── writes ──────────────────────────────────────────────────────────────────


def store_provider_key(
    db: Session,
    *,
    project_id: str,
    provider: str,
    plaintext_key: str,
    label: str | None = None,
    created_by_user_id: str | None = None,
) -> ProviderKeyVault:
    """Encrypt + persist a plaintext provider key.

    Behaviour:
      1. Normalises `provider`, validates `plaintext_key`.
      2. Computes the fingerprint.
      3. Rejects duplicates (`DuplicateKeyError`) when an active row
         with the same (project_id, provider, fingerprint) exists —
         this catches "user re-pasted the same key" gracefully.
      4. Marks any other ACTIVE row for (project_id, provider) inactive
         (sets `is_active=False`, `revoked_at=now`) so the new row is
         the only active one — implements the "rotation" semantics
         documented on the migration.
      5. Encrypts the plaintext via `provider_key_cipher` and inserts
         the new row.

    Raises:
      InvalidProviderError, InvalidKeyPlaintextError, DuplicateKeyError,
      VaultCipherUnavailable (from the cipher).
    """
    provider_norm = _normalize_provider(provider)
    plaintext_clean = _validate_plaintext(plaintext_key)
    fingerprint = compute_fingerprint(plaintext_clean)
    now = datetime.now(timezone.utc)

    # 1. Reject re-uploads of the exact same key for the same provider
    #    when the existing row is still active. We do allow re-adding a
    #    previously-revoked key (rotation back to a known-good key).
    existing_dup = db.execute(
        select(ProviderKeyVault).where(
            ProviderKeyVault.project_id == project_id,
            ProviderKeyVault.provider == provider_norm,
            ProviderKeyVault.key_fingerprint == fingerprint,
            ProviderKeyVault.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if existing_dup is not None:
        raise DuplicateKeyError(
            f"provider {provider_norm!r} already has an active key with the "
            "same fingerprint for this project"
        )

    # 2. Revoke whatever else is currently active for (project_id, provider).
    active_rows = db.execute(
        select(ProviderKeyVault).where(
            ProviderKeyVault.project_id == project_id,
            ProviderKeyVault.provider == provider_norm,
            ProviderKeyVault.is_active.is_(True),
        )
    ).scalars().all()
    for row in active_rows:
        row.is_active = False
        row.revoked_at = now
        db.add(row)

    # 3. Encrypt + persist the new row.
    bundle: EnvelopeBundle = encrypt_provider_key(
        plaintext=plaintext_clean, project_id=project_id
    )
    new_row = ProviderKeyVault(
        id=str(uuid4()),
        project_id=project_id,
        provider=provider_norm,
        ciphertext=bundle.ciphertext,
        key_fingerprint=bundle.key_fingerprint,
        key_last4=bundle.key_last4,
        kms_key_id=bundle.kms_key_id,
        is_active=True,
        label=(label.strip() if isinstance(label, str) and label.strip() else None),
        created_by_user_id=created_by_user_id,
    )
    db.add(new_row)

    try:
        db.commit()
    except IntegrityError as exc:
        # Defence-in-depth: race against the SELECT above. The unique
        # constraint on (project_id, provider, key_fingerprint) catches
        # double-submits.
        db.rollback()
        raise DuplicateKeyError(
            "provider key with this fingerprint already exists for this project"
        ) from exc
    db.refresh(new_row)

    logger.info(
        "provider_key_stored project=%s provider=%s fp_prefix=%s rotated=%d",
        project_id,
        provider_norm,
        fingerprint[:8],
        len(active_rows),
    )
    return new_row


def revoke_provider_key(
    db: Session,
    *,
    project_id: str,
    key_id: str,
) -> ProviderKeyVault | None:
    """Mark a key inactive. Idempotent — calling on an already-revoked
    row is a no-op (returns the row unchanged).

    Returns None if no row matches (project_id, key_id) — the route
    layer maps this to 404."""
    row = db.execute(
        select(ProviderKeyVault).where(
            ProviderKeyVault.project_id == project_id,
            ProviderKeyVault.id == key_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    if row.is_active:
        row.is_active = False
        row.revoked_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "provider_key_revoked project=%s provider=%s key=%s fp_prefix=%s",
            project_id, row.provider, row.id, row.key_fingerprint[:8],
        )
    return row


# ── reads ───────────────────────────────────────────────────────────────────


def get_provider_key(
    db: Session, *, project_id: str, key_id: str
) -> ProviderKeyVault | None:
    """Tenant-scoped lookup by id. Returns None if not found OR if the
    row belongs to a different project (the route maps both to 404)."""
    return db.execute(
        select(ProviderKeyVault).where(
            ProviderKeyVault.project_id == project_id,
            ProviderKeyVault.id == key_id,
        )
    ).scalar_one_or_none()


def list_provider_keys(
    db: Session,
    *,
    project_id: str,
    provider: str | None = None,
    include_revoked: bool = False,
) -> list[ProviderKeyVault]:
    """Tenant-scoped list, newest-first. Returns ORM rows; the route
    layer is responsible for projecting to the wire shape (which omits
    ciphertext)."""
    conditions: list[Any] = [ProviderKeyVault.project_id == project_id]
    if provider is not None:
        conditions.append(ProviderKeyVault.provider == _normalize_provider(provider))
    if not include_revoked:
        conditions.append(ProviderKeyVault.is_active.is_(True))

    rows = db.execute(
        select(ProviderKeyVault)
        .where(*conditions)
        .order_by(ProviderKeyVault.created_at.desc(), ProviderKeyVault.id.desc())
    ).scalars().all()
    return list(rows)


def get_active_provider_key(
    db: Session, *, project_id: str, provider: str
) -> ProviderKeyVault | None:
    """Single active row for (project_id, provider). Used by the
    replay worker to find which key to decrypt for a given API call.

    Returns None if no active row exists OR if `provider` is not in
    VALID_PROVIDERS (defensive against worker payload typos)."""
    try:
        provider_norm = _normalize_provider(provider)
    except InvalidProviderError:
        return None
    return db.execute(
        select(ProviderKeyVault).where(
            ProviderKeyVault.project_id == project_id,
            ProviderKeyVault.provider == provider_norm,
            ProviderKeyVault.is_active.is_(True),
        )
    ).scalar_one_or_none()


def decrypt_active_provider_key(
    db: Session,
    *,
    project_id: str,
    provider: str,
    mark_used: bool = True,
) -> str | None:
    """Convenience wrapper for the replay worker.

    Steps:
      1. Look up the active row (None if missing/wrong tenant/bad provider).
      2. Decrypt the envelope under the calling project_id (the per-row
         AAD ensures cross-project misuse fails authentication).
      3. If `mark_used=True`, bump `last_used_at` on the row — this is
         the "vault read access logged" telemetry the threat model
         demands (plan §13 risk #5).

    Raises VaultCipherUnavailable / EnvelopeFormatError unmodified —
    the caller (replay worker) decides whether to retry or fail the
    replay run.
    """
    row = get_active_provider_key(db, project_id=project_id, provider=provider)
    if row is None:
        return None

    plaintext = decrypt_provider_key(
        ciphertext=row.ciphertext, project_id=project_id
    )

    if mark_used:
        row.last_used_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        # Don't refresh(row) — the caller probably just wanted the plaintext.

    return plaintext


# ── route-layer wire shape ──────────────────────────────────────────────────


def serialize_vault_row(row: ProviderKeyVault) -> dict[str, Any]:
    """Canonical wire shape for a vault row. NEVER includes plaintext or
    raw ciphertext — only the metadata + fingerprint + last-4 needed
    by the dashboard."""
    return {
        "id": row.id,
        "project_id": row.project_id,
        "provider": row.provider,
        "key_fingerprint": row.key_fingerprint,
        "key_last4": row.key_last4,
        "kms_key_id": row.kms_key_id,
        "label": row.label,
        "is_active": bool(row.is_active),
        "created_by_user_id": row.created_by_user_id,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# Re-exported for convenience (so the route layer doesn't need to know
# about `provider_key_cipher` directly).
__all__ = [
    "VALID_PROVIDERS",
    "InvalidProviderError",
    "InvalidKeyPlaintextError",
    "DuplicateKeyError",
    "VaultCipherUnavailable",
    "EnvelopeFormatError",
    "store_provider_key",
    "revoke_provider_key",
    "get_provider_key",
    "list_provider_keys",
    "get_active_provider_key",
    "decrypt_active_provider_key",
    "serialize_vault_row",
]
