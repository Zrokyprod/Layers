import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";
import AgentDetailPage from "./page";

const api = vi.hoisted(() => ({
  getActionsLifecycleSummary: vi.fn(),
  getAgentProfile: vi.fn(),
  listActionRunners: vi.fn(),
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

vi.mock("next/navigation", () => ({
  useParams: () => ({ agentId: "agent_profile_inventory" }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-06-28T10:00:00Z";

function renderDetailPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <AgentDetailPage />
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
    default_policy_id: "policy_1",
    risk_limits: { max_items: 1 },
    verification_connectors: ["generic_rest"],
    metadata: { agent_name: "inventory-agent" },
    is_active: true,
    created_at: now,
    updated_at: now,
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

function mockDetail() {
  api.getAgentProfile.mockResolvedValue(profile());
  api.getActionsLifecycleSummary.mockResolvedValue({
    project_id: "proj_1",
    window_days: 7,
    window_start: "2026-06-21T00:00:00Z",
    generated_at: now,
    row_limit: 200,
    source_totals: { intents: 1, approvals: 1, outcomes: 1, mutations: 0, attempts: 1, stale_attempts: 0 },
    truncated: false,
    truncated_sources: [],
    metrics: {
      controlled_actions: 1,
      held_actions: 0,
      matched_outcomes: 1,
      mismatched_outcomes: 0,
      not_verified_outcomes: 0,
      bypass_risk: 0,
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
      intents: [intent()],
      approvals: [decision()],
      outcomes: [outcome()],
      outcome_summary: null,
      source_summary: {
        total: 0,
        matched_receipt: 0,
        authorized_external: 0,
        legacy_path: 0,
        unmanaged_agent_action: 0,
        policy_bypass: 0,
        unknown_actor: 0,
        unreceipted: 0,
        connected_feeds: 1,
        successful_pollers: 1,
      },
      mutations: [],
      attempts: [attempt()],
      stale_attempts: [],
      billing_usage: null,
    },
  });
  api.listActionRunners.mockResolvedValue({ items: [runner()] });
}

describe("AgentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders time-windowed config, proof, and compatible runner context", async () => {
    mockDetail();

    renderDetailPage();

    expect(await screen.findByRole("heading", { name: "Inventory Agent", level: 1 })).toBeInTheDocument();
    expect(api.getActionsLifecycleSummary).toHaveBeenCalledWith(
      { days: 7, limit: 200 },
      expect.any(AbortSignal),
    );
    const config = screen.getByLabelText("Agent control configuration summary");
    expect(config).toBeInTheDocument();
    expect(within(config).getByText("Managed by setup wizard")).toBeInTheDocument();
    expect(within(config).getByRole("link", { name: "Configure" }).getAttribute("href")).toBe(
      "/agents/setup?agentId=agent_profile_inventory",
    );
    expect(screen.queryByRole("button", { name: "Save profile" })).toBeNull();

    const proof = screen.getByLabelText("Agent proof and runner context");
    expect(within(proof).getByLabelText("Proof chain")).toBeInTheDocument();
    expect(within(proof).getByText("Archive inventory item")).toBeInTheDocument();

    const runners = screen.getByLabelText("Agent compatible runners and attempts");
    expect(within(runners).getByText("Inventory runner")).toBeInTheDocument();
    expect(screen.queryByLabelText("Agent tool plan")).toBeNull();
  });
});
