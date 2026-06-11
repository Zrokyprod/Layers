import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RegressionCIRunDetailResponse, ReplayRunDetailItem } from "@/lib/api";

import CiGateDetailPage from "./page";

const api = vi.hoisted(() => ({
  getRegressionCIRun: vi.fn(),
  getReplayRun: vi.fn(),
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
  useParams: () => ({ runId: "run_ci_1" }),
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

function replayRun(overrides: Partial<ReplayRunDetailItem> = {}): ReplayRunDetailItem {
  return {
    id: "run_ci_1",
    project_id: "proj_1",
    golden_set_id: "golden_1",
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
    replay_mode: "mocked-tool",
    executor_replay_mode: "mocked-tool",
    replay_mode_warning: null,
    candidate_prompt_override: null,
    candidate_model_override: null,
    prevented_outcome_cost_usd: null,
    traces: [],
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
      regression_threshold: 0.02,
      regressed_count: 3,
      replay_mode: "mocked_tool",
      golden_set_id: "golden_1",
      pr_number: 42,
      pr_title: "Refund retry guard",
      branch: "refund-retry",
      pr_url: "https://github.com/acme/app/pull/42",
      summary_url: "/v1/regression-ci/runs/run_ci_1",
      clusters: [{ label: "Refund protected flow", size: 3, reason: "Refund status changed" }],
      notes: "Regression exceeded threshold.",
    },
    pr_comment_markdown: "## Replay CI regressed\n\n3 protected flows failed.",
    ...overrides,
  };
}

function mockDetail(run: ReplayRunDetailItem = replayRun(), detail: RegressionCIRunDetailResponse = ciDetail()) {
  api.getReplayRun.mockResolvedValue(run);
  api.getRegressionCIRun.mockResolvedValue(detail);
}

describe("CI Gate detail MVP", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.push.mockClear();
  });

  it("renders fail detail with blocked copy and failed flows", async () => {
    mockDetail();

    render(<CiGateDetailPage />);

    expect(await screen.findByRole("heading", { name: "PR #42 - Refund retry guard" })).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Regression CI blocked this change.").length).toBeGreaterThan(0);
    expect(screen.getByText("Refund protected flow (3)")).toBeInTheDocument();
    expect(screen.getByText("Refund status changed")).toBeInTheDocument();
    expect(screen.getAllByText("/v1/regression-ci/runs/run_ci_1").length).toBeGreaterThan(0);
    expect(screen.getByText(/Replay CI regressed/)).toBeInTheDocument();
  });

  it("renders pass detail with trusted under-threshold copy", async () => {
    mockDetail(
      replayRun({ status: "pass", summary: { ...replayRun().summary, fail_count: 0, pass_count: 10, verification_status: "verified_fix" } }),
      ciDetail({
        status: "pass",
        report: {
          verdict: "pass",
          regression_rate: 0,
          regression_threshold: 0.02,
          regressed_count: 0,
          replay_mode: "real_llm",
          pr_number: 41,
          pr_title: "Billing schema patch",
        },
        pr_comment_markdown: "Replay CI: Passed",
      }),
    );

    render(<CiGateDetailPage />);

    expect(await screen.findByRole("heading", { name: "PR #41 - Billing schema patch" })).toBeInTheDocument();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Trusted replay completed under threshold.").length).toBeGreaterThan(0);
  });

  it("renders not_verified unsafe warning without pass language", async () => {
    mockDetail(
      replayRun({ status: "not_verified", summary: { ...replayRun().summary, fail_count: 0, pass_count: 0, verification_status: "not_verified" } }),
      ciDetail({
        status: "not_verified",
        report: {
          verdict: "not_verified",
          replay_mode: "stub",
          pr_number: 40,
          pr_title: "Checkout prompt cleanup",
        },
        pr_comment_markdown: "Replay CI: Not verified",
      }),
    );

    render(<CiGateDetailPage />);

    expect(await screen.findByRole("heading", { name: "PR #40 - Checkout prompt cleanup" })).toBeInTheDocument();
    expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
    expect(screen.getByText("This CI run did not execute trusted replay. Do not treat this PR as safe.")).toBeInTheDocument();
    expect(screen.getAllByText("This CI run did not execute trusted replay, so it cannot prove this PR is safe.").length).toBeGreaterThan(0);
    expect(screen.queryByText("Passed")).not.toBeInTheDocument();
    expect(screen.queryByText("Trusted replay completed under threshold.")).not.toBeInTheDocument();
  });

  it("renders Golden gate evidence and active override state", async () => {
    mockDetail(
      replayRun({ status: "fail" }),
      ciDetail({
        status: "fail",
        effective_status: "pass",
        failed_goldens: [
          {
            golden_name: "Refund policy Golden",
            golden_trace_id: "gt_1",
            assertion: "tool_sequence",
            replay_mode: "mocked_tool",
            recommended_fix: "Restore policy lookup before refund.",
          },
        ],
        warn_goldens: [
          {
            golden_name: "Support tone Golden",
            golden_trace_id: "gt_2",
            status: "fail",
            replay_mode: "real_llm",
          },
        ],
        not_verified_reasons: ["blocking Golden gt_3 has no replay evidence"],
        override: {
          original_status: "fail",
          effective_status: "pass",
          reason: "Hotfix approved by owner until replay worker recovers.",
        },
      }),
    );

    render(<CiGateDetailPage />);

    expect(await screen.findByText("Golden gate evidence")).toBeInTheDocument();
    expect(screen.getByText("Refund policy Golden")).toBeInTheDocument();
    expect(screen.getByText(/Restore policy lookup/)).toBeInTheDocument();
    expect(screen.getByText("Support tone Golden")).toBeInTheDocument();
    expect(screen.getByText("blocking Golden gt_3 has no replay evidence")).toBeInTheDocument();
    expect(screen.getByText(/Override active: effective status pass/)).toBeInTheDocument();
  });

  it("renders existing action links", async () => {
    mockDetail();

    render(<CiGateDetailPage />);

    expect((await screen.findByRole("link", { name: "View replay" })).getAttribute("href")).toBe("/replay/run_ci_1");
    expect(screen.getByRole("link", { name: "View Golden set" }).getAttribute("href")).toBe("/goldens/golden_1");
    expect(screen.getByRole("link", { name: "Open PR" }).getAttribute("href")).toBe("https://github.com/acme/app/pull/42");
  });

  it("reruns a CI gate with the current SHA and threshold", async () => {
    mockDetail();
    api.runRegressionCI.mockResolvedValue({
      run_id: "ci_rerun",
      project_id: "proj_1",
      git_sha: "abcdef1234567890",
      status: "queued",
      summary_url: "/v1/regression-ci/runs/ci_rerun",
    });

    render(<CiGateDetailPage />);

    await screen.findByRole("heading", { name: "PR #42 - Refund retry guard" });
    fireEvent.click(screen.getByRole("button", { name: "Rerun gate" }));

    await waitFor(() =>
      expect(api.runRegressionCI).toHaveBeenCalledWith({
        git_sha: "abcdef1234567890",
        threshold: 0.02,
      }),
    );
    expect(navigation.push).toHaveBeenCalledWith("/ci-gates/ci_rerun");
  });

  it("copies the PR comment preview", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    mockDetail();

    render(<CiGateDetailPage />);

    await screen.findByRole("heading", { name: "PR #42 - Refund retry guard" });
    fireEvent.click(screen.getByRole("button", { name: "Copy comment" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("Replay CI regressed")));
  });
});
