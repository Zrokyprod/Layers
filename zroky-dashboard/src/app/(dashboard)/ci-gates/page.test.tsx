import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RegressionCIRunDetailResponse, ReplayRunItem } from "@/lib/api";

import CiGatesPage from "./page";

const api = vi.hoisted(() => ({
  getRegressionCIRun: vi.fn(),
  listReplayRuns: vi.fn(),
  runRegressionCI: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
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
  useRouter: () => navigation,
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function replayRun(overrides: Partial<ReplayRunItem> = {}): ReplayRunItem {
  return {
    id: "run_ci_1",
    project_id: "proj_1",
    golden_set_id: "regression-ci:tenant_1",
    trigger: "github",
    git_sha: "abcdef1234567890",
    status: "fail",
    started_at: now,
    completed_at: now,
    summary: {
      trace_count_at_dispatch: 10,
      trace_count_executed: 10,
      pass_count: 8,
      fail_count: 2,
      error_count: 0,
      reproduced_original_failure: null,
      fix_passed: null,
      verified_fix: false,
      verification_status: "regression_detected",
      output_diff: null,
      tool_behavior_diff: null,
      cost_delta_usd: null,
      latency_delta_ms: null,
      replay_cost_usd: null,
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

function ciDetail(overrides: Partial<RegressionCIRunDetailResponse> = {}): RegressionCIRunDetailResponse {
  return {
    run_id: "run_ci_1",
    project_id: "proj_1",
    git_sha: "abcdef1234567890",
    status: "fail",
    created_at: now,
    started_at: now,
    completed_at: now,
    report: {
      verdict: "fail",
      regression_rate: 0.125,
      regressed_count: 3,
      trace_count: 24,
      replay_mode: "mocked_tool",
      pr_number: 42,
      pr_title: "Refund retry guard",
      branch: "refund-retry",
      pr_url: "https://github.com/acme/app/pull/42",
      summary_url: "/v1/regression-ci/runs/run_ci_1",
    },
    pr_comment_markdown: "## Replay CI regressed\n\n3 protected flows failed.",
    ...overrides,
  };
}

function mockCi({
  runs = [
    replayRun(),
    replayRun({ id: "run_pass", status: "pass", git_sha: "feedface123456", summary: { ...replayRun().summary, fail_count: 0, pass_count: 10 } }),
    replayRun({ id: "run_error", status: "error", git_sha: "eeeeee123456", summary: { ...replayRun().summary, fail_count: 0, error_count: 1 } }),
    replayRun({ id: "run_nv", status: "not_verified", git_sha: "badcafe123456", summary: { ...replayRun().summary, fail_count: 0, pass_count: 0, verification_status: "not_verified" } }),
    replayRun({ id: "run_pending", status: "pending", git_sha: "111111123456" }),
    replayRun({ id: "manual_1", trigger: "manual", golden_set_id: "golden_1" }),
  ],
  details = [
    ciDetail(),
    ciDetail({
      run_id: "run_pass",
      status: "pass",
      git_sha: "feedface123456",
      report: { verdict: "pass", regression_rate: 0, regressed_count: 0, trace_count: 10, replay_mode: "real_llm", pr_number: 41, pr_title: "Billing schema patch" },
    }),
    ciDetail({
      run_id: "run_error",
      status: "error",
      git_sha: "eeeeee123456",
      report: { verdict: "error", trace_count: 8, replay_mode: "live_sandbox", pr_number: 40, pr_title: "Provider timeout handling" },
    }),
    ciDetail({
      run_id: "run_nv",
      status: "not_verified",
      git_sha: "badcafe123456",
      report: { verdict: "not_verified", trace_count: 6, replay_mode: "stub", pr_number: 39, pr_title: "Checkout prompt cleanup" },
      pr_comment_markdown: "Replay CI: Not verified",
    }),
    ciDetail({
      run_id: "run_pending",
      status: "pending",
      git_sha: "111111123456",
      report: { verdict: "pending", trace_count: 4, pr_number: 38, pr_title: "Pending replay" },
    }),
  ],
}: {
  runs?: ReplayRunItem[];
  details?: RegressionCIRunDetailResponse[];
} = {}) {
  api.listReplayRuns.mockResolvedValue({
    items: runs,
    next_cursor: null,
    total_in_page: runs.length,
  });
  api.getRegressionCIRun.mockImplementation((runId: string) => {
    const detail = details.find((item) => item.run_id === runId);
    return detail ? Promise.resolve(detail) : Promise.reject(new Error("missing detail"));
  });
}

describe("CI Gates list MVP", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.push.mockClear();
  });

  it("renders list header, KPI cards, required columns, and CI rows", async () => {
    mockCi();

    render(<CiGatesPage />);

    expect(await screen.findByRole("heading", { name: "CI Gates" })).toBeInTheDocument();
    expect(screen.getByText("Replay-backed PR safety checks for protected agent flows.")).toBeInTheDocument();
    expect(screen.getByText("Review failed, not verified, and blocking regression runs before merge.")).toBeInTheDocument();
    for (const label of ["Failed / blocked", "Not verified", "Passed", "Protected flows"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }

    const table = await screen.findByRole("table");
    for (const heading of ["Run", "Status", "Regression", "Failed flows", "Replay proof", "Git SHA", "Summary URL", "Completed", "Action"]) {
      expect(within(table).getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText("PR #42 - Refund retry guard")).toBeInTheDocument();
    expect(screen.getByText("refund-retry")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "/v1/regression-ci/runs/run_ci_1" }).getAttribute("href")).toBe(
      "/ci-gates/run_ci_1",
    );
    expect(screen.queryByText("manual_1")).not.toBeInTheDocument();
  });

  it("renders pass, fail, error, and not_verified labels correctly", async () => {
    mockCi();

    render(<CiGatesPage />);

    expect((await screen.findAllByText("Failed")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Error").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
  });

  it("does not style not_verified as pass or success", async () => {
    mockCi();

    const { container } = render(<CiGatesPage />);

    await screen.findAllByText("Not verified");
    const badge = Array.from(container.querySelectorAll(".alert-cat-badge")).find((node) => node.textContent === "Not verified");
    expect(badge?.getAttribute("class")).toContain("badge-yellow");
    expect(badge?.getAttribute("class")).not.toContain("badge-green");
    expect(screen.getByText("Not verified is never treated as pass.")).toBeInTheDocument();
  });

  it("renders replay proof and action labels", async () => {
    mockCi();

    render(<CiGatesPage />);

    expect(await screen.findByText("Repository replay")).toBeInTheDocument();
    expect(screen.getAllByText("Managed provider replay").length).toBeGreaterThan(0);
    expect(screen.getByText("Sandbox replay")).toBeInTheDocument();
    expect(screen.getAllByText("No trusted replay").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Review" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "View" }).getAttribute("href")).toBe("/ci-gates/run_pass");
    expect(screen.getByRole("link", { name: "View status" }).getAttribute("href")).toBe("/ci-gates/run_pending");
  });

  it("filters live from KPI cards, status controls, and search", async () => {
    mockCi();

    render(<CiGatesPage />);

    expect(await screen.findByText("PR #42 - Refund retry guard")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Failed \/ blocked/i }));
    expect(screen.getByText("PR #42 - Refund retry guard")).toBeInTheDocument();
    expect(screen.queryByText("PR #41 - Billing schema patch")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Protected flows/i }));
    fireEvent.change(screen.getByLabelText("Search CI gates"), { target: { value: "Billing" } });
    expect(screen.getByText("PR #41 - Billing schema patch")).toBeInTheDocument();
    expect(screen.queryByText("PR #42 - Refund retry guard")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Status filter"), { target: { value: "not_verified" } });
    expect(screen.getByText("No CI gates match filters")).toBeInTheDocument();
  });

  it("queues a live CI gate from the run form", async () => {
    mockCi();
    api.runRegressionCI.mockResolvedValue({
      run_id: "ci_new",
      project_id: "proj_1",
      git_sha: "abc1234",
      status: "queued",
      summary_url: "/v1/regression-ci/runs/ci_new",
    });

    render(<CiGatesPage />);

    await screen.findByRole("heading", { name: "CI Gates" });
    fireEvent.click(screen.getByRole("button", { name: "Run gate" }));
    fireEvent.change(screen.getByLabelText("Commit SHA"), { target: { value: "abc1234" } });
    fireEvent.change(screen.getByLabelText("Changed files"), { target: { value: "src/agent/refund.ts\nprompts/refund.md" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue CI gate" }));

    await waitFor(() =>
      expect(api.runRegressionCI).toHaveBeenCalledWith({
        git_sha: "abc1234",
        threshold: 0.02,
        changed_files: [{ path: "src/agent/refund.ts" }, { path: "prompts/refund.md" }],
      }),
    );
    expect(navigation.push).toHaveBeenCalledWith("/ci-gates/ci_new");
  });

  it("renders empty state", async () => {
    mockCi({ runs: [], details: [] });

    render(<CiGatesPage />);

    expect(await screen.findByText("No CI gate runs yet")).toBeInTheDocument();
    expect(screen.getByText("Run active Contracts from GitHub CI to block regressions before merge.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Contracts" }).getAttribute("href")).toBe("/contracts");
  });

  it("degrades when replay run context fails instead of showing a global page failure", async () => {
    api.listReplayRuns.mockRejectedValue(new Error("GET /v1/replay/runs failed (500)"));

    render(<CiGatesPage />);

    expect(await screen.findByText("No CI gate runs yet")).toBeInTheDocument();
    expect(screen.getByText("Replay run context unavailable. CI gate results are still shown when available.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("GET /v1/replay/runs failed (500)")).not.toBeInTheDocument();
    expect(api.getRegressionCIRun).not.toHaveBeenCalled();

    const protectedFlowsCard = screen.getByText("Protected flows").closest("button");
    expect(protectedFlowsCard).not.toBeNull();
    expect(within(protectedFlowsCard as HTMLElement).getByText("0")).toBeInTheDocument();
  });

  it("keeps rows visible when regression CI details are unavailable", async () => {
    mockCi({ details: [] });

    render(<CiGatesPage />);

    expect(await screen.findByText("Regression CI details unavailable for some runs.")).toBeInTheDocument();
    expect(screen.getByText("Run run_ci_1")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
