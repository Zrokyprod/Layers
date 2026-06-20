import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IssuesPage from "./page";

const api = vi.hoisted(() => ({
  createReplayRunFromIssue: vi.fn(),
  listIssues: vi.fn(),
}));

const providerKeyState = vi.hoisted(() => ({
  active: true,
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
  useRouter: () => ({
    push: navigation.push,
  }),
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
      items: providerKeyState.active ? [{ id: "key_1", is_active: true }] : [],
      total_in_page: providerKeyState.active ? 1 : 0,
    },
    refetch: vi.fn(async () => ({
      data: {
        items: providerKeyState.active ? [{ id: "key_1", is_active: true }] : [],
        total_in_page: providerKeyState.active ? 1 : 0,
      },
    })),
  }),
}));

const now = "2026-05-29T10:00:00.000Z";

function issue(overrides: Partial<import("@/lib/types").IssueItem> = {}): import("@/lib/types").IssueItem {
  return {
    id: "issue_1",
    project_id: "proj_1",
    failure_code: "LOOP_DETECTED",
    prompt_fingerprint: null,
    agent_name: "checkout-agent",
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
    what_happened: "Agent repeated the same tool call.",
    why_it_matters: "Repeat failures should become replay guards.",
    affected_trace_count: 42,
    affected_user_count: 9,
    suspected_introduced_version: "deployment_id:dep-42",
    blast_radius: {
      affected_traces: 42,
      affected_users: 9,
      cost_usd: 12,
      severity: "critical",
    },
    root_cause: "Agent repeated the same tool call.",
    evidence_traces: [],
    cost_impact_usd: 18,
    user_impact: "Checkout users blocked",
    replay_coverage_status: "not_covered",
    recommended_next_action: "Replay",
    priority_score: 99,
    ...overrides,
  };
}

const issueItems = [
  issue(),
  issue({
    id: "issue_2",
    title: "Refund fix verified",
    failure_code: "ACCURACY_REGRESSION",
    affected_agent: "Refund Agent",
    severity: "high",
    replay_coverage_status: "verified_fix",
    sample_call_id: "call_2",
    priority_score: 80,
  }),
  issue({
    id: "issue_3",
    title: "Billing proof missing",
    affected_agent: "Billing Agent",
    severity: "medium",
    replay_coverage_status: "real_replay_missing_tool_proof",
    sample_call_id: "call_3",
    priority_score: 60,
  }),
  issue({
    id: "issue_4",
    title: "Resolved schema issue",
    status: "resolved",
    severity: "low",
    replay_coverage_status: "stub_only",
    sample_call_id: "call_4",
    priority_score: 40,
  }),
];

function mockIssueList(items = issueItems) {
  api.listIssues.mockImplementation(async (params: { status?: string; severity?: string; failure_code?: string; agent_name?: string }) => {
    let filtered = [...items];
    if (params.status && params.status !== "all") {
      filtered = filtered.filter((item) => item.status === params.status);
    }
    if (params.severity) {
      filtered = filtered.filter((item) => item.severity === params.severity);
    }
    if (params.failure_code) {
      filtered = filtered.filter((item) => item.failure_code.toLowerCase().includes(params.failure_code!.toLowerCase()));
    }
    if (params.agent_name) {
      filtered = filtered.filter((item) =>
        `${item.affected_agent ?? ""} ${item.agent_name ?? ""}`.toLowerCase().includes(params.agent_name!.toLowerCase()),
      );
    }
    return {
      items: filtered,
      next_cursor: null,
      total_in_page: filtered.length,
    };
  });
}

function rowForIssue(title: string): HTMLElement {
  const table = screen.getByRole("table");
  const row = within(table).getByText(title).closest("tr");
  if (!row) throw new Error(`Missing row for ${title}`);
  return row;
}

