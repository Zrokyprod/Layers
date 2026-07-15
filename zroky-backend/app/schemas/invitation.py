from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class ProjectInvitationResponse(BaseModel):
    invitation_id: str
    project_id: str
    email: str
    role: str
    invited_by_subject: str | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ProjectInvitationCreateRequest(BaseModel):
    email: str
    role: str = "member"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        normalized = v.strip().lower()
        local, separator, domain = normalized.partition("@")
        if (
            not separator
            or not local
            or not domain
            or "." not in domain
            or any(char.isspace() for char in normalized)
        ):
            raise ValueError("email must be a valid email address")
        if len(normalized) > 320:
            raise ValueError("email must be at most 320 characters")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in {"viewer", "member", "admin", "owner"}:
            raise ValueError("role must be one of: viewer, member, admin, owner")
        return normalized


class AcceptInvitationRequest(BaseModel):
    token: str


class AcceptInvitationResponse(BaseModel):
    success: bool
    message: str
    project_id: str | None = None
    membership_id: str | None = None
