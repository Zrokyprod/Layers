import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { actionLifecycleCounts, buildActionLifecycle } from "@/lib/action-lifecycle";
import ActionsPage from "./page";

const api = vi.hoisted(() => ({
  getActionsLifecycleSummary: vi.fn(),
  getActionIntentTimeline: vi.fn(),
  listActionExecutionAttempts: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  attempts: [] as Record<string, unknown>[],
  lifecycleAttempts: [] as Record<string, unknown>[],
  billingUsage: null as Record<string, unknown> | null,
  decisions: [] as Record<string, unknown>[],
  intents: [] as Record<string, unknown>[],
  outcomeSummary: null as Record<string, unknown> | null,
  outcomes: [] as Record<string, unknown>[],
  sourceMutationSummary: null as Record<string, unknown> | null,
  staleAttempts: [] as Record<string, unknown>[],
  timeline: [] as Record<string, unknown>[],
  unreceiptedMutations: [] as Record<string, unknown>[],
  dataUpdatedAt: 0,
  isLoading: false,
  isError: false,
  errorKeys: new Set<string>(),
  refetch: vi.fn(),
  queryKeys: [] as string[],
  makeFeed: null as null | (() => Record<string, unknown>),
  sources: {
    lifecycle_summary: true,
    intents: true,
    approvals: true,
    outcomes: true,
    outcome_summary: true,
    source_summary: true,
    mutations: true,
    attempts: true,
    stale_attempts: true,
    billing_usage: true,
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: unknown[] }) => {
    const key = queryKey.join(":");
    queryState.queryKeys.push(key);
    const isError = queryState.isError || queryState.errorKeys.has(key);
    if (key === "actions:lifecycle-summary:7:200") {
      return {
        data: queryState.makeFeed ? queryState.makeFeed() : {
          project_id: "proj_1",
          window_days: 7,
          window_start: "2026-06-13T00:00:00Z",
          generated_at: "2026-06-20T09:15:00Z",
          row_limit: 200,
          source_totals: {
            intents: queryState.intents.length,
            approvals: queryState.decisions.length,
            outcomes: Number(queryState.outcomeSummary?.total ?? queryState.outcomes.length),
            mutations: Number(queryState.sourceMutationSummary?.unreceipted ?? queryState.unreceiptedMutations.length),
            attempts: queryState.lifecycleAttempts.length,
            stale_attempts: queryState.staleAttempts.length,
          },
          truncated: false,
          truncated_sources: [],
          metrics: {
            controlled_actions: queryState.intents.length,
            held_actions: queryState.decisions.filter((item) => item.status === "pending_approval").length,
            matched_outcomes: Number(queryState.outcomeSummary?.matched ?? 0),
            mismatched_outcomes: Number(queryState.outcomeSummary?.mismatched ?? 0),
            not_verified_outcomes: Number(queryState.outcomeSummary?.not_verified ?? 0),
            bypass_risk: Number(queryState.sourceMutationSummary?.unreceipted ?? 0),
          },
          sources: queryState.sources,
          data: {
            intents: queryState.intents,
            approvals: queryState.decisions,
            outcomes: queryState.outcomes,
            outcome_summary: queryState.outcomeSummary,
            source_summary: queryState.sourceMutationSummary,
            mutations: queryState.unreceiptedMutations,
            attempts: queryState.lifecycleAttempts,
            stale_attempts: queryState.staleAttempts,
            billing_usage: queryState.billingUsage,
          },
        },
        isLoading: queryState.isLoading,
        isError,
        dataUpdatedAt: queryState.dataUpdatedAt,
        refetch: queryState.refetch,
      };
    }
    if (key === "action-intent:act_1:timeline:actions-page") {
      return {
        data: { items: queryState.timeline },
        isLoading: queryState.isLoading,
        isError,
        refetch: queryState.refetch,
      };
    }
    if (key === "action-intent:act_1:execution-attempts:actions-page") {
      return {
        data: { items: queryState.attempts },
        isLoading: queryState.isLoading,
        isError,
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

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: { dateRange: { from: Date; to: Date } }) => T) => selector({
    dateRange: {
      from: new Date("2026-06-13T00:00:00Z"),
      to: new Date("2026-06-20T00:00:00Z"),
    },
  }),
}));

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

