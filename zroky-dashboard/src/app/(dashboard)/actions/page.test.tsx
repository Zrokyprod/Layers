import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActionsPage from "./page";

const api = vi.hoisted(() => ({
  getBillingUsage: vi.fn(),
  getOutcomeReconciliationSummary: vi.fn(),
  getSourceMutationSummary: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
  listUnreceiptedSourceMutations: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  billingUsage: null as Record<string, unknown> | null,
  decisions: [] as Record<string, unknown>[],
  outcomeSummary: null as Record<string, unknown> | null,
  outcomes: [] as Record<string, unknown>[],
  sourceMutationSummary: null as Record<string, unknown> | null,
  unreceiptedMutations: [] as Record<string, unknown>[],
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: unknown[] }) => {
    const key = queryKey.join(":");
    if (key === "billing:usage:protected-action-dashboard") {
      return {
        data: queryState.billingUsage,
        isLoading: queryState.isLoading,
        isError: queryState.isError,
        refetch: queryState.refetch,
      };
    }
    if (key === "runtime-policy:actions:all") {
      return {
        data: { total_in_page: queryState.decisions.length, items: queryState.decisions },
        isLoading: queryState.isLoading,
        isError: queryState.isError,
        refetch: queryState.refetch,
      };
    }
    if (key === "outcomes:actions:summary:30") {
      return {
        data: queryState.outcomeSummary,
        isLoading: queryState.isLoading,
        isError: queryState.isError,
        refetch: queryState.refetch,
      };
    }
    if (key === "outcomes:actions:reconciliation") {
      return {
        data: { total_in_page: queryState.outcomes.length, items: queryState.outcomes },
        isLoading: queryState.isLoading,
        isError: queryState.isError,
        refetch: queryState.refetch,
      };
    }
    if (key === "outcomes:actions:source-mutations:summary") {
      return {
        data: queryState.sourceMutationSummary,
        isLoading: queryState.isLoading,
        isError: queryState.isError,
        refetch: queryState.refetch,
      };
    }
    if (key === "outcomes:actions:source-mutations:unreceipted") {
      return {
        data: { total_in_page: queryState.unreceiptedMutations.length, items: queryState.unreceiptedMutations },
        isLoading: queryState.isLoading,
        isError: queryState.isError,
        refetch: queryState.refetch,
      };
    }
    return {
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: queryState.refetch,
    };
  }),
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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

function usageMeter(used: number, limit: number | null, state = "ok") {
  return {
    used,
    limit,
    unlimited: limit == null,
    overage: null,
    state,
    resets_at: "2026-07-01",
  };
}

function billingUsage(overrides: Record<string, unknown> = {}) {
  return {
    tenant_id: "org_1",
    org_id: "org_1",
    period_month: "2026-06",
    period_start: "2026-06-01T00:00:00Z",
    period_end: "2026-07-01T00:00:00Z",
    plan_code: "pro",
    plan_name: "Pro",
    subscription_status: "active",
    calls: usageMeter(1000, 250000),
    replay: usageMeter(0, 500),
    goldens: usageMeter(0, 2500),
    golden_sets: usageMeter(0, 25),
    protected_actions: usageMeter(12, 25000),
    policy_checks: usageMeter(30, 100000),
    runner_executions: usageMeter(10, 25000),
    action_receipts: usageMeter(8, 25000),
    verification_checks: usageMeter(14, 50000),
    source_mutations: usageMeter(3, 100000),
    active_connectors: usageMeter(2, 10),
    metering_health: {
      state: "ok",
      failure_count: 0,
      last_failure_at: null,
      last_failure_type: null,
      failure_policy: "strict",
      detail: "Metering healthy.",
    },
    ...overrides,
  };
}

function decision(overrides: Record<string, unknown> = {}) {
  return {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "Refund agent",
    role: "refund_ops",
    action_type: "refund",
    tool_name: "ledger.refund",
    decision: "requires_approval",
    status: "approved",
    allowed: false,
    requires_approval: true,
    reasons: ["amount_requires_approval"],
    request: { amount_usd: 42.5 },
    policy_snapshot: {},
    intended_action: { summary: "Refund RF-1001", refund_id: "RF-1001", amount_usd: 42.5 },
    trace_context: {},
    policy_hit: { policy: "refund_mandate" },
    business_impact: { amount_usd: 42.5 },
    audit_log: [],
    created_at: "2026-06-20T09:00:00Z",
    expires_at: null,
    resolved_at: "2026-06-20T09:05:00Z",
    resolved_by: "ops@example.com",
    resolution_reason: "approved for pilot",
    consumed_at: null,
    consumed_by_decision_id: null,
    ...overrides,
  };
}

