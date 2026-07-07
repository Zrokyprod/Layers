import { describe, expect, it } from "vitest";

import { buildFleetView } from "./agent-fleet";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "./api";

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_profile_inventory",
    project_id: "proj_123",
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
    created_at: "2026-06-28T09:00:00Z",
    updated_at: "2026-06-28T09:05:00Z",
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
    intended_action: { summary: "Delete inventory item" },
    trace_context: {},
    policy_hit: {},
    business_impact: {},
    audit_log: [],
    created_at: "2026-06-28T10:01:00Z",
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
      purpose: { summary: "Delete inventory item" },
      resource: { id: "item_123" },
      trace_context: {
        agent_name: "inventory-agent",
        trace_id: "trace_inventory",
        call_id: "call_inventory",
      },
    },
    created_at: "2026-06-28T10:00:00Z",
    decided_at: "2026-06-28T10:01:00Z",
    authorized_at: "2026-06-28T10:02:00Z",
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
    checked_at: "2026-06-28T10:03:00Z",
    created_at: "2026-06-28T10:03:00Z",
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
    last_heartbeat_at: "2026-06-28T10:04:00Z",
    created_at: "2026-06-28T09:30:00Z",
    updated_at: "2026-06-28T10:04:00Z",
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
    started_at: "2026-06-28T10:02:00Z",
    finished_at: "2026-06-28T10:03:00Z",
    created_at: "2026-06-28T10:02:00Z",
    updated_at: "2026-06-28T10:03:00Z",
    ...overrides,
  };
}

