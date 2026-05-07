from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import get_settings


def normalize_github_scopes(raw_scope: str | None) -> list[str]:
    if not raw_scope:
        return []

    tokens: list[str] = []
    for part in raw_scope.replace(",", " ").split():
        normalized = part.strip()
        if normalized and normalized not in tokens:
            tokens.append(normalized)
    return tokens


def _require_encryption_key() -> str:
    key = (get_settings().GITHUB_TOKEN_ENCRYPTION_KEY or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "GITHUB_TOKEN_ENCRYPTION_KEY is not configured. "
                "Configure it before connecting GitHub repo access."
            ),
        )
    return key


@lru_cache
def _cipher_for_key(key: str) -> Fernet:
    return Fernet(key.encode("utf-8"))


def ensure_github_token_encryption_ready() -> None:
    key = _require_encryption_key()
    try:
        _cipher_for_key(key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_TOKEN_ENCRYPTION_KEY is invalid. Expected a Fernet-compatible key.",
        ) from exc


def encrypt_github_token(token: str) -> str:
    normalized = token.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub access token is missing from OAuth response.",
        )

    ensure_github_token_encryption_ready()
    key = _require_encryption_key()
    encrypted = _cipher_for_key(key).encrypt(normalized.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_github_token(encrypted_token: str | None) -> str | None:
    if not encrypted_token:
        return None

    ensure_github_token_encryption_ready()
    key = _require_encryption_key()

    try:
        decrypted = _cipher_for_key(key).decrypt(encrypted_token.encode("utf-8"))
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stored GitHub connection token is invalid. Reconnect GitHub in settings.",
        ) from exc

    return decrypted.decode("utf-8").strip() or None
