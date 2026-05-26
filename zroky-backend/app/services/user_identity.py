from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token
from app.core.config import get_settings, is_jwt_configured
from app.db.models import User
from app.services.security import decode_access_token


@dataclass(frozen=True)
class RequestIdentity:
    subject: str
    email: str | None


def _normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _resolve_internal_identity(token: str) -> RequestIdentity | None:
    settings = get_settings()
    secret = (settings.AUTH_JWT_SECRET or "").strip()
    if not secret:
        return None

    try:
        claims = decode_access_token(token, secret)
    except Exception:  # noqa: BLE001
        return None

    # Reject blacklisted tokens (logout support)
    jti = str(claims.get("jti") or "").strip()
    user_id = str(claims.get("user_id") or "").strip()
    if jti:
        try:
            from app.services import token_store
            if token_store.get(f"jwt_blacklisted:{jti}"):
                return None
            if user_id and token_store.get(f"jwt_blacklisted_user:{user_id}"):
                return None
        except Exception:  # noqa: BLE001
            pass

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        return None

    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    return RequestIdentity(subject=subject, email=_normalize_email(email))


def _resolve_external_identity(token: str) -> RequestIdentity | None:
    settings = get_settings()
    if not is_jwt_configured(settings):
        return None

    try:
        claims = decode_jwt_claims(token)
        identity = build_identity_context(claims)
    except HTTPException:
        return None

    return RequestIdentity(subject=identity.subject, email=_normalize_email(identity.email))


def resolve_request_identity(request: Request) -> RequestIdentity | None:
    token = extract_bearer_token(request)
    if not token:
        return None

    internal_identity = _resolve_internal_identity(token)
    if internal_identity is not None:
        return internal_identity

    return _resolve_external_identity(token)


def require_authenticated_user(
    request: Request,
    db: Session,
    *,
    auto_create: bool,
) -> User:
    identity = resolve_request_identity(request)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated bearer token is required for this action.",
        )

    user = db.execute(select(User).where(User.subject == identity.subject)).scalar_one_or_none()
    if user is None and auto_create:
        user = User(
            subject=identity.subject,
            email=identity.email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user account not found for this token.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    if user.email is None and identity.email:
        user.email = identity.email
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
