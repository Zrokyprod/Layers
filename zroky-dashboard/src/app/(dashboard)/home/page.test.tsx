import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";

const api = vi.hoisted(() => ({
  createReplayRunFromIssue: vi.fn(),
  getAnalyticsSummary: vi.fn(),
  getBillingMe: vi.fn(),
  getReplayQuota: vi.fn(),
  listGoldenSets: vi.fn(),
  listIssues: vi.fn(),
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
    payment_provider: "skydo",
    payment_customer_ref: null,
    payment_subscription_ref: null,
    payment_request_ref: null,
    stripe_customer_id: null,
    stripe_sub_id: null,
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
}

describe("Failure Inbox home", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the action-first Failure Inbox command center", async () => {
    mockInbox({
      "pilot.root_cause_diagnosis": true,
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
      "pro.ci_gate_nonblocking": true,
    });

    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "Failure Inbox" })).toBeInTheDocument();
    expect((await screen.findAllByText("Checkout loop")).length).toBeGreaterThan(0);
    expect(screen.getByText("1 issues need trusted replay before they can become Goldens or block CI.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Run trusted replay" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "View all issues" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("Loaded open issues")).toBeNull();
    expect(screen.queryByText("Replay mode")).toBeNull();
    expect(screen.queryByText("Silent failures detected")).toBeNull();

    const nextBestAction = screen.getByLabelText("Next best action");
    const summary = screen.getByLabelText("Failure Inbox summary");
    expect(Boolean(nextBestAction.compareDocumentPosition(summary) & 4)).toBe(true);

    expect(document.querySelectorAll(".fi-kpi-card")).toHaveLength(4);
    expect(within(summaryCard("Critical & high")).getByText("2")).toBeInTheDocument();
    expect(within(summaryCard("Needs trusted replay")).getByText("1")).toBeInTheDocument();
    expect(within(summaryCard("Loaded issue impact")).getByText("$24.00")).toBeInTheDocument();
    expect(within(summaryCard("Verified fixes")).getByText("1")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Failure queue" })).toBeInTheDocument();
    expect(screen.getByText("Sorted by severity, impact, and replay trust gaps.")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Issue",
      "Impact",
      "Replay proof",
      "Last seen",
      "Action",
    ]);
    expect(within(table).queryByText("Severity")).toBeNull();
    expect(within(table).queryByText("Failure code")).toBeNull();
    expect(within(rowForIssueTitle("Checkout loop")).getByText(/Checkout Agent/)).toBeInTheDocument();
    expect(within(rowForIssueTitle("Checkout loop")).getByText(/42 affected calls/)).toBeInTheDocument();

    const detail = screen.getByLabelText("Selected issue detail");
    expect(within(detail).getByText("Issue #1")).toBeInTheDocument();
    expect(within(detail).getByText("Root cause")).toBeInTheDocument();
    expect(within(detail).getByText("Replay proof")).toBeInTheDocument();
    expect(within(detail).getByText("Cost impact")).toBeInTheDocument();
    expect(within(detail).getByText("Loop repeated the same checkout tool call.")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Trace evidence" })).toBeInTheDocument();
    expect(screen.getAllByText("Pending replay runs").length).toBeGreaterThan(0);
    expect(screen.getByText("Failed/not_verified CI gates")).toBeInTheDocument();
    expect(screen.getByText("Goldens needing review")).toBeInTheDocument();
    expect(screen.getByText("Usage/plan status")).toBeInTheDocument();
  });

  it("guides first users through capture before replay when no issues are loaded", async () => {
    mockInbox(
      {
        "pilot.root_cause_diagnosis": true,
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
      },
      [],
    );

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Capture your first agent failure." })).toBeInTheDocument();
    expect(screen.getByText("Start by capturing one agent call. Zroky turns failed runs into issues, stub replay, verified replay, Goldens, and CI gates.")).toBeInTheDocument();
    expect(screen.getByText("Provider keys are only needed later for verified replay.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create project key" }).getAttribute("href")).toBe("/settings/keys");
    expect(screen.getByRole("link", { name: "Confirm first trace" }).getAttribute("href")).toBe("/trace");
    expect(screen.getByRole("link", { name: "Open provider settings" }).getAttribute("href")).toBe("/settings/providers");
    expect(screen.getByLabelText("First run checklist")).toBeInTheDocument();
    expect(screen.queryByLabelText("Next best action")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Failure queue" })).toBeNull();
  });

  it("renders Cost Impact values and sums loaded issue impact", async () => {
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
    expect(within(summaryCard("Loaded issue impact")).getByText("$19.50")).toBeInTheDocument();
    expect(screen.getByText("Cost signal from loaded open issues.")).toBeInTheDocument();
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
    expect(within(summaryCard("Loaded issue impact")).getByText("$3.25")).toBeInTheDocument();
  });

  it("renders a dash when cost impact is missing", async () => {
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
    expect(within(rowForIssueTitle("Checkout loop")).getByText("\u2014")).toBeInTheDocument();
  });

  it("shows upgrade gates for free users", async () => {
    mockInbox({});

    render(<HomePage />);

    expect((await screen.findAllByText("Checkout loop")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Upgrade").length).toBeGreaterThan(0);
    expect(screen.getByText("Usage/plan status")).toBeInTheDocument();
  });

  it("enables pilot replay and golden actions only for verified fixes", async () => {
    mockInbox({
      "pilot.root_cause_diagnosis": true,
      "pilot.replay_stub": true,
      "pilot.goldens_basic": true,
    });

    render(<HomePage />);

    expect((await screen.findAllByText("Checkout loop")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Replay").length).toBeGreaterThan(0);
    expect(within(rowForIssueTitle("Answer drift")).getByText("Open Goldens")).toBeInTheDocument();
    expect(within(rowForIssueTitle("Checkout loop")).queryByText("Open Goldens")).toBeNull();
  });

  it.each([
    ["covered_failed", "Replay failed"],
    ["sanity_replay_passed", "Stub only"],
    ["real_replay_missing_tool_proof", "Missing tool proof"],
    ["stub_only", "Stub only"],
    ["not_verified", "Not verified"],
    ["tool_snapshot_missing", "Missing tool proof"],
    ["inconclusive", "Inconclusive"],
    ["unknown_untrusted_state", "No trusted replay"],
  ])("routes untrusted replay status %s to replay instead of Create Golden", async (status, label) => {
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
    expect(within(row).queryByText("Open Goldens")).toBeNull();
    expect(within(row).getByRole("button", { name: /Replay/i })).toBeInTheDocument();
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
    expect(screen.getByText("Review CI run")).toBeInTheDocument();
  });
});
