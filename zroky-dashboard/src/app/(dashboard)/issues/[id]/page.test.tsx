import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IssueDetailPage from "./page";

const api = vi.hoisted(() => ({
  createReplayRunFromCall: vi.fn(),
  createReplayRunFromIssue: vi.fn(),
  createProviderKey: vi.fn(),
  getBillingMe: vi.fn(),
  getIssue: vi.fn(),
  ignoreIssue: vi.fn(),
  promoteIssueToGolden: vi.fn(),
  resolveIssue: vi.fn(),
  runIssueCiGate: vi.fn(),
  updateIssueTriage: vi.fn(),
}));

const providerKeyState = vi.hoisted(() => ({
  active: true,
}));

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  issueId: "issue_1",
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
  useParams: () => ({ id: navigation.issueId }),
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

function proof(
  overrides: Partial<import("@/lib/types").IssueProofSnapshot> = {},
): import("@/lib/types").IssueProofSnapshot {
  return {
    replay: {
      run_id: null,
      status: null,
      replay_mode: null,
      verified_fix: false,
      summary_url: null,
      created_at: null,
      completed_at: null,
    },
    golden: {
      golden_set_id: null,
      golden_set_name: null,
      golden_trace_id: null,
      status: null,
      blocks_ci: false,
      trace_count: 0,
      created_at: null,
    },
    ci_gate: {
      run_id: null,
      status: null,
      git_sha: null,
      summary_url: null,
      created_at: null,
      completed_at: null,
    },
    ...overrides,
  };
}

function issue(overrides: Partial<import("@/lib/types").IssueItem> = {}): import("@/lib/types").IssueItem {
  return {
    id: "issue_1",
    project_id: "proj_1",
    failure_code: "LOOP_DETECTED",
    prompt_fingerprint: "prompt_fp_1",
    agent_name: "checkout-agent",
    status: "open",
    severity: "critical",
    occurrence_count: 42,
    blast_radius_usd: 84,
    first_seen_at: "2026-05-28T10:00:00.000Z",
    last_seen_at: now,
    sample_call_id: "call_1",
    sample_diagnosis_id: "diag_1",
    last_fix_id: null,
    resolved_at: null,
    resolution_source: null,
    assigned_to: "oncall",
    deploy_pr_url: "https://github.com/acme/repo/pull/42",
    created_at: now,
    updated_at: now,
    title: "Checkout loop",
    affected_agent: "Checkout Agent",
    affected_workflow: "checkout",
    root_cause: "Agent repeated the same payment tool call.",
    evidence_traces: [
      {
        call_id: "call_1",
        trace_id: "trace_1",
        workflow_name: "checkout",
        prompt_version: "v7",
        model: "gpt-4.1",
        provider: "openai",
        status: "failed",
        latency_ms: 1234,
        cost_usd: 0.42,
        created_at: now,
        evidence_summary: "The model retried the same tool call three times.",
      },
    ],
    cost_impact_usd: 18,
    user_impact: "Checkout users could not complete payment.",
    replay_coverage_status: "not_covered",
    recommended_next_action: "Replay the issue and verify the payment retry guard.",
    priority_score: 99,
    proof: proof(),
    ...overrides,
  };
}

