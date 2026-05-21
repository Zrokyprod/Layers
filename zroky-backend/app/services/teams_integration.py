from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import TenantTeamsInstall


def _require_encryption_key() -> str:
    settings = get_settings()
    key = (
        settings.MS_TEAMS_WEBHOOK_ENCRYPTION_KEY
        or settings.SLACK_TOKEN_ENCRYPTION_KEY
        or settings.GITHUB_TOKEN_ENCRYPTION_KEY
        or ""
    ).strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MS_TEAMS_WEBHOOK_ENCRYPTION_KEY is not configured. Configure it before connecting Teams.",
        )
    return key


@lru_cache
def _cipher_for_key(key: str) -> Fernet:
    return Fernet(key.encode("utf-8"))


def ensure_teams_webhook_encryption_ready() -> None:
    key = _require_encryption_key()
    try:
        _cipher_for_key(key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MS_TEAMS_WEBHOOK_ENCRYPTION_KEY is invalid. Expected a Fernet-compatible key.",
        ) from exc


def encrypt_teams_webhook_url(webhook_url: str) -> str:
    normalized = webhook_url.strip()
    if not normalized.startswith("https://"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Teams webhook URL must start with https://")
    ensure_teams_webhook_encryption_ready()
    encrypted = _cipher_for_key(_require_encryption_key()).encrypt(normalized.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_teams_webhook_url(encrypted_webhook_url: str | None) -> str | None:
    if not encrypted_webhook_url:
        return None
    ensure_teams_webhook_encryption_ready()
    try:
        decrypted = _cipher_for_key(_require_encryption_key()).decrypt(encrypted_webhook_url.encode("utf-8"))
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stored Teams webhook is invalid. Reconnect Microsoft Teams in settings.",
        ) from exc
    return decrypted.decode("utf-8").strip() or None


def get_teams_install(db: Session, tenant_id: str) -> TenantTeamsInstall | None:
    return db.execute(
        select(TenantTeamsInstall).where(TenantTeamsInstall.tenant_id == tenant_id)
    ).scalar_one_or_none()


def build_teams_status(install: TenantTeamsInstall | None) -> dict[str, Any]:
    if install is None:
        return {
            "connected": False,
            "channel_name": None,
            "connector_type": None,
            "installed_by_user": None,
            "installed_at": None,
            "updated_at": None,
        }
    return {
        "connected": True,
        "channel_name": install.channel_name,
        "connector_type": install.connector_type,
        "installed_by_user": install.installed_by_user,
        "installed_at": install.installed_at,
        "updated_at": install.updated_at,
    }


async def send_teams_message(db: Session, tenant_id: str, text: str) -> bool:
    install = get_teams_install(db, tenant_id)
    if install is None:
        return False
    webhook_url = decrypt_teams_webhook_url(install.webhook_url_encrypted)
    if not webhook_url:
        return False
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json={"text": text})
    return 200 <= response.status_code < 300
