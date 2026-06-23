import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentScoreView, OutcomeReconciliationView, RuntimePolicyDecisionResponse } from "@/lib/api";
import type { AnalyticsSummaryResponse, CallListItem, CaptureHealthResponse, IssueItem } from "@/lib/types";
import AgentsPage from "./page";

const api = vi.hoisted(() => ({
  getAnalyticsSummary: vi.fn(),
  getCaptureHealth: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
  listCalls: vi.fn(),
  listIssues: vi.fn(),
}));

const leaderboardState = vi.hoisted(() => ({
  items: [] as unknown[],
}));

const leaderboardRefetch = vi.hoisted(() => ({
  fn: vi.fn(),
}));

const store = vi.hoisted(() => ({
  setSdkConnected: vi.fn(),
  dateRange: { from: null as Date | null, to: null as Date | null },
  realTimeEnabled: true,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

vi.mock("@/lib/hooks", () => ({
  useReliabilityLeaderboard: () => ({
    data: leaderboardState.items,
    isLoading: false,
    refetch: leaderboardRefetch.fn,
  }),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: {
    setSdkConnected: (value: boolean) => void;
    dateRange: { from: Date | null; to: Date | null };
    realTimeEnabled: boolean;
  }) => T) =>
    selector({
      setSdkConnected: store.setSdkConnected,
      dateRange: store.dateRange,
      realTimeEnabled: store.realTimeEnabled,
    }),
}));

const now = "2026-06-20T09:00:00.000Z";

function renderAgentsPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <AgentsPage />
    </QueryClientProvider>,
  );
}

function agentScore(overrides: Partial<AgentScoreView> = {}): AgentScoreView {
  return {
    agent_name: "Refund Agent",
    score_date: "2026-06-20",
    health_score: 42,
    fail_rate: 0.18,
    fail_rate_score: 52,
    cost_efficiency_score: 71,
    determinism_score: 64,
    regression_trend_score: 58,
    call_count: 2,
    avg_cost_usd: 0.22,
    p95_latency_ms: 1600,
    prev_week_fail_rate: 0.09,
    determinism_breakdown: null,
    top_failure_axis: "tool_call",
    computed_at: now,
    ...overrides,
  };
}

function call(overrides: Partial<CallListItem> = {}): CallListItem {
  return {
    call_id: "call_1",
    tenant_id: "proj_1",
    status: "success",
    provider: "openai",
    model: "gpt-4.1",
    agent_name: "Refund Agent",
    user_id: null,
    call_type: "agent",
    total_tokens: 1200,
    cost_usd: 0.25,
    pricing_version: null,
    pricing_last_updated_at: null,
    pricing_age_days: null,
    cost_confidence: "estimated",
    latency_ms: 900,
    error_code: null,
    diagnoses: [],
    has_blast_radius: false,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function issue(overrides: Partial<IssueItem> = {}): IssueItem {
  return {
    id: "issue_1",
    project_id: "proj_1",
    failure_code: "UNSAFE_ACTION",
    prompt_fingerprint: null,
    agent_name: "Refund Agent",
    status: "open",
    severity: "critical",
    occurrence_count: 3,
    blast_radius_usd: 18,
    first_seen_at: now,
    last_seen_at: now,
    sample_call_id: "call_1",
    sample_diagnosis_id: "diag_1",
    last_fix_id: null,
    resolved_at: null,
    resolution_source: null,
    assigned_to: null,
    deploy_pr_url: null,
    created_at: now,
    updated_at: now,
    title: "Refund action exceeded mandate",
    affected_agent: "Refund Agent",
    affected_workflow: "refund approval",
    root_cause: "Agent attempted a refund outside the mandate threshold.",
    evidence_traces: [
      {
        call_id: "call_1",
        trace_id: "trace_1",
        workflow_name: "Refund approval",
        prompt_version: "refund-v4",
        model: "gpt-4.1",
        provider: "openai",
        status: "failed",
        latency_ms: 1600,
        cost_usd: 0.31,
        created_at: now,
        evidence_summary: "Runtime policy found an unsafe refund action.",
      },
    ],
    cost_impact_usd: 18,
    user_impact: "Wrong refund could hit the ledger.",
    replay_coverage_status: "covered_not_run",
    recommended_next_action: "Run a replay before allowing the action path.",
    priority_score: 98,
    ...overrides,
  };
}

function runtimeDecision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "Refund Agent",
    role: "refund_ops",
    action_type: "refund",
    tool_name: "ledger.refund",
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["amount_requires_approval"],
    request: {},
    policy_snapshot: {},
    intended_action: {},
    trace_context: {},
    policy_hit: {},
    business_impact: {},
    audit_log: [],
    created_at: now,
    expires_at: null,
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    consumed_at: null,
    consumed_by_decision_id: null,
    ...overrides,
  };
}

