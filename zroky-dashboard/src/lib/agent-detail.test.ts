import { describe, expect, it } from "vitest";

import { buildAgentDetail } from "./agent-detail";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  ToolRegistryResponse,
} from "./api";

const now = "2026-06-28T10:00:00Z";

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_profile_inventory",
    project_id: "proj_123",
    display_name: "Inventory Agent",
    slug: "inventory-agent",
    description: "Controls inventory actions.",
    runtime_path: "sdk",
    framework: "langgraph",
    environment: "production",
    model_provider: "openai",
    model_name: "gpt-4.1",
    tool_names: ["inventory.item.delete"],
    allowed_action_types: ["custom"],
    blocked_action_types: [],
    default_policy_id: "policy_123",
    risk_limits: { max_items: 1 },
    verification_connectors: ["generic_rest"],
    metadata: { agent_name: "inventory-agent" },
    is_active: true,
    created_at: "2026-06-28T09:00:00Z",
    updated_at: now,
    ...overrides,
  };
}

function decision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_inventory",
    project_id: "proj_123",
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
    project_id: "proj_123",
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
    project_id: "proj_123",
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
    project_id: "proj_123",
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
    project_id: "proj_123",
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

function toolRegistry(overrides: Partial<ToolRegistryResponse> = {}): ToolRegistryResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    project_id: "proj_123",
    agent_id: "agent_profile_inventory",
    action_type: "inventory.item.delete",
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
    native_tool_families: [
      {
        id: "internal_api",
        kind: "native_tool_family",
        label: "Internal API",
        description: "Action contract templates for internal APIs.",
        category: "native_tool",
        phase: "phase1",
        implementation_status: "planned",
        launch_tier: "p2",
        supported_action_types: ["custom"],
        recommended_for_action_types: [],
        requires_customer_credentials: false,
        dashboard_href: null,
        backend_capability: null,
        availability_notes: null,
      },
    ],
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

describe("agent detail foundation", () => {
  it("builds a focused profile detail view with linked proof, runners, and attempts", () => {
    const view = buildAgentDetail({
      profile: profile(),
      intents: [intent()],
      decisions: [decision()],
      outcomes: [outcome()],
      runners: [runner(), runner({ runner_id: "runner_unmatched", supported_operation_kinds: ["UPDATE"] })],
      attempts: [attempt()],
      staleAttemptIds: [],
    });

    expect(view.row.kind).toBe("profile");
    expect(view.row.actionRollup.receiptsGenerated).toBe(1);
    expect(view.latestAction?.actionId).toBe("act_inventory");
    expect(view.proofChain.map((step) => step.step)).toEqual([
      "action",
      "policy",
      "execution",
      "verification",
      "receipt",
    ]);
    expect(view.runners.map((item) => item.runner_id)).toEqual(["runner_inventory"]);
    expect(view.attemptSummary.total).toBe(1);
  });

  it("preserves editable profile configuration", () => {
    const view = buildAgentDetail({ profile: profile() });

    expect(view.config).toMatchObject({
      displayName: "Inventory Agent",
      runtimePath: "sdk",
      framework: "langgraph",
      environment: "production",
      defaultPolicyId: "policy_123",
      toolNames: ["inventory.item.delete"],
      allowedActionTypes: ["custom"],
      verificationConnectors: ["generic_rest"],
      riskLimits: { max_items: 1 },
      metadata: { agent_name: "inventory-agent" },
    });
  });

  it("extracts the tool registry into recommended setup groups", () => {
    const view = buildAgentDetail({
      profile: profile(),
      toolRegistry: toolRegistry(),
    });

    expect(view.toolPlan?.summary).toEqual({
      available: 1,
      template: 1,
      planned: 1,
      recommended: 2,
    });
    expect(view.toolPlan?.groups[0]?.items[0]).toMatchObject({
      id: "sdk",
      recommended: true,
      status: "available",
    });
    expect(view.toolPlan?.nextSteps).toEqual(["Connect a generic REST verifier."]);
  });

  it("keeps the latest action as the newest activity for the profile", () => {
    const older = intent({
      action_id: "act_older",
      idempotency_key: "idem_older",
      authorized_at: "2026-06-28T09:00:00Z",
      runtime_policy_decision_id: "decision_older",
    });
    const newer = intent({
      action_id: "act_newer",
      idempotency_key: "idem_newer",
      authorized_at: "2026-06-28T10:30:00Z",
      runtime_policy_decision_id: "decision_newer",
    });

    const view = buildAgentDetail({
      profile: profile(),
      intents: [older, newer],
      decisions: [
        decision({ id: "decision_older" }),
        decision({ id: "decision_newer" }),
      ],
    });

    expect(view.latestAction?.actionId).toBe("act_newer");
  });
});
