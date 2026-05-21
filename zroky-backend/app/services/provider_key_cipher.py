"""
Per-project AES-256-GCM envelope cipher for `provider_keys_vault`
(Module 4.5; plan §14.2 + migration 0058).

The vault stores a single binary blob per row in
`provider_keys_vault.ciphertext`:

    nonce(12) || ciphertext || tag(16)

This module is the *only* place that knows how to encode/decode that
envelope. Callers (the vault service + replay worker) hand in a
plaintext provider key + `project_id` and get back an opaque envelope —
or vice versa.

KEK derivation:
  - The master KEK comes from `Settings.PROVIDER_KEY_VAULT_KEK`. In
    production this should be populated from a KMS GenerateDataKey
    response at process start; locally/in-tests any string ≥ 32 chars
    works.
  - Per-row KEK = HKDF-SHA256(master_kek, salt=project_id, info="zroky-pkv-v1").
    This means the actual encryption key is project-bound: even with
    the master KEK, an attacker who reads a row from project A cannot
    decrypt it as project B because HKDF would derive a different DEK.
  - This is NOT a substitute for a real KMS-backed per-org KEK
    (plan §14.2). It is the local-dev / test fallback that preserves
    the project-isolation invariant the schema promises.

Public surface:
  - `VaultCipherUnavailable`              raised at envelope time when KEK unset
  - `EnvelopeFormatError`                 raised when stored bytes don't decode
  - `compute_fingerprint(plaintext)`      sha256 hex digest
  - `last4_of(plaintext)`                 last 4 chars (UI convenience)
  - `encrypt_provider_key(...)`           returns EnvelopeBundle
  - `decrypt_provider_key(...)`           returns plaintext
  - `get_kms_key_id()`                    Settings.PROVIDER_KEY_VAULT_KEY_ID
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

if TYPE_CHECKING:  # pragma: no cover
    from app.core.config import Settings


# ── envelope constants (must NEVER change without a re-wrap migration) ───────

_NONCE_LEN = 12        # AESGCM standard 96-bit nonce
_KEY_LEN = 32          # AES-256
_HKDF_INFO = b"zroky-pkv-v1"
_HKDF_LEN = _KEY_LEN
_MIN_MASTER_KEK_LEN = 32


# ── exceptions ───────────────────────────────────────────────────────────────


class VaultCipherUnavailable(RuntimeError):
    """`PROVIDER_KEY_VAULT_KEK` is unset or too short.

    The route layer maps this to HTTP 503 so misconfiguration surfaces
    loudly rather than silently degrading to plaintext storage."""


class EnvelopeFormatError(ValueError):
    """The stored ciphertext is shorter than 12+16 bytes or fails GCM
    auth on decrypt. Either bit-rot OR cross-project access OR KEK has
    rotated without a re-wrap migration. The route layer maps this to
    HTTP 500 with an opaque message."""


# ── public bundle returned by encrypt_provider_key ───────────────────────────


@dataclass(frozen=True)
class EnvelopeBundle:
    """The persistence shape for a single vaulted key.

    Caller writes:
      ProviderKeyVault(
          ciphertext=bundle.ciphertext,
          key_fingerprint=bundle.key_fingerprint,
          key_last4=bundle.key_last4,
          kms_key_id=bundle.kms_key_id,
          ...
      )
    """

    ciphertext: bytes        # nonce(12) || ciphertext || tag(16)
    key_fingerprint: str     # sha256 hex of plaintext
    key_last4: str           # last 4 chars of plaintext (or "" if shorter)
    kms_key_id: str          # records which KEK encrypted this row


# ── helpers ──────────────────────────────────────────────────────────────────


def _resolve_master_kek(settings: "Settings | None" = None) -> bytes:
    s = settings or get_settings()
    raw = (s.PROVIDER_KEY_VAULT_KEK or "").strip()
    if not raw:
        raise VaultCipherUnavailable(
            "PROVIDER_KEY_VAULT_KEK is not configured; vault is unavailable."
        )
    encoded = raw.encode("utf-8")
    if len(encoded) < _MIN_MASTER_KEK_LEN:
        raise VaultCipherUnavailable(
            f"PROVIDER_KEY_VAULT_KEK must be at least {_MIN_MASTER_KEK_LEN} "
            "bytes; vault is unavailable."
        )
    return encoded


def _derive_per_project_dek(master_kek: bytes, project_id: str) -> bytes:
    """HKDF-SHA256(master_kek, salt=project_id, info="zroky-pkv-v1") → 32 bytes.

    Project_id is used as the HKDF salt so the same plaintext key in two
    different tenants encrypts to different ciphertext (and decryption
    with the wrong project_id silently produces a different DEK and
    GCM auth-fails).
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=_HKDF_LEN,
        salt=project_id.encode("utf-8"),
        info=_HKDF_INFO,
    ).derive(master_kek)