function outcomeCheck(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "check_1",
    project_id: "proj_1",
    call_id: "call_1",
    trace_id: "trace_1",
    runtime_policy_decision_id: "decision_1",
    action_type: "refund",
    connector_type: "ledger_refund_api",
    system_ref: "ledger:RF-1001",
    verdict: "matched",
    reason: "all_compared_fields_matched",
    amount_usd: 18,
    currency: "USD",
    claimed: { refund_id: "RF-1001" },
    actual: { refund_id: "RF-1001" },
    comparison: { compared_fields: [], mismatches: [] },
    idempotency_key: "refund:RF-1001",
    metadata: {},
    checked_at: now,
    created_at: now,
    ...overrides,
  };
}

function captureHealth(
  overrides: Partial<CaptureHealthResponse> = {},
): CaptureHealthResponse {
  return {
    project_id: "proj_1",
    status: "connected",
    stale_after_minutes: 15,
    last_call_id: "call_1",
    last_seen_at: now,
    seconds_since_last_call: 45,
    last_provider: "openai",
    last_model: "gpt-4.1",
    last_call_type: "agent",
    last_source: "sdk_ingest",
    calls_24h: 17,
    sdk_events_24h: 17,
    gateway_events_24h: 0,
    retrieval_spans_24h: 0,
    memory_spans_24h: 0,
    trace_runs_24h: 2,
    trace_spans_24h: 4,
    policy_spans_24h: 3,
    handoff_spans_24h: 0,
    incomplete_trace_runs_24h: 0,
    projection_failures_24h: 0,
    gateway_count: 0,
    gateway_unhealthy_count: 0,
    gateway_worst_status: "unknown",
    gateway_spool_backlog: 0,
    gateway_spool_bytes: 0,
    gateway_spool_oldest_age_seconds: 0,
    gateway_loss_count: 0,
    gateway_backpressure_rejections: 0,
    gateway_last_heartbeat_at: null,
    error_events_24h: 0,
    outcome_events_24h: 2,
    sampled_recent_calls: 2,
    validation_warnings: [],
    ...overrides,
  };
}

function analyticsSummary(overrides: Partial<AnalyticsSummaryResponse> = {}): AnalyticsSummaryResponse {
  return {
    calls_today: 17,
    calls_yesterday: 12,
    cost_today_usd: 3.2,
    cost_yesterday_usd: 2.8,
    open_issues: 1,
    health_score: 72,
    fix_adoption: {
      viewed_diagnoses: 0,
      resolved_diagnoses: 0,
      adoption_rate_percent: 0,
      status_band: "warning",
    },
    feedback_loop: {
      feedback_total: 0,
      thumbs_down_total: 0,
      thumbs_down_rate_percent: 0,
      by_category: [],
    },
    unusual_activity: null,
    updated_at: now,
    ...overrides,
  };
}

function mockAgents({
  scores = [agentScore()],
  calls = [call(), call({ call_id: "call_2", status: "failed", cost_usd: 0.31, latency_ms: 1600 })],
  issues = [issue()],
  decisions = [runtimeDecision()],
  outcomes = [outcomeCheck()],
  capture = captureHealth(),
  summary = analyticsSummary(),
}: {
  scores?: AgentScoreView[];
  calls?: CallListItem[];
  issues?: IssueItem[];
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  capture?: CaptureHealthResponse;
  summary?: AnalyticsSummaryResponse;
} = {}) {
  leaderboardState.items = scores;
  api.listCalls.mockResolvedValue({
    total: calls.length,
    limit: 200,
    offset: 0,
    items: calls,
  });
  api.listIssues.mockResolvedValue({
    items: issues,
    next_cursor: null,
    total_in_page: issues.length,
  });
  api.listRuntimePolicyApprovals.mockResolvedValue({
    items: decisions,
    total_in_page: decisions.length,
  });
  api.listOutcomeReconciliations.mockResolvedValue({
    items: outcomes,
    total_in_page: outcomes.length,
  });
  api.getCaptureHealth.mockResolvedValue(capture);
  api.getAnalyticsSummary.mockResolvedValue(summary);
}

