import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GoldenSetView, ReplayRunItem } from "@/lib/api";
import type { CallListItem, IssueItem } from "@/lib/types";

import ReplayPage from "./page";

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  issueMutate: vi.fn(),
  callMutate: vi.fn(),
}));

const api = vi.hoisted(() => ({
  createProviderKey: vi.fn(),
  runGoldenSet: vi.fn(),
  runRegressionCI: vi.fn(),
}));

const providerKeyState = vi.hoisted(() => ({
  active: true,
}));

const quotaState = vi.hoisted(() => ({
  data: { enabled: true, limit: 100, used: 8, resets_at: "2026-06-30", plan_code: "pro", real_comparison_enabled: true } as
    | { enabled: boolean; limit: number; used: number; resets_at: string; plan_code: string; real_comparison_enabled?: boolean }
    | undefined,
  error: null as Error | null,
  isError: false,
  isFetching: false,
  isLoading: false,
  refetch: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  issues: [] as IssueItem[],
  calls: [] as CallListItem[],
  goldenSets: [] as GoldenSetView[],
  runs: [] as ReplayRunItem[],
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
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listIssues: vi.fn(),
    listGoldenSets: vi.fn(),
    createProviderKey: api.createProviderKey,
    runGoldenSet: api.runGoldenSet,
    runRegressionCI: api.runRegressionCI,
  };
});

