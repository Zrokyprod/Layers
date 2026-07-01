from datetime import datetime

from pydantic import BaseModel, Field, field_validator


VALID_PROJECT_ROLES = {"owner", "admin", "member", "viewer"}
VALID_API_KEY_SCOPES = {"project:member"}


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    owner_ref: str | None = Field(default=None, max_length=128)


class ProjectDeleteRequest(BaseModel):
    confirm_project_name: str = Field(min_length=1, max_length=120)

    @field_validator("confirm_project_name")
    @classmethod
    def validate_confirm_project_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name confirmation must not be empty")
        return normalized


class ProjectUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name must not be empty")
        return normalized


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    owner_ref: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="Zroky API", min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["project:member"])
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("API key name must not be empty")
        return normalized

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip().lower() for item in value if item.strip()})
        if not normalized:
            return ["project:member"]
        unsupported = [item for item in normalized if item not in VALID_API_KEY_SCOPES]
        if unsupported:
            raise ValueError("API key scopes must be project:member.")
        return normalized


class ApiKeyCreateResponse(BaseModel):
    key_id: str
    project_id: str
    name: str
    key_prefix: str
    api_key: str
    scopes: list[str]
    expires_at: datetime | None
    rotated_from_key_id: str | None = None
    created_at: datetime


class ApiKeyResponse(BaseModel):
    key_id: str
    project_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    revoked: bool
    expired: bool
    expires_at: datetime | None
    rotated_from_key_id: str | None = None
    last_used_at: datetime | None
    created_at: datetime


class ProjectMembershipUpsertRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    role: str = Field(default="member", min_length=1, max_length=32)
    is_active: bool = True

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Subject must not be empty")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_PROJECT_ROLES:
            raise ValueError("Role must be one of owner, admin, member, viewer")
        return normalized


class ProjectMembershipResponse(BaseModel):
    membership_id: str
    project_id: str
    user_id: str
    subject: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectInviteRequest(BaseModel):
    email: str
    role: str = "member"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) < 3:
            raise ValueError("Invalid email address")
        return value


class ProjectInviteResponse(BaseModel):
    invited: bool
    message: str
    email: str