function protectedMatrix(): HTMLElement {
  const panel = screen.getByText("Needs your decision").closest("article");
  if (!panel) throw new Error("Missing protected agent matrix");
  return panel as HTMLElement;
}

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    leaderboardState.items = [];
    store.dateRange = { from: null, to: null };
    store.realTimeEnabled = true;
  });

  it("renders the protected-agent workflow with proof-first sections", async () => {
    mockAgents();

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Held actions pending", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Protected agents")).toBeInTheDocument();
    expect(screen.getByText("capture stream")).toBeInTheDocument();
    expect(screen.getByText("actions today")).toBeInTheDocument();
    expect(screen.getByText("needs review")).toBeInTheDocument();
    expect(screen.getByText("evidence ready")).toBeInTheDocument();

    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText("Held decisions")).toBeInTheDocument();
    expect(screen.getByText("Missing outcome proof")).toBeInTheDocument();
    expect(screen.getByText("Evidence ready")).toBeInTheDocument();

    expect(screen.getByText("Needs your decision")).toBeInTheDocument();
    expect(screen.getByText("Accountability loop")).toBeInTheDocument();
    expect(screen.getByText("System-of-record health")).toBeInTheDocument();
    expect(screen.getByText("Capture stream")).toBeInTheDocument();
    expect(screen.getByText("Outcome events")).toBeInTheDocument();
    expect(screen.getByText("Gateway backlog")).toBeInTheDocument();
    expect(screen.getByText("Capture warnings")).toBeInTheDocument();
    expect(screen.getByText("Selected agent proof")).toBeInTheDocument();
    expect((await screen.findAllByText("Refund action exceeded mandate")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Runtime decision").length).toBeGreaterThan(0);
    expect(screen.getByText("Outcome verdict")).toBeInTheDocument();
    expect((await screen.findAllByText("ledger_refund_api - ledger:RF-1001")).length).toBeGreaterThan(0);
    expect(screen.getByText("No evidence capture warnings.")).toBeInTheDocument();
    expect(screen.queryByText("Behavior drift by agent")).toBeNull();
    expect(screen.queryByText("Proof gap clusters")).toBeNull();
    expect(screen.queryByText("Evidence trail")).toBeNull();

    expect(screen.getAllByRole("link", { name: /Run replay/i })[0]?.getAttribute("href")).toBe("/replay");
    expect(screen.getByRole("link", { name: /Open connectors/i }).getAttribute("href")).toBe("/integrations");
    expect(screen.getByRole("link", { name: "View evidence trace" }).getAttribute("href")).toBe("/calls/call_1");
    expect(screen.getAllByRole("link", { name: "Review held action" })[0]?.getAttribute("href")).toBe("/approvals");
    expect(screen.getAllByRole("link", { name: /Evidence Pack/i })[0]?.getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
    expect(screen.getByRole("link", { name: /Export JSON/i }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
  });

  it("shows mandate/proof columns in the protected agent matrix", async () => {
    mockAgents();

    renderAgentsPage();

    await screen.findAllByText("Refund action exceeded mandate");
    const headers = within(protectedMatrix()).getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual([
      "Agent",
      "Mandate / risk",
      "Runtime decision",
      "Outcome proof",
      "Evidence readiness",
      "Impact",
      "Next step",
    ]);
    expect(within(protectedMatrix()).getByText("Refund Agent")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("Held / blocked")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("Health 42")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("HOLD")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("matched")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("Export ready")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByRole("link", { name: /Evidence Pack/i }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
    expect(within(protectedMatrix()).getByText("Refund action exceeded mandate")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByRole("link", { name: "Review held action" }).getAttribute("href")).toBe(
      "/approvals",
    );
  });

  it("uses the global dashboard date window for the agents summary", async () => {
    store.dateRange = {
      from: new Date("2026-06-01T00:00:00.000Z"),
      to: new Date("2026-06-15T00:00:00.000Z"),
    };
    store.realTimeEnabled = false;
    mockAgents();

    renderAgentsPage();

    await screen.findByText("Needs your decision");
    expect(api.getAnalyticsSummary.mock.calls[0]?.[0]).toBe(14);
  });

  it("shows protected agents instead of an empty default review queue", async () => {
    mockAgents({
      scores: [agentScore({ health_score: 91, fail_rate: 0.01, call_count: 1 })],
      calls: [call()],
      issues: [],
      decisions: [
        runtimeDecision({
          decision: "allow",
          status: "allowed",
          allowed: true,
          requires_approval: false,
        }),
      ],
      outcomes: [outcomeCheck()],
      summary: analyticsSummary({ open_issues: 0 }),
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Protected", level: 1 })).toBeInTheDocument();
    expect(await within(protectedMatrix()).findByText("Refund Agent")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("ALLOW")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("matched")).toBeInTheDocument();
    expect(screen.queryByText("No agents match this filter.")).toBeNull();
  });

  it("prioritizes mismatched outcomes over newer not verified checks", async () => {
    mockAgents({
      outcomes: [
        outcomeCheck({
          id: "check_mismatch",
          verdict: "mismatched",
          reason: "field_mismatch",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:RF-1001",
          checked_at: now,
          comparison: {
            compared_fields: ["refund_id", "amount_usd"],
            mismatches: [{ field: "amount_usd", claimed: 42.18, actual: 41.18 }],
          },
        }),
        outcomeCheck({
          id: "check_email_not_verified",
          runtime_policy_decision_id: null,
          action_type: "email",
          connector_type: "email_provider",
          system_ref: "email:refund-status-followup",
          verdict: "not_verified",
          reason: "system_of_record_missing",
          checked_at: "2026-06-20T09:05:00.000Z",
        }),
      ],
    });

    renderAgentsPage();

    await screen.findByText("Needs your decision");
    await screen.findAllByText("decision_1");
    expect(within(protectedMatrix()).getByText("mismatched")).toBeInTheDocument();
    expect(within(protectedMatrix()).getByText("ledger_refund_api - ledger:RF-1001")).toBeInTheDocument();
    expect(within(protectedMatrix()).queryByText("email_provider - email:refund-status-followup")).toBeNull();
  });

  it("keeps evidence capture warnings visible when proof quality is incomplete", async () => {
    mockAgents({
      capture: captureHealth({
        validation_warnings: [
          {
            code: "policy_decisions_missing",
            label: "Policy decisions missing",
            detail: "Runtime policy spans were not attached to the captured action.",
          },
        ],
      }),
    });

    renderAgentsPage();

    expect(await screen.findByText("Evidence capture quality")).toBeInTheDocument();
    expect(screen.getByText("Warnings that affect proof and attribution accuracy")).toBeInTheDocument();
    expect(screen.getByText("Policy decisions missing")).toBeInTheDocument();
    expect(screen.getByText("policy_decisions_missing")).toBeInTheDocument();
  });

  it("guides first users to connect a real agent action before rows exist", async () => {
    mockAgents({
      scores: [],
      calls: [],
      issues: [],
      decisions: [],
      outcomes: [],
      capture: captureHealth({
        status: "no_data",
        last_call_id: null,
        last_seen_at: null,
        seconds_since_last_call: null,
        calls_24h: 0,
        sdk_events_24h: 0,
        outcome_events_24h: 0,
      }),
      summary: analyticsSummary({ calls_today: 0, open_issues: 0 }),
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Setup required", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Protection setup")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Connect one real agent action to start proof." })).toBeInTheDocument();
    expect(screen.getByText(/At least one agent action ingested/)).toBeInTheDocument();
    expect(screen.getByText(/System-of-record connector selected/)).toBeInTheDocument();
    expect(screen.queryByText("Needs your decision")).toBeNull();
  });
});
