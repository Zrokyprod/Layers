import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "@/lib/api";
import type { CaptureHealthResponse } from "@/lib/types";
import AgentsPage from "./page";

const api = vi.hoisted(() => ({
  getActionsLifecycleSummary: vi.fn(),
  getCaptureHealth: vi.fn(),
  listActionRunners: vi.fn(),
  listAgentProfiles: vi.fn(),
}));

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(selector: (state: { dateRange: { from: Date; to: Date } }) => T) => selector({
    dateRange: {
      from: new Date("2026-06-21T00:00:00Z"),
      to: new Date("2026-06-28T00:00:00Z"),
    },
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

const now = "2026-06-28T10:00:00.000Z";

function captureHealth(overrides: Partial<CaptureHealthResponse> = {}): CaptureHealthResponse {
  return {
    project_id: "proj_1",
    status: "no_data",
    stale_after_minutes: 10,
    last_call_id: null,
    last_seen_at: null,
    seconds_since_last_call: null,
    last_provider: null,
    last_model: null,
    last_call_type: null,
    last_source: null,
    calls_24h: 0,
    sdk_events_24h: 0,
    gateway_events_24h: 0,
    retrieval_spans_24h: 0,
    memory_spans_24h: 0,
    trace_runs_24h: 0,
    trace_spans_24h: 0,
    policy_spans_24h: 0,
    handoff_spans_24h: 0,
    incomplete_trace_runs_24h: 0,
    projection_failures_24h: 0,
    gateway_count: 0,
    gateway_unhealthy_count: 0,
    gateway_worst_status: "unknown",
    gateway_spool_backlog: 0,
    gateway_spool_bytes: 0,
    gateway_spool_oldest_age_seconds: 0,
    gateway_loss_count: 0,
    gateway_backpressure_rejections: 0,
    gateway_last_heartbeat_at: null,
    error_events_24h: 0,
    outcome_events_24h: 0,
    sampled_recent_calls: 0,
    validation_warnings: [],
    ...overrides,
  };
}

function renderAgentsPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <AgentsPage />
    </QueryClientProvider>,
  );
}

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_profile_inventory",
    project_id: "proj_1",
    display_name: "Inventory Agent",
    slug: "inventory-agent",
    description: "Deletes inventory items with proof.",
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

function setupPolicyProfile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return profile({
    metadata: {
      setup_source: "agent_control_setup_wizard",
      runtime_policy_mandate_enforced: true,
      product_context: {
        product_name: "Production Agent Workflow",
        business_goal: "Protect high-risk inventory changes.",
        critical_objects: ["inventory item"],
        source_systems: ["Generic REST"],
      },
      workflow_manifest: {
        workflow_id: "inventory_control",
        owner_team: "AI Platform",
        protected_actions: ["inventory.item.delete"],
      },
      action_contracts: [
        {
          id: "inventory_control.inventory_item_delete",
          verb: "DELETE",
          risk_class: "R3",
        },
      ],
      policy_preview: {
        approval_required_above_usd: 500,
        deny_above_usd: 5000,
        unknown_contract_decision: "deny",
      },
      runner_verification: {
        credential_ref: "cred_inventory",
        verifier_connector: "generic_rest",
        source_of_record: "Inventory API",
      },
    },
    ...overrides,
  });
}

function decision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_inventory",
    project_id: "proj_1",
    trace_id: "trace_inventory",
    call_id: "call_inventory",
    agent_name: "inventory-agent",
    role: "agent",
    action_type: "inventory.item.delete",
    tool_name: "inventory.item.delete",
    decision: "allow",
    status: "allowed",
    allowed: true,
    requires_approval: false,
    reasons: ["policy checks passed"],
    request: {},
    policy_snapshot: {},
    intended_action: { summary: "Archive inventory item" },
    trace_context: {},
    policy_hit: {},
    business_impact: {},
    audit_log: [],
    created_at: now,
    expires_at: null,
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    consumed_at: null,
    consumed_by_decision_id: null,
    ...overrides,
  };
}

