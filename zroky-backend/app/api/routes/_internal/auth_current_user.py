from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes._internal.auth_schemas import MeResponse
from app.api.routes._internal.auth_tokens import _require_auth_secret
from app.auth.identity import extract_bearer_token
from app.db.models import User
from app.services import token_store
from app.services.security import decode_session_token

def _get_current_user(authorization: str | None = None, db: Session | None = None) -> User:
    """Extract and validate Bearer token, return User."""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database session unavailable.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header.")
    token = authorization[len("Bearer "):]
    secret = _require_auth_secret()
    try:
        payload = decode_session_token(token, secret, expected_use="access")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    jti = str(payload.get("jti") or "").strip()
    if jti and token_store.get(f"jwt_blacklisted:{jti}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked.")
    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject.")
    stmt = select(User).where(User.id == user_id)
    user = db.scalars(stmt).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if token_store.get(f"jwt_blacklisted_user:{user.id}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="All sessions for this user have been revoked.")
    return user


def _decode_current_session_expiry(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):]
    try:
        payload = decode_session_token(token, _require_auth_secret())
    except Exception:
        return None
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        return datetime.fromtimestamp(exp, tz=UTC).isoformat()
    return None


def _me_response(user: User) -> MeResponse:
    return MeResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name if hasattr(user, "display_name") else None,
        github_login=user.github_login,
        google_id=user.google_id,
        has_password=bool(user.password_hash),
        is_active=bool(user.is_active),
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at.isoformat() if hasattr(user, "created_at") and user.created_at else "",
    )


