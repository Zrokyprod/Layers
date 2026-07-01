"""Zoho CRM OAuth helpers for system-of-record verification."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.db.models import SystemOfRecordConnectorConfig
from app.services.system_of_record_connector_config import (
    decrypt_connector_bearer_token,
    decrypt_connector_oauth_refresh_token,
)

ZOHO_AUTHORIZE_PATH = "/oauth/v2/auth"
ZOHO_TOKEN_PATH = "/oauth/v2/token"


class ZohoOAuthError(RuntimeError):
    """Raised when Zoho OAuth exchange or refresh fails."""


def zoho_accounts_base_url(settings: Settings) -> str:
    return settings.ZOHO_ACCOUNTS_BASE_URL.rstrip("/")


def require_zoho_oauth_config(settings: Settings) -> None:
    if not settings.ZOHO_CLIENT_ID or not settings.ZOHO_CLIENT_SECRET:
        raise ZohoOAuthError("Zoho OAuth is not configured on this server.")


def exchange_zoho_code(*, code: str, settings: Settings) -> dict[str, Any]:
    require_zoho_oauth_config(settings)
    try:
        response = httpx.post(
            f"{zoho_accounts_base_url(settings)}{ZOHO_TOKEN_PATH}",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.ZOHO_CLIENT_ID,
                "client_secret": settings.ZOHO_CLIENT_SECRET,
                "redirect_uri": settings.ZOHO_OAUTH_REDIRECT_URL,
                "code": code,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except ZohoOAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ZohoOAuthError("Zoho OAuth token exchange failed.") from exc
    if not isinstance(payload, dict):
        raise ZohoOAuthError("Zoho OAuth response was not an object.")
    error = payload.get("error")
    if error:
        description = str(payload.get("error_description") or error)
        raise ZohoOAuthError(f"Zoho OAuth failed: {description}")
    if not str(payload.get("access_token") or "").strip():
        raise ZohoOAuthError("Zoho OAuth response missing access token.")
    return payload


def refresh_zoho_access_token(*, refresh_token: str, settings: Settings) -> str:
    require_zoho_oauth_config(settings)
    try:
        response = httpx.post(
            f"{zoho_accounts_base_url(settings)}{ZOHO_TOKEN_PATH}",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.ZOHO_CLIENT_ID,
                "client_secret": settings.ZOHO_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except ZohoOAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ZohoOAuthError("Zoho OAuth token refresh failed.") from exc
    if not isinstance(payload, dict):
        raise ZohoOAuthError("Zoho OAuth refresh response was not an object.")
    error = payload.get("error")
    if error:
        description = str(payload.get("error_description") or error)
        raise ZohoOAuthError(f"Zoho OAuth refresh failed: {description}")
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise ZohoOAuthError("Zoho OAuth refresh response missing access token.")
    return access_token


def resolve_zoho_crm_bearer_token(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
    settings: Settings,
) -> str | None:
    refresh_token = decrypt_connector_oauth_refresh_token(row, project_id=project_id)
    if refresh_token and settings.ZOHO_CLIENT_ID and settings.ZOHO_CLIENT_SECRET:
        return refresh_zoho_access_token(refresh_token=refresh_token, settings=settings)
    return decrypt_connector_bearer_token(row, project_id=project_id)
