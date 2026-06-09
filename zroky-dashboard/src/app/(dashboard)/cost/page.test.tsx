import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReplayCreateResponse, ReplayRunItem } from "@/lib/api";
import type {
  BudgetConfigResponse,
  BudgetStatusResponse,
  CacheSavingsResponse,
  CostBreakdownResponse,
  CostDailyTrendResponse,
  CostTopCallsResponse,
  IssueItem,
  ReasoningShareResponse,
  SavingsSummaryResponse,
} from "@/lib/types";

import CostOverviewPage from "./page";

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

const reactQuery = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
  useQuery: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  callReplayMutate: vi.fn(),
  issueReplayMutate: vi.fn(),
  updateBudgetMutate: vi.fn(),
  useBudget: vi.fn(),
  useBudgetStatus: vi.fn(),
  useCacheSavings: vi.fn(),
  useCostByAgent: vi.fn(),
  useCostByModel: vi.fn(),
  useCostByUser: vi.fn(),
  useCostDailyTrend: vi.fn(),
  useCostTopCalls: vi.fn(),
  useCreateReplayRunFromCall: vi.fn(),
  useCreateReplayRunFromIssue: vi.fn(),
  useReasoningShare: vi.fn(),
  useReplayRuns: vi.fn(),
  useUpdateBudget: vi.fn(),
}));

const refetches = vi.hoisted(() => ({
  agents: vi.fn(),
  budget: vi.fn(),
  budgetStatus: vi.fn(),
  cache: vi.fn(),
  issues: vi.fn(),
  models: vi.fn(),
  replays: vi.fn(),
  reasoning: vi.fn(),
  savings: vi.fn(),
  topCalls: vi.fn(),
  trend: vi.fn(),
  users: vi.fn(),
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
  useRouter: () => router,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: reactQuery.useQuery,
  useQueryClient: () => ({
    invalidateQueries: reactQuery.invalidateQueries,
  }),
}));

vi.mock("@/lib/hooks", () => ({
  useBudget: hooks.useBudget,
  useBudgetStatus: hooks.useBudgetStatus,
  useCacheSavings: hooks.useCacheSavings,
  useCostByAgent: hooks.useCostByAgent,
  useCostByModel: hooks.useCostByModel,
  useCostByUser: hooks.useCostByUser,
  useCostDailyTrend: hooks.useCostDailyTrend,
  useCostTopCalls: hooks.useCostTopCalls,
  useCreateReplayRunFromCall: hooks.useCreateReplayRunFromCall,
  useCreateReplayRunFromIssue: hooks.useCreateReplayRunFromIssue,
  useReasoningShare: hooks.useReasoningShare,
  useReplayRuns: hooks.useReplayRuns,
  useUpdateBudget: hooks.useUpdateBudget,
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getSavingsSummary: vi.fn(),
    listIssues: vi.fn(),
  };
});

type QueryLike<T> = {
  data: T | undefined;
  error: Error | null;
  isFetching: boolean;
  isLoading: boolean;
  refetch: ReturnType<typeof vi.fn>;
};

type CostData = {
  agents: CostBreakdownResponse;
  budget: BudgetConfigResponse;
  budgetStatus: BudgetStatusResponse;
  cache: CacheSavingsResponse;
  issues: IssueItem[];
  models: CostBreakdownResponse;
  replays: ReplayRunItem[];
  reasoning: ReasoningShareResponse;
  savings: SavingsSummaryResponse;
  topCalls: CostTopCallsResponse;
  trend: CostDailyTrendResponse;
  users: CostBreakdownResponse;
};

const now = "2026-05-29T10:00:00.000Z";

let data: CostData;

function query<T>(payload: T | undefined, refetch: ReturnType<typeof vi.fn>, error: Error | null = null): QueryLike<T> {
  return {
    data: error ? undefined : payload,
    error,
    isFetching: false,
    isLoading: false,
    refetch,
  };
}

