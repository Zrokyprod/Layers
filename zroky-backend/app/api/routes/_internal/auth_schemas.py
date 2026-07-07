import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_MIN_PW_LEN = 8

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


class MfaLoginChallengeResponse(BaseModel):
    mfa_required: bool = True
    challenge_token: str
    expires_in_seconds: int
    token_type: str = "mfa_challenge"
    user_id: str
    email: str | None
    email_verified: bool = True


class MfaLoginVerifyRequest(BaseModel):
    challenge_token: str
    code: str

    @field_validator("challenge_token")
    @classmethod
    def validate_challenge_token(cls, value: str) -> str:
        token = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,180}", token):
            raise ValueError("Invalid MFA challenge token.")
        return token

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        code = re.sub(r"\s+", "", value.strip())
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("MFA code must be 6 digits.")
        return code


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


class OAuthHandoffRequest(BaseModel):
    handoff_id: str

    @field_validator("handoff_id")
    @classmethod
    def validate_handoff_id(cls, value: str) -> str:
        handoff_id = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,160}", handoff_id):
            raise ValueError("Invalid OAuth handoff id.")
        return handoff_id


class SessionHandoffRequest(BaseModel):
    access_token: str
    refresh_token: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int
    token_type: str = "bearer"
    user_id: str | None = None
    email: str | None = None
    email_verified: bool = True

    @field_validator("access_token", "refresh_token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("Token is required.")
        return token

    @field_validator("access_expires_in_seconds", "refresh_expires_in_seconds")
    @classmethod
    def validate_expiry(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Token expiry must be positive.")
        return value


class SessionHandoffResponse(BaseModel):
    handoff_id: str



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


class CurrentUserProjectResponse(BaseModel):
    membership_id: str
    project_id: str
    project_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CurrentUserProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name must not be empty")
        return normalized


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MfaTotpStartResponse(BaseModel):
    secret: str
    otpauth_uri: str
    expires_in_seconds: int


class MfaTotpConfirmRequest(BaseModel):
    current_password: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        code = re.sub(r"\s+", "", value.strip())
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("MFA code must be 6 digits.")
        return code


class MfaTotpDisableRequest(BaseModel):
    current_password: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        code = re.sub(r"\s+", "", value.strip())
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("MFA code must be 6 digits.")
        return code


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