function mockDetail(
  issueOverrides: Partial<import("@/lib/types").IssueItem> = {},
  planTemplate: Record<string, unknown> = {
    "pilot.root_cause_diagnosis": true,
    "pilot.replay_stub": true,
    "pilot.goldens_basic": true,
  },
) {
  const loadedIssue = issue(issueOverrides);
  api.getIssue.mockResolvedValue(loadedIssue);
  api.getBillingMe.mockResolvedValue({
    org_id: "org_1",
    plan_code: Object.keys(planTemplate).length === 0 ? "free" : "pilot",
    status: "active",
    seats: 1,
    payment_provider: "skydo",
    payment_customer_ref: null,
    payment_subscription_ref: null,
    payment_request_ref: null,
    stripe_customer_id: null,
    stripe_sub_id: null,
    current_period_end: null,
    trial_end: null,
    sla_tier: "standard",
    plan_template: planTemplate,
  });
  api.createReplayRunFromIssue.mockResolvedValue({
    id: "run_issue",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    status: "pending",
    created_at: now,
    summary_url: "/replay/run_issue",
    replay_mode: "mocked_tool",
  });
  api.createReplayRunFromCall.mockResolvedValue({
    id: "run_call",
    project_id: "proj_1",
    golden_set_id: "golden_1",
    trigger: "manual",
    status: "pending",
    created_at: now,
    summary_url: "/replay/run_call",
    replay_mode: "mocked_tool",
  });
  api.updateIssueTriage.mockResolvedValue(loadedIssue);
  api.resolveIssue.mockResolvedValue({ ...loadedIssue, status: "resolved" });
  api.ignoreIssue.mockResolvedValue({ ...loadedIssue, status: "ignored" });
  api.promoteIssueToGolden.mockResolvedValue({
    issue: {
      ...loadedIssue,
      proof: proof({
        golden: {
          golden_set_id: "golden_1",
          golden_set_name: "Issue regression guards",
          golden_trace_id: "trace_golden_1",
          status: "active",
          blocks_ci: true,
          trace_count: 1,
          created_at: now,
        },
      }),
    },
    golden: {
      golden_set_id: "golden_1",
      golden_set_name: "Issue regression guards",
      golden_trace_id: "trace_golden_1",
      status: "active",
      blocks_ci: true,
      trace_count: 1,
      created_at: now,
    },
  });
  api.runIssueCiGate.mockResolvedValue({
    issue: {
      ...loadedIssue,
      proof: proof({
        golden: {
          golden_set_id: "golden_1",
          golden_set_name: "Issue regression guards",
          golden_trace_id: "trace_golden_1",
          status: "active",
          blocks_ci: true,
          trace_count: 1,
          created_at: now,
        },
        ci_gate: {
          run_id: "ci_run_1",
          status: "pending",
          git_sha: null,
          summary_url: "/replay/ci_run_1",
          created_at: now,
          completed_at: null,
        },
      }),
    },
    ci_gate: {
      run_id: "ci_run_1",
      status: "pending",
      git_sha: null,
      summary_url: "/replay/ci_run_1",
      created_at: now,
      completed_at: null,
    },
  });
}

