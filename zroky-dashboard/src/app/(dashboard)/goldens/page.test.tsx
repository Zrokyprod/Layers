import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GoldenSetView, ReplayRunItem } from "@/lib/api";

import GoldensPage from "./page";

const api = vi.hoisted(() => ({
  createGoldenSet: vi.fn(),
  getBillingMe: vi.fn(),
  listGoldenSets: vi.fn(),
  listReplayRuns: vi.fn(),
  runGoldenSet: vi.fn(),
}));

const nav = vi.hoisted(() => ({
  push: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  planTemplate: { "pilot.goldens_basic": true, "pro.ci_gate_blocking": true } as Record<string, unknown>,
  planCode: "pro",
  sets: [] as GoldenSetView[],
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
  useRouter: () => nav,
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: unknown[] }) => {
    const key = queryKey[0];
    if (key === "billing-me") {
      return {
        data: {
          plan_template: queryState.planTemplate,
          plan_code: queryState.planCode,
          status: "active",
        },
        isLoading: false,
        error: null,
      };
    }
    if (key === "golden-sets") {
      return {
        data: { items: queryState.sets, next_cursor: null, total_in_page: queryState.sets.length },
        isLoading: false,
        error: null,
      };
    }
    if (key === "replay-runs") {
      return {
        data: { items: queryState.runs, next_cursor: null, total_in_page: queryState.runs.length },
        isLoading: false,
        error: null,
      };
    }
    return { data: undefined, isLoading: false, error: null };
  }),
  useMutation: vi.fn((options: {
    mutationFn: (variables?: unknown) => unknown;
    onSuccess?: (data: unknown, variables?: unknown) => void;
    onError?: (error: Error, variables?: unknown) => void;
  }) => ({
    mutate: (variables?: unknown) => {
      Promise.resolve()
        .then(() => options.mutationFn(variables))
        .then((data) => options.onSuccess?.(data, variables))
        .catch((error: Error) => options.onError?.(error, variables));
    },
    isPending: false,
    error: null,
  })),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

const now = "2026-05-29T10:00:00.000Z";

function goldenSet(overrides: Partial<GoldenSetView> = {}): GoldenSetView {
  return {
    id: "golden_1",
    project_id: "proj_1",
    name: "Refund protected flow",
    description: "Refund agent verified behavior",
    judge_config_json: JSON.stringify({ source_issue_id: "issue_47" }),
    is_flaky: false,
    blocks_ci: true,
    trace_count: 12,
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
    git_sha: null,
    status: "pass",
    started_at: now,
    completed_at: now,
    created_at: now,
    replay_mode: "real_llm",
    executor_replay_mode: "real_llm",
    replay_mode_warning: null,
    candidate_prompt_override: null,
    candidate_model_override: null,
    prevented_outcome_cost_usd: null,
    summary: {
      trace_count_at_dispatch: 12,
      trace_count_executed: 12,
      pass_count: 11,
      fail_count: 1,
      error_count: 0,
      reproduced_original_failure: true,
      fix_passed: true,
      verified_fix: true,
      verification_status: "verified_fix",
      output_diff: null,
      tool_behavior_diff: null,
      cost_delta_usd: null,
      latency_delta_ms: null,
      replay_cost_usd: 0.24,
    },
    ...overrides,
  };
}

function mockGoldens({
  sets = [goldenSet(), goldenSet({ id: "golden_2", name: "Refund regression set", description: null, trace_count: 0, blocks_ci: false })],
  runs = [replayRun(), replayRun({ id: "run_2", golden_set_id: "golden_2", status: "not_verified", summary: { ...replayRun().summary, pass_count: 0, fail_count: 1, verification_status: "not_verified" } })],
  planTemplate = { "pilot.goldens_basic": true, "pro.ci_gate_blocking": true },
  planCode = "pro",
}: {
  sets?: GoldenSetView[];
  runs?: ReplayRunItem[];
  planTemplate?: Record<string, unknown>;
  planCode?: string;
} = {}) {
  queryState.sets = sets;
  queryState.runs = runs;
  queryState.planTemplate = planTemplate;
  queryState.planCode = planCode;
  api.createGoldenSet.mockResolvedValue(goldenSet({ id: "created_set" }));
  api.runGoldenSet.mockResolvedValue({
    id: "run_new",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    git_sha: null,
    status: "pending",
    created_at: now,
    summary_url: "/replay/run_new",
    idempotent: false,
  });
}

