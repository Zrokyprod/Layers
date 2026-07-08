from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode


TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_SECRET_BYTES = 20


def generate_totp_secret() -> str:
    """Return a base32 TOTP seed without padding."""
    raw = secrets.token_bytes(TOTP_SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def build_totp_uri(*, secret: str, account_name: str, issuer: str = "Zroky") -> str:
    label = f"{issuer}:{account_name}"
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": str(TOTP_DIGITS),
            "period": str(TOTP_PERIOD_SECONDS),
        }
    )
    return f"otpauth://totp/{quote(label)}?{query}"


def _totp_at(secret: str, *, counter: int) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(f"{normalized}{padding}", casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp_code(
    *,
    secret: str | None,
    code: str,
    now: int | None = None,
    window: int = 1,
) -> bool:
    if not secret:
        return False
    normalized_code = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(normalized_code) != TOTP_DIGITS:
        return False

    current_counter = int((now if now is not None else time.time()) // TOTP_PERIOD_SECONDS)
    for offset in range(-window, window + 1):
        candidate = _totp_at(secret, counter=current_counter + offset)
        if hmac.compare_digest(candidate, normalized_code):
            return True
    return False