function issue(overrides: Partial<IssueItem> = {}): IssueItem {
  return {
    id: "issue_47",
    project_id: "proj_1",
    failure_code: "LOOP_DETECTED",
    prompt_fingerprint: null,
    agent_name: "refund-agent",
    status: "open",
    severity: "critical",
    occurrence_count: 312,
    blast_radius_usd: 0,
    first_seen_at: now,
    last_seen_at: now,
    sample_call_id: "call_1",
    sample_diagnosis_id: null,
    last_fix_id: null,
    resolved_at: null,
    resolution_source: null,
    assigned_to: null,
    deploy_pr_url: null,
    created_at: now,
    updated_at: now,
    title: "Refund agent loop",
    affected_agent: "Refund Agent",
    affected_workflow: null,
    root_cause: "Retry loop missing terminal condition",
    evidence_traces: [],
    cost_impact_usd: 620,
    user_impact: "Refund calls blocked",
    replay_coverage_status: "not_verified",
    recommended_next_action: "Replay",
    priority_score: 99,
    proof: null,
    ...overrides,
  };
}

function replayRun(overrides: Partial<ReplayRunItem> = {}): ReplayRunItem {
  return {
    id: "run_refund",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    git_sha: null,
    status: "pass",
    started_at: now,
    completed_at: now,
    summary: {
      trace_count_at_dispatch: 1,
      trace_count_executed: 1,
      pass_count: 1,
      fail_count: 0,
      error_count: 0,
      reproduced_original_failure: true,
      fix_passed: true,
      verified_fix: true,
      verification_status: "verified_fix",
      output_diff: null,
      tool_behavior_diff: null,
      cost_delta_usd: -0.12,
      latency_delta_ms: null,
      replay_cost_usd: 0.34,
    },
    created_at: now,
    replay_mode: "real_llm",
    executor_replay_mode: "real_llm",
    replay_mode_warning: null,
    candidate_prompt_override: null,
    candidate_model_override: null,
    prevented_outcome_cost_usd: null,
    ...overrides,
  };
}

function defaultCostData(): CostData {
  return {
    issues: [
      issue(),
      issue({
        id: "issue_2",
        title: "Billing timeout",
        affected_agent: "Billing Agent",
        cost_impact_usd: 120,
        occurrence_count: 44,
        replay_coverage_status: "verified_fix",
        severity: "high",
      }),
    ],
    trend: {
      days: 30,
      pricing_last_updated_at: now,
      pricing_source: "provider catalog",
      pricing_age_days: 0,
      cost_confidence: "known",
      confidence_reason: "Provider price table matched every model.",
      points: [
        { day: "2026-05-28", total_cost_usd: 10, call_count: 100, failed_cost_usd: 2, failed_call_count: 4 },
        { day: "2026-05-29", total_cost_usd: 15, call_count: 140, failed_cost_usd: 4, failed_call_count: 6 },
      ],
    },
    agents: {
      days: 30,
      items: [
        { key: "Refund Agent", total_cost_usd: 840, call_count: 420, failed_cost_usd: 120, failed_call_count: 12 },
        { key: "Billing Agent", total_cost_usd: 410, call_count: 200, failed_cost_usd: 0, failed_call_count: 0 },
      ],
    },
    models: {
      days: 30,
      items: [
        { key: "gpt-4.1", total_cost_usd: 900, call_count: 300, failed_cost_usd: 80, failed_call_count: 7 },
      ],
    },
    users: {
      days: 30,
      items: [
        { key: "user_1", total_cost_usd: 100, call_count: 30, failed_cost_usd: 10, failed_call_count: 2 },
      ],
    },
    savings: {
      window_days: 30,
      total_caught_count: 2,
      total_resolved_count: 1,
      cumulative_wasted_usd: 1340,
      cumulative_resolved_blast_usd: 120,
      projected_averted_usd: 620,
      affected_calls: 312,
      incidents_by_severity: { critical: 1 },
      updated_at: now,
    },
    replays: [replayRun()],
    budget: {
      monthly_limit_usd: 1000,
      threshold_percentage: 80,
      updated_at: now,
    },
    budgetStatus: {
      spent_usd: 250,
      limit_usd: 1000,
      percent_used: 25,
      days_remaining_in_period: 12,
      forecast_exhaust_in_days: null,
      status: "ok",
      forecast_risk_level: "low",
      forecast_recommendation: "Budget is healthy.",
    },
    topCalls: {
      window_hours: 720,
      items: [
        {
          call_id: "call_expensive_failed",
          model: "gpt-4.1",
          provider: "openai",
          cost_usd: 4.25,
          status: "failed",
          agent_name: "Refund Agent",
          user_id: "user_1",
          call_type: "tool_call",
          error_code: "LOOP_DETECTED",
          cost_confidence: "known",
          confidence_reason: "Matched model pricing.",
          pricing_source: "provider catalog",
          pricing_age_days: 0,
          created_at: now,
        },
        {
          call_id: "call_success",
          model: "claude-sonnet",
          provider: "anthropic",
          cost_usd: 1.2,
          status: "success",
          agent_name: "Billing Agent",
          user_id: "user_2",
          call_type: "chat",
          error_code: null,
          cost_confidence: "known",
          created_at: now,
        },
      ],
    },
    reasoning: {
      days: 30,
      total_cost_usd: 25,
      reasoning_cost_usd: 5,
      reasoning_share_percent: 20,
    },
    cache: {
      days: 30,
      total_cache_savings_usd: 18.75,
      points: [{ day: "2026-05-29", cache_savings_usd: 18.75 }],
    },
  };
}

