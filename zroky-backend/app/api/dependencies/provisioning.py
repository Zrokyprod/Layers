import secrets

from fastapi import HTTPException, Request, status

from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token, has_admin_role
from app.core.config import get_settings


def _allow_via_admin_jwt(request: Request) -> bool:
    settings = get_settings()
    if not settings.ALLOW_JWT_PROVISIONING_ACCESS:
        return False

    token = extract_bearer_token(request)
    if not token:
        return False

    try:
        claims = decode_jwt_claims(token)
        identity = build_identity_context(claims)
    except HTTPException:
        return False
    return has_admin_role(identity)


def has_provisioning_access(request: Request) -> bool:
    settings = get_settings()

    if not settings.REQUIRE_PROVISIONING_TOKEN:
        return True

    if settings.PROVISIONING_TOKEN:
        provided_token = request.headers.get(settings.PROVISIONING_TOKEN_HEADER_NAME)
        if provided_token and secrets.compare_digest(provided_token, settings.PROVISIONING_TOKEN):
            return True

    return _allow_via_admin_jwt(request)


def require_provisioning_access(request: Request) -> None:
    settings = get_settings()

    if not settings.REQUIRE_PROVISIONING_TOKEN:
        return

    if not settings.PROVISIONING_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Provisioning auth is enabled but PROVISIONING_TOKEN is not configured.",
        )

    if not has_provisioning_access(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid provisioning credentials.",
        )
