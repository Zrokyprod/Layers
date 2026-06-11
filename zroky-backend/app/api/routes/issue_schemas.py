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


class IssueReplayProof(BaseModel):
    run_id: str | None = None
    status: str | None = None
    replay_mode: str | None = None
    verified_fix: bool = False
    summary_url: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class IssueGoldenProof(BaseModel):
    golden_set_id: str | None = None
    golden_set_name: str | None = None
    golden_trace_id: str | None = None
    status: str | None = None
    blocks_ci: bool = False
    trace_count: int = 0
    created_at: datetime | None = None


class IssueCiGateProof(BaseModel):
    run_id: str | None = None
    status: str | None = None
    git_sha: str | None = None
    summary_url: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class IssueProofSnapshot(BaseModel):
    replay: IssueReplayProof
    golden: IssueGoldenProof
    ci_gate: IssueCiGateProof


class IssueBlastRadius(BaseModel):
    affected_traces: int
    affected_users: int
    cost_usd: float
    severity: str


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
    what_happened: str
    why_it_matters: str
    affected_trace_count: int
    affected_user_count: int
    suspected_introduced_version: str | None
    blast_radius: IssueBlastRadius
    root_cause: str
    evidence_traces: list[IssueEvidenceTrace]
    cost_impact_usd: float
    user_impact: str
    replay_coverage_status: str
    recommended_next_action: str
    priority_score: float
    proof: IssueProofSnapshot


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    next_cursor: str | None
    total_in_page: int


class IssueResolveRequest(BaseModel):
    fix_id: str | None = None
    resolution_source: str = "manual"


class IssueGoldenPromotionRequest(BaseModel):
    golden_set_id: str | None = None
    expected_output_text: str | None = None
    criteria_json: str | None = None
    blocks_ci: bool = True


class IssueGoldenPromotionResponse(BaseModel):
    issue: IssueResponse
    golden: IssueGoldenProof


class IssueCiGateRequest(BaseModel):
    git_sha: str | None = None
    branch_name: str | None = None
    pr_number: int | None = None
    commit_message: str | None = None
    replay_mode: str | None = None


class IssueCiGateResponse(BaseModel):
    issue: IssueResponse
    ci_gate: IssueCiGateProof