function setupHookMocks() {
  reactQuery.useQuery.mockImplementation(({ queryKey }: { queryKey: unknown[] }) => {
    if (queryKey[0] === "issues") {
      return query({ items: data.issues, next_cursor: null, total_in_page: data.issues.length }, refetches.issues);
    }
    if (queryKey[0] === "savings") {
      return query(data.savings, refetches.savings);
    }
    return query(undefined, vi.fn());
  });
  hooks.useCostDailyTrend.mockImplementation((days: number) => query({ ...data.trend, days }, refetches.trend));
  hooks.useCostByAgent.mockImplementation((days: number) => query({ ...data.agents, days }, refetches.agents));
  hooks.useCostByModel.mockImplementation((days: number) => query({ ...data.models, days }, refetches.models));
  hooks.useCostByUser.mockImplementation((days: number) => query({ ...data.users, days }, refetches.users));
  hooks.useCostTopCalls.mockImplementation((limit: number, hours: number) =>
    query({ ...data.topCalls, window_hours: hours, items: data.topCalls.items.slice(0, limit) }, refetches.topCalls)
  );
  hooks.useReasoningShare.mockImplementation((days: number) => query({ ...data.reasoning, days }, refetches.reasoning));
  hooks.useCacheSavings.mockImplementation((days: number) => query({ ...data.cache, days }, refetches.cache));
  hooks.useBudget.mockImplementation(() => query(data.budget, refetches.budget));
  hooks.useBudgetStatus.mockImplementation(() => query(data.budgetStatus, refetches.budgetStatus));
  hooks.useReplayRuns.mockImplementation(() =>
    query({ items: data.replays, next_cursor: null, total_in_page: data.replays.length }, refetches.replays)
  );
  hooks.useUpdateBudget.mockImplementation(() => ({
    isPending: false,
    mutate: (
      vars: { monthly_limit_usd: number | null; threshold_percentage: number },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void },
    ) => {
      hooks.updateBudgetMutate(vars);
      options?.onSuccess?.();
    },
  }));
  hooks.useCreateReplayRunFromCall.mockImplementation((options?: { onSuccess?: (run: ReplayCreateResponse) => void }) => ({
    isPending: false,
    mutate: (vars: unknown) => {
      hooks.callReplayMutate(vars);
      options?.onSuccess?.({
        id: "run_from_call",
        project_id: "proj_1",
        golden_set_id: "golden_1",
        trigger: "manual",
        status: "pending",
        created_at: now,
        summary_url: "/v1/replay/runs/run_from_call",
        replay_mode: "real_llm",
      });
    },
  }));
  hooks.useCreateReplayRunFromIssue.mockImplementation((options?: { onSuccess?: (run: ReplayCreateResponse) => void }) => ({
    isPending: false,
    mutate: (vars: unknown) => {
      hooks.issueReplayMutate(vars);
      options?.onSuccess?.({
        id: "run_from_issue",
        project_id: "proj_1",
        golden_set_id: "golden_1",
        trigger: "manual",
        status: "pending",
        created_at: now,
        summary_url: "/v1/replay/runs/run_from_issue",
        replay_mode: "real_llm",
      });
    },
  }));
}

