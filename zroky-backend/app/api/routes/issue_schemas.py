"""Schemas for the customer-facing `/v1/issues` API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IssueEvidenceTrace(BaseModel):
    call_id: str | None
    trace_id: str | None
    workflow_name: str | None
    prompt_version: str | None
    model: str | None
    provider: str | None
    status: str | None
    latency_ms: float | None
    cost_usd: float
    created_at: datetime | None
    evidence_summary: str | None


class IssueResponse(BaseModel):
    id: str
    project_id: str
    failure_code: str
    prompt_fingerprint: str | None
    agent_name: str | None
    status: str
    severity: str
    occurrence_count: int
    blast_radius_usd: float
    first_seen_at: datetime
    last_seen_at: datetime
    sample_call_id: str | None
    sample_diagnosis_id: str | None
    last_fix_id: str | None
    resolved_at: datetime | None
    resolution_source: str | None
    assigned_to: str | None
    deploy_pr_url: str | None
    created_at: datetime
    updated_at: datetime

    title: str
    affected_agent: str | None
    affected_workflow: str | None
    root_cause: str
    evidence_traces: list[IssueEvidenceTrace]
    cost_impact_usd: float
    user_impact: str
    replay_coverage_status: str
    recommended_next_action: str
    priority_score: float


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    next_cursor: str | None
    total_in_page: int


class IssueResolveRequest(BaseModel):
    fix_id: str | None = None
    resolution_source: str = "manual"