function outcome(overrides: Record<string, unknown> = {}) {
  return {
    id: "check_1",
    project_id: "proj_1",
    call_id: "call_1",
    trace_id: "trace_1",
    runtime_policy_decision_id: "decision_1",
    action_type: "refund",
    connector_type: "ledger_refund_api",
    system_ref: "ledger:RF-1001",
    verdict: "matched",
    verification_status: "verified",
    reason: "all_compared_fields_matched",
    amount_usd: 42.5,
    currency: "USD",
    claimed: { refund_id: "RF-1001", amount_usd: 42.5 },
    actual: { refund_id: "RF-1001", amount_usd: 42.5 },
    comparison: { compared_fields: ["refund_id", "amount_usd"], mismatches: [] },
    idempotency_key: "refund:RF-1001",
    metadata: {},
    checked_at: "2026-06-20T09:06:00Z",
    created_at: "2026-06-20T09:06:00Z",
    ...overrides,
  };
}

function sourceMutation(overrides: Record<string, unknown> = {}) {
  return {
    id: "mutation_bypass_1",
    project_id: "proj_1",
    source_system: "stripe",
    mutation_id: "evt_refund_outside_zroky",
    action_type: "refund",
    resource_type: "refund",
    resource_id: "rf_bypass",
    system_ref: "stripe:rf_bypass",
    actor_type: "ai_agent",
    actor_id: "refund-agent",
    zroky_action_id: null,
    action_receipt_id: null,
    idempotency_key: null,
    classification: "policy_bypass",
    metadata: { protected_action: true },
    occurred_at: "2026-06-20T09:08:00Z",
    created_at: "2026-06-20T09:08:00Z",
    ...overrides,
  };
}

function renderActionsPage() {
  return render(<ActionsPage />);
}

