import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
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

  return {
    decision,
    matchedPack,
    missingPack,
  };
});

const hookState = vi.hoisted(() => ({
  evidenceMode: "matched" as "matched" | "missing",
  evidenceDecisionId: null as string | null,
  approvalsRefetch: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
  killSwitch: vi.fn(),
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

vi.mock("@/lib/hooks", () => ({
  useRuntimePolicyApprovals: () => ({
    data: { items: [fixtures.decision], total_in_page: 1 },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: hookState.approvalsRefetch,
  }),
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
  useSetRuntimePolicyKillSwitch: () => ({
    isPending: false,
    mutateAsync: hookState.killSwitch,
  }),
}));

describe("RuntimeApprovalsPage evidence pack", () => {
  beforeEach(() => {
    hookState.evidenceMode = "matched";
    hookState.evidenceDecisionId = null;
    hookState.approvalsRefetch.mockClear();
    hookState.approve.mockClear();
    hookState.reject.mockClear();
    hookState.killSwitch.mockClear();
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

    expect(screen.getByRole("heading", { name: "Held actions before commit" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Approval priority queue" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected action control" })).toBeInTheDocument();
    expect(screen.getByText("P0")).toBeInTheDocument();
    expect(screen.getByText("money-action hold")).toBeInTheDocument();
    expect(screen.getByText("Outcome proof")).toBeInTheDocument();
    expect(screen.getByText("Outcome verified")).toBeInTheDocument();
    expect(screen.getByText("Matched system-of-record outcome is linked.")).toBeInTheDocument();
    expect(hookState.evidenceDecisionId).toBe("decision_1");
  });

  it("requires an audit reason before approving or rejecting a held action", async () => {
    render(<RuntimeApprovalsPage />);

    const approve = screen.getByRole("button", { name: "Approve" });
    const reject = screen.getByRole("button", { name: "Reject" });
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

  it("requires confirmation before enabling the runtime kill switch", async () => {
    render(<RuntimeApprovalsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Arm kill switch confirmation" }));
    expect(hookState.killSwitch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm kill switch" }));

    await waitFor(() => expect(hookState.killSwitch).toHaveBeenCalledWith(true));
  });

  it("opens the evidence pack, shows the hash, matched outcome, and exports JSON", () => {
    render(<RuntimeApprovalsPage />);

    expect(screen.getAllByText(/Financial action/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Evidence Pack" }));

    expect(hookState.evidenceDecisionId).toBe("decision_1");
    const dialog = screen.getByRole("dialog", { name: "Evidence Pack" });
    expect(within(dialog).getByText("Outcome verified against the system of record.")).toBeInTheDocument();
    expect(within(dialog).getByText(fixtures.matchedPack.evidence_hash)).toBeInTheDocument();
    expect(within(dialog).getByText("ledger:rf_100")).toBeInTheDocument();
    expect(within(dialog).getByText("matched")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Download JSON" }));

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:evidence-pack");
  });

  it("shows a not verified state when outcome evidence is missing", () => {
    hookState.evidenceMode = "missing";

    render(<RuntimeApprovalsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Evidence Pack" }));

    const dialog = screen.getByRole("dialog", { name: "Evidence Pack" });
    expect(within(dialog).getByText("Not verified")).toBeInTheDocument();
    expect(within(dialog).getByText(fixtures.missingPack.evidence_hash)).toBeInTheDocument();
    expect(within(dialog).getByText("Missing evidence")).toBeInTheDocument();
    expect(within(dialog).getByText("No matched system-of-record outcome is linked to this decision yet.")).toBeInTheDocument();
  });
});
