import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  GoldenSetView,
  GoldenTraceView,
  RegressionCIRunDetailResponse,
  ReplayRunDetailItem,
  ReplayRunItem,
} from "@/lib/api";
import type { CallDetailResponse, CallListItem, IssueItem } from "@/lib/types";
import {
  moneyPathBilling,
  moneyPathCall,
  moneyPathCallDetail,
  moneyPathCiDetail,
  moneyPathCiRun,
  moneyPathCiRunDetail,
  moneyPathGoldenSet,
  moneyPathGoldenTrace,
  moneyPathIds,
  moneyPathIssue,
  moneyPathReplayRun,
  moneyPathReplayRunDetail,
} from "@/test/money-path-fixture";

import CiGateDetailPage from "./ci-gates/[runId]/page";
import CiGatesPage from "./ci-gates/page";
import GoldenDetailPage from "./goldens/[id]/page";
import GoldensPage from "./goldens/page";
import IssueDetailPage from "./issues/[id]/page";
import IssuesPage from "./issues/page";
import ReplayPage from "./replay/page";

const api = vi.hoisted(() => ({
  addGoldenTrace: vi.fn(),
  createGoldenSet: vi.fn(),
  createProviderKey: vi.fn(),
  createReplayRunFromCall: vi.fn(),
  createReplayRunFromIssue: vi.fn(),
  deleteGoldenSet: vi.fn(),
  deleteGoldenTrace: vi.fn(),
  getBillingMe: vi.fn(),
  getGoldenSet: vi.fn(),
  getIssue: vi.fn(),
  getRegressionCIRun: vi.fn(),
  getReplayRun: vi.fn(),
  ignoreIssue: vi.fn(),
  listGoldenSets: vi.fn(),
  listGoldenTraces: vi.fn(),
  listIssues: vi.fn(),
  listReplayRuns: vi.fn(),
  promoteIssueToGolden: vi.fn(),
  resolveIssue: vi.fn(),
  runGoldenSet: vi.fn(),
  runIssueCiGate: vi.fn(),
  runRegressionCI: vi.fn(),
  updateGoldenSet: vi.fn(),
  updateIssueTriage: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  params: {} as Record<string, string>,
  push: vi.fn(),
  replace: vi.fn(),
  searchParams: "",
}));

