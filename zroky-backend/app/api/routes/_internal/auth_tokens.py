import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.routes._internal.auth_schemas import AuthTokenResponse, SessionHandoffRequest
from app.core.config import get_settings
from app.db.models import User
from app.services import token_store
from app.services.security import decode_session_token, issue_access_token, issue_refresh_token

_OAUTH_HANDOFF_KEY_PREFIX = "oauth_handoff:"
_OAUTH_HANDOFF_TTL_SECONDS = 300
_EMAIL_VERIFICATION_TOKEN_PREFIX = "sha256:"
_EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_auth_secret() -> str:
    settings = get_settings()
    if not settings.AUTH_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email/password auth is not configured on this server.",
        )
    return settings.AUTH_JWT_SECRET


def _issue_token(user: User) -> AuthTokenResponse:
    settings = get_settings()
    secret = _require_auth_secret()
    access_expire_hours = max(1, settings.AUTH_JWT_EXPIRE_HOURS)
    refresh_expire_hours = max(access_expire_hours, settings.AUTH_REFRESH_TOKEN_EXPIRE_HOURS)

    access_token = issue_access_token(
        user_id=user.id,
        email=user.email,
        subject=user.subject,
        expire_hours=access_expire_hours,
        secret=secret,
    )
    refresh_token = issue_refresh_token(
        user_id=user.id,
        email=user.email,
        subject=user.subject,
        expire_hours=refresh_expire_hours,
        secret=secret,
    )

    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_in_seconds=access_expire_hours * 60 * 60,
        refresh_expires_in_seconds=refresh_expire_hours * 60 * 60,
        user_id=user.id,
        email=user.email,
        email_verified=user.email_verified_at is not None,
    )


def _store_oauth_handoff(token: AuthTokenResponse) -> str:
    handoff_id = secrets.token_urlsafe(32)
    token_store.set_with_ttl(
        f"{_OAUTH_HANDOFF_KEY_PREFIX}{handoff_id}",
        token.model_dump_json(),
        _OAUTH_HANDOFF_TTL_SECONDS,
    )
    return handoff_id


def _consume_oauth_handoff(handoff_id: str) -> AuthTokenResponse:
    key = f"{_OAUTH_HANDOFF_KEY_PREFIX}{handoff_id}"
    raw = token_store.get(key)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth handoff.",
        )

    token_store.delete(key)
    try:
        return AuthTokenResponse.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth handoff.",
        ) from exc


def _email_verification_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _store_email_verification_token(token: str, *, now: datetime | None = None) -> str:
    issued_at = int((now or datetime.now(UTC)).timestamp())
    return f"{_EMAIL_VERIFICATION_TOKEN_PREFIX}{issued_at}:{_email_verification_digest(token)}"


def _email_verification_token_filter(token: str):
    digest = _email_verification_digest(token)
    return or_(
        User.email_verification_token == f"{_EMAIL_VERIFICATION_TOKEN_PREFIX}{digest}",
        User.email_verification_token == token,
        User.email_verification_token.like(f"{_EMAIL_VERIFICATION_TOKEN_PREFIX}%:{digest}"),
    )


def _email_verification_token_expired(stored_token: str | None, *, now: datetime | None = None) -> bool:
    if not stored_token or not stored_token.startswith(_EMAIL_VERIFICATION_TOKEN_PREFIX):
        return False
    parts = stored_token.split(":", 2)
    if len(parts) != 3:
        return False
    try:
        issued_at = datetime.fromtimestamp(int(parts[1]), tz=UTC)
    except (TypeError, ValueError, OSError):
        return True
    return (now or datetime.now(UTC)) - issued_at > timedelta(seconds=_EMAIL_VERIFICATION_TTL_SECONDS)


def _validated_session_handoff_token(body: SessionHandoffRequest, db: Session) -> AuthTokenResponse:
    secret = _require_auth_secret()
    try:
        access_claims = decode_session_token(body.access_token, secret, expected_use="access")
        refresh_claims = decode_session_token(body.refresh_token, secret, expected_use="refresh")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session handoff tokens.",
        ) from exc

    access_user_id = str(access_claims.get("user_id") or "").strip()
    refresh_user_id = str(refresh_claims.get("user_id") or "").strip()
    if not access_user_id or access_user_id != refresh_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session handoff tokens.",
        )

    if body.user_id and body.user_id != access_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session handoff tokens.",
        )

    user = db.execute(select(User).where(User.id == access_user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session handoff tokens.",
        )

    if token_store.get(f"jwt_blacklisted_user:{access_user_id}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="All sessions for this user have been revoked.",
        )

    return AuthTokenResponse(
        access_token=body.access_token,
        refresh_token=body.refresh_token,
        access_expires_in_seconds=body.access_expires_in_seconds,
        refresh_expires_in_seconds=body.refresh_expires_in_seconds,
        token_type=body.token_type,
        user_id=access_user_id,
        email=user.email,
        email_verified=user.email_verified_at is not None,
    )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