def compute_fingerprint(plaintext: str) -> str:
    """SHA-256 hex digest of the plaintext key. Used for:
      - dedup ((project_id, provider, fingerprint) UNIQUE)
      - UI display of a key's identity without decrypting
      - audit log cross-reference
    """
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def last4_of(plaintext: str) -> str:
    """Last 4 chars of the plaintext key — UI convenience. Returns the
    full string if it's shorter than 4 chars (e.g. test fixtures)."""
    return plaintext[-4:] if len(plaintext) >= 4 else plaintext


def get_kms_key_id() -> str:
    """The KEK identifier recorded on each new row. Pulled fresh from
    settings on every call so a rotation flag flip doesn't require a
    process restart."""
    return get_settings().PROVIDER_KEY_VAULT_KEY_ID


# ── encrypt / decrypt ────────────────────────────────────────────────────────


def encrypt_provider_key(
    *,
    plaintext: str,
    project_id: str,
) -> EnvelopeBundle:
    """Encrypt `plaintext` under the per-project DEK derived from the
    master KEK. Returns a self-contained EnvelopeBundle ready for
    persistence.

    Raises VaultCipherUnavailable if the master KEK is unset/short.
    """
    if not isinstance(plaintext, str) or not plaintext.strip():
        raise ValueError("plaintext must be a non-empty string")

    master_kek = _resolve_master_kek()
    dek = _derive_per_project_dek(master_kek, project_id)
    aesgcm = AESGCM(dek)

    nonce = os.urandom(_NONCE_LEN)
    aad = project_id.encode("utf-8")  # binds project_id into the auth tag
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)

    envelope = nonce + ct_with_tag

    return EnvelopeBundle(
        ciphertext=envelope,
        key_fingerprint=compute_fingerprint(plaintext),
        key_last4=last4_of(plaintext),
        kms_key_id=get_kms_key_id(),
    )


def decrypt_provider_key(
    *,
    ciphertext: bytes,
    project_id: str,
) -> str:
    """Reverse of encrypt_provider_key. Returns the plaintext key.

    Raises:
      VaultCipherUnavailable if master KEK is unset.
      EnvelopeFormatError if the bytes are too short or GCM auth-fails
        (wrong project_id, bit-rot, or KEK rotation without re-wrap).
    """
    if not isinstance(ciphertext, (bytes, bytearray, memoryview)):
        raise EnvelopeFormatError("ciphertext must be bytes")

    blob = bytes(ciphertext)
    if len(blob) < _NONCE_LEN + 16:  # 16 = GCM tag length
        raise EnvelopeFormatError(
            f"envelope too short ({len(blob)} bytes); expected ≥ "
            f"{_NONCE_LEN + 16}"
        )

    master_kek = _resolve_master_kek()
    dek = _derive_per_project_dek(master_kek, project_id)
    aesgcm = AESGCM(dek)

    nonce = blob[:_NONCE_LEN]
    ct_with_tag = blob[_NONCE_LEN:]
    aad = project_id.encode("utf-8")

    try:
        plain = aesgcm.decrypt(nonce, ct_with_tag, aad)
    except Exception as exc:  # InvalidTag from cryptography lib
        raise EnvelopeFormatError(
            "envelope authentication failed (wrong project_id, KEK "
            "rotation without re-wrap, or bit-rot)"
        ) from exc

    return plain.decode("utf-8")