function intent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_inventory",
    project_id: "proj_1",
    agent_id: "agent_profile_inventory",
    agent_profile: {
      id: "agent_profile_inventory",
      display_name: "Inventory Agent",
      slug: "inventory-agent",
      runtime_path: "sdk",
      environment: "production",
    },
    contract_version: "inventory.item.delete/1.0",
    action_type: "inventory.item.delete",
    operation_kind: "DELETE",
    environment: "production",
    status: "authorized",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "idem_inventory",
    intent_digest: "sha256:intent-inventory",
    canonical_intent: {
      principal: { id: "inventory-agent" },
      purpose: { summary: "Archive inventory item" },
      resource: { id: "item_123" },
      trace_context: {
        agent_name: "inventory-agent",
        trace_id: "trace_inventory",
        call_id: "call_inventory",
      },
    },
    created_at: now,
    decided_at: now,
    authorized_at: now,
    runtime_policy_decision_id: "decision_inventory",
    deadline: null,
    status_url: "/v1/action-intents/act_inventory",
    ...overrides,
  };
}

function outcome(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "outcome_inventory",
    project_id: "proj_1",
    call_id: "call_inventory",
    trace_id: "trace_inventory",
    runtime_policy_decision_id: "decision_inventory",
    action_type: "inventory.item.delete",
    connector_type: "generic_rest",
    system_ref: "item_123",
    verdict: "matched",
    reason: "matched",
    amount_usd: null,
    currency: null,
    claimed: {},
    actual: {},
    comparison: {},
    idempotency_key: "idem_inventory",
    metadata: {},
    checked_at: now,
    created_at: now,
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

function attempt(overrides: Partial<ActionExecutionAttemptResponse> = {}): ActionExecutionAttemptResponse {
  return {
    attempt_id: "attempt_inventory",
    project_id: "proj_1",
    action_id: "act_inventory",
    runner_id: "runner_inventory",
    attempt_number: 1,
    status: "succeeded",
    idempotency_key: "idem_inventory",
    credential_ref: "cred:inventory",
    plan_digest: "sha256:plan",
    execution_plan: {},
    result_summary: {},
    error_message: null,
    protected_credential_returned: false,
    requested_by_subject: "agent",
    started_at: now,
    finished_at: now,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function mutation(overrides: Partial<SourceMutationView> = {}): SourceMutationView {
  return {
    id: "mutation_inventory",
    project_id: "proj_1",
    source_system: "stripe",
    mutation_id: "rf_bypass",
    action_type: "stripe_refund",
    resource_type: "refund",
    resource_id: "rf_bypass",
    system_ref: "stripe:rf_bypass",
    actor_type: "ai_agent",
    actor_id: "inventory-agent",
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

function mockAgents({
  profiles = [profile()],
  activeCount = profiles.filter((item) => item.is_active).length,
  cap = 3,
  limitReached = false,
  intents = [intent()],
  decisions = [decision()],
  outcomes = [outcome()],
  runners = [runner()],
  attempts = [attempt()],
  staleAttempts = [] as ActionExecutionAttemptResponse[],
  mutations = [] as SourceMutationView[],
  connectedFeeds = 1,
}: {
  profiles?: AgentProfileResponse[];
  activeCount?: number;
  cap?: number;
  limitReached?: boolean;
  intents?: ActionIntentResponse[];
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  runners?: ActionRunnerResponse[];
  attempts?: ActionExecutionAttemptResponse[];
  staleAttempts?: ActionExecutionAttemptResponse[];
  mutations?: SourceMutationView[];
  connectedFeeds?: number;
} = {}) {
  api.getCaptureHealth.mockResolvedValue(captureHealth());
  api.listAgentProfiles.mockResolvedValue({
    items: profiles,
    total: profiles.length,
    limit: 200,
    offset: 0,
    active_count: activeCount,
    max_active_agents: cap,
    limit_reached: limitReached,
  });
  api.getActionsLifecycleSummary.mockResolvedValue({
    project_id: "proj_1",
    window_days: 7,
    window_start: "2026-06-21T00:00:00Z",
    generated_at: now,
    row_limit: 200,
    source_totals: {
      intents: intents.length,
      approvals: decisions.length,
      outcomes: outcomes.length,
      mutations: mutations.length,
      attempts: attempts.length,
      stale_attempts: staleAttempts.length,
    },
    truncated: false,
    truncated_sources: [],
    metrics: {
      controlled_actions: intents.length,
      held_actions: decisions.filter((item) => item.status === "pending_approval").length,
      matched_outcomes: outcomes.filter((item) => item.verdict === "matched").length,
      mismatched_outcomes: outcomes.filter((item) => item.verdict === "mismatched").length,
      not_verified_outcomes: outcomes.filter((item) => item.verdict === "not_verified").length,
      bypass_risk: mutations.length,
    },
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
    data: {
      intents,
      approvals: decisions,
      outcomes,
      outcome_summary: null,
      source_summary: {
        total: mutations.length,
        matched_receipt: 0,
        authorized_external: 0,
        legacy_path: 0,
        unmanaged_agent_action: 0,
        policy_bypass: mutations.filter((item) => item.classification === "policy_bypass").length,
        unknown_actor: 0,
        unreceipted: mutations.length,
        connected_feeds: connectedFeeds,
        successful_pollers: connectedFeeds,
      },
      mutations,
      attempts,
      stale_attempts: staleAttempts,
      billing_usage: null,
    },
  });
  api.listActionRunners.mockResolvedValue({ items: runners });
}

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a simple fleet view with proof and runner context", async () => {
    mockAgents();

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent control incomplete", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("1 / 3")).toBeInTheDocument();
    expect(screen.getAllByText("Coverage").length).toBeGreaterThan(0);
    expect(screen.getByText("Runners online")).toBeInTheDocument();

    const fleet = await screen.findByLabelText("Agent fleet");
    expect(within(fleet).getByText("Inventory Agent")).toBeInTheDocument();
    expect(within(fleet).getByText("Matched")).toBeInTheDocument();
    expect(within(fleet).getByText("100% covered")).toBeInTheDocument();
    expect(within(fleet).getByText("No risky drift")).toBeInTheDocument();
    expect(within(fleet).getByText("online / compatible")).toBeInTheDocument();

    const inspector = screen.getByLabelText("Selected agent control");
    expect(within(inspector).getByText("Managed profile")).toBeInTheDocument();
    expect(within(inspector).getByLabelText("Agent mandate summary")).toBeInTheDocument();
    expect(within(inspector).getByLabelText("Proof chain")).toBeInTheDocument();
    expect(within(inspector).getByText("Archive inventory item")).toBeInTheDocument();
    expect(within(inspector).getByRole("link", { name: "Open evidence" }).getAttribute("href")).toBe("/evidence?action_id=act_inventory");
    expect(api.getActionsLifecycleSummary).toHaveBeenCalledWith(
      { days: 7, limit: 200 },
      expect.any(AbortSignal),
    );
  });

  it("locks add-agent when the backend plan meter is reached", async () => {
    mockAgents({ profiles: [setupPolicyProfile()], activeCount: 1, cap: 1, limitReached: true });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent control incomplete", level: 1 })).toBeInTheDocument();
    await waitFor(() => {
      expect(document.querySelector('a[href="/agents/setup?agentId=agent_profile_inventory"]')).not.toBeNull();
    });
    expect(screen.getByText("Plan cap reached.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Add agent$/i })).toBeNull();
  });

  it("explains legacy profiles above the current plan limit", async () => {
    mockAgents({ profiles: [profile(), setupPolicyProfile({ id: "agent_2", slug: "agent-2" })], activeCount: 2, cap: 1, limitReached: true });

    renderAgentsPage();

    expect(await screen.findByText("2 managed \u00b7 limit 1")).toBeInTheDocument();
    expect(screen.getByText("Existing profiles exceed the current plan limit; new agents are blocked.")).toBeInTheDocument();
  });

  it("keeps the hero live when secondary feeds degrade", async () => {
    mockAgents();
    api.getActionsLifecycleSummary.mockRejectedValue(new Error("lifecycle unavailable"));

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent control incomplete", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Agent visibility unavailable", level: 1 })).toBeNull();
    expect(await screen.findByText(/Action lifecycle degraded/i)).toBeInTheDocument();
  });

  it("does not claim coverage or zero bypass risk without a connected source feed", async () => {
    mockAgents({ connectedFeeds: 0 });

    renderAgentsPage();

    const metrics = await screen.findByRole("region", { name: "Agent fleet summary" });
    expect(within(metrics).getAllByText("Not covered")).toHaveLength(2);
    expect(within(metrics).getByText(/protected-action observations alone do not prove coverage/i)).toBeInTheDocument();

    const fleet = await screen.findByLabelText("Agent fleet");
    expect(within(fleet).getAllByText("Not covered").length).toBeGreaterThan(0);
    expect(within(fleet).getByText("Bypass feed not connected")).toBeInTheDocument();
  });

  it("makes runner unavailability the primary state for authorized actions", async () => {
    mockAgents({
      intents: [intent({ proof_status: "not_started", receipt_status: "missing" })],
      outcomes: [],
      attempts: [],
      runners: [runner({ status: "offline" })],
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agents waiting for runner", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Restore runner" }).getAttribute("href")).toBe(
      "/actions?filter=awaiting_runner",
    );
    const fleet = screen.getByLabelText("Agent fleet");
    expect(within(fleet).getByText("Runner unavailable")).toBeInTheDocument();
    expect(within(fleet).getByText("0 / 1")).toBeInTheDocument();
    const inspector = screen.getByLabelText("Selected agent control");
    expect(within(inspector).getAllByText("Awaiting runner").length).toBeGreaterThan(0);
  });

  it("shows unavailable only when the core profile feed fails", async () => {
    mockAgents();
    api.listAgentProfiles.mockRejectedValue(new Error("profiles unavailable"));

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent visibility unavailable", level: 1 })).toBeInTheDocument();
  });

  it("keeps managed count visible when the plan cap is unlimited", async () => {
    mockAgents({
      profiles: [],
      activeCount: 0,
      cap: -1,
      intents: [],
      decisions: [],
      outcomes: [],
      runners: [],
      attempts: [],
    });

    renderAgentsPage();

    expect(await screen.findByText("0 managed · unlimited")).toBeInTheDocument();
  });

  it("keeps telemetry-only agent identities visible as secondary rows", async () => {
    mockAgents({
      profiles: [profile()],
      intents: [
        intent({
          action_id: "act_shadow",
          agent_id: null,
          agent_profile: null,
          runtime_policy_decision_id: "decision_shadow",
          canonical_intent: {
            principal: { id: "shadow-agent" },
            purpose: { summary: "Update shadow record" },
            resource: { id: "record_1" },
            trace_context: { agent_name: "shadow-agent" },
          },
        }),
      ],
      decisions: [decision({ id: "decision_shadow", agent_name: "shadow-agent" })],
      outcomes: [],
    });

    renderAgentsPage();

    const fleet = await screen.findByLabelText("Agent fleet");
    expect(within(fleet).getByText("Inventory Agent")).toBeInTheDocument();
    expect(within(fleet).getByText("shadow-agent")).toBeInTheDocument();
    expect(within(fleet).getByText("Telemetry-only / unmanaged")).toBeInTheDocument();
  });

  it("surfaces managed-agent bypass and sequence-risk signals in fleet governance", async () => {
    mockAgents({
      decisions: [
        decision({
          policy_hit: {
            sequence_risk: {
              pattern: "sensitive_read_then_external_send",
            },
          },
          reasons: ["sequence risk: sensitive read before external send"],
        }),
      ],
      mutations: [mutation()],
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent control bypass detected", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Risk signals")).toBeInTheDocument();

    const fleet = await screen.findByLabelText("Agent fleet");
    expect(within(fleet).getByText("Control bypass")).toBeInTheDocument();
    expect(within(fleet).getByText("0% covered")).toBeInTheDocument();
    expect(within(fleet).getAllByText("1 signal").length).toBeGreaterThan(0);
    expect(within(fleet).getByText("1 bypass / 0 sequence")).toBeInTheDocument();
    expect(within(fleet).getByText("0 bypass / 1 sequence")).toBeInTheDocument();

    const inspector = screen.getByLabelText("Selected agent control");
    expect(within(inspector).getByText("Bypass")).toBeInTheDocument();
    expect(within(inspector).getByText("Sequence risk")).toBeInTheDocument();
  });

  it("routes a telemetry-only identity into setup prefilled with the observed agent name", async () => {
    mockAgents({
      profiles: [],
      activeCount: 0,
      cap: 3,
      intents: [
        intent({
          action_id: "act_shadow",
          agent_id: null,
          agent_profile: null,
          runtime_policy_decision_id: "decision_shadow",
          canonical_intent: {
            principal: { id: "shadow-agent" },
            purpose: { summary: "Update shadow record" },
            resource: { id: "record_1" },
            trace_context: { agent_name: "shadow-agent" },
          },
        }),
      ],
      decisions: [decision({ id: "decision_shadow", agent_name: "shadow-agent" })],
      outcomes: [],
      runners: [],
      attempts: [],
    });

    renderAgentsPage();

    const inspector = await screen.findByLabelText("Selected agent control");
    expect(within(inspector).getByRole("link", { name: "Promote to managed" }).getAttribute("href")).toBe(
      "/agents/setup?agentName=shadow-agent",
    );
  });

  it("locks telemetry promotion when the agent plan cap is reached", async () => {
    mockAgents({
      profiles: [],
      activeCount: 1,
      cap: 1,
      limitReached: true,
      intents: [
        intent({
          action_id: "act_shadow",
          agent_id: null,
          agent_profile: null,
          runtime_policy_decision_id: "decision_shadow",
          canonical_intent: {
            principal: { id: "shadow-agent" },
            purpose: { summary: "Update shadow record" },
            resource: { id: "record_1" },
            trace_context: { agent_name: "shadow-agent" },
          },
        }),
      ],
      decisions: [decision({ id: "decision_shadow", agent_name: "shadow-agent" })],
      outcomes: [],
      runners: [],
      attempts: [],
    });

    renderAgentsPage();

    const inspector = await screen.findByLabelText("Selected agent control");
    expect(within(inspector).getByRole("link", { name: "Promote to managed" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("keeps runner and attempt context summarized without secondary tabs", async () => {
    const runningAttempt = attempt({ attempt_id: "attempt_running", status: "running" });
    mockAgents({
      attempts: [attempt(), runningAttempt],
      staleAttempts: [runningAttempt],
      runners: [
        runner(),
        runner({ runner_id: "runner_degraded", name: "Degraded runner", status: "degraded" }),
      ],
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent control incomplete", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Runners/i })).toBeNull();
    expect(screen.queryByRole("tab", { name: /Attempts/i })).toBeNull();
    expect(screen.getByText("Runners online")).toBeInTheDocument();
  });

  it("routes first-run agent creation through the setup wizard", async () => {
    mockAgents({
      profiles: [],
      activeCount: 0,
      cap: 1,
      intents: [],
      decisions: [],
      outcomes: [],
      runners: [],
      attempts: [],
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agent control incomplete", level: 1 })).toBeInTheDocument();
    const setupStatus = screen.getByLabelText("Agent control setup status");
    expect(within(setupStatus).getByRole("link", { name: /^Start setup$/i }).getAttribute("href")).toBe("/agents/setup");
    expect(screen.queryByRole("link", { name: /^Add agent$/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /^Open setup$/i })).toBeNull();
  });

  it("marks a fully configured enforced agent live when capture is connected", async () => {
    mockAgents({ profiles: [setupPolicyProfile()] });
    api.getCaptureHealth.mockResolvedValue(captureHealth({
      status: "connected",
      calls_24h: 2,
      outcome_events_24h: 1,
    }));

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agents controlled", level: 1 })).toBeInTheDocument();
    expect(screen.queryByLabelText("Agent control setup status")).toBeNull();
    expect(api.getCaptureHealth).toHaveBeenCalled();
  });
});
