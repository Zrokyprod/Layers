from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeatureFlagResponse(BaseModel):
    id: str
    key: str
    description: str | None = None
    enabled_globally: bool
    enabled_tenants: list[str] = Field(default_factory=list)
    disabled_tenants: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, obj: Any) -> "FeatureFlagResponse":
        import json

        enabled = []
        disabled = []
        try:
            enabled = json.loads(obj.enabled_tenants_json or "[]")
        except Exception:
            pass
        try:
            disabled = json.loads(obj.disabled_tenants_json or "[]")
        except Exception:
            pass
        return cls(
            id=obj.id,
            key=obj.key,
            description=obj.description,
            enabled_globally=obj.enabled_globally,
            enabled_tenants=enabled,
            disabled_tenants=disabled,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class FeatureFlagListResponse(BaseModel):
    items: list[FeatureFlagResponse]


class FeatureFlagCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(None, max_length=5000)
    enabled_globally: bool = False


class FeatureFlagUpdateRequest(BaseModel):
    description: str | None = Field(None, max_length=5000)
    enabled_globally: bool | None = None
    add_enabled_tenants: list[str] = Field(default_factory=list)
    remove_enabled_tenants: list[str] = Field(default_factory=list)
    add_disabled_tenants: list[str] = Field(default_factory=list)
    remove_disabled_tenants: list[str] = Field(default_factory=list)


class TenantFeatureFlagsResponse(BaseModel):
    flags: dict[str, bool]
