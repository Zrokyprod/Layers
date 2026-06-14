"""
Auth routes — email/password registration + login + GitHub OAuth.

Endpoints:
    POST /v1/auth/register        — create account with email + password
    POST /v1/auth/login           — email + password -> JWT
    POST /v1/auth/refresh         — refresh token -> rotated JWT session bundle
    GET  /v1/auth/github/start    — redirect to GitHub OAuth
    GET  /v1/auth/github/callback — exchange code -> JWT
"""
import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes._internal.auth_current_user import (
    _decode_current_session_expiry,
    _get_current_user,
    _me_response,
)
from app.api.routes._internal.auth_oauth_clients import (
    _exchange_github_code,
    _exchange_google_code,
    _fetch_github_user,
    _fetch_google_user,
    _fetch_primary_github_email,
)
from app.api.routes._internal.auth_schemas import (
    AuthTokenResponse,
    ChangePasswordRequest,
    CurrentUserProjectResponse,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    OAuthHandoffRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SecurityStatusResponse,
    SessionHandoffRequest,
    SessionHandoffResponse,
    UpdateMeRequest,
)
from app.api.routes._internal.auth_tokens import (
    _consume_oauth_handoff,
    _email_verification_token_expired,
    _email_verification_token_filter,
    _issue_token,
    _require_auth_secret,
    _store_email_verification_token,
    _store_oauth_handoff,
    _validated_session_handoff_token,
)
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
    password_hash_needs_upgrade,
    verify_oauth_state,
    verify_password,
)

router = APIRouter(prefix="/v1/auth")

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

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
        email_verification_token=_store_email_verification_token(verification_token),
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
    normalized_token = token.strip()
    if not normalized_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
    user = db.execute(
        select(User).where(_email_verification_token_filter(normalized_token)).limit(1)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
    if user.email_verified_at is not None:
        return {"detail": "Email already verified."}
    if _email_verification_token_expired(user.email_verification_token):
        user.email_verification_token = None
        db.add(user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
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
    user.email_verification_token = _store_email_verification_token(token)
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
# OAuth handoff
# ---------------------------------------------------------------------------

@router.post("/session/handoff", response_model=SessionHandoffResponse)
@limiter.limit("30/minute")
def create_session_handoff(
    request: Request,
    body: SessionHandoffRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SessionHandoffResponse:
    token = _validated_session_handoff_token(body, db)
    return SessionHandoffResponse(handoff_id=_store_oauth_handoff(token))


@router.post("/oauth/handoff", response_model=AuthTokenResponse)
@limiter.limit("30/minute")
def complete_oauth_handoff(request: Request, body: OAuthHandoffRequest) -> AuthTokenResponse:
    return _consume_oauth_handoff(body.handoff_id)


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
    token_store.revoke_all_user_tokens(user.id)
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

@router.get(
    "/google/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses={status.HTTP_302_FOUND: {"description": "Redirect to dashboard OAuth handoff callback."}},
)
@limiter.limit("10/minute")
def google_oauth_callback(
    request: Request,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
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

    frontend_url = (settings.FRONTEND_URL or "https://zroky-dashboard.vercel.app").rstrip("/")
    handoff_id = _store_oauth_handoff(_issue_token(user))
    params = urlencode({
        "handoff_id": handoff_id,
    })
    return RedirectResponse(url=f"{frontend_url}/auth/oauth/callback?{params}", status_code=302)


@router.get("/me", response_model=MeResponse)
def get_current_user_profile(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> MeResponse:
    user = _get_current_user(authorization=authorization, db=db)
    return _me_response(user)


@router.get("/me/projects", response_model=list[CurrentUserProjectResponse])
def list_current_user_projects(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> list[CurrentUserProjectResponse]:
    user = _get_current_user(authorization=authorization, db=db)
    rows = db.execute(
        select(ProjectMembership, Project)
        .join(Project, Project.id == ProjectMembership.project_id)
        .where(
            ProjectMembership.user_id == user.id,
            ProjectMembership.is_active.is_(True),
            Project.is_active.is_(True),
        )
        .order_by(Project.name.asc(), ProjectMembership.created_at.asc(), ProjectMembership.id.asc())
    ).all()

    return [
        CurrentUserProjectResponse(
            membership_id=membership.id,
            project_id=membership.project_id,
            project_name=project.name,
            role=membership.role,
            is_active=membership.is_active,
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )
        for membership, project in rows
    ]


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
