import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  HomeSummaryResponse,
  OutcomeReconciliationSummaryResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationSummaryResponse,
  SourceMutationView,
} from "@/lib/api";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

const api = vi.hoisted(() => ({
  getBillingUsage: vi.fn(),
  getHomeSummary: vi.fn(),
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
  dateRange: { from: null, to: null },
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
    selector: (state: {
      selectedProject: string;
      realTimeEnabled: boolean;
      dateRange: { from: Date | null; to: Date | null };
    }) => T,
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

function homeSummary(
  overrides: Partial<HomeSummaryResponse["metrics"]> = {},
  data: HomeSummaryResponse["data"] = {},
): HomeSummaryResponse {
  return {
    project_id: "proj_1",
    window_days: 7,
    window_start: "2026-05-22T10:00:00.000Z",
    generated_at: now,
    metrics: {
      controlled_actions: 0,
      pending_approvals: 0,
      verified_outcomes: 0,
      outcome_checks: 0,
      receipts_generated: 0,
      bypass_mutations: 0,
      unreceipted_mutations: 0,
      sequence_risks: 0,
      ...overrides,
    },
    sources: {
      home_summary: true,
      intents: true,
      approvals: true,
      outcomes: true,
      outcome_summary: true,
      source_summary: true,
      mutations: true,
      stale_attempts: true,
      agent_profiles: true,
      action_runners: true,
      api_keys: true,
      billing_usage: true,
    },
    data,
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
  homeSummary?: HomeSummaryResponse;
} = {}) {
  const profiles = overrides.profiles ?? [];
  const agentProfileMeta = {
    active_count: overrides.activeAgentCount ?? profiles.filter((item) => item.is_active).length,
    max_active_agents: overrides.maxActiveAgents ?? -1,
    limit_reached: overrides.limitReached ?? false,
  };
  const summaryData: HomeSummaryResponse["data"] = {
    intents: overrides.intents ?? [],
    approvals: overrides.approvals ?? [],
    outcomes: overrides.outcomes ?? [],
    outcome_summary: overrides.outcomeSummary ?? outcomeSummary(),
    source_summary: overrides.sourceSummary ?? sourceSummary(),
    mutations: overrides.mutations ?? [],
    stale_attempts: overrides.staleAttempts ?? [],
    agent_profiles: profiles,
    agent_profile_meta: agentProfileMeta,
    action_runners: overrides.runners ?? [],
    api_keys: overrides.apiKeys ?? [apiKey()],
    billing_usage: overrides.billing ?? billingUsage(),
  };
  api.getHomeSummary.mockResolvedValue(
    overrides.homeSummary ??
      homeSummary({
        controlled_actions: overrides.intents?.length ?? 0,
        pending_approvals: overrides.approvals?.length ?? 0,
        verified_outcomes: overrides.outcomeSummary?.matched ?? overrides.outcomes?.filter((item) => item.verdict === "matched").length ?? 0,
        outcome_checks: overrides.outcomeSummary?.total ?? overrides.outcomes?.length ?? 0,
        receipts_generated: overrides.intents?.filter((item) => item.receipt_status === "generated").length ?? 0,
        bypass_mutations: overrides.sourceSummary?.policy_bypass ?? overrides.mutations?.filter((item) => item.classification === "policy_bypass").length ?? 0,
        unreceipted_mutations: overrides.sourceSummary?.unreceipted ?? overrides.mutations?.length ?? 0,
        sequence_risks: overrides.approvals?.filter((item) => JSON.stringify(item.policy_hit).includes("sequence_risk")).length ?? 0,
      }, summaryData),
  );
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
  api.listAgentProfiles.mockResolvedValue({
    items: profiles,
    total: profiles.length,
    limit: 200,
    offset: 0,
    ...agentProfileMeta,
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
    storeState.dateRange = { from: null, to: null };
  });

  it("renders kernel verdict, top KPIs, and real activity sections", async () => {
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
    const proofMetrics = screen.getByLabelText("Proof metrics");
    expect(within(proofMetrics).getByText("Agents protected")).toBeInTheDocument();
    expect(within(proofMetrics).getByText("Actions controlled")).toBeInTheDocument();
    expect(within(proofMetrics).getByText("Pending approvals")).toBeInTheDocument();
    expect(within(proofMetrics).getByText("Proof generated")).toBeInTheDocument();
    const agentHealth = screen.getByLabelText("Agent health over time");
    expect(within(agentHealth).getByRole("heading", { name: "Timeframe-wise control confidence" })).toBeInTheDocument();
    expect(within(agentHealth).getByText("Health score")).toBeInTheDocument();
    expect(within(agentHealth).getByText("0 / 0 online")).toBeInTheDocument();
    expect(within(agentHealth).getByText("2 signals")).toBeInTheDocument();
    expect(screen.queryByText("Verified action loop")).not.toBeInTheDocument();
    expect(screen.queryByText("Sequence risk watch")).not.toBeInTheDocument();
    const protectedActions = screen.getByLabelText("Recent protected actions");
    const proofChecks = screen.getByLabelText("Recent proof checks");
    expect(protectedActions).toBeInTheDocument();
    expect(screen.getByLabelText("Recent approvals")).toBeInTheDocument();
    expect(proofChecks).toBeInTheDocument();
    expect(within(protectedActions).getAllByText("Delete inventory item").length).toBeGreaterThan(0);
    expect(within(proofChecks).getByText(/deleted flag was still false/i)).toBeInTheDocument();
  });

  it("shows protected agent count without repeating runner status", async () => {
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

    const proofMetrics = await screen.findByLabelText("Proof metrics");
    const agentsCard = within(proofMetrics).getByText("Agents protected").closest(".mc-proof-card") as HTMLElement;
    expect(agentsCard).toBeInTheDocument();
    expect(within(agentsCard).getByText("2")).toBeInTheDocument();
    expect(screen.queryByLabelText("Agent fleet context")).not.toBeInTheDocument();
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
    expect(container.querySelector(".mc-locked-home")).not.toBeInTheDocument();
    expect(container.querySelector(".mc-locked-preview")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Proof metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Recent Home activity")).toBeInTheDocument();
    expect(screen.getByText("Actions controlled")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Get Home reporting real activity" })).toBeInTheDocument();
    const agentHealth = screen.getByLabelText("Agent health over time");
    expect(within(agentHealth).getByText("No signal")).toBeInTheDocument();
    expect(within(agentHealth).getByText("No agent health events in this timeframe yet.")).toBeInTheDocument();
    expect(screen.getByText("Setup checklist")).toBeInTheDocument();
    const runnerCard = screen.getAllByText("Connect runner")[0].closest(".mc-first-run-step-card");
    const verificationCard = screen.getByText("Connect source-of-record").closest(".mc-first-run-step-card");
    const actionCard = screen.getByText("Run first protected action").closest(".mc-first-run-step-card");
    const receiptCard = screen.getByText("Generate first receipt").closest(".mc-first-run-step-card");
    expect(runnerCard?.getAttribute("data-state")).toBe("current");
    expect(verificationCard?.getAttribute("data-state")).toBe("locked");
    expect(actionCard?.getAttribute("data-state")).toBe("locked");
    expect(receiptCard?.getAttribute("data-state")).toBe("locked");
    expect(screen.queryByRole("link", { name: "Setup agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Connect runner/i }).getAttribute("href")).toBe(
      "/agents/setup?intent=connect-runner&source=home",
    );
    expect(screen.getAllByRole("link", { name: /Agents protected/i }).some((link) => link.getAttribute("href") === "/agents")).toBe(true);
    expect(screen.queryByRole("link", { name: /^Actions$/i })).not.toBeInTheDocument();
  });

  it("tracks runner and verification progress before the first action signal", async () => {
    mockHomeData({
      apiKeys: [apiKey()],
      profiles: [
        profile(),
      ],
      runners: [runner()],
    });

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Setup required" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Get Home reporting real activity" })).toBeInTheDocument();
    expect(screen.getByText("Connect runner").closest(".mc-first-run-step-card")?.getAttribute("data-state")).toBe("done");
    expect(screen.getByText("Connect source-of-record").closest(".mc-first-run-step-card")?.getAttribute("data-state")).toBe("current");
    expect(screen.getByText("Connect the system Zroky checks after an action runs.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Connect verification/i }).getAttribute("href")).toBe("/integrations");
  });

  it("opens the mission dashboard after the first protected action signal", async () => {
    mockHomeData({
      apiKeys: [apiKey()],
      profiles: [profile()],
      runners: [runner()],
      intents: [intent({ status: "authorized", proof_status: "matched", receipt_status: "generated", runtime_policy_decision_id: null })],
      outcomes: [outcome({ verdict: "matched", verification_status: "matched" })],
    });

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Protected" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Get Home reporting real activity" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Proof metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Recent Home activity")).toBeInTheDocument();
  });

  it("does not turn a failed home summary into zero KPI metrics", async () => {
    const authorizedIntent = intent({ status: "authorized", runtime_policy_decision_id: null });
    const degradedSummary = homeSummary(
      { controlled_actions: 1 },
      {
        intents: [authorizedIntent],
        approvals: [],
        outcomes: [],
        outcome_summary: outcomeSummary(),
        source_summary: sourceSummary(),
        mutations: [],
        stale_attempts: [],
        agent_profiles: [profile()],
        agent_profile_meta: {
          active_count: 1,
          max_active_agents: -1,
          limit_reached: false,
        },
        action_runners: [],
        api_keys: [apiKey()],
        billing_usage: billingUsage(),
      },
    );
    degradedSummary.sources = {
      ...degradedSummary.sources!,
      home_summary: false,
    };
    mockHomeData({ homeSummary: degradedSummary });

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Protected" })).toBeInTheDocument();
    const proofMetrics = screen.getByLabelText("Proof metrics");
    const approvalsCard = within(proofMetrics).getByText("Pending approvals").closest(".mc-proof-card") as HTMLElement;
    expect(approvalsCard).toBeInTheDocument();
    expect(approvalsCard.classList.contains("mc-tone-warning")).toBe(true);
    expect(within(approvalsCard).getByText("— unavailable")).toBeInTheDocument();
    expect(within(approvalsCard).getByText("Home summary unavailable")).toBeInTheDocument();
    expect(within(approvalsCard).queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("1 data source unavailable")).toBeInTheDocument();
  });

  it("keeps stale runner attempts out of the real activity grid", async () => {
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

    expect(await screen.findByLabelText("Recent protected actions")).toBeInTheDocument();
    const activityGrid = screen.getByLabelText("Recent Home activity");
    expect(within(activityGrid).queryByText(/No runner claimed execution/)).not.toBeInTheDocument();
    expect(within(activityGrid).queryByText(/Attempt 1 planned/i)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(api.getHomeSummary).toHaveBeenCalledWith(7, expect.any(AbortSignal));
      expect(api.listProjectActionExecutionAttempts).not.toHaveBeenCalled();
    });
  });
});