describe("ActionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryState.isLoading = false;
    queryState.isError = false;
    queryState.refetch.mockClear();
    queryState.billingUsage = billingUsage();
    queryState.decisions = [
      decision(),
      decision({
        id: "decision_2",
        agent_name: "Deploy agent",
        action_type: "deploy",
        tool_name: "ci.deploy",
        status: "pending_approval",
        intended_action: { summary: "Deploy production release" },
        created_at: "2026-06-20T09:07:00Z",
      }),
    ];
    queryState.outcomeSummary = {
      window_days: 30,
      total: 2,
      matched: 1,
      mismatched: 0,
      not_verified: 1,
      verified: 1,
      pending: 0,
      unverifiable: 1,
      cancelled: 0,
    };
    queryState.outcomes = [outcome()];
    queryState.sourceMutationSummary = {
      total: 3,
      matched_receipt: 1,
      authorized_external: 1,
      legacy_path: 0,
      unmanaged_agent_action: 0,
      policy_bypass: 1,
      unknown_actor: 0,
      unreceipted: 1,
    };
    queryState.unreceiptedMutations = [sourceMutation()];
    api.getBillingUsage.mockResolvedValue(billingUsage());
    api.listRuntimePolicyApprovals.mockResolvedValue({
      total_in_page: 2,
      items: [
        decision(),
        decision({
          id: "decision_2",
          agent_name: "Deploy agent",
          action_type: "deploy",
          tool_name: "ci.deploy",
          status: "pending_approval",
          intended_action: { summary: "Deploy production release" },
          created_at: "2026-06-20T09:07:00Z",
        }),
      ],
    });
    api.getOutcomeReconciliationSummary.mockResolvedValue({
      window_days: 30,
      total: 2,
      matched: 1,
      mismatched: 0,
      not_verified: 1,
      verified: 1,
      pending: 0,
      unverifiable: 1,
      cancelled: 0,
    });
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [outcome()],
    });
    api.getSourceMutationSummary.mockResolvedValue({
      total: 3,
      matched_receipt: 1,
      authorized_external: 1,
      legacy_path: 0,
      unmanaged_agent_action: 0,
      policy_bypass: 1,
      unknown_actor: 0,
      unreceipted: 1,
    });
    api.listUnreceiptedSourceMutations.mockResolvedValue({
      total_in_page: 1,
      items: [sourceMutation()],
    });
  });

  it("combines quota, action lifecycle, evidence, and bypass risk in one dashboard", async () => {
    renderActionsPage();

    expect(
      await screen.findByRole("heading", { name: "Bypass risk visible before customer handoff" }),
    ).toBeInTheDocument();

    const metrics = screen.getByRole("region", { name: "Protected action control metrics" });
    expect(within(metrics).getByText("Protected actions")).toBeInTheDocument();
    expect(within(metrics).getByText("12 / 25,000")).toBeInTheDocument();
    expect(within(metrics).getByText("Policy checks")).toBeInTheDocument();
    expect(within(metrics).getByText("30 / 100,000")).toBeInTheDocument();
    expect(within(metrics).getByText("Runner executions")).toBeInTheDocument();
    expect(within(metrics).getByText("Receipts")).toBeInTheDocument();
    expect(within(metrics).getByText("Bypass risk")).toBeInTheDocument();

    const queue = screen.getByRole("region", { name: "Action lifecycle queue" });
    expect(within(queue).getByText("Refund RF-1001")).toBeInTheDocument();
    expect(within(queue).getByText("Deploy production release")).toBeInTheDocument();
    expect(within(queue).getByText("Bypass: stripe:rf_bypass")).toBeInTheDocument();

    fireEvent.click(within(queue).getByRole("button", { name: /Refund RF-1001/ }));

    const selected = screen.getByRole("region", { name: "Selected action lifecycle" });
    expect(within(selected).getByRole("heading", { name: "Refund RF-1001" })).toBeInTheDocument();
    expect(within(selected).getByText((content) => content.includes("ledger:RF-1001"))).toBeInTheDocument();
    expect(within(selected).getByRole("link", { name: "Open Evidence Pack" }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );

    const bypassWatch = screen.getByRole("region", { name: "Bypass risk watch" });
    expect(within(bypassWatch).getByText("Source mutations must map back to a Zroky receipt or an approved exception.")).toBeInTheDocument();
    expect(within(bypassWatch).getByText("unreceipted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Billing" }).getAttribute("href")).toBe("/settings/billing");
  });

  it("renders a ready state when no protected action data exists yet", async () => {
    queryState.billingUsage =
      billingUsage({
        protected_actions: usageMeter(0, 25),
        policy_checks: usageMeter(0, 100),
        runner_executions: usageMeter(0, 25),
        action_receipts: usageMeter(0, 25),
        verification_checks: usageMeter(0, 50),
        source_mutations: usageMeter(0, 100),
      });
    queryState.decisions = [];
    queryState.outcomeSummary = {
      window_days: 30,
      total: 0,
      matched: 0,
      mismatched: 0,
      not_verified: 0,
      verified: 0,
      pending: 0,
      unverifiable: 0,
      cancelled: 0,
    };
    queryState.outcomes = [];
    queryState.sourceMutationSummary = {
      total: 0,
      matched_receipt: 0,
      authorized_external: 0,
      legacy_path: 0,
      unmanaged_agent_action: 0,
      policy_bypass: 0,
      unknown_actor: 0,
      unreceipted: 0,
    };
    queryState.unreceiptedMutations = [];
    api.getBillingUsage.mockResolvedValue(
      billingUsage({
        protected_actions: usageMeter(0, 25),
        policy_checks: usageMeter(0, 100),
        runner_executions: usageMeter(0, 25),
        action_receipts: usageMeter(0, 25),
        verification_checks: usageMeter(0, 50),
        source_mutations: usageMeter(0, 100),
      }),
    );
    api.listRuntimePolicyApprovals.mockResolvedValue({ total_in_page: 0, items: [] });
    api.getOutcomeReconciliationSummary.mockResolvedValue({
      window_days: 30,
      total: 0,
      matched: 0,
      mismatched: 0,
      not_verified: 0,
      verified: 0,
      pending: 0,
      unverifiable: 0,
      cancelled: 0,
    });
    api.listOutcomeReconciliations.mockResolvedValue({ total_in_page: 0, items: [] });
    api.getSourceMutationSummary.mockResolvedValue({
      total: 0,
      matched_receipt: 0,
      authorized_external: 0,
      legacy_path: 0,
      unmanaged_agent_action: 0,
      policy_bypass: 0,
      unknown_actor: 0,
      unreceipted: 0,
    });
    api.listUnreceiptedSourceMutations.mockResolvedValue({ total_in_page: 0, items: [] });

    renderActionsPage();

    expect(await screen.findByRole("heading", { name: "Action control plane ready" })).toBeInTheDocument();
    expect(screen.getByText("No protected action signals")).toBeInTheDocument();
  });
});
