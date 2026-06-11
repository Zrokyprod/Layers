import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GoldenSetView, GoldenTraceView, ReplayRunDetailItem, ReplayRunItem } from "@/lib/api";

import GoldenDetailPage from "./page";

const api = vi.hoisted(() => ({
  addGoldenTrace: vi.fn(),
  deleteGoldenSet: vi.fn(),
  deleteGoldenTrace: vi.fn(),
  getBillingMe: vi.fn(),
  getGoldenSet: vi.fn(),
  getReplayRun: vi.fn(),
  listGoldenHistory: vi.fn(),
  listGoldenTraces: vi.fn(),
  listReplayRuns: vi.fn(),
  runGoldenSet: vi.fn(),
  updateGoldenSet: vi.fn(),
}));

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  planTemplate: { "pilot.goldens_basic": true, "pro.ci_gate_blocking": true } as Record<string, unknown>,
  planCode: "pro",
  set: null as GoldenSetView | null,
  traces: [] as GoldenTraceView[],
  runs: [] as ReplayRunItem[],
  runDetail: null as ReplayRunDetailItem | null,
  history: [] as import("@/lib/api").GoldenHistoryItem[],
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
  useParams: () => ({ id: "golden_1" }),
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
  useQuery: vi.fn(({ queryKey, enabled = true }: { queryKey: unknown[]; enabled?: boolean }) => {
    if (!enabled) return { data: undefined, isLoading: false, error: null };
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
    if (key === "golden-set") {
      return { data: queryState.set, isLoading: false, error: null };
    }
    if (key === "golden-traces") {
      return {
        data: { items: queryState.traces, total_in_page: queryState.traces.length },
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
    if (key === "replay-run") {
      return { data: queryState.runDetail, isLoading: false, error: null };
    }
    if (key === "golden-history") {
      return {
        data: { items: queryState.history },
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
    description: "12 verified traces protecting refund-agent behavior.",
    judge_config_json: null,
    is_flaky: false,
    blocks_ci: true,
    trace_count: 1,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function goldenTrace(overrides: Partial<GoldenTraceView> = {}): GoldenTraceView {
  return {
    id: "trace_1",
    golden_set_id: "golden_1",
    project_id: "proj_1",
    call_id: "call_1",
    status: "active",
    expected_output_text: "Call get_refund_status(order_id) and return the specific refund status.",
    source_output_text: "Verified replay returned refund status.",
    source_evidence_json: JSON.stringify({ required_tool_behavior: "get_refund_status" }),
    expected_tokens: null,
    expected_cost_usd: 0.12,
    expected_latency_ms: 1500,
    criteria_json: JSON.stringify({ forbidden_behavior: "generic policy answer" }),
    weight: 1,
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
      latency_delta_ms: 220,
      replay_cost_usd: 0.3,
    },
    ...overrides,
  };
}

function replayDetail(overrides: Partial<ReplayRunDetailItem> = {}): ReplayRunDetailItem {
  return {
    ...replayRun(),
    traces: [
      {
        id: "replay_trace_1",
        replay_run_id: "run_1",
        golden_trace_id: "trace_1",
        project_id: "proj_1",
        call_id_replayed: "call_1",
        judge_scores_json: null,
        status: "pass",
        diff_metric: 0.01,
        output_text: "Refund status returned.",
        completed_at: now,
        created_at: now,
        output_diff: { before: "generic policy", after: "specific refund status" },
        tool_behavior_diff: { before: "missing tool", after: "get_refund_status" },
        cost_delta_usd: -0.12,
        latency_delta_ms: 220,
      },
    ],
    ...overrides,
  };
}

function mockDetail({
  set = goldenSet(),
  traces = [goldenTrace()],
  runs = [replayRun()],
  runDetail = replayDetail(),
  history = [
    {
      id: "hist_1",
      project_id: "proj_1",
      golden_set_id: "golden_1",
      golden_trace_id: "trace_1",
      action: "golden_trace.created",
      actor_user_id: "user_1",
      reason: "Created from verified replay.",
      before_json: null,
      after_json: "{}",
      created_at: now,
    },
  ],
  planTemplate = { "pilot.goldens_basic": true, "pro.ci_gate_blocking": true },
  planCode = "pro",
}: {
  set?: GoldenSetView;
  traces?: GoldenTraceView[];
  runs?: ReplayRunItem[];
  runDetail?: ReplayRunDetailItem | null;
  history?: import("@/lib/api").GoldenHistoryItem[];
  planTemplate?: Record<string, unknown>;
  planCode?: string;
} = {}) {
  queryState.set = set;
  queryState.traces = traces;
  queryState.runs = runs;
  queryState.runDetail = runDetail;
  queryState.history = history;
  queryState.planTemplate = planTemplate;
  queryState.planCode = planCode;
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
  api.updateGoldenSet.mockResolvedValue(goldenSet({ blocks_ci: false }));
  api.addGoldenTrace.mockResolvedValue(goldenTrace({ id: "trace_new", call_id: "call_new" }));
  api.deleteGoldenTrace.mockResolvedValue(undefined);
  api.deleteGoldenSet.mockResolvedValue(undefined);
}

describe("GoldenDetailPage MVP", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDetail();
  });

  it("renders header, badges, metadata cards, and side panel", () => {
    render(<GoldenDetailPage />);

    expect(screen.getByRole("link", { name: "Back to Goldens" }).getAttribute("href")).toBe("/goldens");
    expect(screen.getByRole("heading", { name: "Refund protected flow" })).toBeInTheDocument();
    expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Blocks CI").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    for (const label of ["Trace count", "Last pass rate", "Blocks CI", "Needs review"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("heading", { name: "Golden health" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Golden set" })).toBeInTheDocument();
  });

  it("renders protected traces and expected behavior without raw JSON by default", () => {
    render(<GoldenDetailPage />);

    const table = screen.getByRole("table");
    for (const heading of ["Trace", "Expected behavior", "Last result", "Cost bound", "Latency bound", "Action"]) {
      expect(within(table).getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getAllByText("Call get_refund_status(order_id) and return the specific refund status.").length).toBeGreaterThan(0);
    expect(screen.getByText("Verified replay returned refund status.")).toBeInTheDocument();
    expect(screen.getByText("View criteria JSON")).toBeInTheDocument();
    expect(screen.getByText("View source evidence JSON")).toBeInTheDocument();
  });

  it("renders latest replay result summaries and run history", () => {
    render(<GoldenDetailPage />);

    expect(screen.getByRole("heading", { name: "Last replay result" })).toBeInTheDocument();
    expect(screen.getAllByText(/specific refund status/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/get_refund_status/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Run history" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /verified_fix/i }).getAttribute("href")).toBe("/replay/run_1");
  });

  it("renders structured Golden contract and change history", () => {
    mockDetail({
      traces: [
        goldenTrace({
          criteria_json: JSON.stringify({
            golden_contract_v1: {
              final_output: { kind: "text", expected: "Refund status returned." },
              tool_sequence: ["get_refund_status"],
              policy_checks: ["refund_policy_checked"],
              budgets: { max_latency_ms: 1500 },
              linked_proof: { replay_run_id: "run_1", proof_status: "verified_fix" },
            },
          }),
        }),
      ],
    });

    render(<GoldenDetailPage />);

    expect(screen.getByRole("heading", { name: "Golden contract" })).toBeInTheDocument();
    expect(screen.getAllByText(/get_refund_status/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Change history" })).toBeInTheDocument();
    expect(screen.getByText("golden_trace.created")).toBeInTheDocument();
    expect(screen.getByText("Created from verified replay.")).toBeInTheDocument();
  });

  it("renders zero trace empty state", () => {
    mockDetail({ set: goldenSet({ trace_count: 0, blocks_ci: false }), traces: [], runs: [], runDetail: null });

    render(<GoldenDetailPage />);

    expect(screen.getByText("This set has no protected traces yet.")).toBeInTheDocument();
    expect(screen.getByText("Create a Golden from a verified replay.")).toBeInTheDocument();
  });

  it("shows flaky and drift warnings but allows disabling existing CI blocking", async () => {
    mockDetail({
      set: goldenSet({
        is_flaky: true,
        blocks_ci: true,
        judge_config_json: JSON.stringify({ drift_suspected: true }),
      }),
    });

    render(<GoldenDetailPage />);

    expect(screen.getAllByText("Flaky").length).toBeGreaterThan(0);
    expect(screen.getByText("Draft, flaky, drift-suspected, or empty Goldens should be reviewed before blocking CI.")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Disable CI blocking" }) as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Disable CI blocking" }));

    await waitFor(() => expect(api.updateGoldenSet).toHaveBeenCalledWith("golden_1", { blocks_ci: false }));
  });

  it("runs the Golden set through existing API", async () => {
    render(<GoldenDetailPage />);

    fireEvent.click(screen.getByRole("button", { name: "Run Golden set" }));

    await waitFor(() => expect(api.runGoldenSet).toHaveBeenCalledWith("golden_1", { trigger: "manual" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/replay/run_new"));
  });

  it("switches selected trace proof without leaving the page", () => {
    mockDetail({
      traces: [
        goldenTrace(),
        goldenTrace({
          id: "trace_2",
          call_id: "call_2",
          expected_output_text: "Escalate the refund safely.",
          source_output_text: "Second trusted evidence.",
        }),
      ],
    });

    render(<GoldenDetailPage />);

    expect(screen.queryByText("Second trusted evidence.")).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Select" })[1]);

    expect(screen.getByText("Second trusted evidence.")).toBeInTheDocument();
  });

  it("adds a Golden trace with validated criteria JSON", async () => {
    render(<GoldenDetailPage />);

    fireEvent.click(screen.getAllByRole("button", { name: "Add trace" })[0]);
    fireEvent.change(screen.getByLabelText("Trace call ID"), { target: { value: "call_new" } });
    fireEvent.change(screen.getByLabelText("Trace status"), { target: { value: "active" } });
    fireEvent.change(screen.getByLabelText("Trace expected behavior"), { target: { value: "Use order lookup before refund response." } });
    fireEvent.change(screen.getByLabelText("Trace source evidence"), { target: { value: "Verified from replay run." } });
    fireEvent.change(screen.getByLabelText("Trace criteria JSON"), { target: { value: "{\"required_tool\":\"order_lookup\"}" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Add trace" })[1]);

    await waitFor(() =>
      expect(api.addGoldenTrace).toHaveBeenCalledWith("golden_1", {
        call_id: "call_new",
        status: "active",
        expected_output_text: "Use order lookup before refund response.",
        source_output_text: "Verified from replay run.",
        criteria_json: "{\"required_tool\":\"order_lookup\"}",
        weight: 1,
      }),
    );
  });

  it("removes a Golden trace", async () => {
    render(<GoldenDetailPage />);

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(api.deleteGoldenTrace).toHaveBeenCalledWith("golden_1", "trace_1"));
  });

  it("saves edited Golden set metadata", async () => {
    render(<GoldenDetailPage />);

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Refund protected flow v2" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Updated verified behavior." } });
    fireEvent.change(screen.getByLabelText("Judge config JSON"), { target: { value: "{\"owner\":\"support\"}" } });
    fireEvent.click(screen.getByRole("button", { name: "Save set" }));

    await waitFor(() =>
      expect(api.updateGoldenSet).toHaveBeenCalledWith("golden_1", {
        name: "Refund protected flow v2",
        description: "Updated verified behavior.",
        judge_config_json: "{\"owner\":\"support\"}",
      }),
    );
  });

  it("deletes the Golden set and returns to the list", async () => {
    render(<GoldenDetailPage />);

    fireEvent.click(screen.getByRole("button", { name: "Delete set" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => expect(api.deleteGoldenSet).toHaveBeenCalledWith("golden_1"));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/goldens"));
  });

  it("allows Pro plan-code fallback when entitlement payload is missing", () => {
    mockDetail({ planTemplate: {}, planCode: "pro" });

    render(<GoldenDetailPage />);

    expect((screen.getByRole("button", { name: "Run Golden set" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
