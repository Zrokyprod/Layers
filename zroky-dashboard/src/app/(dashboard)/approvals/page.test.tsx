import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActionIntentResponse,
  RuntimePolicyDecisionResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";

import RuntimeApprovalsPage from "./page";

const fixtures = vi.hoisted(() => {
  const decision: RuntimePolicyDecisionResponse = {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_refund",
    call_id: "call_refund",
    agent_name: "Refund agent",
    role: "ops",
    action_type: "refund",
    tool_name: "refund_payment",
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["refund amount above runtime mandate"],
    request: { amount_usd: 42.5, customer_id: "cus_1" },
    policy_snapshot: { max_refund_usd: 25, require_approval: true },
    intended_action: { summary: "Refund payment rf_100", refund_id: "rf_100", amount_usd: 42.5 },
    trace_context: { agent_name: "Refund agent", trace_id: "trace_refund" },
    policy_hit: { policy: "money_action", threshold_usd: 25 },
    business_impact: { risk_category: "financial_loss", amount_usd: 42.5 },
    audit_log: [
      {
        id: "audit_requested",
        event_type: "approval_requested",
        actor: "system",
        reason: "refund amount above runtime mandate",
        before: null,
        after: null,
        created_at: "2026-06-20T09:00:00Z",
      },
    ],
    created_at: "2026-06-20T09:00:00Z",
    expires_at: "2099-06-20T09:15:00Z",
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    consumed_at: null,
    consumed_by_decision_id: null,
  };

  const evidenceDecision = {
    ...decision,
    approval_scope_hash: "scope_hash_1",
  };

  const matchedPack: RuntimePolicyEvidencePackResponse = {
    schema_version: "runtime_policy_evidence.v1",
    project_id: "proj_1",
    decision_id: "decision_1",
    verification_status: "pass",
    decision: evidenceDecision,
    related_decisions: [],
    audit_log: [
      {
        id: "audit_requested",
        decision_id: "decision_1",
        event_type: "approval_requested",
        actor: "system",
        reason: "refund amount above runtime mandate",
        before: null,
        after: null,
        created_at: "2026-06-20T09:00:00Z",
      },
      {
        id: "audit_approved",
        decision_id: "decision_1",
        event_type: "approved",
        actor: "ops@example.com",
        reason: "customer support ticket verified",
        before: null,
        after: { status: "approved" },
        created_at: "2026-06-20T09:01:00Z",
      },
    ],
    trace_policy_spans: [],
    outcome_reconciliation: [
      {
        id: "check_1",
        project_id: "proj_1",
        call_id: "call_refund",
        trace_id: "trace_refund",
        runtime_policy_decision_id: "decision_1",
        action_type: "refund",
        connector_type: "ledger_api",
        reverify_connector: "ledger_refund_api",
        system_ref: "ledger:rf_100",
        verdict: "matched",
        reason: "all_compared_fields_matched",
        amount_usd: 42.5,
        currency: "USD",
        claimed: { refund_id: "rf_100", amount_usd: 42.5 },
        actual: { refund_id: "rf_100", amount_usd: 42.5, status: "posted" },
        comparison: { mismatches: [] },
        idempotency_key: "call_refund:rf_100",
        metadata: { source: "fixture" },
        checked_at: "2026-06-20T09:02:00Z",
        created_at: "2026-06-20T09:02:00Z",
      },
    ],
    call: null,
    generated_at: "2026-06-20T09:03:00Z",
    hash_algorithm: "sha256",
    evidence_hash: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd",
    hash_payload_excludes: ["generated_at"],
  };

  const missingPack: RuntimePolicyEvidencePackResponse = {
    ...matchedPack,
    verification_status: "not_verified",
    outcome_reconciliation: [],
    evidence_hash: "def456def456def456def456def456def456def456def456def456def456def0",
  };

  const actionIntent: ActionIntentResponse = {
    action_id: "act_1",
    project_id: "proj_1",
    contract_version: "v1",
    action_type: "refund",
    operation_kind: "business_mutation",
    environment: "test",
    status: "approval_pending",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "idem_act_1",
    intent_digest: "intent_digest_1",
    canonical_intent: {
      principal: { id: "Refund agent" },
      purpose: { summary: "Refund payment rf_100" },
      resource: { id: "rf_100" },
    },
    created_at: "2026-06-20T09:00:00Z",
    decided_at: null,
    authorized_at: null,
    runtime_policy_decision_id: "decision_1",
    deadline: "2099-06-20T09:15:00Z",
    status_url: "/v1/action-intents/act_1",
  };

  return {
    actionIntent,
    decision,
    matchedPack,
    missingPack,
  };
});

