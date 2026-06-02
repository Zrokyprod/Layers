"""
Auth routes — email/password registration + login + GitHub OAuth.

Endpoints:
    POST /v1/auth/register        — create account with email + password
    POST /v1/auth/login           — email + password -> JWT
    POST /v1/auth/refresh         — refresh token -> rotated JWT session bundle
    GET  /v1/auth/github/start    — redirect to GitHub OAuth
    GET  /v1/auth/github/callback — exchange code -> JWT
"""
import re
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import extract_bearer_token
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import Project, ProjectMembership, User, compute_email_hash
from app.db.session import get_db_session as get_db
from app.services import token_store
from app.services.email_sender import send_email
from app.services.security import (
    decode_session_token,
    generate_oauth_state,
    generate_project_id,
    hash_password,
    issue_access_token,
    issue_refresh_token,
    password_hash_needs_upgrade,
    verify_oauth_state,
    verify_password,
)

router = APIRouter(prefix="/v1/auth")

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_MIN_PW_LEN = 8
_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip().lower()):
            raise ValueError("Invalid email format.")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < _MIN_PW_LEN:
            raise ValueError(f"Password must be at least {_MIN_PW_LEN} characters.")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int
    token_type: str = "bearer"
    user_id: str
    email: str | None
    email_verified: bool = True


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("Refresh token is required.")
        return token


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


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
def register(request: Request, body: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> AuthTokenResponse:
    if body.password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Passwords do not match.",
        )

    existing = db.execute(select(User).where(User.email_hash == compute_email_hash(body.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    verification_token = secrets.token_urlsafe(48)
    user = User(
        subject=f"email:{body.email}",
        email=body.email,
        password_hash=hash_password(body.password),
        email_verification_token=verification_token,
    )
    db.add(user)
    db.flush()  # get user.id without committing

    # Auto-create a default project + owner membership so dashboard works immediately
    project = Project(
        id=generate_project_id(),
        name="My Project",
        owner_ref=user.subject,
    )
    db.add(project)
    db.flush()
    membership = ProjectMembership(
        project_id=project.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)
    db.commit()
    db.refresh(user)

    # Send verification email (non-blocking — failure doesn't prevent registration)
    settings = get_settings()
    frontend_url = (settings.FRONTEND_URL or "https://zroky-dashboard.vercel.app").rstrip("/")
    verify_url = f"{frontend_url}/auth/verify-email?token={verification_token}"
    send_email(
        to=[body.email],
        subject="Verify your Zroky AI email address",
        html_body=f"""
        <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px;">
          <h2 style="color:#111;">Welcome to Zroky AI!</h2>
          <p style="color:#444;">Please verify your email address to complete your registration.</p>
          <a href="{verify_url}" style="display:inline-block;margin:24px 0;padding:12px 28px;background:#4f46e5;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;">Verify Email</a>
          <p style="color:#888;font-size:13px;">This link expires in 24 hours. If you didn't create this account, you can ignore this email.</p>
        </div>
        """,
        plain_body=f"Welcome to Zroky AI! Verify your email: {verify_url}",
    )

    return _issue_token(user)


# ---------------------------------------------------------------------------
# Verify Email
# ---------------------------------------------------------------------------

@router.get("/verify-email")
@limiter.limit("10/minute")
def verify_email(
    request: Request,
    token: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    user = db.execute(
        select(User).where(User.email_verification_token == token)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
    if user.email_verified_at is not None:
        return {"detail": "Email already verified."}
    user.email_verified_at = datetime.now(UTC)
    user.email_verification_token = None
    db.commit()
    return {"detail": "Email verified successfully."}


# ---------------------------------------------------------------------------
# Resend Verification Email
# ---------------------------------------------------------------------------

@router.post("/resend-verification")
@limiter.limit("2/minute")
def resend_verification(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, str]:
    user = _get_current_user(authorization=authorization, db=db)
    if user.email_verified_at is not None:
        return {"detail": "Email is already verified."}
    if not user.email:
        raise HTTPException(status_code=400, detail="No email on this account.")
    token = secrets.token_urlsafe(48)
    user.email_verification_token = token
    db.commit()
    settings = get_settings()
    frontend_url = (settings.FRONTEND_URL or "https://zroky-dashboard.vercel.app").rstrip("/")
    verify_url = f"{frontend_url}/auth/verify-email?token={token}"
    send_email(
        to=[user.email],
        subject="Verify your Zroky AI email address",
        html_body=f"""
        <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px;">
          <h2 style="color:#111;">Verify your email</h2>
          <p style="color:#444;">Click below to verify your Zroky AI email address.</p>
          <a href="{verify_url}" style="display:inline-block;margin:24px 0;padding:12px 28px;background:#4f46e5;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;">Verify Email</a>
          <p style="color:#888;font-size:13px;">This link expires in 24 hours.</p>
        </div>
        """,
        plain_body=f"Verify your email: {verify_url}",
    )
    return {"detail": "Verification email sent."}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=AuthTokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> AuthTokenResponse:
    normalized_email = body.email.strip().lower()
    user = db.execute(
        select(User).where(User.email_hash == compute_email_hash(normalized_email))
    ).scalar_one_or_none()

    # Use constant-time check even when user not found (prevents timing oracle)
    dummy_hash = "$2b$12$" + "a" * 53
    stored_hash = user.password_hash if (user and user.password_hash) else dummy_hash
    password_ok = verify_password(body.password, stored_hash)

    if not user or not password_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    if user.password_hash and password_hash_needs_upgrade(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()

    return _issue_token(user)


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=AuthTokenResponse)
@limiter.limit("20/minute")
def refresh_token(
    request: Request,
    body: RefreshTokenRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AuthTokenResponse:
    secret = _require_auth_secret()

    try:
        claims = decode_session_token(body.refresh_token, secret, expected_use="refresh")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        ) from exc

    user_id = str(claims.get("user_id") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token user is no longer active.",
        )
    if token_store.get(f"jwt_blacklisted_user:{user.id}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="All sessions for this user have been revoked.",
        )

    return _issue_token(user)


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    # Always return 200 — never leak whether the email is registered.
    normalized = body.email.strip().lower()
    user = db.execute(select(User).where(User.email_hash == compute_email_hash(normalized))).scalar_one_or_none()

    if user and user.is_active:
        reset_token = secrets.token_urlsafe(32)
        token_store.set_with_ttl(f"pw_reset:{reset_token}", str(user.id), 3600)

        settings = get_settings()
        frontend = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        reset_link = f"{frontend}/auth/reset-password?token={reset_token}"
        send_email(
            to=[normalized],
            subject="Reset your Zroky password",
            html_body=(
                f"<p>Click the link below to reset your password. "
                f"It expires in 1 hour.</p>"
                f"<p><a href='{reset_link}'>{reset_link}</a></p>"
            ),
            plain_body=f"Reset your password: {reset_link}\n\nThis link expires in 1 hour.",
        )

    return {"message": "If that email is registered, a reset link was sent."}


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _require_auth_secret()

    user_id = token_store.get(f"pw_reset:{body.token}")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.commit()
    # Consume the token so it cannot be reused.
    token_store.delete(f"pw_reset:{body.token}")

    return {"message": "Password updated successfully."}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def logout(request: Request) -> dict:
    token = extract_bearer_token(request)
    if not token:
        return {"message": "Logged out."}

    try:
        secret = _require_auth_secret()
        claims = decode_session_token(token, secret)
    except Exception:  # noqa: BLE001
        return {"message": "Logged out."}

    jti = str(claims.get("jti") or "").strip()
    exp = claims.get("exp")
    if jti and isinstance(exp, (int, float)):
        remaining_ttl = max(1, int(exp - datetime.now(UTC).timestamp()))
        token_store.set_with_ttl(f"jwt_blacklisted:{jti}", "1", remaining_ttl)

    return {"message": "Logged out."}


# ---------------------------------------------------------------------------
# GitHub OAuth — start
# ---------------------------------------------------------------------------

@router.get("/github/start")
def github_oauth_start() -> RedirectResponse:
    settings = get_settings()
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured on this server.",
        )
    state_secret = settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or ""
    if not state_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is not configured.",
        )

    state = generate_oauth_state(state_secret)
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_OAUTH_REDIRECT_URL,
        "scope": "user:email",
        "state": state,
    }
    return RedirectResponse(url=f"{_GITHUB_AUTH_URL}?{urlencode(params)}")


# ---------------------------------------------------------------------------
# GitHub OAuth — callback
# ---------------------------------------------------------------------------

@router.get("/github/callback")
@limiter.limit("10/minute")
def github_oauth_callback(
    request: Request,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> AuthTokenResponse:
    settings = get_settings()
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured on this server.",
        )

    state_secret = settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or ""
    if not verify_oauth_state(state, state_secret):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try signing in again.",
        )

    # Exchange code for access token
    github_token = _exchange_github_code(
        code=code,
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        redirect_uri=settings.GITHUB_OAUTH_REDIRECT_URL,
    )

    # Fetch GitHub user profile
    github_user = _fetch_github_user(github_token)
    github_id = str(github_user["id"])
    github_login = github_user.get("login", "")
    github_email = github_user.get("email") or _fetch_primary_github_email(github_token)

    # Find or create user
    user = db.execute(
        select(User).where(User.github_id == github_id)
    ).scalar_one_or_none()

    if user is not None and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been deactivated.",
        )

    if user is None and github_email:
        # Check if email account exists — link GitHub to it
        user = db.execute(
            select(User).where(User.email_hash == compute_email_hash(github_email))
        ).scalar_one_or_none()
        if user is not None:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="This account has been deactivated.",
                )
            user.github_id = github_id
            user.github_login = github_login or user.github_login
            user.display_name = user.display_name or github_login

    if user is None:
        user = User(
            subject=f"github:{github_id}",
            email=github_email.lower() if github_email else None,
            github_id=github_id,
            github_login=github_login,
            display_name=github_login,
        )
        db.add(user)

    if user is not None and github_login:
        user.github_login = github_login
        if not user.display_name:
            user.display_name = github_login

    db.commit()
    db.refresh(user)
    return _issue_token(user)


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

# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

@router.get("/google/start")
def google_oauth_start() -> RedirectResponse:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server.",
        )
    state_secret = settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or ""
    if not state_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is not configured.",
        )

    state = generate_oauth_state(state_secret)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": state,
    }
    return RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{urlencode(params)}")

@router.get("/google/callback")
@limiter.limit("10/minute")
def google_oauth_callback(
    request: Request,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> AuthTokenResponse:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server.",
        )

    state_secret = settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or ""
    if not verify_oauth_state(state, state_secret):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try signing in again.",
        )

    # Exchange code for access token
    google_token = _exchange_google_code(
        code=code,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URL,
    )

    # Fetch Google user profile
    google_user = _fetch_google_user(google_token)
    google_id = str(google_user["id"])
    google_email = google_user.get("email")
    google_name = google_user.get("name")

    if not google_email:
        raise HTTPException(status_code=400, detail="Google account has no email.")

    # Find or create user
    user = db.execute(
        select(User).where(User.google_id == google_id)
    ).scalar_one_or_none()

    if user is not None and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been deactivated.",
        )

    if user is None:
        user = db.execute(
            select(User).where(User.email_hash == compute_email_hash(google_email))
        ).scalar_one_or_none()
        if user is not None:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="This account has been deactivated.",
                )
            user.google_id = google_id
            user.display_name = user.display_name or google_name

    if user is None:
        user = User(
            subject=f"google:{google_id}",
            email=google_email.lower(),
            google_id=google_id,
            display_name=google_name,
        )
        db.add(user)
    
    db.commit()
    db.refresh(user)

    # Redirect to frontend with tokens
    settings = get_settings()
    frontend_url = (settings.FRONTEND_URL or "https://zroky-dashboard.vercel.app").rstrip("/")
    token = _issue_token(user)
    params = urlencode({
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "expires_in": token.access_expires_in_seconds,
        "user_id": token.user_id,
    })
    return RedirectResponse(url=f"{frontend_url}/auth/oauth/callback?{params}", status_code=302)


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