describe("Fixtures compatibility page MVP list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGoldens();
  });

  it("renders header, CTAs, KPI cards, trust copy, and required columns", () => {
    render(<GoldensPage />);

    expect(screen.getByRole("heading", { name: "Fixtures" })).toBeInTheDocument();
    expect(screen.getByText("Verified production behaviors used as Contract evidence and replay fixtures.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run fixture set" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create set" })).toBeInTheDocument();
    for (const label of ["Active fixtures", "Blocking CI", "Need review", "Last pass rate"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Only verified replay fixes can become active Contracts.")).toBeInTheDocument();

    const table = screen.getByRole("table");
    for (const heading of ["Fixture set", "Traces", "Last run", "CI blocking", "Health", "Action"]) {
      expect(within(table).getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
  });

  it("renders rows with clear CI blocking and health labels", () => {
    render(<GoldensPage />);

    expect(screen.getByText("Refund protected flow")).toBeInTheDocument();
    expect(screen.getByText("Refund agent verified behavior")).toBeInTheDocument();
    expect(screen.getByText("Blocks CI")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("Refund regression set")).toBeInTheDocument();
    expect(screen.getByText("Needs traces")).toBeInTheDocument();
    expect(screen.getAllByText("Not blocking").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Run" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "View" }).length).toBeGreaterThan(0);
  });

  it("renders empty state with Replay CTA", () => {
    mockGoldens({ sets: [], runs: [] });

    render(<GoldensPage />);

    expect(screen.getByText("No fixtures yet")).toBeInTheDocument();
    expect(screen.getByText("Create a fixture from a verified replay, then approve a Contract to protect that flow in future CI runs.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Replay" }).getAttribute("href")).toBe("/replay");
  });

  it("shows Upgrade to Starter only for Free and Watch plans", () => {
    for (const planCode of ["free", "watch"]) {
      mockGoldens({ planTemplate: {}, planCode });
      const { unmount } = render(<GoldensPage />);

      expect(screen.getByText("Fixtures locked")).toBeInTheDocument();
      expect(screen.getByText("Upgrade to Starter to create protected flows from verified replay evidence.")).toBeInTheDocument();

      unmount();
    }
  });

  it("does not show the locked banner for paid fixture plans", () => {
    for (const planCode of ["pilot", "starter", "pro", "plus", "enterprise"]) {
      mockGoldens({ planTemplate: {}, planCode });
      const { unmount } = render(<GoldensPage />);

      expect(screen.queryByText("Fixtures locked")).not.toBeInTheDocument();
      expect(screen.queryByText("Upgrade to Starter to create protected flows from verified replay evidence.")).not.toBeInTheDocument();

      unmount();
    }
  });

  it("shows entitlement unavailable copy for inconsistent Pro entitlement data", () => {
    mockGoldens({ planTemplate: {}, planCode: "pro" });

    render(<GoldensPage />);

    expect(screen.queryByText("Upgrade to Starter to create protected flows from verified replay evidence.")).not.toBeInTheDocument();
    expect(screen.getByText("Fixtures entitlement unavailable")).toBeInTheDocument();
    expect(screen.getByText("Refresh workspace plan or contact admin.")).toBeInTheDocument();
  });

  it("disables header CTAs when entitlement data is unavailable", () => {
    mockGoldens({ planTemplate: {}, planCode: "pro" });

    render(<GoldensPage />);

    const runButton = screen.getByRole("button", { name: "Run fixture set" }) as HTMLButtonElement;
    const createButton = screen.getByRole("button", { name: "Create set" }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
    expect(createButton.disabled).toBe(true);
    expect(runButton.getAttribute("title")).toBe("Plan entitlement unavailable. Refresh workspace plan or contact admin.");
    expect(createButton.getAttribute("title")).toBe("Plan entitlement unavailable. Refresh workspace plan or contact admin.");
  });

  it("replaces Replay CTA with entitlement copy when entitlement data is unavailable", () => {
    mockGoldens({ sets: [], runs: [], planTemplate: {}, planCode: "pro" });

    render(<GoldensPage />);

    expect(screen.queryByRole("link", { name: "Go to Replay" })).not.toBeInTheDocument();
    expect(screen.getByText("Replay and fixture creation require an active Starter or Pro entitlement.")).toBeInTheDocument();
  });

  it("keeps normal CTAs for Pro with valid fixture entitlement", () => {
    mockGoldens({ planTemplate: { "pilot.goldens_basic": true, "pro.ci_gate_blocking": true }, planCode: "pro" });

    render(<GoldensPage />);

    expect((screen.getByRole("button", { name: "Run fixture set" }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: "Create set" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("runs a fixture set from row action", async () => {
    render(<GoldensPage />);

    fireEvent.click(screen.getAllByRole("button", { name: "Run" })[0]);

    await waitFor(() => expect(api.runGoldenSet).toHaveBeenCalledWith("golden_1", { trigger: "manual" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/replay/run_new"));
  });

  it("runs the selected fixture set from the header and opens Replay proof", async () => {
    render(<GoldensPage />);

    fireEvent.change(screen.getByLabelText("Run set"), { target: { value: "golden_1" } });
    fireEvent.click(screen.getByRole("button", { name: "Run fixture set" }));

    await waitFor(() => expect(api.runGoldenSet).toHaveBeenCalledWith("golden_1", { trigger: "manual" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/replay/run_new"));
  });

  it("filters fixture sets by search and KPI cards", () => {
    render(<GoldensPage />);

    fireEvent.change(screen.getByPlaceholderText("Search fixture sets..."), { target: { value: "regression" } });

    expect(screen.queryByText("Refund protected flow")).not.toBeInTheDocument();
    expect(screen.getByText("Refund regression set")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Need review/i }));

    expect(screen.getByText("Refund regression set")).toBeInTheDocument();
  });

  it("does not expose raw JSON on the list page", () => {
    render(<GoldensPage />);

    expect(screen.queryByText(/source_issue_id/)).not.toBeInTheDocument();
    expect(screen.queryByText(/judge_config_json/)).not.toBeInTheDocument();
  });
});
