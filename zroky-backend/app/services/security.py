import hashlib
import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


# ---------------------------------------------------------------------------
# Project / API key helpers (existing)
# ---------------------------------------------------------------------------

def generate_project_id() -> str:
    return f"proj_{secrets.token_hex(8)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key_material() -> tuple[str, str, str]:
    api_key = f"zk_live_{secrets.token_urlsafe(32)}"
    key_prefix = api_key[:18]
    return api_key, key_prefix, hash_api_key(api_key)


def hash_share_token(share_token: str) -> str:
    return hashlib.sha256(share_token.encode("utf-8")).hexdigest()


def generate_share_token_material() -> tuple[str, str, str]:
    share_token = f"zroky_share_live_{secrets.token_urlsafe(32)}"
    token_prefix = share_token[:24]
    return share_token, token_prefix, hash_share_token(share_token)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_BCRYPT_HASH_PREFIX = "bcrypt_sha256$"
_MIN_BCRYPT_ROUNDS = 4
_MAX_BCRYPT_ROUNDS = 15


def _bcrypt_rounds() -> int:
    settings = get_settings()
    rounds = int(settings.AUTH_BCRYPT_ROUNDS)
    if rounds < _MIN_BCRYPT_ROUNDS:
        return _MIN_BCRYPT_ROUNDS
    if rounds > _MAX_BCRYPT_ROUNDS:
        return _MAX_BCRYPT_ROUNDS
    return rounds


def _bcrypt_sha256_material(plain: str) -> bytes:
    # Pre-hash avoids bcrypt's 72-byte input ceiling while preserving entropy.
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("ascii")


def password_hash_needs_upgrade(hashed: str | None) -> bool:
    return bool(hashed) and not hashed.startswith(_BCRYPT_HASH_PREFIX)


def hash_password(plain: str) -> str:
    material = _bcrypt_sha256_material(plain)
    hashed = bcrypt.hashpw(material, bcrypt.gensalt(rounds=_bcrypt_rounds())).decode("utf-8")
    return f"{_BCRYPT_HASH_PREFIX}{hashed}"


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False

    is_prefixed = hashed.startswith(_BCRYPT_HASH_PREFIX)
    stored_hash = hashed[len(_BCRYPT_HASH_PREFIX) :] if is_prefixed else hashed
    candidate = _bcrypt_sha256_material(plain) if is_prefixed else plain.encode("utf-8")

    try:
        return bcrypt.checkpw(candidate, stored_hash.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal JWT issuance (HS256 — for email/password + GitHub OAuth sessions)
# ---------------------------------------------------------------------------

def issue_access_token(
    *,
    user_id: str,
    email: str | None,
    subject: str,
    expire_hours: int,
    secret: str,
) -> str:
    return _issue_session_token(
        user_id=user_id,
        email=email,
        subject=subject,
        expire_hours=expire_hours,
        secret=secret,
        token_use="access",
    )


def issue_refresh_token(
    *,
    user_id: str,
    email: str | None,
    subject: str,
    expire_hours: int,
    secret: str,
) -> str:
    return _issue_session_token(
        user_id=user_id,
        email=email,
        subject=subject,
        expire_hours=expire_hours,
        secret=secret,
        token_use="refresh",
    )


def _issue_session_token(
    *,
    user_id: str,
    email: str | None,
    subject: str,
    expire_hours: int,
    secret: str,
    token_use: str,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "user_id": user_id,
        "token_use": token_use,
        "jti": secrets.token_hex(12),
        "iat": now.timestamp(),
        "exp": now + timedelta(hours=expire_hours),
    }
    if email:
        claims["email"] = email
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    return decode_session_token(token, secret, expected_use="access")


def decode_session_token(
    token: str,
    secret: str,
    *,
    expected_use: str | None = None,
) -> dict[str, Any]:
    claims = jwt.decode(token, secret, algorithms=["HS256"])

    if expected_use:
        normalized_expected = expected_use.strip().lower()
        token_use_raw = claims.get("token_use")
        token_use = str(token_use_raw).strip().lower() if token_use_raw is not None else ""

        if token_use:
            if token_use != normalized_expected:
                raise ValueError("Token use claim does not match expected token use.")
        elif normalized_expected != "access":
            raise ValueError("Token use claim is required for this token type.")

    return claims


# ---------------------------------------------------------------------------
# OAuth state CSRF protection (HMAC-signed, no DB/Redis needed)
# ---------------------------------------------------------------------------

_STATE_TTL_SECONDS = 600  # 10 minutes


def generate_oauth_state(secret: str) -> str:
    """Return a time-tagged HMAC state string safe to embed in OAuth redirect."""
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload = f"{nonce}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), digestmod="sha256").hexdigest()
    return f"{payload}:{sig}"


def verify_oauth_state(state: str, secret: str) -> bool:
    """Return True only if state is valid HMAC and not expired."""
    try:
        parts = state.rsplit(":", 1)
        if len(parts) != 2:
            return False
        payload, received_sig = parts
        expected_sig = hmac.new(secret.encode(), payload.encode(), digestmod="sha256").hexdigest()
        if not hmac.compare_digest(expected_sig, received_sig):
            return False
        _, ts_str = payload.split(":", 1)
        if time.time() - int(ts_str) > _STATE_TTL_SECONDS:
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def generate_oauth_state_with_payload(secret: str, payload: dict[str, Any]) -> str:
    """Return signed OAuth state that includes JSON payload metadata."""
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")
    signed_payload = f"{nonce}:{ts}:{payload_b64}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), digestmod="sha256").hexdigest()
    return f"{signed_payload}:{sig}"


def verify_oauth_state_with_payload(state: str, secret: str) -> dict[str, Any] | None:
    """Return parsed payload when OAuth state is valid and unexpired, else None."""
    try:
        parts = state.rsplit(":", 1)
        if len(parts) != 2:
            return None

        signed_payload, received_sig = parts
        expected_sig = hmac.new(secret.encode(), signed_payload.encode(), digestmod="sha256").hexdigest()
        if not hmac.compare_digest(expected_sig, received_sig):
            return None

        nonce, ts_str, payload_b64 = signed_payload.split(":", 2)
        if not nonce:
            return None
        if time.time() - int(ts_str) > _STATE_TTL_SECONDS:
            return None

        padded = payload_b64 + ("=" * (-len(payload_b64) % 4))
        payload = json.loads(urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None