# ---------------------------------------------------------------------------
# Me — current user profile
# ---------------------------------------------------------------------------

class MeResponse(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None
    github_login: str | None
    google_id: str | None
    has_password: bool
    is_active: bool
    email_verified: bool
    created_at: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateMeRequest(BaseModel):
    display_name: str | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 80:
            raise ValueError("Display name must be 80 characters or fewer.")
        return normalized


class SecurityStatusResponse(BaseModel):
    two_factor_enabled: bool
    password_login_enabled: bool
    github_connected: bool
    google_connected: bool
    current_session_expires_at: str | None = None
    global_logout_available: bool = True


class DeleteAccountRequest(BaseModel):
    confirm_email: str


def _get_current_user(authorization: str | None = None, db: Session | None = None) -> User:
    """Extract and validate Bearer token, return User."""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database session unavailable.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header.")
    token = authorization[len("Bearer "):]
    secret = _require_auth_secret()
    try:
        payload = decode_session_token(token, secret)
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


@router.get("/me", response_model=MeResponse)
def get_current_user_profile(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> MeResponse:
    user = _get_current_user(authorization=authorization, db=db)
    return _me_response(user)


@router.patch("/me", response_model=MeResponse)
@limiter.limit("10/minute")
def update_current_user_profile(
    request: Request,
    body: UpdateMeRequest,
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> MeResponse:
    user = _get_current_user(authorization=authorization, db=db)
    user.display_name = body.display_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return _me_response(user)


@router.patch("/me/password", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, str]:
    user = _get_current_user(authorization=authorization, db=db)

    # Must have a password to change it
    existing_hash = user.password_hash
    if not existing_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account uses OAuth login. Use 'Forgot Password' to set a password.",
        )

    if not verify_password(body.current_password, existing_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"detail": "Password changed successfully."}


@router.get("/me/security", response_model=SecurityStatusResponse)
def get_security_status(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> SecurityStatusResponse:
    user = _get_current_user(authorization=authorization, db=db)
    return SecurityStatusResponse(
        two_factor_enabled=False,
        password_login_enabled=bool(user.password_hash),
        github_connected=bool(user.github_id or user.github_login),
        google_connected=bool(user.google_id),
        current_session_expires_at=_decode_current_session_expiry(authorization),
        global_logout_available=True,
    )


@router.post("/me/logout-all", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")
def logout_all_sessions(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, str]:
    user = _get_current_user(authorization=authorization, db=db)
    token_store.revoke_all_user_tokens(user.id)
    return {"detail": "All sessions for this account have been revoked."}


@router.delete("/me", status_code=status.HTTP_200_OK)
@limiter.limit("2/hour")
def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, str]:
    user = _get_current_user(authorization=authorization, db=db)

    # Confirm email matches the authenticated user
    if not user.email or body.confirm_email.strip().lower() != user.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation email does not match your account email.",
        )

    # Soft-delete: deactivate the user and scrub PII
    user.is_active = False
    user.email = f"deleted_{user.id}@redacted.local"
    user.email_hash = None
    user.password_hash = None
    user.github_login = None
    user.github_id = None
    user.google_id = None
    user.display_name = None

    # Revoke all active tokens for this user
    token_store.revoke_all_user_tokens(user.id)

    db.commit()
    return {"detail": "Account deleted successfully."}
