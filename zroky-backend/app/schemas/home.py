from __future__ import annotations

from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field


class HomeSummaryMetrics(BaseModel):
    controlled_actions: int = Field(ge=0)
    pending_approvals: int = Field(ge=0)
    verified_outcomes: int = Field(ge=0)
    outcome_checks: int = Field(ge=0)
    receipts_generated: int = Field(ge=0)
    bypass_mutations: int = Field(ge=0)
    unreceipted_mutations: int = Field(ge=0)
    sequence_risks: int = Field(ge=0)


class HomeSummarySources(BaseModel):
    home_summary: bool = True
    intents: bool = True
    approvals: bool = True
    outcomes: bool = True
    outcome_summary: bool = True
    source_summary: bool = True
    mutations: bool = True
    stale_attempts: bool = True
    agent_profiles: bool = True
    action_runners: bool = True
    api_keys: bool = True
    billing_usage: bool = True


class HomeAgentProfileMeta(BaseModel):
    active_count: int = Field(ge=0)
    max_active_agents: int
    limit_reached: bool


class HomeSummaryData(BaseModel):
    intents: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[dict[str, Any]] = Field(default_factory=list)
    outcome_summary: dict[str, Any] | None = None
    source_summary: dict[str, Any] | None = None
    mutations: list[dict[str, Any]] = Field(default_factory=list)
    stale_attempts: list[dict[str, Any]] = Field(default_factory=list)
    agent_profiles: list[dict[str, Any]] = Field(default_factory=list)
    agent_profile_meta: HomeAgentProfileMeta | None = None
    action_runners: list[dict[str, Any]] = Field(default_factory=list)
    api_keys: list[dict[str, Any]] = Field(default_factory=list)
    billing_usage: dict[str, Any] | None = None


class HomeSummaryResponse(BaseModel):
    project_id: str
    window_days: int
    window_start: datetime
    generated_at: datetime
    metrics: HomeSummaryMetrics
    sources: HomeSummarySources = Field(default_factory=HomeSummarySources)
    data: HomeSummaryData = Field(default_factory=HomeSummaryData)
