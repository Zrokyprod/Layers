from __future__ import annotations

from datetime import datetime

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


class HomeSummaryResponse(BaseModel):
    project_id: str
    window_days: int
    window_start: datetime
    generated_at: datetime
    metrics: HomeSummaryMetrics
