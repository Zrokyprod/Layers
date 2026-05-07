from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings, is_jwt_configured


@dataclass(frozen=True)
class IdentityContext:
    subject: str
    email: str | None
    project_ids: set[str]
    roles: set[str]
    raw_claims: dict[str, Any]


def _as_string_set(value: Any) -> set[str]:
    if isinstance(value, str) and value.strip():
        return {value.strip()}
    if isinstance(value, list):
        return {item.strip() for item in value if isinstance(item, str) and item.strip()}
    return set()


def extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


@lru_cache
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def decode_jwt_claims(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not is_jwt_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication is not configured.",
        )

    algorithms = [item.strip() for item in settings.JWT_ALGORITHMS.split(",") if item.strip()]
    options = {"verify_aud": bool(settings.JWT_AUDIENCE)}
    decode_kwargs: dict[str, Any] = {
        "algorithms": algorithms,
        "options": options,
    }

    if settings.JWT_ISSUER:
        decode_kwargs["issuer"] = settings.JWT_ISSUER
    if settings.JWT_AUDIENCE:
        decode_kwargs["audience"] = settings.JWT_AUDIENCE

    try:
        if settings.JWT_JWKS_URL:
            signing_key = _get_jwks_client(settings.JWT_JWKS_URL).get_signing_key_from_jwt(token)
            claims = jwt.decode(token, signing_key.key, **decode_kwargs)
        else:
            if not settings.JWT_SIGNING_KEY:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="JWT signing key is not configured.",
                )
            claims = jwt.decode(token, settings.JWT_SIGNING_KEY, **decode_kwargs)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        ) from exc

    if not isinstance(claims, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )
    return claims


def build_identity_context(claims: dict[str, Any]) -> IdentityContext:
    settings = get_settings()

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is missing subject claim.",
        )

    project_ids = _as_string_set(claims.get(settings.JWT_PROJECTS_CLAIM))
    project_ids.update(_as_string_set(claims.get(settings.JWT_PROJECT_CLAIM)))

    roles = _as_string_set(claims.get(settings.JWT_ROLES_CLAIM))
    return IdentityContext(
        subject=subject,
        email=claims.get("email") if isinstance(claims.get("email"), str) else None,
        project_ids=project_ids,
        roles=roles,
        raw_claims=claims,
    )


def resolve_project_from_identity(identity: IdentityContext, selected_project_id: str | None) -> str:
    if selected_project_id:
        if selected_project_id in identity.project_ids:
            return selected_project_id
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested project is not allowed for this identity.",
        )

    if len(identity.project_ids) == 1:
        return next(iter(identity.project_ids))

    if not identity.project_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Identity has no project access claims.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Multiple projects available. Provide project header context.",
    )


def has_admin_role(identity: IdentityContext) -> bool:
    settings = get_settings()
    return settings.JWT_ADMIN_ROLE in identity.roles
