import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReplayRunDetailItem } from "@/lib/api";
import type { CallDetailResponse } from "@/lib/types";

import ReplayRunDetailPage from "./page";

const hooks = vi.hoisted(() => ({
  run: null as ReplayRunDetailItem | null,
}));

const api = vi.hoisted(() => ({
  addGoldenTrace: vi.fn(),
  createGoldenSet: vi.fn(),
  runGoldenSet: vi.fn(),
  runRegressionCI: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  callDetail: null as CallDetailResponse | null,
  goldenSets: {
    items: [
      {
        id: "golden_1",
        project_id: "proj_1",
        name: "Checkout regressions",
        description: null,
        judge_config_json: null,
        is_flaky: false,
        blocks_ci: true,
        trace_count: 2,
        created_at: "2026-05-29T10:00:00.000Z",
        updated_at: "2026-05-29T10:00:00.000Z",
      },
    ],
    next_cursor: null,
    total_in_page: 1,
  },
}));

const mutationState = vi.hoisted(() => ({
  mutate: vi.fn(),
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
  useParams: () => ({ id: "run_1" }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    addGoldenTrace: api.addGoldenTrace,
    createGoldenSet: api.createGoldenSet,
    runGoldenSet: api.runGoldenSet,
    runRegressionCI: api.runRegressionCI,
  };
});

vi.mock("@/lib/hooks", () => ({
  useReplayRunDetail: () => ({
    data: hooks.run,
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: string[] }) => {
    if (queryKey[0] === "call-detail") {
      return { data: queryState.callDetail, isLoading: false, error: null };
    }
    if (queryKey[0] === "golden-sets") {
      return { data: queryState.goldenSets, isLoading: false, error: null };
    }
    return { data: undefined, isLoading: false, error: null };
  }),
  useMutation: vi.fn((options: {
    mutationFn: (variables?: unknown) => unknown;
    onSuccess?: (data: unknown, variables?: unknown) => void;
    onError?: (error: Error, variables?: unknown) => void;
  }) => ({
    mutate: (variables?: unknown) => {
      mutationState.mutate(variables);
      Promise.resolve()
        .then(() => options.mutationFn(variables))
        .then((data) => options.onSuccess?.(data, variables))
        .catch((error: Error) => options.onError?.(error, variables));
    },
    isPending: false,
    isError: false,
  })),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

const now = "2026-05-29T10:00:00.000Z";

function baseRun(overrides: Partial<ReplayRunDetailItem> = {}): ReplayRunDetailItem {
  return {
    id: "run_1",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    git_sha: "abc123",
    status: "pass",
    started_at: now,
    completed_at: now,
    created_at: now,
    replay_mode: "real_llm",
    executor_replay_mode: "real_llm",
    replay_mode_warning: null,
    candidate_prompt_override: "Use the payment retry guard.",
    candidate_model_override: "gpt-4.1",
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
      output_diff: { changed: true, before: "timeout", after: "success" },
      tool_behavior_diff: { matched: true },
      cost_delta_usd: -0.12,
      latency_delta_ms: -240,
      replay_cost_usd: 0.34,
    },
    traces: [
      {
        id: "trace_1",
        replay_run_id: "run_1",
        golden_trace_id: "golden_trace_1",
        project_id: "proj_1",
        call_id_replayed: "call_1",
        judge_scores_json: JSON.stringify({ confidence: 0.91, reason: "Candidate output fixed the failure." }),
        status: "pass",
        diff_metric: 0.02,
        output_text: "Payment completed successfully.",
        completed_at: now,
        created_at: now,
        output_diff: { before: "payment failed", after: "payment completed" },
        tool_behavior_diff: { before: ["charge"], after: ["charge", "receipt"] },
        cost_delta_usd: -0.12,
        latency_delta_ms: -240,
      },
    ],
    ...overrides,
  };
}

function callDetail(): CallDetailResponse {
  return {
    call: {
      call_id: "call_1",
      tenant_id: "tenant_1",
      status: "failed",
      provider: "openai",
      model: "gpt-4.1",
      agent_name: "checkout-agent",
      user_id: "user_1",
      call_type: "chat",
      total_tokens: 432,
      cost_usd: 0.46,
      pricing_version: "2026-05",
      pricing_last_updated_at: now,
      pricing_age_days: 0,
      cost_confidence: "high",
      latency_ms: 1234,
      error_code: "PAYMENT_TIMEOUT",
      diagnoses: [],
      has_blast_radius: false,
      created_at: now,
      updated_at: now,
    },
    payload: {
      input: "Charge customer order 42.",
      output: "Payment failed with timeout.",
      failure_reason: "Payment provider timed out before receipt creation.",
      tool_calls: [{ name: "charge_card", status: "timeout" }],
      retrieval_context: ["plan limit", "payment policy"],
    },
    cost_audit: null,
    diagnosis_result: null,
    feedback_summary: {
      helpful_count: 0,
      not_helpful_count: 0,
    },
  };
}

function renderRun(run: ReplayRunDetailItem) {
  hooks.run = run;
  queryState.callDetail = callDetail();
  render(<ReplayRunDetailPage />);
}

describe("ReplayRunDetailPage Replay Lab MVP", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.run = baseRun();
    queryState.callDetail = callDetail();
    api.runGoldenSet.mockResolvedValue({
      id: "run_rerun_1",
      project_id: "proj_1",
      golden_set_id: "golden_1",
      trigger: "manual",
      git_sha: null,
      status: "pending",
      created_at: now,
      summary_url: "/v1/replay/runs/run_rerun_1",
      idempotent: false,
    });
    api.createGoldenSet.mockResolvedValue({
      id: "golden_new",
      project_id: "proj_1",
      name: "Verified regression memory",
      description: "Created from verified replay run_1",
      judge_config_json: null,
      is_flaky: false,
      blocks_ci: true,
      trace_count: 0,
      created_at: now,
      updated_at: now,
    });
    api.addGoldenTrace.mockResolvedValue({
      id: "golden_trace_new",
      golden_set_id: "golden_new",
      project_id: "proj_1",
      call_id: "call_1",
      status: "active",
      expected_output_text: "Payment completed successfully.",
      source_output_text: null,
      source_evidence_json: null,
      expected_tokens: null,
      expected_cost_usd: null,
      expected_latency_ms: null,
      criteria_json: null,
      weight: 1,
      created_at: now,
      updated_at: now,
    });
    api.runRegressionCI.mockResolvedValue({
      run_id: "ci_run_1",
      project_id: "proj_1",
      git_sha: "abc123",
      status: "queued",
      summary_url: "/v1/regression-ci/runs/ci_run_1",
    });
  });

  it("renders the three required panels and before-after content", () => {
    renderRun(baseRun());

    expect(screen.getByRole("heading", { name: "Replay Lab" })).toBeInTheDocument();
    expect(screen.getByText("Replay failed agent calls, compare candidate behavior, and verify fixes before creating Goldens.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Replay setup" })).toBeInTheDocument();
    expect(screen.getByText("Source type")).toBeInTheDocument();
    expect(screen.getByText("Source call")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Original Failure" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Candidate Replay" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Verification Result" })).toBeInTheDocument();
    expect(screen.getByText("Verification verdict")).toBeInTheDocument();
    expect(screen.getByText("Candidate replay passed with real comparison.")).toBeInTheDocument();
    expect(screen.getByText("Tool behavior corrected")).toBeInTheDocument();
    expect(screen.getByText("Charge customer order 42.")).toBeInTheDocument();
    expect(screen.getByText("Payment failed with timeout.")).toBeInTheDocument();
    expect(screen.getByText("Payment completed successfully.")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getAllByText("gpt-4.1").length).toBeGreaterThan(0);
  });

  it("shows stub replay as sanity-only and disables Create Golden", () => {
    renderRun(baseRun({
      replay_mode: "stub",
      executor_replay_mode: "stub",
      status: "pass",
      summary: {
        ...baseRun().summary,
        verified_fix: false,
        verification_status: "sanity_check_only",
      },
    }));

    expect(screen.getAllByText("stub_only").length).toBeGreaterThan(0);
    expect(screen.getByText("Stub replay is sanity-only and cannot display as verified.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run trusted replay" })).toBeInTheDocument();
    expect(screen.getByText("Run trusted replay before creating a Golden.")).toBeInTheDocument();
    const goldenRegion = screen.getByLabelText("Golden eligibility");
    expect(within(goldenRegion).queryByRole("button", { name: "Create Golden" })).not.toBeInTheDocument();
  });

  it("shows not_verified as untrusted and hides Create Golden", () => {
    renderRun(baseRun({
      status: "pass",
      summary: {
        ...baseRun().summary,
        verified_fix: false,
        verification_status: "not_verified",
      },
    }));

    expect(screen.getAllByText("not_verified").length).toBeGreaterThan(0);
    expect(screen.getByText("This replay state is not trusted enough to create a Golden or block CI. Run trusted replay first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run trusted replay" })).toBeInTheDocument();
    expect(screen.queryByText("Verified fix. Create Golden is available.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Golden" })).not.toBeInTheDocument();
  });

  it("enables Create Golden for verified non-stub fixes", () => {
    renderRun(baseRun());

    expect(screen.getByText("Verified fix. Create Golden is available.")).toBeInTheDocument();
    expect(screen.getByText("This replay can become a Golden.")).toBeInTheDocument();
    expect(screen.getByText("It will protect this flow in future CI runs.")).toBeInTheDocument();
    const createGoldenRegion = screen.getByLabelText("Golden eligibility");
    expect((within(createGoldenRegion).getByRole("button", { name: "Create Golden" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows the proof ladder and enables CI gate for verified fixes", () => {
    renderRun(baseRun());

    expect(screen.getByLabelText("Replay proof stages")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Judge")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "CI gate" })).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Run CI gate" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("reruns the current Golden Set with the current replay configuration", async () => {
    renderRun(baseRun());

    fireEvent.click(screen.getByRole("button", { name: "Rerun replay" }));

    await waitFor(() => expect(api.runGoldenSet).toHaveBeenCalledWith("golden_1", {
      trigger: "manual",
      replay_mode: "real_llm",
      candidate_prompt_override: "Use the payment retry guard.",
      candidate_model_override: "gpt-4.1",
    }));
  });

  it("creates a Golden from verified replay proof", async () => {
    renderRun(baseRun());

    const createGoldenRegion = screen.getByLabelText("Golden eligibility");
    fireEvent.change(within(createGoldenRegion).getByPlaceholderText("Verified regression memory"), {
      target: { value: "Verified regression memory" },
    });
    fireEvent.click(within(createGoldenRegion).getByRole("button", { name: "Create Golden" }));

    await waitFor(() => expect(api.createGoldenSet).toHaveBeenCalledWith({
      name: "Verified regression memory",
      description: "Created from verified replay run_1",
    }));
    await waitFor(() => expect(api.addGoldenTrace).toHaveBeenCalledWith("golden_new", expect.objectContaining({
      call_id: "call_1",
      expected_output_text: "Payment completed successfully.",
      weight: 1,
    })));
  });

  it("runs a CI gate from verified replay proof", async () => {
    renderRun(baseRun());

    const ciGateRegion = screen.getByLabelText("CI gate");
    fireEvent.click(within(ciGateRegion).getByRole("button", { name: "Run CI gate" }));

    await waitFor(() => expect(api.runRegressionCI).toHaveBeenCalledWith({
      git_sha: "abc123",
      sample_window_days: 30,
    }));
  });

  it("lets the operator switch between replay traces", () => {
    renderRun(baseRun({
      traces: [
        baseRun().traces[0],
        {
          ...baseRun().traces[0],
          id: "trace_2",
          status: "fail",
          call_id_replayed: "call_2",
          output_text: "Payment still failed.",
        },
      ],
    }));

    const traceSelector = screen.getByLabelText("Replay trace selector");
    expect(traceSelector).toBeInTheDocument();
    expect(within(traceSelector).getByRole("combobox")).toBeInTheDocument();
  });

  it("shows a trusted replay CTA when the candidate fix failed", () => {
    renderRun(baseRun({
      status: "fail",
      summary: {
        ...baseRun().summary,
        verified_fix: false,
        verification_status: "real_comparison_failed",
        fail_count: 1,
        pass_count: 0,
      },
      traces: [
        {
          ...baseRun().traces[0],
          status: "fail",
          output_text: "Payment still failed.",
        },
      ],
    }));

    expect(screen.getAllByText("fix_failed").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Run trusted replay" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Golden" })).not.toBeInTheDocument();
  });

  it("shows the recommended next replay mode for inconclusive missing tool proof", () => {
    renderRun(baseRun({
      status: "pass",
      summary: {
        ...baseRun().summary,
        verified_fix: false,
        verification_status: "real_comparison_missing_tool_proof",
        tool_behavior_diff: { missing_count: 1 },
      },
    }));

    expect(screen.getAllByText("inconclusive").length).toBeGreaterThan(0);
    expect(screen.getByText("Recommended next replay mode: mocked-tool")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run trusted replay" })).toBeInTheDocument();
  });

  it("renders diffs, deltas, judge confidence, and candidate overrides", () => {
    renderRun(baseRun());

    expect(screen.getByText("output_diff")).toBeInTheDocument();
    expect(screen.getByText("tool_behavior_diff")).toBeInTheDocument();
    expect(screen.getAllByText("View JSON").length).toBeGreaterThan(0);
    expect(screen.getByText("cost_delta")).toBeInTheDocument();
    expect(screen.getByText("latency_delta")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();
    expect(screen.getAllByText("Use the payment retry guard.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-240 ms").length).toBeGreaterThan(0);
    expect(screen.getByText("$0.34")).toBeInTheDocument();
  });
});
