"""Tests for auth routes — register, login, JWT issuance."""
import os
import re
from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_auth.db")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-key-for-auth-tests")
os.environ.setdefault("ALLOW_PROJECT_HEADER_CONTEXT", "true")
os.environ.setdefault("REQUIRE_PROVISIONING_TOKEN", "false")

from app.db.models import User, compute_email_hash
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.api.routes.auth import AuthTokenResponse, _store_email_verification_token, _store_oauth_handoff


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def test_register_creates_account_and_returns_token(client):
    resp = client.post("/v1/auth/register", json={
        "email": "alice@example.com",
        "password": "securepw123",
        "confirm_password": "securepw123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["access_expires_in_seconds"] > 0
    assert data["refresh_expires_in_seconds"] > data["access_expires_in_seconds"]
    assert data["token_type"] == "bearer"
    assert data["email"] == "alice@example.com"


def test_register_login_alias_paths_under_api_v1(client):
    register = client.post("/api/v1/auth/register", json={
        "email": "alias-auth@example.com",
        "password": "securepw123",
        "confirm_password": "securepw123",
    })
    assert register.status_code == 201

    login = client.post("/api/v1/auth/login", json={
        "email": "alias-auth@example.com",
        "password": "securepw123",
    })
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_register_duplicate_email_returns_409(client):
    client.post("/v1/auth/register", json={
        "email": "dupe@example.com",
        "password": "password1",
        "confirm_password": "password1",
    })
    resp = client.post("/v1/auth/register", json={
        "email": "dupe@example.com",
        "password": "password2",
        "confirm_password": "password2",
    })
    assert resp.status_code == 409


def test_register_password_mismatch_returns_422(client):
    resp = client.post("/v1/auth/register", json={
        "email": "mismatch@example.com",
        "password": "password1",
        "confirm_password": "different",
    })
    assert resp.status_code == 422


def test_register_invalid_email_returns_422(client):
    resp = client.post("/v1/auth/register", json={
        "email": "not-an-email",
        "password": "password1",
        "confirm_password": "password1",
    })
    assert resp.status_code == 422


def test_register_short_password_returns_422(client):
    resp = client.post("/v1/auth/register", json={
        "email": "shortpw@example.com",
        "password": "short",
        "confirm_password": "short",
    })
    assert resp.status_code == 422


def test_register_supports_password_longer_than_72_bytes(client):
    long_password = "A" * 100
    email = "longpw@example.com"

    register = client.post("/v1/auth/register", json={
        "email": email,
        "password": long_password,
        "confirm_password": long_password,
    })
    assert register.status_code == 201

    login = client.post("/v1/auth/login", json={
        "email": email,
        "password": long_password,
    })
    assert login.status_code == 200

    with SessionLocal() as session:
        from app.db.models import compute_email_hash
        user = session.execute(select(User).where(User.email_hash == compute_email_hash(email))).scalar_one()
    assert user.password_hash.startswith("bcrypt_sha256$")


def test_register_stores_hashed_email_verification_token_and_verifies(client, monkeypatch):
    captured = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr("app.api.routes.auth.send_email", fake_send_email)
    email = "verify-hash@example.com"

    register = client.post("/v1/auth/register", json={
        "email": email,
        "password": "verifyhash123",
        "confirm_password": "verifyhash123",
    })
    assert register.status_code == 201

    match = re.search(r"token=([A-Za-z0-9_-]+)", str(captured["plain_body"]))
    assert match is not None
    raw_token = match.group(1)

    with SessionLocal() as session:
        user = session.execute(select(User).where(User.email_hash == compute_email_hash(email))).scalar_one()
        stored_token = user.email_verification_token
    assert stored_token is not None
    assert stored_token.startswith("sha256:")
    assert raw_token not in stored_token
    assert len(stored_token) <= 128

    verify = client.get("/v1/auth/verify-email", params={"token": raw_token})
    assert verify.status_code == 200

    with SessionLocal() as session:
        verified = session.execute(select(User).where(User.email_hash == compute_email_hash(email))).scalar_one()
        assert verified.email_verified_at is not None
        assert verified.email_verification_token is None


def test_verify_email_rejects_expired_hashed_token(client):
    token = "expired-verification-token"
    email = "expired-verify@example.com"
    issued_at = datetime.now(UTC) - timedelta(days=2)

    with SessionLocal() as session:
        user = User(
            subject=f"email:{email}",
            email=email,
            email_verification_token=_store_email_verification_token(token, now=issued_at),
        )
        session.add(user)
        session.commit()

    response = client.get("/v1/auth/verify-email", params={"token": token})
    assert response.status_code == 400

    with SessionLocal() as session:
        user = session.execute(select(User).where(User.email_hash == compute_email_hash(email))).scalar_one()
        assert user.email_verified_at is None
        assert user.email_verification_token is None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_with_correct_credentials_returns_token(client):
    client.post("/v1/auth/register", json={
        "email": "logintest@example.com",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    })
    resp = client.post("/v1/auth/login", json={
        "email": "logintest@example.com",
        "password": "mypassword123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["email"] == "logintest@example.com"


def test_refresh_returns_rotated_session_bundle(client):
    register = client.post("/v1/auth/register", json={
        "email": "refresh@example.com",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    })
    assert register.status_code == 201

    token_bundle = register.json()
    refresh_resp = client.post("/v1/auth/refresh", json={"refresh_token": token_bundle["refresh_token"]})
    assert refresh_resp.status_code == 200

    refreshed = refresh_resp.json()
    assert refreshed["email"] == "refresh@example.com"
    assert refreshed["token_type"] == "bearer"
    assert refreshed["access_token"] != token_bundle["access_token"]
    assert refreshed["refresh_token"] != token_bundle["refresh_token"]


def test_refresh_rejects_access_token(client):
    register = client.post("/v1/auth/register", json={
        "email": "refresh-bad@example.com",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    })
    assert register.status_code == 201

    token_bundle = register.json()
    refresh_resp = client.post("/v1/auth/refresh", json={"refresh_token": token_bundle["access_token"]})
    assert refresh_resp.status_code == 401


def test_me_rejects_refresh_token_as_bearer(client):
    register = client.post("/v1/auth/register", json={
        "email": "refresh-as-bearer@example.com",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    })
    assert register.status_code == 201

    refresh_token = register.json()["refresh_token"]
    response = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 401


def test_oauth_handoff_exchanges_once(client):
    token = AuthTokenResponse(
        access_token="oauth-access-token",
        refresh_token="oauth-refresh-token",
        access_expires_in_seconds=3600,
        refresh_expires_in_seconds=7200,
        token_type="bearer",
        user_id="user_123",
        email="oauth@example.com",
        email_verified=True,
    )
    handoff_id = _store_oauth_handoff(token)

    response = client.post("/v1/auth/oauth/handoff", json={"handoff_id": handoff_id})
    assert response.status_code == 200
    assert response.json() == token.model_dump()

    replay = client.post("/v1/auth/oauth/handoff", json={"handoff_id": handoff_id})
    assert replay.status_code == 400


def test_session_handoff_validates_tokens_and_exchanges_once(client):
    register = client.post("/v1/auth/register", json={
        "email": "session-handoff@example.com",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    })
    assert register.status_code == 201
    token_bundle = register.json()

    create = client.post("/v1/auth/session/handoff", json=token_bundle)
    assert create.status_code == 200
    handoff_id = create.json()["handoff_id"]

    complete = client.post("/v1/auth/oauth/handoff", json={"handoff_id": handoff_id})
    assert complete.status_code == 200
    assert complete.json()["access_token"] == token_bundle["access_token"]
    assert complete.json()["refresh_token"] == token_bundle["refresh_token"]

    replay = client.post("/v1/auth/oauth/handoff", json={"handoff_id": handoff_id})
    assert replay.status_code == 400


def test_login_wrong_password_returns_401(client):
    client.post("/v1/auth/register", json={
        "email": "wrongpw@example.com",
        "password": "correctpassword",
        "confirm_password": "correctpassword",
    })
    resp = client.post("/v1/auth/login", json={
        "email": "wrongpw@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


def test_login_nonexistent_user_returns_401(client):
    resp = client.post("/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "doesntmatter",
    })
    assert resp.status_code == 401


def test_login_upgrades_legacy_password_hash(client):
    email = "legacy-hash@example.com"
    password = "LegacyPassword123"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    with SessionLocal() as session:
        user = User(
            subject=f"email:{email}",
            email=email,
            password_hash=legacy_hash,
        )
        session.add(user)
        session.commit()

    login = client.post("/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    assert login.status_code == 200

    with SessionLocal() as session:
        from app.db.models import compute_email_hash
        updated = session.execute(select(User).where(User.email_hash == compute_email_hash(email))).scalar_one()
    assert updated.password_hash != legacy_hash
    assert updated.password_hash.startswith("bcrypt_sha256$")


def test_login_email_case_insensitive(client):
    client.post("/v1/auth/register", json={
        "email": "casetest@example.com",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    })
    resp = client.post("/v1/auth/login", json={
        "email": "CASETEST@EXAMPLE.COM",
        "password": "mypassword123",
    })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# JWT structure validation
# ---------------------------------------------------------------------------

def test_token_is_decodable_with_secret(client):
    import jwt as pyjwt  # noqa: PLC0415

    resp = client.post("/v1/auth/register", json={
        "email": "jwtcheck@example.com",
        "password": "password123",
        "confirm_password": "password123",
    })
    token = resp.json()["access_token"]
    claims = pyjwt.decode(token, "test-secret-key-for-auth-tests", algorithms=["HS256"])
    assert claims["email"] == "jwtcheck@example.com"
    assert "sub" in claims
    assert "exp" in claims


# ---------------------------------------------------------------------------
# Forgot / reset password
# ---------------------------------------------------------------------------

def test_forgot_password_always_returns_200(client):
    # Non-existent email — must not reveal whether it's registered.
    resp = client.post("/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert "reset link" in resp.json()["message"].lower()


def test_reset_password_rejects_bad_token(client):
    resp = client.post("/v1/auth/reset-password", json={"token": "badtoken", "new_password": "newpassword1"})
    assert resp.status_code == 400


def test_forgot_and_reset_password_full_flow(client):
    from app.services import token_store as ts

    # Register user
    client.post("/v1/auth/register", json={
        "email": "resetme@example.com",
        "password": "oldpassword1",
        "confirm_password": "oldpassword1",
    })

    # Trigger forgot-password
    resp = client.post("/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    assert resp.status_code == 200

    # Grab the token directly from the in-memory store
    reset_token = None
    for key, (val, _) in list(ts._mem_store.items()):
        if key.startswith("pw_reset:"):
            reset_token = key[len("pw_reset:"):]
            break
    assert reset_token is not None, "reset token not found in store"

    # Use the token to set a new password
    resp2 = client.post("/v1/auth/reset-password", json={
        "token": reset_token,
        "new_password": "newpassword1",
    })
    assert resp2.status_code == 200

    # Token is consumed — second use must fail
    resp3 = client.post("/v1/auth/reset-password", json={
        "token": reset_token,
        "new_password": "newpassword1",
    })
    assert resp3.status_code == 400

    # Login with new password succeeds
    login_resp = client.post("/v1/auth/login", json={
        "email": "resetme@example.com",
        "password": "newpassword1",
    })
    assert login_resp.status_code == 200


def test_reset_password_revokes_existing_sessions(client, monkeypatch):
    captured_messages = []

    def fake_send_email(**kwargs):
        captured_messages.append(kwargs)
        return True

    monkeypatch.setattr("app.api.routes.auth.send_email", fake_send_email)
    register = client.post("/v1/auth/register", json={
        "email": "reset-revoke@example.com",
        "password": "oldpassword1",
        "confirm_password": "oldpassword1",
    })
    assert register.status_code == 201
    token_bundle = register.json()

    forgot = client.post("/v1/auth/forgot-password", json={"email": "reset-revoke@example.com"})
    assert forgot.status_code == 200

    reset_body = next(
        str(message["plain_body"])
        for message in captured_messages
        if "reset-password?token=" in str(message.get("plain_body"))
    )
    match = re.search(r"token=([A-Za-z0-9_-]+)", reset_body)
    assert match is not None
    reset_token = match.group(1)

    reset = client.post("/v1/auth/reset-password", json={
        "token": reset_token,
        "new_password": "newpassword1",
    })
    assert reset.status_code == 200

    old_me = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token_bundle['access_token']}"},
    )
    assert old_me.status_code == 401

    old_refresh = client.post("/v1/auth/refresh", json={"refresh_token": token_bundle["refresh_token"]})
    assert old_refresh.status_code == 401

    new_login = client.post("/v1/auth/login", json={
        "email": "reset-revoke@example.com",
        "password": "newpassword1",
    })
    assert new_login.status_code == 200


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def test_logout_invalidates_token(client):
    # Register and get a token
    reg = client.post("/v1/auth/register", json={
        "email": "logout@example.com",
        "password": "logoutpw123",
        "confirm_password": "logoutpw123",
    })
    assert reg.status_code == 201
    access_token = reg.json()["access_token"]

    # Logout — should succeed
    logout_resp = client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200

    # Token is now blacklisted — subsequent requests with it should be rejected.
    # We can verify via the /refresh endpoint which also validates bearer tokens
    # indirectly (or by checking the blacklist directly).
    from app.services import token_store as ts
    import jwt as pyjwt
    claims = pyjwt.decode(access_token, options={"verify_signature": False})
    jti = claims.get("jti")
    assert jti is not None
    assert ts.get(f"jwt_blacklisted:{jti}") == "1"


def test_logout_without_token_is_200(client):
    resp = client.post("/v1/auth/logout")
    assert resp.status_code == 200


def test_me_security_and_logout_all_flow(client):
    reg = client.post("/v1/auth/register", json={
        "email": "security@example.com",
        "password": "securitypw123",
        "confirm_password": "securitypw123",
    })
    assert reg.status_code == 201
    access_token = reg.json()["access_token"]
    refresh_token = reg.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    me = client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "security@example.com"
    assert me.json()["display_name"] is None
    assert me.json()["is_active"] is True
    assert me.json()["email_verified"] is False

    profile_update = client.patch(
        "/v1/auth/me",
        headers=headers,
        json={"display_name": "Security Owner"},
    )
    assert profile_update.status_code == 200
    assert profile_update.json()["display_name"] == "Security Owner"

    updated_me = client.get("/v1/auth/me", headers=headers)
    assert updated_me.status_code == 200
    assert updated_me.json()["display_name"] == "Security Owner"

    security = client.get("/v1/auth/me/security", headers=headers)
    assert security.status_code == 200
    body = security.json()
    assert body["password_login_enabled"] is True
    assert body["global_logout_available"] is True

    logout_all = client.post("/v1/auth/me/logout-all", headers=headers)
    assert logout_all.status_code == 200

    refresh = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 401


# ---------------------------------------------------------------------------
# GitHub OAuth — configuration guard
# ---------------------------------------------------------------------------

def test_github_start_returns_503_when_not_configured(client):
    resp = client.get("/v1/auth/github/start", follow_redirects=False)
    assert resp.status_code == 503
