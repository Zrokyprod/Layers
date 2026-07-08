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
  ToolRegistryResponse,
} from "@/lib/api";
import AgentDetailPage from "./page";

const api = vi.hoisted(() => ({
  getAgentProfile: vi.fn(),
  getToolRegistry: vi.fn(),
  listActionIntents: vi.fn(),
  listActionRunners: vi.fn(),
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

function registry(overrides: Partial<ToolRegistryResponse> = {}): ToolRegistryResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    project_id: "proj_1",
    agent_id: "agent_profile_inventory",
    action_type: "custom",
    runtime_paths: [
      {
        id: "sdk",
        kind: "runtime_path",
        label: "SDK",
        description: "Thin SDK wrapper.",
        category: "runtime",
        phase: "phase1",
        implementation_status: "available",
        launch_tier: "p0",
        supported_action_types: ["custom"],
        recommended_for_action_types: ["custom"],
        requires_customer_credentials: false,
        dashboard_href: "/agents/setup",
        backend_capability: "agent_profile.runtime_path",
        availability_notes: null,
      },
    ],
    verification_connectors: [
      {
        id: "generic_rest",
        kind: "verification_connector",
        label: "Generic REST",
        description: "Read source-of-record state over REST.",
        category: "verification",
        phase: "phase1",
        implementation_status: "template",
        launch_tier: "p0",
        supported_action_types: ["custom"],
        recommended_for_action_types: ["custom"],
        requires_customer_credentials: true,
        dashboard_href: "/integrations",
        backend_capability: "verification.generic_rest",
        availability_notes: null,
      },
    ],
    native_tool_families: [],
    recommended: {
      action_types: ["custom"],
      runtime_path_ids: ["sdk"],
      verification_connector_ids: ["generic_rest"],
      native_tool_family_ids: [],
      next_steps: ["Connect a generic REST verifier."],
    },
    ...overrides,
  };
}

function mockDetail() {
  api.getAgentProfile.mockResolvedValue(profile());
  api.listActionIntents.mockResolvedValue({
    items: [intent()],
    total_in_page: 1,
    limit: 200,
    offset: 0,
  });
  api.listRuntimePolicyApprovals.mockResolvedValue({
    items: [decision()],
    total_in_page: 1,
  });
  api.listOutcomeReconciliations.mockResolvedValue({
    items: [outcome()],
    total_in_page: 1,
  });
  api.listActionRunners.mockResolvedValue({ items: [runner()] });
  api.listProjectActionExecutionAttempts.mockImplementation((query: { stale?: boolean }) => Promise.resolve({
    items: query?.stale ? [] : [attempt()],
  }));
  api.getToolRegistry.mockResolvedValue(registry());
}

describe("AgentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders read-only config summary, latest proof chain, runners, and tool plan", async () => {
    mockDetail();

    renderDetailPage();

    expect(await screen.findByRole("heading", { name: "Inventory Agent", level: 1 })).toBeInTheDocument();
    expect(api.listActionIntents).toHaveBeenCalledWith(
      { agent_id: "agent_profile_inventory", limit: 200 },
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

    const runners = screen.getByLabelText("Agent observed runners and attempts");
    expect(within(runners).getByText("Inventory runner")).toBeInTheDocument();

    const toolPlan = screen.getByLabelText("Agent tool plan");
    expect(await within(toolPlan).findByText("Generic REST")).toBeInTheDocument();
    expect(within(toolPlan).getByText("Connect a generic REST verifier.")).toBeInTheDocument();
    expect(within(toolPlan).getByRole("link", { name: "Open setup" }).getAttribute("href")).toBe(
      "/agents/setup?agentId=agent_profile_inventory",
    );
  });
});
