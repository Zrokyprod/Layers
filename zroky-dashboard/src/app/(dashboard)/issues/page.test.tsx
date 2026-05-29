import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IssuesPage from "./page";

const api = vi.hoisted(() => ({
  createReplayRunFromIssue: vi.fn(),
  listIssues: vi.fn(),
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

describe("IssuesPage MVP list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.push.mockReset();
  });

  it("renders issue rows with required columns and actions", async () => {
    mockIssueList();

    render(<IssuesPage />);

    expect(await screen.findByRole("heading", { name: "Issues" })).toBeInTheDocument();
    expect(screen.getByText("Grouped production failures detected across your agents.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review replay gaps" })).toBeInTheDocument();

    const filterBar = screen.getByRole("region", { name: "Issue filters" });
    for (const label of ["Status", "Severity", "Failure code", "Agent", "Replay proof", "Search"]) {
      expect(within(filterBar).getByLabelText(label)).toBeInTheDocument();
    }

    const headers = within(screen.getByRole("table")).getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(["Issue", "Severity", "Impact", "Replay proof", "Status", "Last seen", "Action"]);

    const checkoutRow = rowForIssue("Checkout loop");
    expect(within(checkoutRow).getByText("Loop Detected · Checkout Agent · 42 affected calls")).toBeInTheDocument();
    expect(within(checkoutRow).getByText("$12.00")).toBeInTheDocument();
    expect(within(checkoutRow).getByText("No trusted replay")).toBeInTheDocument();
    expect(within(checkoutRow).getByRole("button", { name: /Replay/i })).toBeInTheDocument();
    expect(within(checkoutRow).getByRole("link", { name: /View issue/i })).toBeInTheDocument();

    const verifiedRow = rowForIssue("Refund fix verified");
    expect(within(verifiedRow).getByText("Verified fix")).toBeInTheDocument();
    expect(within(verifiedRow).getByRole("link", { name: /Create Golden/i }).getAttribute("href")).toBe(
      "/goldens?call_id=call_2",
    );
    expect(within(verifiedRow).getByRole("link", { name: /View issue/i })).toBeInTheDocument();
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

    fireEvent.change(screen.getByPlaceholderText("Search issues, agents, failure codes..."), {
      target: { value: "billing" },
    });
    expect(screen.getByText("Billing proof missing")).toBeInTheDocument();
  });

  it.each([
    ["covered_failed", "Replay failed"],
    ["sanity_replay_passed", "Stub only"],
    ["real_replay_missing_tool_proof", "Missing tool proof"],
    ["stub_only", "Stub only"],
    ["not_verified", "Not verified"],
    ["tool_snapshot_missing", "Missing tool proof"],
    ["inconclusive", "Inconclusive"],
    ["unknown", "No trusted replay"],
  ])("renders replay proof label %s as %s and blocks Create Golden", async (status, label) => {
    mockIssueList([issue({ replay_coverage_status: status, sample_call_id: "call_untrusted" })]);

    render(<IssuesPage />);

    await screen.findByText("Checkout loop");
    const row = rowForIssue("Checkout loop");
    expect(within(row).getByText(label)).toBeInTheDocument();
    expect(within(row).queryByText("Create Golden")).toBeNull();
    expect(within(row).getByRole("button", { name: /Replay/i })).toBeInTheDocument();
  });

  it("falls back to View issue when no sample call is available", async () => {
    mockIssueList([issue({ sample_call_id: null })]);

    render(<IssuesPage />);

    await screen.findByText("Checkout loop");
    const row = rowForIssue("Checkout loop");
    expect(within(row).queryByRole("button", { name: /Replay/i })).toBeNull();
    expect(within(row).getAllByRole("link", { name: /View issue/i }).length).toBeGreaterThan(0);
  });
});
