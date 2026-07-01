import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  OutcomeReconciliationSummaryResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationSummaryResponse,
  SourceMutationView,
} from "@/lib/api";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

const api = vi.hoisted(() => ({
  getBillingUsage: vi.fn(),
  getOutcomeReconciliationSummary: vi.fn(),
  getSourceMutationSummary: vi.fn(),
  listActionRunners: vi.fn(),
  listActionIntents: vi.fn(),
  listAgentProfiles: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  listProjectActionExecutionAttempts: vi.fn(),
  listProjectApiKeys: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
  listUnreceiptedSourceMutations: vi.fn(),
}));

const storeState = vi.hoisted(() => ({
  selectedProject: "proj_1",
  realTimeEnabled: false,
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
  useDashboardStore: <T,>(
    selector: (state: { selectedProject: string; realTimeEnabled: boolean }) => T,
  ) => selector(storeState),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function intent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_1",
    project_id: "proj_1",
    contract_version: "inventory.v1",
    action_type: "inventory.item.delete",
    operation_kind: "DELETE",
    environment: "production",
    status: "approval_pending",
    proof_status: "pending",
    receipt_status: "missing",
    idempotency_key: "idem_1",
    intent_digest: "sha256:digest",
    canonical_intent: {
      purpose: { summary: "Delete inventory item" },
      principal: { id: "inventory-agent" },
      resource: { id: "sku_123" },
      trace_context: { agent_name: "inventory-agent" },
    },
    created_at: now,
    decided_at: null,
    authorized_at: null,
    runtime_policy_decision_id: "decision_1",
    deadline: null,
    status_url: "/v1/action-intents/act_1",
    ...overrides,
  };
}

function approval(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "inventory-agent",
    role: "agent",
    action_type: "inventory.item.delete",
    tool_name: "inventory.delete",
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["Deletes require approval"],
    request: {},
    policy_snapshot: {},
    intended_action: { summary: "Delete inventory item" },
    trace_context: {},
    policy_hit: {},
    business_impact: { risk: "high" },
    audit_log: [],
    created_at: now,
    expires_at: null,
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    consumed_at: null,
    consumed_by_decision_id: null,
    required_approval_count: 1,
    approval_count: 0,
    approver_subjects: [],
    ...overrides,
  };
}

function outcome(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "outcome_1",
    project_id: "proj_1",
    call_id: null,
    trace_id: null,
    runtime_policy_decision_id: "decision_mismatch",
    action_type: "inventory.item.delete",
    connector_type: "generic_rest",
    system_ref: "sku_123",
    verdict: "mismatched",
    verification_status: "mismatched",
    reason: "deleted flag was still false",
    amount_usd: null,
    currency: null,
    claimed: { deleted: true },
    actual: { deleted: false },
    comparison: {},
    idempotency_key: "idem_mismatch",
    metadata: {},
    checked_at: now,
    created_at: now,
    ...overrides,
  };
}

function mutation(overrides: Partial<SourceMutationView> = {}): SourceMutationView {
  return {
    id: "mutation_1",
    project_id: "proj_1",
    source_system: "inventory",
    mutation_id: "mut_1",
    action_type: "inventory.item.update",
    resource_type: "item",
    resource_id: "sku_999",
    system_ref: "sku_999",
    actor_type: "agent",
    actor_id: "legacy-agent",
    zroky_action_id: null,
    action_receipt_id: null,
    idempotency_key: null,
    classification: "policy_bypass",
    metadata: {},
    occurred_at: now,
    created_at: now,
    ...overrides,
  };
}

