import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import HomePage from "./page";

const api = vi.hoisted(() => ({
  createReplayRunFromIssue: vi.fn(),
  getAnalyticsSummary: vi.fn(),
  getBillingMe: vi.fn(),
  getCaptureHealth: vi.fn(),
  getReplayQuota: vi.fn(),
  listCalls: vi.fn(),
  listGoldenSets: vi.fn(),
  listIssues: vi.fn(),
  listProjectApiKeys: vi.fn(),
  listReplayRuns: vi.fn(),
  resolveIssue: vi.fn(),
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: { selectedProject: string }) => T) => selector({ selectedProject: "proj_1" }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function issue(overrides: Partial<import("@/lib/types").IssueItem> = {}): import("@/lib/types").IssueItem {
  return {
    id: "issue_1",
    project_id: "proj_1",
    failure_code: "LOOP_DETECTED",
    prompt_fingerprint: null,
    agent_name: "support-agent",
    status: "open",
    severity: "critical",
    occurrence_count: 42,
    blast_radius_usd: 12,
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
    title: "Checkout loop",
    affected_agent: "Checkout Agent",
    affected_workflow: null,
    root_cause: "Agent repeated the same tool call.",
    evidence_traces: [
      {
        call_id: "call_1",
        trace_id: "trace_1",
        workflow_name: "Checkout flow",
        prompt_version: null,
        model: "gpt-4.1",
        provider: "openai",
        status: "failed",
        latency_ms: 1600,
        cost_usd: 0.14,
        created_at: now,
        evidence_summary: "Loop repeated the same checkout tool call.",
      },
    ],
    cost_impact_usd: 18,
    user_impact: "Checkout users blocked",
    replay_coverage_status: "not_covered",
    recommended_next_action: "Replay",
    priority_score: 99,
    ...overrides,
  };
}

function replayRun(overrides: Partial<import("@/lib/api").ReplayRunItem> = {}): import("@/lib/api").ReplayRunItem {
  return {
    id: "run_1",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    git_sha: null,
    status: "pending",
    started_at: null,
    completed_at: null,
    summary: {
      trace_count_at_dispatch: 1,
      trace_count_executed: 0,
      pass_count: 0,
      fail_count: 0,
      error_count: 0,
      reproduced_original_failure: null,
      fix_passed: null,
      verified_fix: false,
      verification_status: "pending",
      output_diff: null,
      tool_behavior_diff: null,
      cost_delta_usd: null,
      latency_delta_ms: null,
      replay_cost_usd: null,
    },
    created_at: now,
    replay_mode: "stub",
    executor_replay_mode: "stub",
    replay_mode_warning: null,
    candidate_prompt_override: null,
    candidate_model_override: null,
    prevented_outcome_cost_usd: null,
    ...overrides,
  };
}

function goldenSet(overrides: Partial<import("@/lib/api").GoldenSetView> = {}): import("@/lib/api").GoldenSetView {
  return {
    id: "golden_1",
    project_id: "proj_1",
    name: "Checkout regression set",
    description: null,
    judge_config_json: null,
    is_flaky: false,
    blocks_ci: false,
    trace_count: 0,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function captureHealth(
  overrides: Partial<import("@/lib/types").CaptureHealthResponse> = {},
): import("@/lib/types").CaptureHealthResponse {
  return {
    project_id: "proj_1",
    status: "no_data",
    stale_after_minutes: 15,
    last_call_id: null,
    last_seen_at: null,
    seconds_since_last_call: null,
    last_provider: null,
    last_model: null,
    last_call_type: null,
    last_source: null,
    calls_24h: 0,
    sdk_events_24h: 0,
    gateway_events_24h: 0,
    retrieval_spans_24h: 0,
    memory_spans_24h: 0,
    trace_runs_24h: 0,
    trace_spans_24h: 0,
    policy_spans_24h: 0,
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
    outcome_events_24h: 0,
    sampled_recent_calls: 0,
    validation_warnings: [],
    ...overrides,
  };
}

function rowForIssueTitle(title: string): HTMLElement {
  const table = screen.getByRole("table");
  const row = within(table).getAllByText(title)[0]?.closest("tr");
  if (!row) throw new Error(`Missing table row for ${title}`);
  return row;
}

function summaryCard(label: string): HTMLElement {
  const card = screen.getByText(label).closest(".fi-kpi-card");
  if (!card) throw new Error(`Missing summary card ${label}`);
  return card as HTMLElement;
}

function mockInbox(
  planTemplate: Record<string, unknown>,
  issueItems: import("@/lib/types").IssueItem[] = [
    issue(),
    issue({
      id: "issue_2",
      title: "Answer drift",
      failure_code: "ACCURACY_REGRESSION",
      replay_coverage_status: "verified_fix",
      priority_score: 80,
    }),
  ],
) {
  api.listIssues.mockResolvedValue({
    items: issueItems,
    next_cursor: null,
    total_in_page: issueItems.length,
  });
  api.listReplayRuns.mockResolvedValue({
    items: [
      replayRun(),
      replayRun({
        id: "ci_1",
        golden_set_id: "regression-ci:proj_1",
        trigger: "github",
        status: "not_verified",
        git_sha: "abc123",
      }),
    ],
    next_cursor: null,
    total_in_page: 2,
  });
  api.listGoldenSets.mockResolvedValue({
    items: [goldenSet()],
    next_cursor: null,
    total_in_page: 1,
  });
  api.getBillingMe.mockResolvedValue({
    org_id: "org_1",
    plan_code: Object.keys(planTemplate).length === 0 ? "free" : "pro",
    status: "active",
    seats: 1,
    payment_provider: "razorpay",
    payment_customer_ref: null,
    payment_subscription_ref: null,
    payment_request_ref: null,
    current_period_end: null,
    trial_end: null,
    sla_tier: "standard",
    plan_template: planTemplate,
  });
  api.getReplayQuota.mockResolvedValue({
    enabled: Boolean(planTemplate["pilot.replay_stub"]),
    limit: 100,
    used: 4,
    resets_at: now,
    plan_code: "pro",
  });
  api.getAnalyticsSummary.mockResolvedValue({
    calls_today: 1200,
    calls_yesterday: 1000,
    cost_today_usd: 25,
    cost_yesterday_usd: 20,
    open_issues: 2,
    health_score: 80,
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
  });
  api.listCalls.mockResolvedValue({
    total: 0,
    limit: 10,
    offset: 0,
    items: [],
  });
  api.getCaptureHealth.mockResolvedValue(captureHealth());
  api.listProjectApiKeys.mockResolvedValue([
    {
      key_id: "key_1",
      project_id: "proj_1",
      name: "Default capture key",
      key_prefix: "zrk_live",
      scopes: ["capture:write"],
      revoked: false,
      expired: false,
      expires_at: null,
      rotated_from_key_id: null,
      last_used_at: null,
      created_at: now,
    },
  ]);
}

function call(overrides: Partial<import("@/lib/types").CallListItem> = {}): import("@/lib/types").CallListItem {
  return {
    call_id: "call_1",
    tenant_id: "proj_1",
    status: "ok",
    provider: "openai",
    model: "gpt-4.1",
    agent_name: "checkout-agent",
    user_id: null,
    call_type: "agent",
    total_tokens: 1200,
    cost_usd: 0.18,
    pricing_version: null,
    pricing_last_updated_at: null,
    pricing_age_days: null,
    cost_confidence: "estimated",
    latency_ms: 820,
    error_code: null,
    diagnoses: [],
    has_blast_radius: false,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function clearReplayAndGoldens() {
  api.listReplayRuns.mockResolvedValue({
    items: [],
    next_cursor: null,
    total_in_page: 0,
  });
  api.listGoldenSets.mockResolvedValue({
    items: [],
    next_cursor: null,
    total_in_page: 0,
  });
}

describe("Command Center home", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the active operations cockpit", async () => {
    mockInbox({
      "pilot.root_cause_diagnosis": true,
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
      "pro.ci_gate_nonblocking": true,
    });

    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "Evidence ledger", level: 1 })).toBeInTheDocument();
    expect((await screen.findAllByText("Checkout loop")).length).toBeGreaterThan(0);
    expect(screen.getByText("Release blocked")).toBeInTheDocument();
    expect(screen.getByText("1 gate failing on regression-ci:proj_1.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Command Center live status")).toBeNull();
    expect(screen.getAllByRole("button", { name: "Run replay" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open gate" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open issues" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("Loaded open issues")).toBeNull();
    expect(screen.queryByText("Replay mode")).toBeNull();
    expect(screen.queryByText("Silent failures detected")).toBeNull();

    const summary = screen.getByLabelText("Home summary");
    expect(document.querySelectorAll(".fi-kpi-card")).toHaveLength(5);
    expect(within(summaryCard("Failed evidence")).getByText("2")).toBeInTheDocument();
    expect(within(summaryCard("Open proof gaps")).getByText("2")).toBeInTheDocument();
    expect(within(summaryCard("Outcome verified")).getByText("0% verified")).toBeInTheDocument();
    expect(within(summaryCard("Blocked exports")).getByText("1")).toBeInTheDocument();
    expect(within(summaryCard("Spend drift")).getByText("+25% cost")).toBeInTheDocument();
    expect(summary).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Evidence ledger", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "Evidence ledger focus" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "All" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "P0/P1" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Proof gaps" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Impact" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Verified" })).toBeInTheDocument();
    expect(screen.getByText("Sorted by severity, exposure, and proof gaps.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Impact" }));
    expect(screen.getByRole("tab", { name: "Impact" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Showing evidence rows sorted by spend exposure.")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Priority",
      "Proof type",
      "Evidence item",
      "Exposure",
      "State",
      "Proof",
    ]);
    expect(within(rowForIssueTitle("Checkout loop")).getByText("Critical failure")).toBeInTheDocument();
    expect(within(rowForIssueTitle("Checkout loop")).getByText("Loop repeated the same checkout tool call.")).toBeInTheDocument();
    expect(within(rowForIssueTitle("Checkout loop")).getByText("$12.00")).toBeInTheDocument();
    expect(within(rowForIssueTitle("Checkout loop")).getByText("No trusted replay")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Evidence packs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download JSON" }).getAttribute("href")).toBe("/evidence");
    expect(screen.getByRole("heading", { name: "Proof gaps by connector" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Outcome verification chain" })).toBeInTheDocument();
    expect(screen.getAllByText("Open gate").length).toBeGreaterThan(0);
  });

  it("guides first users through the setup cockpit before capture", async () => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [],
    );
    clearReplayAndGoldens();
    api.listProjectApiKeys.mockResolvedValue([]);

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Create a project key" })).toBeInTheDocument();
    expect(screen.getByText("Capture your first agent run to start outcome proof.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Command Center live status")).toBeNull();
    expect(screen.getAllByRole("link", { name: /Create project key/i })[0]?.getAttribute("href")).toBe("/settings/keys");
    expect(screen.getByRole("heading", { name: "Connection health" })).toBeInTheDocument();
    expect(screen.getByText("API key")).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();
    expect(screen.getByText("Capture")).toBeInTheDocument();
    expect(screen.getAllByText("Waiting").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Setup progress" })).toBeInTheDocument();
    expect(screen.getByText("Project key")).toBeInTheDocument();
    expect(screen.getByText("SDK/Gateway connected")).toBeInTheDocument();
    expect(screen.getByText("First trace received")).toBeInTheDocument();
    expect(screen.getByText("First issue/replay ready")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Install SDK/i }).getAttribute("href")).toBe("/settings/keys");
    expect(screen.getByRole("link", { name: /Use Gateway/i }).getAttribute("href")).toBe("/settings/keys");
    expect(screen.getByRole("link", { name: /Send test capture/i }).getAttribute("href")).toBe("/trace");
    expect(screen.getByRole("heading", { name: "What happens next" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Evidence ledger", level: 3 })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open issues" })).toBeNull();
  });

  it("switches to operations mode after the first trace even with no issues", async () => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [],
    );
    clearReplayAndGoldens();
    api.listCalls.mockResolvedValue({
      total: 1,
      limit: 10,
      offset: 0,
      items: [call()],
    });
    api.getCaptureHealth.mockResolvedValue(captureHealth({ status: "connected", calls_24h: 1 }));

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Evidence ledger", level: 3 })).toBeInTheDocument();
    expect(screen.getByText("No proof gaps right now.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Command Center live status")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Setup progress" })).toBeNull();
  });

  it("does not show a refresh failure when free-plan replay and goldens are gated", async () => {
    mockInbox({}, []);
    api.listProjectApiKeys.mockResolvedValue([]);
    api.listReplayRuns.mockRejectedValue(
      new ApiError("GET", "/v1/replay/runs", 402, {
        message: "Your plan does not include 'pilot.autopilot_enabled'.",
        code: null,
      }),
    );
    api.listGoldenSets.mockRejectedValue(
      new ApiError("GET", "/v1/goldens", 402, {
        message: "Your plan does not include 'pilot.autopilot_enabled'.",
        code: null,
      }),
    );

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Create a project key" })).toBeInTheDocument();
    expect(screen.queryByText(/Partial refresh:/)).toBeNull();
  });

  it("renders Cost Impact values in priority rows and keeps cost trend visible", async () => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [
        issue({ blast_radius_usd: 12, cost_impact_usd: 18 }),
        issue({
          id: "issue_2",
          title: "Schema drift",
          failure_code: "SCHEMA_VIOLATION",
          blast_radius_usd: 7.5,
          cost_impact_usd: 30,
          replay_coverage_status: "verified_fix",
          priority_score: 80,
        }),
      ],
    );

    render(<HomePage />);

    await screen.findAllByText("Checkout loop");
    expect(within(rowForIssueTitle("Checkout loop")).getByText("$12.00")).toBeInTheDocument();
    expect(within(rowForIssueTitle("Schema drift")).getByText("$7.50")).toBeInTheDocument();
    expect(within(summaryCard("Spend drift")).getByText("+25% cost")).toBeInTheDocument();
    expect(screen.getByText("Capture traces to calculate latency.")).toBeInTheDocument();
  });

  it("uses estimated wasted AI cost when blast radius is missing", async () => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [issue({ blast_radius_usd: 0, cost_impact_usd: 3.25 })],
    );

    render(<HomePage />);

    await screen.findAllByText("Checkout loop");
    expect(within(rowForIssueTitle("Checkout loop")).getByText("$3.25")).toBeInTheDocument();
  });

  it("falls back to affected calls when cost impact is missing", async () => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [issue({ blast_radius_usd: 0, cost_impact_usd: 0 })],
    );

    render(<HomePage />);

    await screen.findAllByText("Checkout loop");
    expect(within(rowForIssueTitle("Checkout loop")).getByText("42 calls")).toBeInTheDocument();
  });

  it("shows upgrade gates for free users", async () => {
    mockInbox({});

    render(<HomePage />);

    expect((await screen.findAllByText("Checkout loop")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Upgrade").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Proof gaps by connector" })).toBeInTheDocument();
  });

  it("enables pilot replay and golden actions only for verified fixes", async () => {
    mockInbox({
      "pilot.root_cause_diagnosis": true,
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
    });

    render(<HomePage />);

    expect((await screen.findAllByText("Checkout loop")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Run replay").length).toBeGreaterThan(0);
    expect(within(rowForIssueTitle("Answer drift")).getByText("Open Contracts")).toBeInTheDocument();
    expect(within(rowForIssueTitle("Checkout loop")).queryByText("Open Contracts")).toBeNull();
  });

  it.each([
    ["covered_failed", "Replay failed"],
    ["sanity_replay_passed", "Fixture validation only"],
    ["real_replay_missing_tool_proof", "Missing tool proof"],
    ["stub_only", "Fixture validation only"],
    ["not_verified", "Not verified"],
    ["tool_snapshot_missing", "Missing tool proof"],
    ["inconclusive", "Inconclusive"],
    ["unknown_untrusted_state", "No trusted replay"],
  ])("routes untrusted replay status %s to replay instead of Contract promotion", async (status, label) => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [
        issue({
          replay_coverage_status: status,
          sample_call_id: "call_untrusted",
        }),
      ],
    );

    render(<HomePage />);

    await screen.findAllByText("Checkout loop");
    const row = rowForIssueTitle("Checkout loop");
    expect(within(row).queryByText("Open Contracts")).toBeNull();
    expect(within(row).getByRole("button", { name: /Run replay/i })).toBeInTheDocument();
    expect(within(row).getByText(label)).toBeInTheDocument();
  });

  it("treats not_verified CI gates as actionable for pro users", async () => {
    mockInbox({
      "pilot.root_cause_diagnosis": true,
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
      "pro.ci_gate_nonblocking": true,
    });

    render(<HomePage />);

    expect(await screen.findByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("CI failing")).toBeInTheDocument();
    expect(screen.getAllByText("Open gate").length).toBeGreaterThan(0);
  });
});