describe("FailuresPage MVP list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    providerKeyState.active = true;
    navigation.push.mockReset();
  });

  it("renders issue rows with required columns and actions", async () => {
    mockIssueList();

    render(<IssuesPage />);

    expect(await screen.findByRole("heading", { name: "Incidents" })).toBeInTheDocument();
    expect(screen.getByText("Production failures that need replay proof, Contract activation, or CI protection.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review replay gaps" })).toBeInTheDocument();

    const filterBar = screen.getByRole("region", { name: "Incident filters" });
    for (const label of ["Status", "Severity", "Failure code", "Agent", "Replay proof", "Search"]) {
      expect(within(filterBar).getByLabelText(label)).toBeInTheDocument();
    }

    const headers = within(screen.getByRole("table")).getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(["Incident", "Severity", "Impact", "Replay proof", "Status", "Last seen", "Next action", "Action"]);

    const checkoutRow = rowForIssue("Checkout loop");
    expect(
      within(checkoutRow).getByText("Loop Detected · Checkout Agent · 42 affected traces - 9 users · deployment_id:dep-42"),
    ).toBeInTheDocument();
    expect(within(checkoutRow).getByText("$12.00")).toBeInTheDocument();
    expect(within(checkoutRow).getByText("Needs verified replay")).toBeInTheDocument();
    expect(within(checkoutRow).getByRole("link", { name: "Verify replay" }).getAttribute("href")).toBe("/issues/issue_1");
    expect(within(checkoutRow).getByRole("button", { name: /Replay/i })).toBeInTheDocument();
    expect(within(checkoutRow).queryByRole("link", { name: /View issue/i })).not.toBeInTheDocument();

    const verifiedRow = rowForIssue("Refund fix verified");
    expect(within(verifiedRow).getByText("Verified fix")).toBeInTheDocument();
    const promoteLinks = within(verifiedRow).getAllByRole("link", { name: "Promote Contract" });
    expect(promoteLinks.map((link) => link.getAttribute("href"))).toEqual([
      "/contracts?call_id=call_2",
      "/contracts?call_id=call_2",
    ]);
    expect(within(verifiedRow).queryByRole("link", { name: /View issue/i })).not.toBeInTheDocument();
  });

  it("filters by status and severity through the existing list API", async () => {
    mockIssueList();

    render(<IssuesPage />);

    expect(await screen.findByText("Checkout loop")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });
    await waitFor(() => expect(screen.getByText("Resolved schema issue")).toBeInTheDocument());
    expect(screen.queryByText("Checkout loop")).toBeNull();

    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "low" } });
    await waitFor(() => {
      expect(api.listIssues).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "resolved", severity: "low" }),
        expect.any(AbortSignal),
      );
    });
  });

  it("filters loaded rows by replay proof and local search", async () => {
    mockIssueList();

    render(<IssuesPage />);

    expect(await screen.findByText("Checkout loop")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Replay proof"), { target: { value: "missing_tool_proof" } });
    expect(await screen.findByText("Billing proof missing")).toBeInTheDocument();
    expect(screen.queryByText("Checkout loop")).toBeNull();

    fireEvent.change(screen.getByPlaceholderText("Search incidents, agents, failure codes..."), {
      target: { value: "billing" },
    });
    expect(screen.getByText("Billing proof missing")).toBeInTheDocument();
  });

  it.each([
    ["covered_failed", "Replay failed"],
    ["sanity_replay_passed", "Fixture validation only"],
    ["real_replay_missing_tool_proof", "Missing tool proof"],
    ["stub_only", "Fixture validation only"],
    ["not_verified", "Not verified"],
    ["tool_snapshot_missing", "Missing tool proof"],
    ["inconclusive", "Inconclusive"],
    ["unknown", "Needs verified replay"],
  ])("renders replay proof label %s as %s and blocks Contract promotion", async (status, label) => {
    mockIssueList([issue({ replay_coverage_status: status, sample_call_id: "call_untrusted" })]);

    render(<IssuesPage />);

    await screen.findByText("Checkout loop");
    const row = rowForIssue("Checkout loop");
    expect(within(row).getByText(label)).toBeInTheDocument();
    expect(within(row).queryByText("Promote Contract")).toBeNull();
    expect(within(row).getByRole("button", { name: /Replay/i })).toBeInTheDocument();
  });

  it("falls back to View incident when no sample call is available", async () => {
    mockIssueList([issue({ sample_call_id: null })]);

    render(<IssuesPage />);

    await screen.findByText("Checkout loop");
    const row = rowForIssue("Checkout loop");
    expect(within(row).queryByRole("button", { name: /Replay/i })).toBeNull();
    expect(within(row).getByRole("link", { name: "Assign / resolve" }).getAttribute("href")).toBe("/issues/issue_1");
    expect(within(row).getByRole("link", { name: /View incident/i }).getAttribute("href")).toBe("/issues/issue_1");
  });

  it("does not offer Contract promotion again when an active Contract already exists without a linked PR", async () => {
    mockIssueList([
      issue({
        replay_coverage_status: "verified_fix",
        proof: {
          replay: {
            run_id: "run_1",
            status: "pass",
            replay_mode: "real_llm",
            verified_fix: true,
            summary_url: "/v1/replay/runs/run_1",
            created_at: now,
            completed_at: now,
          },
          golden: {
            golden_set_id: "golden_1",
            golden_set_name: "Checkout guards",
            golden_trace_id: "trace_golden_1",
            status: "active",
            blocks_ci: true,
            trace_count: 1,
            created_at: now,
          },
          ci_gate: {
            run_id: null,
            status: null,
            git_sha: null,
            summary_url: null,
            created_at: null,
            completed_at: null,
          },
        },
      }),
    ]);

    render(<IssuesPage />);

    await screen.findByText("Checkout loop");
    const row = rowForIssue("Checkout loop");
    expect(within(row).queryByRole("link", { name: /Promote Contract/i })).not.toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Assign / resolve" }).getAttribute("href")).toBe("/issues/issue_1");
  });

  it("sorts by severity, replay gap, cost, and occurrence count while showing proof-based next actions", async () => {
    mockIssueList([
      issue({
        id: "issue_verified",
        title: "Verified high impact",
        severity: "high",
        replay_coverage_status: "verified_fix",
        blast_radius_usd: 500,
        occurrence_count: 99,
      }),
      issue({
        id: "issue_occurrence_low",
        title: "Same cost fewer occurrences",
        severity: "high",
        replay_coverage_status: "not_covered",
        blast_radius_usd: 10,
        occurrence_count: 1,
      }),
      issue({
        id: "issue_occurrence_high",
        title: "Same cost more occurrences",
        severity: "high",
        replay_coverage_status: "not_covered",
        blast_radius_usd: 10,
        occurrence_count: 7,
      }),
      issue({
        id: "issue_cost",
        title: "Higher cost replay gap",
        severity: "high",
        replay_coverage_status: "not_covered",
        blast_radius_usd: 12,
        occurrence_count: 1,
      }),
      issue({
        id: "issue_ci_ready",
        title: "Contract ready for CI",
        severity: "medium",
        replay_coverage_status: "verified_fix",
        deploy_pr_url: "https://github.com/acme/repo/pull/42",
        proof: {
          replay: {
            run_id: "run_1",
            status: "pass",
            replay_mode: "real_llm",
            verified_fix: true,
            summary_url: "/v1/replay/runs/run_1",
            created_at: now,
            completed_at: now,
          },
          golden: {
            golden_set_id: "golden_1",
            golden_set_name: "Checkout guards",
            golden_trace_id: "trace_golden_1",
            status: "active",
            blocks_ci: true,
            trace_count: 1,
            created_at: now,
          },
          ci_gate: {
            run_id: null,
            status: null,
            git_sha: null,
            summary_url: null,
            created_at: null,
            completed_at: null,
          },
        },
      }),
      issue({
        id: "issue_ci_linked",
        title: "CI already linked",
        severity: "low",
        replay_coverage_status: "verified_fix",
        proof: {
          replay: {
            run_id: "run_2",
            status: "pass",
            replay_mode: "real_llm",
            verified_fix: true,
            summary_url: "/v1/replay/runs/run_2",
            created_at: now,
            completed_at: now,
          },
          golden: {
            golden_set_id: "golden_2",
            golden_set_name: "Linked guards",
            golden_trace_id: "trace_golden_2",
            status: "active",
            blocks_ci: true,
            trace_count: 1,
            created_at: now,
          },
          ci_gate: {
            run_id: "ci_run_2",
            status: "fail",
            git_sha: "abc123",
            summary_url: "/v1/regression-ci/runs/ci_run_2",
            created_at: now,
            completed_at: now,
          },
        },
      }),
    ]);

    render(<IssuesPage />);

    await screen.findByText("Higher cost replay gap");
    const tableRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(tableRows.map((row) => row.querySelector(".im-issue-cell a")?.textContent)).toEqual([
      "Higher cost replay gap",
      "Same cost more occurrences",
      "Same cost fewer occurrences",
      "Verified high impact",
      "Contract ready for CI",
      "CI already linked",
    ]);

    expect(
      within(rowForIssue("Contract ready for CI"))
        .getAllByRole("link", { name: "Run CI gate" })
        .some((link) => link.getAttribute("href") === "/issues/issue_ci_ready"),
    ).toBe(true);
    expect(
      within(rowForIssue("CI already linked"))
        .getAllByRole("link", { name: "Open CI gate" })
        .some((link) => link.getAttribute("href") === "/ci-gates/ci_run_2"),
    ).toBe(true);
  });
});
