import { describe, expect, it } from "vitest";

import {
  buildCostExposureRows,
  buildSignalClusters,
  buildTimelineEntries,
  passingGuardrailRate,
  replayReadyCount,
  verifiedCostCoverage,
} from "./agents-console";
import type { CallListItem, IssueItem } from "./types";

function makeIssue(overrides: Partial<IssueItem> = {}): IssueItem {
  return {
    id: "issue-1",
    project_id: "project-1",
    failure_code: "TOOL_TIMEOUT",
    prompt_fingerprint: null,
    agent_name: "refund-agent",
    status: "open",
    severity: "high",
    occurrence_count: 4,
    blast_radius_usd: 120,
    first_seen_at: "2026-05-28T08:00:00Z",
    last_seen_at: "2026-05-28T08:30:00Z",
    sample_call_id: "call-1",
    sample_diagnosis_id: null,
    last_fix_id: null,
    resolved_at: null,
    resolution_source: null,
    assigned_to: null,
    deploy_pr_url: null,
    created_at: "2026-05-28T08:05:00Z",
    updated_at: "2026-05-28T08:30:00Z",
    title: "Refund agent loop",
    affected_agent: "refund-agent",
    affected_workflow: "refund-flow",
    root_cause: "Retry loop missing terminal condition",
    evidence_traces: [],
    cost_impact_usd: 310,
    user_impact: "Customers waited for retries",
    replay_coverage_status: "not_covered",
    recommended_next_action: "Add replay coverage",
    priority_score: 88,
    ...overrides,
  };
}

function makeCall(overrides: Partial<CallListItem> = {}): CallListItem {
  return {
    call_id: "call-1",
    tenant_id: "tenant-1",
    status: "failed",
    provider: "openai",
    model: "gpt-4.1-mini",
    agent_name: "refund-agent",
    user_id: "user-1",
    call_type: "agent",
    total_tokens: 1200,
    cost_usd: 0.48,
    pricing_version: null,
    pricing_last_updated_at: null,
    pricing_age_days: null,
    cost_confidence: null,
    latency_ms: 1820,
    error_code: "TOOL_TIMEOUT",
    diagnoses: [],
    has_blast_radius: true,
    created_at: "2026-05-28T08:00:00Z",
    updated_at: "2026-05-28T08:00:05Z",
    ...overrides,
  };
}

describe("replayReadyCount", () => {
  it("counts issues that are ready or currently running for replay", () => {
    const issues = [
      makeIssue({ replay_coverage_status: "covered_not_run" }),
      makeIssue({ id: "issue-2", replay_coverage_status: "fix_pending_replay" }),
      makeIssue({ id: "issue-3", replay_coverage_status: "verified_fix" }),
    ];

    expect(replayReadyCount(issues)).toBe(2);
  });
});

describe("passingGuardrailRate", () => {
  it("treats quiet agents and passing replay coverage as protected", () => {
    const rows = [
      { agentName: "refund-agent", latestIssue: makeIssue({ replay_coverage_status: "verified_fix" }) },
      { agentName: "billing-agent", latestIssue: null },
      { agentName: "order-agent", latestIssue: makeIssue({ id: "issue-2", replay_coverage_status: "not_covered" }) },
    ];

    expect(passingGuardrailRate(rows)).toBeCloseTo(66.666, 2);
  });
});

describe("verifiedCostCoverage", () => {
  it("sums only cost impact for issues with passing replay evidence", () => {
    const rows = [
      { agentName: "refund-agent", latestIssue: makeIssue({ replay_coverage_status: "verified_fix", cost_impact_usd: 120 }) },
      { agentName: "billing-agent", latestIssue: makeIssue({ id: "issue-2", replay_coverage_status: "covered_passed", cost_impact_usd: 80 }) },
      { agentName: "order-agent", latestIssue: makeIssue({ id: "issue-3", replay_coverage_status: "not_covered", cost_impact_usd: 300 }) },
    ];

    expect(verifiedCostCoverage(rows)).toBe(200);
  });
});

describe("buildCostExposureRows", () => {
  it("returns open issue cost exposure sorted descending", () => {
    const rows = [
      { agentName: "refund-agent", latestIssue: makeIssue({ cost_impact_usd: 110 }) },
      { agentName: "billing-agent", latestIssue: makeIssue({ id: "issue-2", cost_impact_usd: 410, title: "Billing failure" }) },
      { agentName: "order-agent", latestIssue: makeIssue({ id: "issue-3", cost_impact_usd: 0 }) },
    ];

    const result = buildCostExposureRows(rows);

    expect(result).toHaveLength(2);
    expect(result[0]?.agentName).toBe("billing-agent");
    expect(result[0]?.costUsd).toBe(410);
  });
});

describe("buildSignalClusters", () => {
  it("groups matching failures and aggregates occurrences and affected agents", () => {
    const issues = [
      makeIssue({ occurrence_count: 4, affected_agent: "refund-agent", agent_name: "refund-agent" }),
      makeIssue({
        id: "issue-2",
        occurrence_count: 3,
        severity: "critical",
        affected_agent: "billing-agent",
        agent_name: "billing-agent",
      }),
      makeIssue({
        id: "issue-3",
        title: "Policy refusal spike",
        failure_code: "POLICY_REFUSAL",
        occurrence_count: 2,
        severity: "medium",
      }),
    ];

    const result = buildSignalClusters(issues);

    expect(result[0]?.title).toBe("Refund agent loop");
    expect(result[0]?.occurrences).toBe(7);
    expect(result[0]?.affectedAgents).toBe(2);
    expect(result[0]?.severity).toBe("critical");
    expect(result[1]?.failureCode).toBe("POLICY_REFUSAL");
  });
});

describe("buildTimelineEntries", () => {
  it("prefers issue evidence traces when available", () => {
    const issue = makeIssue({
      evidence_traces: [
        {
          call_id: "call-9",
          trace_id: "trace-9",
          workflow_name: "refund workflow",
          prompt_version: null,
          model: "gpt-4.1-mini",
          provider: "openai",
          status: "failed",
          latency_ms: 2420,
          cost_usd: 0.62,
          created_at: "2026-05-28T08:12:00Z",
          evidence_summary: null,
        },
      ],
    });

    const result = buildTimelineEntries(issue, "refund-agent", [makeCall()]);

    expect(result[0]?.href).toBe("/evidence");
    expect(result[0]?.latencyMs).toBe(2420);
    expect(result[0]?.label).toBe("refund workflow");
  });

  it("falls back to recent calls when there is no issue evidence", () => {
    const result = buildTimelineEntries(null, null, [makeCall({ call_id: "call-7", latency_ms: 980 })]);

    expect(result[0]?.href).toBe("/evidence");
    expect(result[0]?.latencyMs).toBe(980);
    expect(result[0]?.label).toBe("refund-agent");
  });
});
