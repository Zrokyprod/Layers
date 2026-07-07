from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionsLifecycleSources(BaseModel):
    lifecycle_summary: bool = True
    intents: bool = True
    approvals: bool = True
    outcomes: bool = True
    outcome_summary: bool = True
    source_summary: bool = True
    mutations: bool = True
    stale_attempts: bool = True
    billing_usage: bool = True


class ActionsLifecycleMetrics(BaseModel):
    controlled_actions: int = Field(ge=0)
    held_actions: int = Field(ge=0)
    matched_outcomes: int = Field(ge=0)
    mismatched_outcomes: int = Field(ge=0)
    not_verified_outcomes: int = Field(ge=0)
    bypass_risk: int = Field(ge=0)


class ActionsLifecycleData(BaseModel):
    intents: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[dict[str, Any]] = Field(default_factory=list)
    outcome_summary: dict[str, Any] | None = None
    source_summary: dict[str, Any] | None = None
    mutations: list[dict[str, Any]] = Field(default_factory=list)
    stale_attempts: list[dict[str, Any]] = Field(default_factory=list)
    billing_usage: dict[str, Any] | None = None


class ActionsLifecycleSummaryResponse(BaseModel):
    project_id: str
    window_days: int
    window_start: datetime
    generated_at: datetime
    row_limit: int
    metrics: ActionsLifecycleMetrics
    sources: ActionsLifecycleSources = Field(default_factory=ActionsLifecycleSources)
    data: ActionsLifecycleData = Field(default_factory=ActionsLifecycleData)
