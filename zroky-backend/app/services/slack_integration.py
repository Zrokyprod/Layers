from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import TenantSlackInstall

_SLACK_WEBHOOK_CIPHERTEXT_PREFIX = "fernet:"


def normalize_slack_scopes(raw_scope: str | None) -> list[str]:
    if not raw_scope:
        return []
    scopes: list[str] = []
    for part in raw_scope.replace(",", " ").split():
        normalized = part.strip()
        if normalized and normalized not in scopes:
            scopes.append(normalized)
    return scopes


def _require_encryption_key() -> str:
    settings = get_settings()
    key = (settings.SLACK_TOKEN_ENCRYPTION_KEY or settings.GITHUB_TOKEN_ENCRYPTION_KEY or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLACK_TOKEN_ENCRYPTION_KEY is not configured. Configure it before connecting Slack.",
        )
    return key


@lru_cache
def _cipher_for_key(key: str) -> Fernet:
    return Fernet(key.encode("utf-8"))


def ensure_slack_token_encryption_ready() -> None:
    key = _require_encryption_key()
    try:
        _cipher_for_key(key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLACK_TOKEN_ENCRYPTION_KEY is invalid. Expected a Fernet-compatible key.",
        ) from exc


def encrypt_slack_token(token: str) -> str:
    normalized = token.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slack access token is missing.")
    ensure_slack_token_encryption_ready()
    encrypted = _cipher_for_key(_require_encryption_key()).encrypt(normalized.encode("utf-8"))
    return encrypted.decode("utf-8")


def encrypt_slack_webhook_url(webhook_url: str | None) -> str | None:
    if webhook_url is None:
        return None
    normalized = webhook_url.strip()
    if not normalized:
        return None
    if not normalized.startswith("https://"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slack webhook URL must start with https://")
    ensure_slack_token_encryption_ready()
    encrypted = _cipher_for_key(_require_encryption_key()).encrypt(normalized.encode("utf-8"))
    return f"{_SLACK_WEBHOOK_CIPHERTEXT_PREFIX}{encrypted.decode('utf-8')}"


def decrypt_slack_token(encrypted_token: str | None) -> str | None:
    if not encrypted_token:
        return None
    ensure_slack_token_encryption_ready()
    try:
        decrypted = _cipher_for_key(_require_encryption_key()).decrypt(encrypted_token.encode("utf-8"))
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stored Slack token is invalid. Reconnect Slack in settings.",
        ) from exc
    return decrypted.decode("utf-8").strip() or None


def decrypt_slack_webhook_url(stored_webhook_url: str | None) -> str | None:
    if not stored_webhook_url:
        return None
    normalized = stored_webhook_url.strip()
    if not normalized:
        return None
    if not normalized.startswith(_SLACK_WEBHOOK_CIPHERTEXT_PREFIX):
        return normalized

    ensure_slack_token_encryption_ready()
    encrypted = normalized[len(_SLACK_WEBHOOK_CIPHERTEXT_PREFIX):]
    try:
        decrypted = _cipher_for_key(_require_encryption_key()).decrypt(encrypted.encode("utf-8"))
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stored Slack webhook is invalid. Reconnect Slack in settings.",
        ) from exc
    return decrypted.decode("utf-8").strip() or None


def get_slack_install(db: Session, tenant_id: str) -> TenantSlackInstall | None:
    return db.execute(
        select(TenantSlackInstall).where(TenantSlackInstall.tenant_id == tenant_id)
    ).scalar_one_or_none()


def build_slack_status(install: TenantSlackInstall | None) -> dict[str, Any]:
    if install is None:
        return {
            "connected": False,
            "team_id": None,
            "team_name": None,
            "channel_id": None,
            "channel_name": None,
            "bot_user_id": None,
            "scopes": [],
            "installed_by_user": None,
            "installed_at": None,
            "updated_at": None,
        }
    return {
        "connected": True,
        "team_id": install.team_id,
        "team_name": install.team_name,
        "channel_id": install.channel_id,
        "channel_name": install.channel_name,
        "bot_user_id": install.bot_user_id,
        "scopes": normalize_slack_scopes(install.scope),
        "installed_by_user": install.installed_by_user,
        "installed_at": install.installed_at,
        "updated_at": install.updated_at,
    }


def slack_approval_user_ids(install: TenantSlackInstall | None) -> list[str]:
    if install is None:
        return []
    try:
        loaded = json.loads(install.approval_user_ids_json or "[]")
    except Exception:
        loaded = []
    if not isinstance(loaded, list):
        return []
    user_ids: list[str] = []
    for item in loaded:
        user_id = str(item or "").strip()
        if user_id and user_id not in user_ids:
            user_ids.append(user_id)
    return user_ids


async def send_slack_message(
    db: Session,
    tenant_id: str,
    text: str,
    *,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    install = get_slack_install(db, tenant_id)
    if install is None or not install.webhook_url:
        return False
    webhook_url = decrypt_slack_webhook_url(install.webhook_url)
    if not webhook_url:
        return False
    payload: dict[str, Any] = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json=payload)
    return 200 <= response.status_code < 300