const hookActions = vi.hoisted(() => ({
  callReplayMutate: vi.fn(),
  issueReplayMutate: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  calls: [] as CallListItem[],
  callDetail: null as CallDetailResponse | null,
  ciDetail: null as RegressionCIRunDetailResponse | null,
  ciRunDetail: null as ReplayRunDetailItem | null,
  goldenSets: [] as GoldenSetView[],
  goldenTraces: [] as GoldenTraceView[],
  issue: null as IssueItem | null,
  issues: [] as IssueItem[],
  replayDetail: null as ReplayRunDetailItem | null,
  replayRuns: [] as ReplayRunItem[],
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
  useParams: () => navigation.params,
  useRouter: () => ({
    push: navigation.push,
    replace: navigation.replace,
  }),
  useSearchParams: () => new URLSearchParams(navigation.searchParams),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

vi.mock("@/lib/hooks", () => ({
  useActiveProviderKeys: () => ({
    data: {
      items: [{ id: "provider_key_money_path", provider: "custom", is_active: true }],
      total_in_page: 1,
    },
    refetch: vi.fn(async () => ({
      data: {
        items: [{ id: "provider_key_money_path", provider: "custom", is_active: true }],
        total_in_page: 1,
      },
    })),
  }),
  useCreateReplayRunFromCall: (options?: { onSuccess?: (run: unknown) => void }) => ({
    mutate: (variables: unknown) => {
      hookActions.callReplayMutate(variables);
      options?.onSuccess?.(queryState.replayDetail);
    },
    isPending: false,
  }),
  useCreateReplayRunFromIssue: (options?: { onSuccess?: (run: unknown) => void }) => ({
    mutate: (variables: unknown) => {
      hookActions.issueReplayMutate(variables);
      options?.onSuccess?.(queryState.replayDetail);
    },
    isPending: false,
  }),
  useListCalls: () => ({
    data: {
      total: queryState.calls.length,
      limit: 20,
      offset: 0,
      items: queryState.calls,
    },
    isLoading: false,
    error: null,
  }),
  useReplayQuota: () => ({
    data: {
      enabled: true,
      limit: 100,
      used: 1,
      resets_at: "2026-06-30",
    },
    isLoading: false,
    error: null,
  }),
  useReplayRunDetail: () => ({
    data: queryState.replayDetail,
    isLoading: false,
    error: null,
  }),
  useReplayRuns: () => ({
    data: {
      items: queryState.replayRuns,
      next_cursor: null,
      total_in_page: queryState.replayRuns.length,
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock("@tanstack/react-query", () => ({
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
    isError: false,
    error: null,
  })),
  useQuery: vi.fn(({ queryKey, enabled = true }: { queryKey: unknown[]; enabled?: boolean }) => {
    if (!enabled) return { data: undefined, isLoading: false, error: null };
    const key = queryKey[0];
    if (key === "billing-me") {
      return { data: moneyPathBilling, isLoading: false, error: null };
    }
    if (key === "issues") {
      return {
        data: { items: queryState.issues, next_cursor: null, total_in_page: queryState.issues.length },
        isLoading: false,
        error: null,
      };
    }
    if (key === "call-detail") {
      return { data: queryState.callDetail, isLoading: false, error: null };
    }
    if (key === "golden-set") {
      return { data: queryState.goldenSets[0], isLoading: false, error: null };
    }
    if (key === "golden-sets") {
      return {
        data: { items: queryState.goldenSets, next_cursor: null, total_in_page: queryState.goldenSets.length },
        isLoading: false,
        error: null,
      };
    }
    if (key === "golden-traces") {
      return {
        data: { items: queryState.goldenTraces, total_in_page: queryState.goldenTraces.length },
        isLoading: false,
        error: null,
      };
    }
    if (key === "replay-run") {
      return {
        data: queryKey[1] === moneyPathIds.ciRunId ? queryState.ciRunDetail : queryState.replayDetail,
        isLoading: false,
        error: null,
      };
    }
    if (key === "replay-runs") {
      return {
        data: { items: queryState.replayRuns, next_cursor: null, total_in_page: queryState.replayRuns.length },
        isLoading: false,
        error: null,
      };
    }
    return { data: undefined, isLoading: false, error: null };
  }),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

function seedMoneyPathDashboardState() {
  const issue = moneyPathIssue();
  const replayRun = moneyPathReplayRun();
  const ciRun = moneyPathCiRun();
  const replayDetail = moneyPathReplayRunDetail();
  const ciRunDetail = moneyPathCiRunDetail();
  const ciDetail = moneyPathCiDetail();
  const goldenSet = moneyPathGoldenSet();
  const goldenTrace = moneyPathGoldenTrace();
  const call = moneyPathCall();
  const callDetail = moneyPathCallDetail();

  queryState.issue = issue;
  queryState.issues = [issue];
  queryState.calls = [call];
  queryState.callDetail = callDetail;
  queryState.goldenSets = [goldenSet];
  queryState.goldenTraces = [goldenTrace];
  queryState.replayDetail = replayDetail;
  queryState.ciRunDetail = ciRunDetail;
  queryState.ciDetail = ciDetail;
  queryState.replayRuns = [ciRun, replayRun];

  api.getBillingMe.mockResolvedValue(moneyPathBilling);
  api.getIssue.mockResolvedValue(issue);
  api.listIssues.mockResolvedValue({
    items: [issue],
    next_cursor: null,
    total_in_page: 1,
  });
  api.listReplayRuns.mockResolvedValue({
    items: [ciRun, replayRun],
    next_cursor: null,
    total_in_page: 2,
  });
  api.getReplayRun.mockImplementation((runId: string) =>
    Promise.resolve(runId === moneyPathIds.ciRunId ? ciRunDetail : replayDetail),
  );
  api.getRegressionCIRun.mockImplementation((runId: string) =>
    runId === moneyPathIds.ciRunId
      ? Promise.resolve(ciDetail)
      : Promise.reject(new Error("missing CI detail")),
  );
  api.listGoldenSets.mockResolvedValue({
    items: [goldenSet],
    next_cursor: null,
    total_in_page: 1,
  });
  api.getGoldenSet.mockResolvedValue(goldenSet);
  api.listGoldenTraces.mockResolvedValue({
    items: [goldenTrace],
    total_in_page: 1,
  });
  api.runGoldenSet.mockResolvedValue({
    id: moneyPathIds.replayRunId,
    project_id: moneyPathIds.projectId,
    golden_set_id: moneyPathIds.goldenSetId,
    trigger: "manual",
    git_sha: null,
    status: "pending",
    created_at: "2026-06-04T05:32:34.000Z",
    summary_url: `/v1/replay/runs/${moneyPathIds.replayRunId}`,
    idempotent: false,
  });
  api.runRegressionCI.mockResolvedValue({
    run_id: moneyPathIds.ciRunId,
    project_id: moneyPathIds.projectId,
    git_sha: moneyPathIds.gitSha,
    status: "queued",
    summary_url: `/v1/regression-ci/runs/${moneyPathIds.ciRunId}`,
  });
}

describe("money-path dashboard regression proof", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.params = {};
    navigation.searchParams = "";
    navigation.push.mockReset();
    navigation.replace.mockReset();
    hookActions.callReplayMutate.mockReset();
    hookActions.issueReplayMutate.mockReset();
    seedMoneyPathDashboardState();
  });

  it("renders the money-path issue in Command Center with verified replay state", async () => {
    render(<IssuesPage />);

    expect(await screen.findByRole("heading", { name: "Failures" })).toBeInTheDocument();
    const row = screen.getByText("Refund status tool skipped").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("Verified fix")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText(/refund-support-agent.*17 affected traces/)).toBeInTheDocument();
    expect(within(row as HTMLElement).getByRole("link", { name: /View issue/i }).getAttribute("href")).toBe(
      `/issues/${moneyPathIds.issueId}`,
    );
  });

  it("renders issue proof panel from replay to Golden to failed CI gate", async () => {
    navigation.params = { id: moneyPathIds.issueId };

    render(<IssueDetailPage />);

    expect(await screen.findByRole("heading", { name: "Refund status tool skipped" })).toBeInTheDocument();
    expect(screen.getByLabelText("Issue proof ladder")).toBeInTheDocument();
    expect(screen.getAllByText("Trusted").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Active Golden linked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Gate linked").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Open Golden/i })[0].getAttribute("href")).toBe(
      `/goldens/${moneyPathIds.goldenSetId}`,
    );
    expect(screen.getAllByRole("link", { name: /Open CI gate/i })[0].getAttribute("href")).toBe(
      `/ci-gates/${moneyPathIds.ciRunId}`,
    );
    expect(screen.getByText("CI gate proof exists. Repeat spend is now guarded by replay before merge.")).toBeInTheDocument();
    expect(screen.getByText("fail")).toBeInTheDocument();
  });

  it("renders Replay queue with the verified replay and failed CI replay run", () => {
    render(<ReplayPage />);

    expect(screen.getByRole("heading", { name: "Replay" })).toBeInTheDocument();
    expect(screen.getAllByText(moneyPathIds.issueId).length).toBeGreaterThan(0);
    expect(screen.getByText(`Run ${moneyPathIds.replayRunId.slice(0, 16)}`)).toBeInTheDocument();
    expect(screen.getByText(`Run ${moneyPathIds.ciRunId.slice(0, 16)}`)).toBeInTheDocument();
    expect(screen.getAllByText(/verified fix/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fail").length).toBeGreaterThan(0);
  });

  it("renders the Golden set as CI-blocking and needing review after the failed Golden run", () => {
    render(<GoldensPage />);

    expect(screen.getByRole("heading", { name: "Goldens" })).toBeInTheDocument();
    const row = screen.getByText("Refund status protected flow").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("Protects refund status lookups from generic policy-only answers.")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("Blocks CI")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("Needs review")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByRole("link", { name: "View" }).getAttribute("href")).toBe(
      `/goldens/${moneyPathIds.goldenSetId}`,
    );
  });

  it("renders Golden detail with source call, active trace, and failed latest replay", () => {
    navigation.params = { id: moneyPathIds.goldenSetId };

    render(<GoldenDetailPage />);

    expect(screen.getByRole("heading", { name: "Refund status protected flow" })).toBeInTheDocument();
    expect(screen.getAllByText("Blocks CI").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Needs review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RF-1001/).length).toBeGreaterThan(0);
    expect(screen.getByText("View source evidence JSON")).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: /View call/i })) {
      expect(link.getAttribute("href")).toBe(`/calls/${moneyPathIds.callId}`);
    }
  });

  it("renders CI Gates list as a failed blocking PR gate for the money path", async () => {
    render(<CiGatesPage />);

    expect(await screen.findByRole("heading", { name: "CI Gates" })).toBeInTheDocument();
    expect(screen.getByText("PR #43 - Refund tool guard regression")).toBeInTheDocument();
    expect(screen.getByText("break/refund-tool-call")).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getByText("Mocked tool replay")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review" }).getAttribute("href")).toBe(
      `/ci-gates/${moneyPathIds.ciRunId}`,
    );
  });

  it("renders CI gate detail with blocked verdict, failed flow, and proof links", async () => {
    navigation.params = { runId: moneyPathIds.ciRunId };

    render(<CiGateDetailPage />);

    expect(await screen.findByRole("heading", { name: "PR #43 - Refund tool guard regression" })).toBeInTheDocument();
    expect(screen.getAllByText("Regression CI blocked this change.").length).toBeGreaterThan(0);
    expect(screen.getByText("Refund tool call requirement (1)")).toBeInTheDocument();
    expect(screen.getByText("The PR skipped get_refund_status again.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View replay" }).getAttribute("href")).toBe(
      `/replay/${moneyPathIds.ciRunId}`,
    );
    expect(screen.getByRole("link", { name: "View Golden set" }).getAttribute("href")).toBe(
      `/goldens/${moneyPathIds.goldenSetId}`,
    );
    expect(screen.getByRole("link", { name: "Open PR" }).getAttribute("href")).toBe(moneyPathIds.prUrl);
  });

  it("keeps the Issue replay action wired to the same money-path issue id", async () => {
    render(<ReplayPage />);

    screen.getByRole("button", { name: "Start replay" }).click();

    await waitFor(() =>
      expect(hookActions.issueReplayMutate).toHaveBeenCalledWith({
        issueId: moneyPathIds.issueId,
        payload: { replay_mode: "real_llm" },
      }),
    );
    expect(navigation.push).toHaveBeenCalledWith(`/replay/${moneyPathIds.replayRunId}`);
  });
});
