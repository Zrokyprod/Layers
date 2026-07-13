"""Atlassian OAuth helpers for Jira system-of-record verification."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import SystemOfRecordConnectorConfig
from app.services.system_of_record_connector_config import (
    decrypt_connector_bearer_token,
    decrypt_connector_oauth_refresh_token,
)

ATLASSIAN_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
ATLASSIAN_API_BASE_URL = "https://api.atlassian.com"


class AtlassianOAuthError(RuntimeError):
    """Raised when Atlassian OAuth exchange, refresh, or site lookup fails."""


def require_atlassian_oauth_config(settings: Settings) -> None:
    if not settings.ATLASSIAN_CLIENT_ID or not settings.ATLASSIAN_CLIENT_SECRET:
        raise AtlassianOAuthError("Atlassian OAuth is not configured on this server.")


def exchange_atlassian_code(*, code: str, settings: Settings) -> dict[str, Any]:
    require_atlassian_oauth_config(settings)
    try:
        response = httpx.post(
            ATLASSIAN_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "client_id": settings.ATLASSIAN_CLIENT_ID,
                "client_secret": settings.ATLASSIAN_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.ATLASSIAN_OAUTH_REDIRECT_URL,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except AtlassianOAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AtlassianOAuthError("Atlassian OAuth token exchange failed.") from exc
    if not isinstance(payload, dict):
        raise AtlassianOAuthError("Atlassian OAuth response was not an object.")
    error = payload.get("error")
    if error:
        description = str(payload.get("error_description") or error)
        raise AtlassianOAuthError(f"Atlassian OAuth failed: {description}")
    if not str(payload.get("access_token") or "").strip():
        raise AtlassianOAuthError("Atlassian OAuth response missing access token.")
    return payload


def refresh_atlassian_access_token(*, refresh_token: str, settings: Settings) -> str:
    require_atlassian_oauth_config(settings)
    try:
        response = httpx.post(
            ATLASSIAN_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "client_id": settings.ATLASSIAN_CLIENT_ID,
                "client_secret": settings.ATLASSIAN_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except AtlassianOAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AtlassianOAuthError("Atlassian OAuth token refresh failed.") from exc
    if not isinstance(payload, dict):
        raise AtlassianOAuthError("Atlassian OAuth refresh response was not an object.")
    error = payload.get("error")
    if error:
        description = str(payload.get("error_description") or error)
        raise AtlassianOAuthError(f"Atlassian OAuth refresh failed: {description}")
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise AtlassianOAuthError("Atlassian OAuth refresh response missing access token.")
    return access_token


def list_atlassian_accessible_resources(*, access_token: str) -> list[dict[str, Any]]:
    try:
        response = httpx.get(
            ATLASSIAN_ACCESSIBLE_RESOURCES_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise AtlassianOAuthError("Atlassian accessible resources lookup failed.") from exc
    if not isinstance(payload, list):
        raise AtlassianOAuthError("Atlassian accessible resources response was not a list.")
    return [item for item in payload if isinstance(item, dict)]


def pick_jira_resource(resources: list[dict[str, Any]]) -> dict[str, Any]:
    for resource in resources:
        scopes = resource.get("scopes")
        scope_text = " ".join(str(scope) for scope in scopes) if isinstance(scopes, list) else ""
        if "jira" in scope_text.lower() and str(resource.get("id") or "").strip():
            return resource
    for resource in resources:
        if str(resource.get("id") or "").strip() and ".atlassian.net" in str(resource.get("url") or ""):
            return resource
    raise AtlassianOAuthError("Atlassian OAuth did not return an accessible Jira site.")


def resolve_jira_bearer_token(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
    settings: Settings,
    db: Session | None = None,
) -> str | None:
    refresh_token = decrypt_connector_oauth_refresh_token(row, project_id=project_id, db=db)
    if refresh_token and settings.ATLASSIAN_CLIENT_ID and settings.ATLASSIAN_CLIENT_SECRET:
        return refresh_atlassian_access_token(refresh_token=refresh_token, settings=settings)
    return decrypt_connector_bearer_token(row, project_id=project_id, db=db)