function kpi(label: string): HTMLElement {
  const overview = screen.getByLabelText("Cost overview");
  const labelNode = within(overview).getByText(label, { selector: ".cost-command-kpi-top > span" });
  const button = labelNode.closest("button");
  if (!button) throw new Error(`Missing KPI button for ${label}`);
  return button;
}

function rowByText(text: string): HTMLTableRowElement {
  const row = screen.getByText(text).closest("tr");
  if (!row) throw new Error(`Missing row for ${text}`);
  return row as HTMLTableRowElement;
}

function sectionByHeading(name: string): HTMLElement {
  const heading = screen.getByRole("heading", { name });
  const section = heading.closest("section");
  if (!section) throw new Error(`Missing section ${name}`);
  return section as HTMLElement;
}

describe("Cost page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    data = defaultCostData();
    Object.values(refetches).forEach((refetch) => refetch.mockResolvedValue({}));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    URL.createObjectURL = vi.fn(() => "blob:cost-export");
    URL.revokeObjectURL = vi.fn();
    HTMLAnchorElement.prototype.click = vi.fn();
    setupHookMocks();
  });

  it("renders the command-center shell, controls, KPIs, and key sections", async () => {
    const { container } = render(<CostOverviewPage />);

    expect(await screen.findByRole("heading", { name: "Cost" })).toBeInTheDocument();
    expect(container.querySelector(".cost-command")).toBeInTheDocument();
    expect(screen.getByText("See where AI failures burn money, prove which replays protected spend, and enforce live budget guardrails before repeat regressions ship.")).toBeInTheDocument();
    for (const name of ["Refresh", "Copy report", "Export JSON"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    for (const label of ["Failed runs wasted", "AI spend", "Replay spend", "Projected prevented impact", "Budget risk"]) {
      expect(kpi(label)).toBeInTheDocument();
    }
    for (const heading of ["Spend timeline", "Cost of failure", "Replay ROI", "Top expensive calls", "Cost breakdown", "Cost trust", "Budget guardrails"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
  });

  it("derives executive cost KPIs from live cost, savings, replay, and budget APIs", async () => {
    render(<CostOverviewPage />);

    await screen.findByRole("heading", { name: "Cost" });
    expect(within(kpi("Failed runs wasted")).getByText("$1,340.00")).toBeInTheDocument();
    expect(within(kpi("AI spend")).getByText("$25.00")).toBeInTheDocument();
    expect(within(kpi("Replay spend")).getByText("$0.34")).toBeInTheDocument();
    expect(within(kpi("Projected prevented impact")).getByText("$620.00")).toBeInTheDocument();
    expect(within(kpi("Budget risk")).getByText("Ok")).toBeInTheDocument();
    expect(screen.queryByText(/total saved/i)).not.toBeInTheDocument();
  });

  it("uses the selected window for live hooks and caps top-call hours at the backend guardrail", async () => {
    render(<CostOverviewPage />);

    await screen.findByRole("heading", { name: "Cost" });
    expect(hooks.useCostDailyTrend).toHaveBeenCalledWith(30);
    expect(hooks.useCostTopCalls).toHaveBeenCalledWith(12, 720);

    fireEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(hooks.useCostDailyTrend).toHaveBeenCalledWith(7);
    expect(hooks.useCostTopCalls).toHaveBeenCalledWith(12, 168);

    fireEvent.click(screen.getByRole("button", { name: "90d" }));
    expect(hooks.useCostDailyTrend).toHaveBeenCalledWith(90);
    expect(hooks.useCostTopCalls).toHaveBeenCalledWith(12, 720);
  });

  it("turns KPI cards into live lenses", async () => {
    render(<CostOverviewPage />);

    await screen.findByRole("heading", { name: "Cost" });
    expect(screen.getByText("Cost command center")).toBeInTheDocument();

    fireEvent.click(kpi("Failed runs wasted"));
    expect(screen.getByText("Failure cost focus")).toBeInTheDocument();
    expect(kpi("Failed runs wasted").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(kpi("Budget risk"));
    expect(screen.getByText("Budget focus")).toBeInTheDocument();
    expect(kpi("Budget risk").getAttribute("aria-pressed")).toBe("true");
  });

  it("renders issue rows with real replay dispatch instead of a fake replay link", async () => {
    render(<CostOverviewPage />);

    const row = rowByText("Refund agent loop");
    expect(within(row).getByText("LOOP_DETECTED / CRITICAL")).toBeInTheDocument();
    expect(within(row).getByText("312")).toBeInTheDocument();
    expect(within(row).getByText("$620.00")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "View issue" }).getAttribute("href")).toBe("/issues/issue_47");

    fireEvent.click(within(row).getByRole("button", { name: "Run replay" }));
    expect(hooks.issueReplayMutate).toHaveBeenCalledWith({
      issueId: "issue_47",
      payload: { replay_mode: "real_llm" },
    });
    expect(router.push).toHaveBeenCalledWith("/replay/run_from_issue");
  });

  it("renders top expensive calls with copy, view, and replay actions", async () => {
    render(<CostOverviewPage />);

    const row = rowByText("call_expensive_failed");
    expect(within(row).getByText("Refund Agent")).toBeInTheDocument();
    expect(within(row).getByText("Failed")).toBeInTheDocument();
    expect(within(row).getByText("LOOP_DETECTED")).toBeInTheDocument();
    expect(within(row).getByText("$4.25")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "View call" }).getAttribute("href")).toBe("/calls/call_expensive_failed");

    fireEvent.click(within(row).getByRole("button", { name: "Copy ID" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("call_expensive_failed"));

    fireEvent.click(within(row).getByRole("button", { name: "Replay" }));
    expect(hooks.callReplayMutate).toHaveBeenCalledWith({
      callId: "call_expensive_failed",
      payload: { replay_mode: "real_llm" },
    });
    expect(router.push).toHaveBeenCalledWith("/replay/run_from_call");
  });

  it("refreshes every live source and supports report copy/export", async () => {
    render(<CostOverviewPage />);

    await screen.findByRole("heading", { name: "Cost" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(refetches.issues).toHaveBeenCalledTimes(1));
    for (const refetch of Object.values(refetches)) {
      expect(refetch).toHaveBeenCalledTimes(1);
    }
    expect(screen.getByRole("status").textContent).toBe("Cost command center refreshed.");

    fireEvent.click(screen.getByRole("button", { name: "Copy report" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("Failed runs wasted: $1,340.00")));

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:cost-export");
  });

  it("saves the budget guardrail through the live budget mutation", async () => {
    render(<CostOverviewPage />);

    await screen.findByRole("heading", { name: "Budget guardrails" });
    fireEvent.change(screen.getByLabelText("Monthly budget USD"), { target: { value: "1500" } });
    fireEvent.change(screen.getByLabelText("Alert threshold"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Save budget" }));

    expect(hooks.updateBudgetMutate).toHaveBeenCalledWith({
      monthly_limit_usd: 1500,
      threshold_percentage: 75,
    });
    expect(await screen.findByText("Budget guardrail saved.")).toBeInTheDocument();
    expect(refetches.budgetStatus).toHaveBeenCalledTimes(1);
  });

  it("switches breakdown tabs across agent, model, and user spend", async () => {
    render(<CostOverviewPage />);

    const breakdown = sectionByHeading("Cost breakdown");
    expect(await within(breakdown).findByText("Refund Agent")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Model" }));
    expect(within(breakdown).getByText("gpt-4.1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "User" }));
    expect(within(breakdown).getByText("user_1")).toBeInTheDocument();
  });

  it("degrades missing issue, replay, and top-call data without showing fake savings", async () => {
    data.issues = [];
    data.replays = [];
    data.topCalls = { window_hours: 720, items: [] };
    setupHookMocks();

    render(<CostOverviewPage />);

    expect(await screen.findByText("No failure cost data yet. Link outcomes or capture failed calls to estimate cost of failure.")).toBeInTheDocument();
    expect(screen.getByText("No replay spend data available yet.")).toBeInTheDocument();
    expect(screen.getByText("No expensive calls recorded in this window.")).toBeInTheDocument();
    expect(screen.queryByText(/total saved/i)).not.toBeInTheDocument();
  });
});