function actionIntent(overrides: Record<string, unknown> = {}) {
  return {
    action_id: "act_1",
    project_id: "proj_1",
    contract_version: "v1",
    action_type: "ticket_close",
    operation_kind: "business_mutation",
    environment: "test",
    status: "authorized",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "idem_act_1",
    intent_digest: "intent_digest_1",
    canonical_intent: {
      principal: { id: "Support agent" },
      purpose: { summary: "Close ticket T-1001" },
      resource: { id: "T-1001" },
    },
    created_at: "2026-06-20T09:10:00Z",
    decided_at: "2026-06-20T09:10:10Z",
    authorized_at: "2026-06-20T09:10:20Z",
    runtime_policy_decision_id: "decision_1",
    deadline: null,
    status_url: "/v1/action-intents/act_1",
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
  queryState.makeFeed = () => {
    const rows = buildActionLifecycle({
      intents: queryState.intents as never[],
      decisions: queryState.decisions as never[],
      outcomes: queryState.outcomes as never[],
      attempts: queryState.lifecycleAttempts as never[],
      staleAttemptIds: queryState.staleAttempts.map((attempt) => String(attempt.attempt_id)),
      mutations: queryState.unreceiptedMutations as never[],
    });
    return {
      summary: {
        project_id: "proj_1",
        window_days: 7,
        window_start: "2026-06-13T00:00:00Z",
        generated_at: "2026-06-20T09:15:00Z",
        row_limit: 200,
        source_totals: {
          intents: queryState.intents.length,
          approvals: queryState.decisions.length,
          outcomes: Number(queryState.outcomeSummary?.total ?? queryState.outcomes.length),
          mutations: Number(queryState.sourceMutationSummary?.unreceipted ?? queryState.unreceiptedMutations.length),
          attempts: queryState.lifecycleAttempts.length,
          stale_attempts: queryState.staleAttempts.length,
        },
        truncated: false,
        truncated_sources: [],
        metrics: {
          controlled_actions: queryState.intents.length,
          held_actions: queryState.decisions.filter((item) => item.status === "pending_approval").length,
          matched_outcomes: Number(queryState.outcomeSummary?.matched ?? 0),
          mismatched_outcomes: Number(queryState.outcomeSummary?.mismatched ?? 0),
          not_verified_outcomes: Number(queryState.outcomeSummary?.not_verified ?? 0),
          bypass_risk: Number(queryState.sourceMutationSummary?.unreceipted ?? 0),
        },
        sources: queryState.sources,
        data: {
          intents: queryState.intents,
          approvals: queryState.decisions,
          outcomes: queryState.outcomes,
          outcome_summary: queryState.outcomeSummary,
          source_summary: queryState.sourceMutationSummary,
          mutations: queryState.unreceiptedMutations,
          attempts: queryState.lifecycleAttempts,
          stale_attempts: queryState.staleAttempts,
          billing_usage: queryState.billingUsage,
        },
      },
      rows,
      counts: actionLifecycleCounts(rows),
    };
  };
  return render(<ActionsPage />);
}

describe("ActionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryState.isLoading = false;
    queryState.isError = false;
    queryState.errorKeys.clear();
    queryState.refetch.mockClear();
    queryState.queryKeys = [];
    queryState.makeFeed = null;
    queryState.sources = {
      lifecycle_summary: true,
      intents: true,
      approvals: true,
      outcomes: true,
      outcome_summary: true,
      source_summary: true,
      mutations: true,
      attempts: true,
      stale_attempts: true,
      billing_usage: true,
    };
    queryState.dataUpdatedAt = Date.now();
    queryState.attempts = [];
    queryState.lifecycleAttempts = [];
    queryState.billingUsage = billingUsage();
    queryState.intents = [];
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
    queryState.staleAttempts = [];
    queryState.timeline = [];
    queryState.unreceiptedMutations = [sourceMutation()];
    api.getActionIntentTimeline.mockResolvedValue({ items: [] });
    api.listActionExecutionAttempts.mockResolvedValue({ items: [] });
  });

  it("shows lifecycle metrics, quota, intent rows, and bypass as a first-class queue filter", async () => {
    renderActionsPage();

    expect(
      await screen.findByRole("heading", { name: "Bypass risk" }),
    ).toBeInTheDocument();
    expect(queryState.queryKeys).toContain("actions:lifecycle-summary:7:200");
    expect(queryState.queryKeys).not.toContain("action-intents:actions:all");
    expect(queryState.queryKeys).not.toContain("runtime-policy:actions:all");
    expect(queryState.queryKeys).not.toContain("outcomes:actions:reconciliation");
    expect(queryState.queryKeys).not.toContain("action-execution-attempts:actions:stale");
    expect(queryState.queryKeys).not.toContain("outcomes:actions:summary:30");
    expect(queryState.queryKeys).not.toContain("outcomes:actions:source-mutations:summary");
    expect(queryState.queryKeys).not.toContain("outcomes:actions:source-mutations:unreceipted");
    expect(screen.getByText(/Updated just now/i)).toBeInTheDocument();
    expect(screen.queryByText("Updated live")).not.toBeInTheDocument();

    const metrics = screen.getByRole("region", { name: "Action lifecycle metrics" });
    expect(within(metrics).getByText("Protected actions")).toBeInTheDocument();
    expect(within(metrics).getAllByText("0").length).toBeGreaterThan(0);
    expect(within(metrics).getByText("Waiting approval")).toBeInTheDocument();
    expect(within(metrics).getByText("Awaiting runner")).toBeInTheDocument();
    expect(within(metrics).getByText("Verified outcomes")).toBeInTheDocument();
    expect(within(metrics).getByText("Bypass risk")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Protected action quota" })).not.toBeInTheDocument();

    const queue = screen.getByRole("region", { name: "Action lifecycle queue" });
    expect(within(queue).getByText("Refund RF-1001")).toBeInTheDocument();
    expect(within(queue).getByText("Deploy production release")).toBeInTheDocument();
    expect(within(queue).getByText("Bypass: stripe:rf_bypass")).toBeInTheDocument();

    fireEvent.click(within(queue).getByRole("button", { name: "Bypassed" }));
    expect(within(queue).getByText("Bypass: stripe:rf_bypass")).toBeInTheDocument();
    expect(within(queue).queryByText("Deploy production release")).not.toBeInTheDocument();

    fireEvent.click(within(queue).getByRole("button", { name: "All" }));
    fireEvent.click(within(queue).getByRole("button", { name: /Refund RF-1001/ }));

    const selected = screen.getByRole("region", { name: "Selected action lifecycle" });
    expect(within(selected).getByRole("heading", { name: "Refund RF-1001" })).toBeInTheDocument();
    expect(within(selected).getByText((content) => content.includes("ledger:RF-1001"))).toBeInTheDocument();
    expect(within(selected).getByRole("navigation", { name: "Proof chain" })).toBeInTheDocument();
    expect(within(selected).getByRole("link", { name: "Open Evidence Pack" }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );

    fireEvent.click(within(queue).getByRole("button", { name: /Bypass: stripe:rf_bypass/ }));
    const bypass = screen.getByRole("region", { name: "Bypass risk detail" });
    expect(within(bypass).getByText("Control bypass detected")).toBeInTheDocument();
    expect(within(bypass).getByText("ai_agent:refund-agent")).toBeInTheDocument();
  });

  it("keeps billing failures out of the operational Actions module", async () => {
    queryState.billingUsage = null;
    queryState.sources = { ...queryState.sources, billing_usage: false };

    renderActionsPage();

    expect(await screen.findByRole("heading", { name: "Bypass risk" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Action visibility unavailable" })).not.toBeInTheDocument();
    expect(screen.queryByText("Quota usage unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("One or more lifecycle feeds failed")).not.toBeInTheDocument();
  });

  it("does not replace canonical zero outcome counts with lifecycle fallback counts", async () => {
    queryState.outcomeSummary = {
      window_days: 30,
      total: 1,
      matched: 1,
      mismatched: 0,
      not_verified: 0,
      verified: 1,
      pending: 0,
      unverifiable: 0,
      cancelled: 0,
    };
    queryState.outcomes = [
      outcome({
        verdict: "mismatched",
        verification_status: "failed",
        reason: "ledger amount drifted",
      }),
    ];

    renderActionsPage();

    expect(await screen.findByRole("heading", { name: "Bypass risk" })).toBeInTheDocument();
    const metrics = screen.getByRole("region", { name: "Action lifecycle metrics" });
    expect(within(metrics).getByText("0 mismatched / 0 need verification.")).toBeInTheDocument();
  });

  it("shows action-intent lifecycle details with receipt, timeline, and execution attempts", async () => {
    queryState.intents = [actionIntent()];
    queryState.decisions = [];
    queryState.outcomes = [];
    queryState.unreceiptedMutations = [];
    queryState.timeline = [
      {
        event_id: "evt_1",
        action_id: "act_1",
        project_id: "proj_1",
        event_type: "authorized",
        event_digest: "evt_digest_1",
        actor: "system",
        payload: {},
        created_at: "2026-06-20T09:10:20Z",
      },
    ];
    queryState.attempts = [
      {
        attempt_id: "attempt_1",
        project_id: "proj_1",
        action_id: "act_1",
        runner_id: "runner_1",
        attempt_number: 1,
        status: "succeeded",
        idempotency_key: "idem_attempt_1",
        credential_ref: "cred:scoped",
        plan_digest: "plan_digest_1",
        execution_plan: {},
        result_summary: {},
        error_message: null,
        protected_credential_returned: false,
        requested_by_subject: "agent",
        started_at: "2026-06-20T09:10:30Z",
        finished_at: "2026-06-20T09:10:40Z",
        created_at: "2026-06-20T09:10:30Z",
        updated_at: "2026-06-20T09:10:40Z",
      },
    ];

    renderActionsPage();

    const queue = await screen.findByRole("region", { name: "Action lifecycle queue" });
    fireEvent.click(within(queue).getByRole("button", { name: /Close ticket T-1001/ }));

    const selected = screen.getByRole("region", { name: "Selected action lifecycle" });
    expect(within(selected).getByRole("button", { name: /Action: Authorized/i })).toBeInTheDocument();
    expect(within(selected).getByRole("button", { name: /Verification: Matched/i })).toBeInTheDocument();
    expect(within(selected).getByRole("button", { name: /Receipt: Generated/i })).toBeInTheDocument();
    expect(within(selected).getByText("Action timeline")).toBeInTheDocument();
    expect(within(selected).getByText("Intent")).toBeInTheDocument();
    expect(document.querySelectorAll(".al-json-section[open]")).toHaveLength(0);
    expect(within(selected).getAllByText("Authorized").length).toBeGreaterThan(0);
    expect(within(selected).getByText("Execution attempts")).toBeInTheDocument();
    expect(within(selected).getByText("runner_1")).toBeInTheDocument();
    expect(within(selected).getByRole("link", { name: "Open Action Receipt" }).getAttribute("href")).toBe(
      "/evidence?action_id=act_1",
    );
  });

  it("does not call an authorized action controlled while it is awaiting a runner", async () => {
    queryState.intents = [actionIntent({ proof_status: "not_started", receipt_status: "missing" })];
    queryState.decisions = [];
    queryState.outcomes = [];
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

    renderActionsPage();

    expect(await screen.findByRole("heading", { name: "Actions awaiting runner" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Actions controlled" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Restore runner" }).getAttribute("href")).toBe("/agents");
  });

  it("surfaces verification mismatches without opening raw JSON", async () => {
    queryState.intents = [
      actionIntent({
        proof_status: "mismatched",
        receipt_status: "generated",
      }),
    ];
    queryState.decisions = [decision()];
    queryState.outcomes = [
      outcome({
        verdict: "mismatched",
        reason: "amount did not match ledger",
        claimed: { refund_id: "RF-1001", amount_usd: 42.5 },
        actual: { refund_id: "RF-1001", amount_usd: 0 },
        comparison: {
          compared_fields: ["refund_id", "amount_usd"],
          mismatches: [{ field: "amount_usd" }],
        },
      }),
    ];
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

    renderActionsPage();

    const selected = await screen.findByRole("region", { name: "Selected action lifecycle" });
    const mismatch = within(selected).getByRole("region", { name: "Verification mismatch" });
    expect(within(mismatch).getByText("Verification failed")).toBeInTheDocument();
    expect(within(mismatch).getByText("amount did not match ledger")).toBeInTheDocument();
    const diff = within(mismatch).getByRole("table", { name: "Claimed versus actual mismatch" });
    expect(within(diff).getByText("amount_usd")).toBeInTheDocument();
    expect(within(diff).getByText("42.5")).toBeInTheDocument();
    expect(within(diff).getByText("0")).toBeInTheDocument();
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

    renderActionsPage();

    expect(await screen.findByRole("heading", { name: "Setup required" })).toBeInTheDocument();
    expect(screen.getByText("No actions match this filter")).toBeInTheDocument();
  });
});