vi.mock("@/lib/hooks", () => ({
  useActiveProviderKeys: () => ({
    data: {
      items: providerKeyState.active
        ? [{ id: "key_1", provider: "openai", is_active: true }]
        : [],
      total_in_page: providerKeyState.active ? 1 : 0,
    },
    refetch: vi.fn(async () => ({
      data: {
        items: providerKeyState.active
          ? [{ id: "key_1", provider: "openai", is_active: true }]
          : [],
        total_in_page: providerKeyState.active ? 1 : 0,
      },
    })),
  }),
  useReplayQuota: () => ({
    data: quotaState.data,
    error: quotaState.error,
    isError: quotaState.isError,
    isFetching: quotaState.isFetching,
    isLoading: quotaState.isLoading,
    refetch: quotaState.refetch,
  }),
  useReplayRuns: () => ({
    data: { items: queryState.runs, next_cursor: null, total_in_page: queryState.runs.length },
    isLoading: false,
    error: null,
  }),
  useListCalls: () => ({
    data: { total: queryState.calls.length, limit: 20, offset: 0, items: queryState.calls },
    isLoading: false,
    error: null,
  }),
  useCreateReplayRunFromCall: (options?: {
    onSuccess?: (run: { id: string; project_id: string; golden_set_id: string; trigger: string; status: string; created_at: string; summary_url: string; replay_mode: string }) => void;
    onError?: (error: Error) => void;
  }) => ({
    mutate: (variables: unknown) => {
      hooks.callMutate(variables);
      options?.onSuccess?.({
        id: "run_call_1",
        project_id: "proj_1",
        golden_set_id: "golden_1",
        trigger: "manual",
        status: "pending",
        created_at: now,
        summary_url: "/v1/replay/runs/run_call_1",
        replay_mode: "real_llm",
      });
    },
    isPending: false,
  }),
  useCreateReplayRunFromIssue: (options?: {
    onSuccess?: (run: { id: string; project_id: string; golden_set_id: string; trigger: string; status: string; created_at: string; summary_url: string; replay_mode: string }) => void;
    onError?: (error: Error) => void;
  }) => ({
    mutate: (variables: unknown) => {
      hooks.issueMutate(variables);
      options?.onSuccess?.({
        id: "run_issue_1",
        project_id: "proj_1",
        golden_set_id: "golden_1",
        trigger: "manual",
        status: "pending",
        created_at: now,
        summary_url: "/v1/replay/runs/run_issue_1",
        replay_mode: "real_llm",
      });
    },
    isPending: false,
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: unknown[] }) => {
    if (queryKey[0] === "issues") {
      return {
        data: { items: queryState.issues, next_cursor: null, total_in_page: queryState.issues.length },
        isLoading: false,
        error: null,
      };
    }
    if (queryKey[0] === "golden-sets") {
      return {
        data: { items: queryState.goldenSets, next_cursor: null, total_in_page: queryState.goldenSets.length },
        isLoading: false,
        error: null,
      };
    }
    return { data: undefined, isLoading: false, error: null };
  }),
  useMutation: vi.fn((options: {
    mutationFn: (variables?: unknown) => unknown;
    onSuccess?: (data: unknown) => void;
    onError?: (error: Error) => void;
  }) => ({
    mutate: (variables?: unknown) => {
      Promise.resolve()
        .then(() => options.mutationFn(variables))
        .then((data) => options.onSuccess?.(data))
        .catch((error: Error) => options.onError?.(error));
    },
    isPending: false,
    isError: false,
  })),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

const now = "2026-06-01T10:00:00.000Z";

function issue(overrides: Partial<IssueItem> = {}): IssueItem {
  return {
    id: "issue_1",
    project_id: "proj_1",
    failure_code: "PAYMENT_TIMEOUT",
    prompt_fingerprint: "pf_1",
    agent_name: "checkout-agent",
    status: "open",
    severity: "high",
    occurrence_count: 12,
    blast_radius_usd: 1240,
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
    title: "Checkout payment timeout",
    affected_agent: "checkout-agent",
    affected_workflow: "checkout",
    root_cause: "Payment provider timed out.",
    evidence_traces: [],
    cost_impact_usd: 1240,
    user_impact: "Checkout failures",
    replay_coverage_status: "missing",
    recommended_next_action: "Replay failing checkout call",
    priority_score: 91,
    proof: null,
    ...overrides,
  };
}

function call(overrides: Partial<CallListItem> = {}): CallListItem {
  return {
    call_id: "call_1",
    tenant_id: "tenant_1",
    status: "failed",
    provider: "openai",
    model: "gpt-4.1",
    agent_name: "checkout-agent",
    user_id: "user_1",
    call_type: "chat",
    total_tokens: 500,
    cost_usd: 0.42,
    pricing_version: "2026-05",
    pricing_last_updated_at: now,
    pricing_age_days: 0,
    cost_confidence: "high",
    latency_ms: 1200,
    error_code: "PAYMENT_TIMEOUT",
    diagnoses: [],
    has_blast_radius: true,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function goldenSet(overrides: Partial<GoldenSetView> = {}): GoldenSetView {
  return {
    id: "golden_1",
    project_id: "proj_1",
    name: "Checkout regressions",
    description: null,
    judge_config_json: null,
    is_flaky: false,
    blocks_ci: true,
    trace_count: 3,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function replayRun(overrides: Partial<ReplayRunItem> = {}): ReplayRunItem {
  return {
    id: "run_1",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    git_sha: "abc1234",
    status: "pass",
    started_at: now,
    completed_at: now,
    created_at: now,
    replay_mode: "real_llm",
    executor_replay_mode: "real_llm",
    replay_mode_warning: null,
    candidate_prompt_override: null,
    candidate_model_override: null,
    prevented_outcome_cost_usd: 1240,
    source_context: {
      kind: "issue",
      id: "issue_1",
      call_id: "call_1",
      issue_id: "issue_1",
      title: "Checkout payment timeout",
      reason: "Payment provider timed out before receipt creation.",
      failure_code: "PAYMENT_TIMEOUT",
      severity: "high",
      affected_agent: "checkout-agent",
      affected_workflow: "checkout",
      occurrence_count: 12,
      last_seen_at: now,
      origin: "issue",
      confidence: null,
      discovery_signature: null,
    },
    summary: {
      trace_count_at_dispatch: 3,
      trace_count_executed: 3,
      pass_count: 3,
      fail_count: 0,
      error_count: 0,
      reproduced_original_failure: true,
      fix_passed: true,
      verified_fix: true,
      verification_status: "verified_fix",
      output_diff: null,
      tool_behavior_diff: null,
      cost_delta_usd: -0.2,
      latency_delta_ms: -100,
      replay_cost_usd: 0.31,
    },
    ...overrides,
  };
}

describe("ReplayPage command center", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    providerKeyState.active = true;
    quotaState.data = { enabled: true, limit: 100, used: 8, resets_at: "2026-06-30", plan_code: "pro", real_comparison_enabled: true };
    quotaState.error = null;
    quotaState.isError = false;
    quotaState.isFetching = false;
    quotaState.isLoading = false;
    queryState.issues = [issue()];
    queryState.calls = [call()];
    queryState.goldenSets = [goldenSet()];
    queryState.runs = [replayRun()];
    api.runGoldenSet.mockResolvedValue({
      id: "run_golden_1",
      project_id: "proj_1",
      golden_set_id: "golden_1",
      trigger: "manual",
      git_sha: null,
      status: "pending",
      created_at: now,
      summary_url: "/v1/replay/runs/run_golden_1",
      idempotent: false,
    });
    api.runRegressionCI.mockResolvedValue({
      run_id: "ci_run_1",
      project_id: "proj_1",
      git_sha: "abc1234",
      status: "queued",
      summary_url: "/v1/regression-ci/runs/ci_run_1",
    });
  });

  it("renders the live command center controls and proof queue", () => {
    render(<ReplayPage />);

    expect(screen.getByRole("heading", { name: "Replay" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Start replay" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Issue/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Call/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Golden Set/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PR \/ CI/ })).toBeInTheDocument();
    expect(screen.getByText("Protected spend")).toBeInTheDocument();
    expect(screen.getByText("Run run_1")).toBeInTheDocument();
    expect(screen.getAllByText("Payment provider timed out.").length).toBeGreaterThan(0);
    expect(screen.getByText("Payment provider timed out before receipt creation.")).toBeInTheDocument();
    expect(screen.getByLabelText("Replay proof composition")).toBeInTheDocument();
  });

  it("keeps the workspace visible but gates launch while quota is pending", () => {
    quotaState.data = undefined;
    quotaState.isLoading = true;
    quotaState.isFetching = true;

    render(<ReplayPage />);

    expect(screen.getByRole("heading", { name: "Replay" })).toBeInTheDocument();
    expect(screen.getByText("Checking replay quota")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Start replay" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("starts a replay from the highest priority issue", async () => {
    render(<ReplayPage />);

    fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

    await waitFor(() => expect(hooks.issueMutate).toHaveBeenCalledWith({
      issueId: "issue_1",
      payload: { replay_mode: "real_llm" },
    }));
    expect(router.push).toHaveBeenCalledWith("/replay/run_issue_1");
  });

  it("prompts for a provider key before verified replay when no active key exists", async () => {
    providerKeyState.active = false;
    render(<ReplayPage />);

    fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

    expect(await screen.findByText("Connect the matching provider key.")).toBeInTheDocument();
    expect(hooks.issueMutate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Use stub replay" }));

    expect(hooks.issueMutate).toHaveBeenCalledWith({
      issueId: "issue_1",
      payload: { replay_mode: "stub" },
    });
  });

  it("falls back to stub when real comparison is disabled", async () => {
    quotaState.data = {
      enabled: true,
      limit: 100,
      used: 8,
      resets_at: "2026-06-30",
      plan_code: "pro",
      real_comparison_enabled: false,
    };
    render(<ReplayPage />);

    await waitFor(() => {
      expect((screen.getByRole("button", { name: /stubsanity only/ }) as HTMLButtonElement).className).toContain("is-active");
    });
    expect((screen.getByRole("button", { name: /real_llmreal comparison/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

    await waitFor(() => expect(hooks.issueMutate).toHaveBeenCalledWith({
      issueId: "issue_1",
      payload: { replay_mode: "stub" },
    }));
  });

  it("starts a replay from a failed call with candidate overrides", async () => {
    render(<ReplayPage />);

    fireEvent.click(screen.getByRole("button", { name: /Call/ }));
    fireEvent.change(screen.getByPlaceholderText("optional"), { target: { value: "gpt-4.1-mini" } });
    fireEvent.change(screen.getByPlaceholderText("optional prompt patch"), { target: { value: "Retry payment once before failing." } });
    fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

    await waitFor(() => expect(hooks.callMutate).toHaveBeenCalledWith({
      callId: "call_1",
      payload: {
        replay_mode: "real_llm",
        candidate_model_override: "gpt-4.1-mini",
        candidate_prompt_override: "Retry payment once before failing.",
      },
    }));
    expect(router.push).toHaveBeenCalledWith("/replay/run_call_1");
  });

  it("sends the selected replay mode to Issue replay", async () => {
    render(<ReplayPage />);

    fireEvent.click(screen.getByRole("button", { name: /mocked-tool/ }));
    fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

    await waitFor(() => expect(hooks.issueMutate).toHaveBeenCalledWith({
      issueId: "issue_1",
      payload: { replay_mode: "mocked-tool" },
    }));
  });

  it("runs the selected Golden Set through the live replay endpoint", async () => {
    render(<ReplayPage />);

    fireEvent.click(screen.getByRole("button", { name: /Golden Set/ }));
    fireEvent.click(screen.getByRole("button", { name: "Start replay" }));

    await waitFor(() => expect(api.runGoldenSet).toHaveBeenCalledWith("golden_1", {
      trigger: "manual",
      replay_mode: "real_llm",
    }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/replay/run_golden_1"));
  });

  it("runs a commit-linked CI gate through the live regression endpoint", async () => {
    render(<ReplayPage />);

    fireEvent.click(screen.getByRole("button", { name: /PR \/ CI/ }));
    fireEvent.change(screen.getByPlaceholderText("abc1234"), { target: { value: "abc1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Run CI gate" }));

    await waitFor(() => expect(api.runRegressionCI).toHaveBeenCalledWith({
      git_sha: "abc1234",
      sample_window_days: 30,
    }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/ci-gates/ci_run_1"));
  });
});
