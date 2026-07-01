from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.agent_profiles import (
    SCHEMA_VERSION,
    VALID_RISKY_ACTION_TYPES,
    VALID_RUNTIME_PATHS,
    VALID_VERIFICATION_CONNECTORS,
    normalize_string_list,
)


class AgentProfileCreateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    runtime_path: str = Field(default="sdk", max_length=32)
    framework: str | None = Field(default=None, max_length=64)
    environment: str | None = Field(default=None, max_length=64)
    model_provider: str | None = Field(default=None, max_length=120)
    model_name: str | None = Field(default=None, max_length=120)
    tool_names: list[str] = Field(default_factory=list, max_length=100)
    allowed_action_types: list[str] = Field(default_factory=list, max_length=100)
    blocked_action_types: list[str] = Field(default_factory=list, max_length=100)
    default_policy_id: str | None = Field(default=None, max_length=36)
    risk_limits: dict[str, Any] = Field(default_factory=dict)
    verification_connectors: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name must not be empty")
        return cleaned

    @field_validator("runtime_path")
    @classmethod
    def _validate_runtime_path(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in VALID_RUNTIME_PATHS:
            raise ValueError(f"runtime_path must be one of: {', '.join(sorted(VALID_RUNTIME_PATHS))}")
        return cleaned

    @field_validator("tool_names")
    @classmethod
    def _normalize_tool_names(cls, value: list[str]) -> list[str]:
        return normalize_string_list(value, lower=False)

    @field_validator("allowed_action_types", "blocked_action_types")
    @classmethod
    def _validate_action_types(cls, value: list[str]) -> list[str]:
        cleaned = normalize_string_list(value, lower=True)
        invalid = sorted(set(cleaned) - VALID_RISKY_ACTION_TYPES)
        if invalid:
            raise ValueError(f"Unsupported action type: {', '.join(invalid)}")
        return cleaned

    @field_validator("verification_connectors")
    @classmethod
    def _validate_verification_connectors(cls, value: list[str]) -> list[str]:
        cleaned = normalize_string_list(value, lower=True)
        invalid = sorted(set(cleaned) - VALID_VERIFICATION_CONNECTORS)
        if invalid:
            raise ValueError(f"Unsupported verification connector: {', '.join(invalid)}")
        return cleaned

    @model_validator(mode="after")
    def _reject_action_overlap(self) -> "AgentProfileCreateRequest":
        overlap = sorted(set(self.allowed_action_types) & set(self.blocked_action_types))
        if overlap:
            raise ValueError(f"Action type cannot be both allowed and blocked: {', '.join(overlap)}")
        return self


class AgentProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    runtime_path: str | None = Field(default=None, max_length=32)
    framework: str | None = Field(default=None, max_length=64)
    environment: str | None = Field(default=None, max_length=64)
    model_provider: str | None = Field(default=None, max_length=120)
    model_name: str | None = Field(default=None, max_length=120)
    tool_names: list[str] | None = Field(default=None, max_length=100)
    allowed_action_types: list[str] | None = Field(default=None, max_length=100)
    blocked_action_types: list[str] | None = Field(default=None, max_length=100)
    default_policy_id: str | None = Field(default=None, max_length=36)
    risk_limits: dict[str, Any] | None = None
    verification_connectors: list[str] | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name must not be empty")
        return cleaned

    @field_validator("runtime_path")
    @classmethod
    def _validate_runtime_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in VALID_RUNTIME_PATHS:
            raise ValueError(f"runtime_path must be one of: {', '.join(sorted(VALID_RUNTIME_PATHS))}")
        return cleaned

    @field_validator("tool_names")
    @classmethod
    def _normalize_tool_names(cls, value: list[str] | None) -> list[str] | None:
        return normalize_string_list(value, lower=False) if value is not None else None

    @field_validator("allowed_action_types", "blocked_action_types")
    @classmethod
    def _validate_action_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = normalize_string_list(value, lower=True)
        invalid = sorted(set(cleaned) - VALID_RISKY_ACTION_TYPES)
        if invalid:
            raise ValueError(f"Unsupported action type: {', '.join(invalid)}")
        return cleaned

    @field_validator("verification_connectors")
    @classmethod
    def _validate_verification_connectors(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = normalize_string_list(value, lower=True)
        invalid = sorted(set(cleaned) - VALID_VERIFICATION_CONNECTORS)
        if invalid:
            raise ValueError(f"Unsupported verification connector: {', '.join(invalid)}")
        return cleaned


class AgentProfileResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    project_id: str
    display_name: str
    slug: str
    description: str | None
    runtime_path: str
    framework: str | None
    environment: str | None
    model_provider: str | None
    model_name: str | None
    tool_names: list[str]
    allowed_action_types: list[str]
    blocked_action_types: list[str]
    default_policy_id: str | None
    risk_limits: dict[str, Any]
    verification_connectors: list[str]
    metadata: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AgentProfileListResponse(BaseModel):
    items: list[AgentProfileResponse]
    total: int
    limit: int
    offset: int
    active_count: int
    max_active_agents: int
    limit_reached: bool
