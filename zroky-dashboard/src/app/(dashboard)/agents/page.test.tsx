import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  AgentScoreView,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";
import AgentsPage from "./page";

const api = vi.hoisted(() => ({
  getReliabilityLeaderboard: vi.fn(),
  listActionIntents: vi.fn(),
  listActionRunners: vi.fn(),
  listAgentProfiles: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
  listProjectActionExecutionAttempts: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
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

function score(overrides: Partial<AgentScoreView> = {}): AgentScoreView {
  return {
    agent_name: "inventory-agent",
    score_date: "2026-06-28",
    health_score: 92,
    fail_rate: 0.02,
    fail_rate_score: 98,
    cost_efficiency_score: 90,
    determinism_score: 88,
    regression_trend_score: 86,
    call_count: 10,
    avg_cost_usd: 0.04,
    p95_latency_ms: 640,
    prev_week_fail_rate: 0.03,
    determinism_breakdown: null,
    top_failure_axis: null,
    computed_at: now,
    ...overrides,
  };
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

function mockAgents({
  profiles = [profile()],
  activeCount = profiles.filter((item) => item.is_active).length,
  cap = 3,
  limitReached = false,
  scores = [score()],
  intents = [intent()],
  decisions = [decision()],
  outcomes = [outcome()],
  runners = [runner()],
  attempts = [attempt()],
  staleAttempts = [] as ActionExecutionAttemptResponse[],
}: {
  profiles?: AgentProfileResponse[];
  activeCount?: number;
  cap?: number;
  limitReached?: boolean;
  scores?: AgentScoreView[];
  intents?: ActionIntentResponse[];
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  runners?: ActionRunnerResponse[];
  attempts?: ActionExecutionAttemptResponse[];
  staleAttempts?: ActionExecutionAttemptResponse[];
} = {}) {
  api.listAgentProfiles.mockResolvedValue({
    items: profiles,
    total: profiles.length,
    limit: 200,
    offset: 0,
    active_count: activeCount,
    max_active_agents: cap,
    limit_reached: limitReached,
  });
  api.getReliabilityLeaderboard.mockResolvedValue(scores);
  api.listActionIntents.mockResolvedValue({
    items: intents,
    total_in_page: intents.length,
    limit: 200,
    offset: 0,
  });
  api.listRuntimePolicyApprovals.mockResolvedValue({
    items: decisions,
    total_in_page: decisions.length,
  });
  api.listOutcomeReconciliations.mockResolvedValue({
    items: outcomes,
    total_in_page: outcomes.length,
  });
  api.listActionRunners.mockResolvedValue({ items: runners });
  api.listProjectActionExecutionAttempts.mockImplementation((query: { stale?: boolean }) => Promise.resolve({
    items: query?.stale ? staleAttempts : attempts,
  }));
}

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a kernel-first fleet cockpit with proof and runner context", async () => {
    mockAgents();

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agents controlled", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    expect(screen.getByText("Runners online")).toBeInTheDocument();

    const table = screen.getByLabelText("Agent fleet table");
    expect(within(table).getByText("Inventory Agent")).toBeInTheDocument();
    expect(within(table).getByText("Matched")).toBeInTheDocument();
    expect(within(table).getByText("observed compatible")).toBeInTheDocument();

    const inspector = screen.getByLabelText("Selected agent control");
    expect(within(inspector).getByText("Managed profile")).toBeInTheDocument();
    expect(within(inspector).getByLabelText("Proof chain")).toBeInTheDocument();
    expect(within(inspector).getByText("Archive inventory item")).toBeInTheDocument();
    expect(within(inspector).getByRole("link", { name: "Open evidence" }).getAttribute("href")).toBe("/evidence?action_id=act_inventory");
  });

  it("locks add-agent when the backend plan meter is reached", async () => {
    mockAgents({ activeCount: 1, cap: 1, limitReached: true });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agents controlled", level: 1 })).toBeInTheDocument();
    const locked = screen.getByRole("button", { name: /Upgrade to add agents/i });
    expect((locked as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: /^Add agent$/i })).toBeNull();
  });

  it("keeps the hero live when secondary feeds degrade", async () => {
    mockAgents();
    api.listOutcomeReconciliations.mockRejectedValue(new Error("outcomes unavailable"));

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Agents controlled", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Agent visibility unavailable", level: 1 })).toBeNull();
    expect(await screen.findByText(/Proof feed degraded/i)).toBeInTheDocument();
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
      scores: [],
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

    const table = await screen.findByLabelText("Agent fleet table");
    expect(within(table).getByText("Inventory Agent")).toBeInTheDocument();
    expect(within(table).getByText("shadow-agent")).toBeInTheDocument();
    expect(within(table).getByText("Telemetry-only / unmanaged")).toBeInTheDocument();
  });

  it("routes a telemetry-only identity into setup prefilled with the observed agent name", async () => {
    mockAgents({
      profiles: [],
      activeCount: 0,
      cap: 3,
      intents: [
        intent({
          action_id: "act_shadow",
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
      scores: [],
    });

    renderAgentsPage();

    const table = await screen.findByLabelText("Agent fleet table");
    expect(within(table).getByRole("link", { name: "Promote" }).getAttribute("href")).toBe(
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
      scores: [],
    });

    renderAgentsPage();

    const table = await screen.findByLabelText("Agent fleet table");
    expect(within(table).getByRole("link", { name: "Promote" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("shows project runners and attempts in tabs", async () => {
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

    fireEvent.click(await screen.findByRole("tab", { name: /Runners/i }));
    const runnersPanel = screen.getByLabelText("Project runners");
    expect(within(runnersPanel).getByText("Inventory runner")).toBeInTheDocument();
    expect(within(runnersPanel).getByText("Degraded runner")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Attempts/i }));
    const attemptsPanel = screen.getByLabelText("Execution attempts");
    expect(within(attemptsPanel).getAllByText("act_inventory").length).toBeGreaterThan(0);
    expect(within(attemptsPanel).getByText("Stalled")).toBeInTheDocument();
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
      scores: [],
    });

    renderAgentsPage();

    expect(await screen.findByRole("heading", { name: "Setup required", level: 1 })).toBeInTheDocument();
    const addLinks = screen.getAllByRole("link", { name: /^Add agent$/i });
    expect(addLinks.some((link) => link.getAttribute("href") === "/agents/setup")).toBe(true);
  });
});
