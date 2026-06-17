from typing import Any

import httpx
from fastapi import HTTPException, status

_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# ---------------------------------------------------------------------------
# GitHub HTTP helpers
# ---------------------------------------------------------------------------

def _exchange_github_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> str:
    try:
        response = httpx.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if "access_token" not in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub token exchange failed: {data.get('error_description', 'unknown error')}",
            )
        return str(data["access_token"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact GitHub. Please try again.",
        ) from exc


def _fetch_github_user(token: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            _GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[return-value]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch GitHub profile. Please try again.",
        ) from exc


def _fetch_primary_github_email(token: str) -> str | None:
    try:
        response = httpx.get(
            _GITHUB_EMAILS_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        emails: list[dict[str, Any]] = response.json()
        primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        return str(primary["email"]) if primary else None
    except Exception:  # noqa: BLE001
        return None


def _exchange_google_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> str:
    try:
        response = httpx.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        token = data.get("access_token")
        if not token:
            raise ValueError("No access token returned from Google")
        return str(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact Google. Please try again.",
        ) from exc

def _fetch_google_user(token: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch Google profile. Please try again.",
        ) from exc