describe("agent fleet foundation", () => {
  it("uses profile list metadata for single/fleet mode and the plan meter", () => {
    const single = buildFleetView({
      profiles: [profile()],
      profileMeta: {
        active_count: 1,
        max_active_agents: 1,
        limit_reached: true,
      },
    });

    expect(single.mode).toBe("single");
    expect(single.meter).toEqual({ active: 1, cap: 1, reached: true });

    const fleet = buildFleetView({
      profiles: [
        profile(),
        profile({
          id: "agent_profile_support",
          display_name: "Support Agent",
          slug: "support-agent",
        }),
      ],
      profileMeta: {
        active_count: 2,
        max_active_agents: 3,
        limit_reached: false,
      },
    });

    expect(fleet.mode).toBe("fleet");
    expect(fleet.meter).toEqual({ active: 2, cap: 3, reached: false });
  });

  it("rolls action intents into profile rows with honest status tones", () => {
    const mismatchIntent = intent({
      action_id: "act_mismatch",
      idempotency_key: "idem_mismatch",
      proof_status: "mismatched",
      receipt_status: "generated",
      runtime_policy_decision_id: "decision_mismatch",
      canonical_intent: {
        principal: { id: "inventory-agent" },
        purpose: { summary: "Delete another inventory item" },
        resource: { id: "item_456" },
        trace_context: { agent_name: "inventory-agent" },
      },
    });
    const view = buildFleetView({
      profiles: [profile()],
      intents: [intent(), mismatchIntent],
      decisions: [decision(), decision({ id: "decision_mismatch" })],
      outcomes: [
        outcome(),
        outcome({
          id: "outcome_mismatch",
          runtime_policy_decision_id: "decision_mismatch",
          idempotency_key: "idem_mismatch",
          verdict: "mismatched",
        }),
      ],
    });

    const row = view.rows.find((item) => item.profile?.slug === "inventory-agent");
    expect(row).toMatchObject({
      kind: "profile",
      status: "mismatched",
      tone: "danger",
      actionRollup: {
        total: 2,
        matched: 1,
        mismatched: 1,
        receiptsGenerated: 2,
      },
    });
    expect(view.totals).toMatchObject({ mismatched: 1, receiptReady: 2 });
  });

  it("does not attach name-matched telemetry to managed profiles without an agent id", () => {
    const view = buildFleetView({
      profiles: [profile()],
      intents: [
        intent({
          action_id: "act_unmanaged_name_match",
          agent_id: null,
          agent_profile: null,
          canonical_intent: {
            principal: { id: "inventory-agent" },
            purpose: { summary: "Legacy inventory update" },
            resource: { id: "item_legacy" },
            trace_context: { agent_name: "inventory-agent" },
          },
        }),
      ],
    });

    const managed = view.rows.find((row) => row.id === "profile:agent_profile_inventory");
    const telemetry = view.rows.find((row) => row.kind === "telemetry");
    expect(managed?.actionRollup.total).toBe(0);
    expect(telemetry).toMatchObject({
      kind: "telemetry",
      agentName: "inventory-agent",
      actionRollup: { total: 1 },
    });
  });

  it("sorts each agent's action rows by newest activity first", () => {
    const olderIntent = intent({
      action_id: "act_older",
      idempotency_key: "idem_older",
      created_at: "2026-06-28T09:10:00Z",
      authorized_at: "2026-06-28T09:12:00Z",
      runtime_policy_decision_id: "decision_older",
    });
    const newerIntent = intent({
      action_id: "act_newer",
      idempotency_key: "idem_newer",
      created_at: "2026-06-28T10:10:00Z",
      authorized_at: "2026-06-28T10:12:00Z",
      runtime_policy_decision_id: "decision_newer",
    });

    const view = buildFleetView({
      profiles: [profile()],
      intents: [olderIntent, newerIntent],
      decisions: [
        decision({ id: "decision_older" }),
        decision({ id: "decision_newer" }),
      ],
    });

    const row = view.rows.find((item) => item.profile?.slug === "inventory-agent");
    expect(row?.actionRows.map((actionRow) => actionRow.actionId)).toEqual([
      "act_newer",
      "act_older",
    ]);
  });

  it("keeps unprofiled telemetry visible as secondary rows", () => {
    const view = buildFleetView({
      profiles: [profile()],
      intents: [
        intent({
          action_id: "act_unprofiled",
          agent_id: null,
          agent_profile: null,
          runtime_policy_decision_id: "decision_unprofiled",
          canonical_intent: {
            principal: { id: "shadow-agent" },
            purpose: { summary: "Update shadow record" },
            resource: { id: "shadow_1" },
            trace_context: { agent_name: "shadow-agent" },
          },
        }),
      ],
      decisions: [decision({ id: "decision_unprofiled", agent_name: "shadow-agent" })],
    });

    const telemetryRow = view.rows.find((row) => row.kind === "telemetry");
    expect(telemetryRow).toMatchObject({
      agentName: "shadow-agent",
      profile: null,
      actionRollup: { total: 1 },
    });
    expect(view.totals.telemetryOnly).toBe(1);
  });

  it("summarizes runners and attempts without inventing per-agent links", () => {
    const view = buildFleetView({
      profiles: [profile()],
      intents: [intent()],
      decisions: [decision()],
      outcomes: [outcome()],
      runners: [
        runner(),
        runner({ runner_id: "runner_slow", status: "degraded", supported_operation_kinds: ["DELETE"] }),
        runner({ runner_id: "runner_offline", status: "offline", supported_operation_kinds: ["UPDATE"] }),
      ],
      attempts: [
        attempt({ status: "planned", attempt_id: "attempt_claimable" }),
        attempt({ status: "running", attempt_id: "attempt_running" }),
      ],
      staleAttemptIds: ["attempt_running"],
    });

    expect(view.runners).toEqual({
      total: 3,
      online: 1,
      degraded: 1,
      offline: 1,
      disabled: 0,
      other: 0,
    });
    expect(view.attempts).toMatchObject({
      total: 2,
      claimable: 1,
      running: 1,
      stalled: 1,
    });

    const inventoryRow = view.rows.find((row) => row.profile?.slug === "inventory-agent");
    expect(inventoryRow?.runnerCount).toBe(2);
    expect(inventoryRow?.attemptSummary).toMatchObject({
      total: 2,
      claimable: 1,
      running: 1,
      stalled: 1,
    });
  });
});