const hookState = vi.hoisted(() => ({
  evidenceMode: "matched" as "matched" | "missing",
  evidenceDecisionId: null as string | null,
  decisions: null as RuntimePolicyDecisionResponse[] | null,
  intents: null as ActionIntentResponse[] | null,
  actionIntentOptions: null as Record<string, unknown> | null,
  approvalsOptions: null as Record<string, unknown> | null,
  approvalsStatus: null as string | null,
  approvalsRefetch: vi.fn(),
  projectRole: "admin",
  approve: vi.fn(),
  reject: vi.fn(),
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

vi.mock("@/lib/store", () => ({
  useDashboardStore: (selector: (state: { dateRange: { from: Date; to: Date }; selectedProject: string }) => unknown) =>
    selector({
      dateRange: {
        from: new Date("2026-06-19T00:00:00Z"),
        to: new Date("2026-06-21T00:00:00Z"),
      },
      selectedProject: "proj_1",
    }),
}));

vi.mock("@/lib/hooks", () => ({
  useMyProjects: () => ({
    data: [{ project_id: "proj_1", role: hookState.projectRole }],
  }),
  useRuntimePolicyApprovals: (status: string, options?: Record<string, unknown>) => {
    hookState.approvalsStatus = status;
    hookState.approvalsOptions = options ?? null;
    return {
      data: {
        items: hookState.decisions ?? [fixtures.decision],
        total_in_page: hookState.decisions?.length ?? 1,
      },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: hookState.approvalsRefetch,
    };
  },
  useActionIntents: (_query: unknown, options?: Record<string, unknown>) => {
    hookState.actionIntentOptions = options ?? null;
    return {
      data: {
        items: hookState.intents ?? [fixtures.actionIntent],
        total_in_page: hookState.intents?.length ?? 1,
        limit: 100,
        offset: 0,
      },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    };
  },
  useRuntimePolicyEvidencePack: (decisionId: string | null) => {
    hookState.evidenceDecisionId = decisionId;
    return {
      data: decisionId ? (hookState.evidenceMode === "matched" ? fixtures.matchedPack : fixtures.missingPack) : undefined,
      isLoading: false,
      isError: false,
      error: null,
    };
  },
  useApproveRuntimePolicyDecision: () => ({
    isPending: false,
    mutateAsync: hookState.approve,
  }),
  useRejectRuntimePolicyDecision: () => ({
    isPending: false,
    mutateAsync: hookState.reject,
  }),
}));

describe("RuntimeApprovalsPage evidence pack", () => {
  beforeEach(() => {
    hookState.evidenceMode = "matched";
    hookState.evidenceDecisionId = null;
    hookState.decisions = null;
    hookState.intents = null;
    hookState.actionIntentOptions = null;
    hookState.approvalsOptions = null;
    hookState.approvalsStatus = null;
    hookState.projectRole = "admin";
    hookState.approvalsRefetch.mockClear();
    hookState.approve.mockClear();
    hookState.reject.mockClear();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:evidence-pack"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("renders the cockpit queue, selected inspector, and loaded outcome proof", () => {
    render(<RuntimeApprovalsPage />);

    expect(screen.getByRole("heading", { name: "Approval control" })).toBeInTheDocument();
    expect(hookState.approvalsStatus).toBe("all");
    expect(hookState.approvalsOptions?.refetchInterval).toBe(15_000);
    expect(hookState.actionIntentOptions?.refetchInterval).toBe(15_000);
    const metrics = screen.getByRole("region", { name: "Approval control filters" });
    expect(within(metrics).getByRole("button", { name: "Pending" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(metrics).getByRole("button", { name: "Approved" })).toBeInTheDocument();
    expect(within(metrics).getByRole("button", { name: "Stopped" })).toBeInTheDocument();
    expect(within(metrics).getByRole("button", { name: "All decisions" })).toBeInTheDocument();
    expect(within(metrics).queryByText("Expiring soon")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Approval queue" })).toBeInTheDocument();
    const selected = screen.getByRole("region", { name: "Selected action control" });
    expect(screen.getByText("P0")).toBeInTheDocument();
    expect(screen.getByText(/money-touching hold/)).toBeInTheDocument();
    expect(screen.getAllByText("Action intent").length).toBeGreaterThan(0);
    expect(within(selected).getByText("Held by runtime policy")).toBeInTheDocument();
    expect(within(selected).getByText("Refund amount above runtime mandate")).toBeInTheDocument();
    expect(within(selected).getByText("Approval will release")).toBeInTheDocument();
    expect(within(selected).getByText(/Business mutation: Refund payment rf_100/)).toBeInTheDocument();
    expect(within(selected).getByText("0/1 approvals recorded")).toBeInTheDocument();
    expect(within(selected).getByText("No approval recorded yet. The action remains held at the runtime gate.")).toBeInTheDocument();
    expect(within(selected).getByText("Any project admin can decide")).toBeInTheDocument();
    expect(within(selected).getByRole("link", { name: "Slack escalation" }).getAttribute("href")).toBe("/integrations/slack");
    expect(within(selected).getByRole("navigation", { name: "Proof chain" })).toBeInTheDocument();
    expect(within(selected).getByRole("tab", { name: "Decision" }).getAttribute("aria-selected")).toBe("true");
    expect(within(selected).getByText("Decision mechanism")).toBeInTheDocument();
    expect(within(selected).queryByText("act_1")).not.toBeInTheDocument();
    fireEvent.click(within(selected).getByRole("tab", { name: "Developer" }));
    expect(within(selected).getByText("act_1")).toBeInTheDocument();
    expect(within(selected).getByText("intent_digest_1")).toBeInTheDocument();
    fireEvent.click(within(selected).getByRole("tab", { name: "Evidence" }));
    expect(within(selected).getByRole("link", { name: "Open full evidence" }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
    const evidence = screen.getByRole("region", { name: "Runtime policy Evidence Pack" });
    expect(within(evidence).getByText(fixtures.matchedPack.evidence_hash)).toBeInTheDocument();
    expect(within(evidence).getByText("ledger:rf_100")).toBeInTheDocument();
    expect(hookState.evidenceDecisionId).toBe("decision_1");
  });

  it("shows a scoped empty state when no approval decisions exist", () => {
    hookState.decisions = [];
    hookState.intents = [];

    render(<RuntimeApprovalsPage />);

    expect(screen.getByRole("heading", { name: "Approval control" })).toBeInTheDocument();
    expect(screen.getByText("No approval decisions in this window")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Runtime safety hold" })).not.toBeInTheDocument();
  });

  it("opens a blocked-only approval set on the visible blocked queue", async () => {
    hookState.decisions = [
      {
        ...fixtures.decision,
        status: "blocked",
        decision: "block",
        resolved_at: "2026-06-20T09:01:00Z",
        resolved_by: "runtime-policy",
        resolution_reason: "unsafe action blocked",
      },
    ];

    render(<RuntimeApprovalsPage />);

    expect(await screen.findByRole("heading", { name: "Approval control" })).toBeInTheDocument();
    expect(screen.getByText("1 blocked, rejected, or expired decision remains preserved with audit evidence.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stopped" }).className).toContain("is-active");
    const queue = screen.getByRole("region", { name: "Decision history" });
    expect(within(queue).getByText("1 decision shown")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected action control" })).toBeInTheDocument();
    expect(screen.getByText("Held by runtime policy")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Approval decision control" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Execution: Prevented" })).toBeInTheDocument();
    expect(screen.queryByText("Approver chain")).not.toBeInTheDocument();
    expect(screen.queryByText("No decisions in this view")).not.toBeInTheDocument();
  });

  it("frames approved decisions as completed releases rather than stopped or expired actions", async () => {
    hookState.decisions = [
      {
        ...fixtures.decision,
        status: "approved",
        decision: "allow",
        approval_count: 1,
        required_approval_count: 1,
        approver_subjects: ["google:114252601469329571267"],
        expires_at: "2026-06-20T09:15:00Z",
        resolved_at: "2026-06-20T09:05:00Z",
        resolved_by: "google:114252601469329571267",
        resolution_reason: "Evidence matches request",
      },
    ];
    render(<RuntimeApprovalsPage />);
    expect((await screen.findByRole("button", { name: "Approved" })).className).toContain("is-active");
    expect(screen.getByText("Decision reason")).toBeInTheDocument();
    expect(screen.getByText("Approved by reviewer")).toBeInTheDocument();
    expect(screen.queryByText("Approval completed")).not.toBeInTheDocument();
    expect(screen.getByText("Approved, waiting for a runner")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check runner" }).getAttribute("href")).toBe("/agents");
    expect(screen.getByText("Google account ...571267")).toBeInTheDocument();
    expect(screen.queryByText("Why policy stopped it")).not.toBeInTheDocument();
    expect(screen.queryByText("Expired")).not.toBeInTheDocument();
  });

  it("keeps the inspector empty when the selected filter has no rows", async () => {
    hookState.decisions = [
      {
        ...fixtures.decision,
        status: "blocked",
        decision: "block",
        resolved_at: "2026-06-20T09:01:00Z",
        resolved_by: "runtime-policy",
        resolution_reason: "unsafe action blocked",
      },
    ];

    render(<RuntimeApprovalsPage />);

    expect((await screen.findByRole("button", { name: "Stopped" })).className).toContain("is-active");
    fireEvent.click(screen.getByRole("button", { name: "Pending" }));

    expect(await screen.findByText("No pending approvals")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Select an action" })).toBeInTheDocument();
    expect(screen.queryByText("Blocked by policy")).not.toBeInTheDocument();
  });

  it("requires an audit reason before approving or rejecting a held action", async () => {
    render(<RuntimeApprovalsPage />);

    const approve = screen.getByRole("button", { name: "Approve action" });
    const reject = screen.getByRole("button", { name: "Reject action" });
    expect(approve).toHaveProperty("disabled", true);
    expect(reject).toHaveProperty("disabled", true);

    fireEvent.change(screen.getByLabelText("Decision reason"), {
      target: { value: "support ticket verified" },
    });

    expect(approve).toHaveProperty("disabled", false);
    expect(reject).toHaveProperty("disabled", false);
    fireEvent.click(approve);

    await waitFor(() =>
      expect(hookState.approve).toHaveBeenCalledWith({
        decisionId: "decision_1",
        reason: "support ticket verified",
      }),
    );
  });

  it("lets approvers fill a consistent reason with quick chips", () => {
    render(<RuntimeApprovalsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Suspicious sequence" }));

    expect(screen.getByLabelText("Decision reason")).toHaveProperty("value", "Suspicious sequence");
  });

  it("keeps approval evidence readable without exposing decision controls to viewers", () => {
    hookState.projectRole = "viewer";
    render(<RuntimeApprovalsPage />);
    expect(screen.getByRole("note").textContent).toContain("Admin access is required");
    expect(screen.queryByRole("button", { name: "Approve action" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject action" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Evidence" })).toBeInTheDocument();
  });

  it("renders compact evidence inline and links to the full evidence page", () => {
    render(<RuntimeApprovalsPage />);

    expect(hookState.evidenceDecisionId).toBe("decision_1");
    fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    const evidence = screen.getByRole("region", { name: "Runtime policy Evidence Pack" });
    expect(within(evidence).getByText(fixtures.matchedPack.evidence_hash)).toBeInTheDocument();
    expect(within(evidence).getByText("ledger:rf_100")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open full evidence" }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
    expect(screen.queryByRole("dialog", { name: "Evidence Pack" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export Evidence JSON" })).not.toBeInTheDocument();
  });

  it("shows a not verified state when outcome evidence is missing", () => {
    hookState.evidenceMode = "missing";

    render(<RuntimeApprovalsPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    const evidence = screen.getByRole("region", { name: "Runtime policy Evidence Pack" });
    expect(within(evidence).getByText("Not verified")).toBeInTheDocument();
    expect(within(evidence).getByText(fixtures.missingPack.evidence_hash)).toBeInTheDocument();
    expect(within(evidence).getByText("No system-of-record outcome proof is linked.")).toBeInTheDocument();
  });
});
