from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FixEventType(str, Enum):
    SHOWN = "shown"
    COPIED = "copied"
    PR_GENERATED = "pr_generated"
    PR_MERGED = "pr_merged"
    APPLIED = "applied"
    RESOLVED = "resolved"
    IGNORED = "ignored"
    REGRESSED = "regressed"


class FixEventCreateRequest(BaseModel):
    fix_id: str = Field(min_length=1, max_length=128)
    diagnosis_id: str = Field(min_length=1, max_length=64)
    event_type: FixEventType
    source: str = Field(default="dashboard", min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fix_id", "diagnosis_id", "source", "idempotency_key", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return value.strip()


class FixResolutionStatus(BaseModel):
    resolved: bool
    resolution_confidence: float
    resolution_correlation: str
    attribution_mode: str
    confidence_calibration: str
    resolution_window: str
    checked_calls: int
    recurrence_count: int
    target_categories: list[str]
    reason: str


class FixEventCreateResponse(BaseModel):
    id: str
    project_id: str
    diagnosis_id: str
    fix_id: str
    event_type: FixEventType
    source: str
    idempotency_key: str
    timestamp: datetime
    metadata: dict[str, Any]
    resolution: FixResolutionStatus | None = None