function attempt(overrides: Partial<ActionExecutionAttemptResponse> = {}): ActionExecutionAttemptResponse {
  return {
    attempt_id: "attempt_1",
    project_id: "proj_1",
    action_id: "act_stale",
    runner_id: "runner_1",
    attempt_number: 1,
    status: "planned",
    idempotency_key: "attempt_idem",
    credential_ref: "cred_alias",
    plan_digest: "plan_digest",
    execution_plan: {},
    result_summary: {},
    error_message: null,
    protected_credential_returned: false,
    requested_by_subject: null,
    started_at: null,
    finished_at: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_profile_inventory",
    project_id: "proj_1",
    display_name: "Inventory Agent",
    slug: "inventory-agent",
    description: null,
    runtime_path: "sdk",
    framework: "langgraph",
    environment: "production",
    model_provider: "openai",
    model_name: "gpt-4.1",
    tool_names: ["inventory.item.delete"],
    allowed_action_types: ["custom"],
    blocked_action_types: [],
    default_policy_id: null,
    risk_limits: {},
    verification_connectors: ["generic_rest"],
    metadata: {},
    is_active: true,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function runner(overrides: Partial<ActionRunnerResponse> = {}): ActionRunnerResponse {
  return {
    runner_id: "runner_inventory",
    project_id: "proj_1",
    name: "Inventory runner",
    runner_type: "customer_hosted",
    environment: "production",
    status: "online",
    supported_operation_kinds: ["DELETE"],
    credential_scope: {},
    heartbeat_payload: {},
    capability_version: "2026-06-28",
    last_heartbeat_at: now,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function sourceSummary(overrides: Partial<SourceMutationSummaryResponse> = {}): SourceMutationSummaryResponse {
  return {
    total: 0,
    matched_receipt: 0,
    authorized_external: 0,
    legacy_path: 0,
    unmanaged_agent_action: 0,
    policy_bypass: 0,
    unknown_actor: 0,
    unreceipted: 0,
    ...overrides,
  };
}

function outcomeSummary(overrides: Partial<OutcomeReconciliationSummaryResponse> = {}): OutcomeReconciliationSummaryResponse {
  return {
    window_days: 30,
    total: 0,
    matched: 0,
    mismatched: 0,
    not_verified: 0,
    ...overrides,
  };
}

function meter(overrides: Partial<BillingUsageMeter> = {}): BillingUsageMeter {
  return {
    used: 0,
    limit: null,
    unlimited: true,
    overage: null,
    state: "ok",
    resets_at: null,
    ...overrides,
  };
}

function billingUsage(overrides: Partial<BillingUsageResponse> = {}): BillingUsageResponse {
  return {
    tenant_id: "tenant_1",
    org_id: "org_1",
    period_month: "2026-05",
    period_start: now,
    period_end: now,
    plan_code: "team",
    plan_name: "Team",
    subscription_status: "active",
    calls: meter(),
    replay: meter(),
    goldens: meter(),
    golden_sets: meter(),
    protected_actions: meter(),
    policy_checks: meter(),
    runner_executions: meter(),
    action_receipts: meter(),
    verification_checks: meter(),
    source_mutations: meter(),
    active_connectors: meter(),
    metering_health: {
      state: "ok",
      failure_count: 0,
      last_failure_at: null,
      last_failure_type: null,
      failure_policy: "fail_open",
      detail: null,
    },
    ...overrides,
  };
}

function apiKey(overrides: Partial<ApiKeyResponse> = {}): ApiKeyResponse {
  return {
    key_id: "key_1",
    project_id: "proj_1",
    name: "Default",
    key_prefix: "zrk",
    scopes: ["actions:write"],
    revoked: false,
    expired: false,
    expires_at: null,
    rotated_from_key_id: null,
    last_used_at: null,
    created_at: now,
    ...overrides,
  };
}

function mockHomeData(overrides: {
  intents?: ActionIntentResponse[];
  approvals?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  outcomeSummary?: OutcomeReconciliationSummaryResponse;
  sourceSummary?: SourceMutationSummaryResponse;
  mutations?: SourceMutationView[];
  staleAttempts?: ActionExecutionAttemptResponse[];
  profiles?: AgentProfileResponse[];
  activeAgentCount?: number;
  maxActiveAgents?: number;
  limitReached?: boolean;
  runners?: ActionRunnerResponse[];
  apiKeys?: ApiKeyResponse[];
  billing?: BillingUsageResponse;
} = {}) {
  api.listActionIntents.mockResolvedValue({
    items: overrides.intents ?? [],
    total_in_page: overrides.intents?.length ?? 0,
    limit: 75,
    offset: 0,
  });
  api.listRuntimePolicyApprovals.mockResolvedValue({
    items: overrides.approvals ?? [],
    total_in_page: overrides.approvals?.length ?? 0,
  });
  api.listOutcomeReconciliations.mockResolvedValue({
    items: overrides.outcomes ?? [],
    total_in_page: overrides.outcomes?.length ?? 0,
  });
  api.getOutcomeReconciliationSummary.mockResolvedValue(overrides.outcomeSummary ?? outcomeSummary());
  api.getSourceMutationSummary.mockResolvedValue(overrides.sourceSummary ?? sourceSummary());
  api.listUnreceiptedSourceMutations.mockResolvedValue({
    items: overrides.mutations ?? [],
    total_in_page: overrides.mutations?.length ?? 0,
  });
  api.listProjectActionExecutionAttempts.mockResolvedValue({
    items: overrides.staleAttempts ?? [],
  });
  const profiles = overrides.profiles ?? [];
  api.listAgentProfiles.mockResolvedValue({
    items: profiles,
    total: profiles.length,
    limit: 200,
    offset: 0,
    active_count: overrides.activeAgentCount ?? profiles.filter((item) => item.is_active).length,
    max_active_agents: overrides.maxActiveAgents ?? -1,
    limit_reached: overrides.limitReached ?? false,
  });
  api.listActionRunners.mockResolvedValue({
    items: overrides.runners ?? [],
  });
  api.listProjectApiKeys.mockResolvedValue(overrides.apiKeys ?? [apiKey()]);
  api.getBillingUsage.mockResolvedValue(overrides.billing ?? billingUsage());
}

describe("Mission Control Home", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.selectedProject = "proj_1";
    storeState.realTimeEnabled = false;
  });

  it("renders kernel verdict, proof strip, and prioritized queue rows", async () => {
    mockHomeData({
      intents: [
        intent({
          action_id: "act_mismatch",
          runtime_policy_decision_id: "decision_mismatch",
          idempotency_key: "idem_mismatch",
        }),
        intent({ action_id: "act_approval", runtime_policy_decision_id: "decision_1" }),
      ],
      approvals: [approval()],
      outcomes: [outcome()],
      outcomeSummary: outcomeSummary({ total: 3, matched: 2, mismatched: 1 }),
      sourceSummary: sourceSummary({ total: 1, policy_bypass: 1, unreceipted: 1 }),
      mutations: [mutation()],
    });

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Action mismatch" })).toBeInTheDocument();
    expect(screen.getByText("Controlled actions")).toBeInTheDocument();
    expect(screen.getByText("66.67% matched")).toBeInTheDocument();
    const queue = screen.getByLabelText("Decision queue");
    expect(within(queue).getByText(/Source-of-record mismatch/)).toBeInTheDocument();
    expect(within(queue).getByText(/Policy bypass mutation/)).toBeInTheDocument();
    expect(within(queue).getByText(/Action held for approval/)).toBeInTheDocument();
    expect(within(queue).getAllByText(/Agent:/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Bypass 1/i }));
    expect(within(queue).getByText(/Policy bypass mutation/)).toBeInTheDocument();
    expect(within(queue).queryByText(/Source-of-record mismatch/)).not.toBeInTheDocument();
  });

  it("shows fleet context only for multi-agent projects", async () => {
    mockHomeData({
      profiles: [
        profile(),
        profile({
          id: "agent_profile_support",
          display_name: "Support Agent",
          slug: "support-agent",
        }),
      ],
      activeAgentCount: 2,
      maxActiveAgents: 3,
      runners: [
        runner(),
        runner({ runner_id: "runner_offline", name: "Offline runner", status: "offline" }),
      ],
      intents: [intent({ action_id: "act_approval", runtime_policy_decision_id: "decision_1" })],
      approvals: [approval()],
    });

    render(<HomePage />);

    const fleetLine = await screen.findByLabelText("Agent fleet context");
    expect(within(fleetLine).getByText("2")).toBeInTheDocument();
    expect(within(fleetLine).getByText("managed agents")).toBeInTheDocument();
    expect(within(fleetLine).getByText("1 / 2")).toBeInTheDocument();
    expect(within(fleetLine).getByText("runners online")).toBeInTheDocument();
  });

  it("keeps guard-only runtime approvals visible", async () => {
    mockHomeData({
      approvals: [
        approval({
          id: "guard_decision",
          agent_name: "legacy-guard-agent",
          intended_action: { summary: "Send customer email" },
          action_type: "customer.email.send",
          expires_at: null,
        }),
      ],
    });

    render(<HomePage />);

    expect((await screen.findAllByText("Guard-only approval hold")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Send customer email").length).toBeGreaterThan(0);
  });

  it("shows the first-run panel when no setup exists", async () => {
    mockHomeData({ apiKeys: [] });

    const { container } = render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Setup required" })).toBeInTheDocument();
    const lockedHome = container.querySelector(".mc-locked-home");
    const lockedPreview = container.querySelector(".mc-locked-preview");
    expect(lockedHome).toBeInTheDocument();
    expect(lockedPreview?.getAttribute("aria-hidden")).toBe("true");
    expect(lockedPreview?.hasAttribute("inert")).toBe(true);
    expect(lockedPreview?.querySelector('[aria-label="Proof metrics"]')).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Protect your first agent action" })).toBeInTheDocument();
    expect(screen.getByText("Home unlocks after the first protected action signal")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Install SDK/i }).getAttribute("href")).toBe("/settings/keys");
    expect(screen.queryByRole("link", { name: "Setup agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Start agent setup/i }).getAttribute("href")).toBe("/agents/setup");
  });

  it("opens the mission dashboard after the agent setup wizard saves a profile", async () => {
    mockHomeData({
      apiKeys: [],
      profiles: [
        profile(),
      ],
    });

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Protected" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Protect your first agent action" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Proof metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Decision queue")).toBeInTheDocument();
  });

  it("surfaces stale runner attempts as a P2 queue item", async () => {
    mockHomeData({
      intents: [
        intent({
          action_id: "act_stale",
          status: "authorized",
          proof_status: "pending",
          receipt_status: "pending",
          runtime_policy_decision_id: null,
        }),
      ],
      staleAttempts: [attempt()],
    });

    render(<HomePage />);

    expect((await screen.findAllByText(/No runner claimed execution/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Attempt 1 planned/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(api.listProjectActionExecutionAttempts).toHaveBeenCalledWith(
        {
          status: ["planned", "running"],
          stale: true,
          stale_after_seconds: 600,
          limit: 75,
        },
        expect.any(AbortSignal),
      );
    });
  });
});