describe("IssueDetailPage MVP investigation layout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    providerKeyState.active = true;
    navigation.push.mockReset();
    navigation.issueId = "issue_1";
  });

  it("renders the two-column incident investigation page", async () => {
    mockDetail();

    render(<IssueDetailPage />);

    expect(await screen.findByRole("heading", { name: "Checkout loop" })).toBeInTheDocument();
    expect(screen.getByText(/Loop Detected.*Checkout Agent.*Production/)).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getAllByText("No trusted replay").length).toBeGreaterThan(0);
    expect(screen.getAllByText("open").length).toBeGreaterThan(0);
    for (const label of ["Occurrences", "Impact", "First seen", "Last seen", "Sample call"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(document.querySelector(".imd-layout")).toBeInTheDocument();
    expect(screen.getByLabelText("Resolution")).toBeInTheDocument();
    expect(screen.getByText("Status: Open")).toBeInTheDocument();
    for (const heading of [
      "Executive diagnosis",
      "Evidence workbench",
      "Replay, Golden, and CI readiness",
      "Cost impact",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Issue proof ladder")).toBeInTheDocument();
    expect(screen.getByText("Agent repeated the same payment tool call.")).toBeInTheDocument();
    expect(screen.getByText("Recommended path")).toBeInTheDocument();
    expect(screen.getByText("Replay the issue and verify the payment retry guard.")).toBeInTheDocument();
    expect(screen.getAllByText("The model retried the same tool call three times.").length).toBeGreaterThan(0);
    expect(screen.getByText("Status / owner")).toBeInTheDocument();
    expect(screen.getByText("CI gate readiness")).toBeInTheDocument();
    expect(screen.getAllByText("Cost impact").length).toBeGreaterThan(0);
    expect(screen.getByText("$84.00 from 42 calls")).toBeInTheDocument();
  });

  it("renders a calm root cause fallback when missing", async () => {
    mockDetail({ root_cause: null, evidence_traces: [] });

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    expect(screen.getByText("No structured root cause available yet.")).toBeInTheDocument();
    expect(screen.getByText("No structured evidence yet.")).toBeInTheDocument();
  });

  it("shows Run trusted replay for untrusted replay states", async () => {
    mockDetail({ replay_coverage_status: "not_verified" });

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Run trusted replay/i }).length).toBeGreaterThan(0);
    expect(screen.queryByText("Create Golden")).toBeNull();
  });

  it("promotes a verified fix to an active Golden", async () => {
    mockDetail({ replay_coverage_status: "verified_fix" });

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    fireEvent.click(screen.getByRole("button", { name: /Promote to Golden/i }));

    await waitFor(() => expect(api.promoteIssueToGolden).toHaveBeenCalledWith("issue_1", { blocks_ci: true }));
    expect(await screen.findByText("Golden guard created and linked to this issue.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Open Golden/i })[0].getAttribute("href")).toBe("/goldens/golden_1");
  });

  it.each(["stub_only", "not_verified"])("does not show Golden promotion for %s", async (status) => {
    mockDetail({ replay_coverage_status: status });

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    expect(screen.queryByText("Create Golden")).toBeNull();
    expect(screen.queryByRole("button", { name: /Promote to Golden/i })).toBeNull();
    expect(screen.getAllByText("Needs trusted replay before Golden promotion.").length).toBeGreaterThan(0);
  });

  it("does not show Golden promotion when verified_fix has no sample call", async () => {
    mockDetail({ replay_coverage_status: "verified_fix", sample_call_id: null });

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    expect(screen.queryByText("Create Golden")).toBeNull();
    expect(screen.queryByRole("button", { name: /Promote to Golden/i })).toBeNull();
  });

  it("runs a CI gate when an active Golden and PR are linked", async () => {
    mockDetail(
      {
        replay_coverage_status: "verified_fix",
        proof: proof({
          golden: {
            golden_set_id: "golden_1",
            golden_set_name: "Issue regression guards",
            golden_trace_id: "trace_golden_1",
            status: "active",
            blocks_ci: true,
            trace_count: 1,
            created_at: now,
          },
        }),
      },
      {
        "pilot.replay_stub": true,
        "pilot.goldens_basic": true,
        "pro.ci_gate_nonblocking": true,
      },
    );

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    fireEvent.click(screen.getAllByRole("button", { name: /Run CI gate/i })[0]);

    await waitFor(() =>
      expect(api.runIssueCiGate).toHaveBeenCalledWith("issue_1", {
        replay_mode: "real_llm",
      }),
    );
    expect(navigation.push).toHaveBeenCalledWith("/ci-gates/ci_run_1");
  });

  it("calls existing resolve and ignore APIs", async () => {
    mockDetail();

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));
    expect(screen.getByText("Resolve this issue?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm resolve" }));
    await waitFor(() => expect(api.resolveIssue).toHaveBeenCalledWith("issue_1", { resolution_source: "manual" }));

    fireEvent.click(screen.getByRole("button", { name: "Ignore" }));
    expect(screen.getByText("Ignore this issue?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm ignore" }));
    await waitFor(() => expect(api.ignoreIssue).toHaveBeenCalledWith("issue_1"));
  });

  it("calls updateIssueTriage for assignment and PR URL", async () => {
    mockDetail();

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    fireEvent.change(screen.getByLabelText("Assign"), { target: { value: "refund-oncall" } });
    fireEvent.change(screen.getByLabelText("Add PR URL"), { target: { value: "https://github.com/acme/repo/pull/99" } });
    fireEvent.click(screen.getByRole("button", { name: "Save triage" }));

    await waitFor(() =>
      expect(api.updateIssueTriage).toHaveBeenCalledWith("issue_1", {
        assigned_to: "refund-oncall",
        deploy_pr_url: "https://github.com/acme/repo/pull/99",
      }),
    );
  });

  it("can replay the sample call using the existing replay API", async () => {
    mockDetail();

    render(<IssueDetailPage />);

    await screen.findByRole("heading", { name: "Checkout loop" });
    const sampleSection = screen.getByRole("heading", { name: "Evidence workbench" }).closest(".imd-card");
    if (!sampleSection) throw new Error("Missing sample traces section");
    fireEvent.click(within(sampleSection).getAllByRole("button", { name: /Replay this call/i })[0]);

    await waitFor(() =>
      expect(api.createReplayRunFromCall).toHaveBeenCalledWith("call_1", {
        replay_mode: "real_llm",
      }),
    );
  });
});
