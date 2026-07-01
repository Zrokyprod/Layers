import { describe, expect, it } from "vitest";

import { buildDecisionQueue, homeVerdictForQueue, queueCounts } from "./home-queue";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "./api";

const now = new Date("2026-06-28T12:00:00Z").getTime();

function intent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_123",
    project_id: "proj_123",
    contract_version: "inventory.item.update/1.0",
    action_type: "inventory.item.update",
    operation_kind: "UPDATE",
    environment: "production",
    status: "authorized",
    proof_status: "pending",
    receipt_status: "pending",
    idempotency_key: "idem_123",
    intent_digest: "sha256:abc",
    canonical_intent: {
      principal: { id: "inventory-agent" },
      purpose: { summary: "Update inventory item" },
      resource: { id: "item_123" },
    },
    created_at: "2026-06-28T10:00:00Z",
    decided_at: "2026-06-28T10:01:00Z",
    authorized_at: "2026-06-28T10:02:00Z",
    runtime_policy_decision_id: "decision_123",
    deadline: null,
    status_url: "/v1/action-intents/act_123",
    ...overrides,
  };
}

function approval(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_123",
    project_id: "proj_123",
    trace_id: "trace_123",
    call_id: null,
    agent_name: "inventory-agent",
    role: "agent",
    action_type: "inventory.item.update",
    tool_name: "inventory.item.update",
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["sensitive action requires human approval"],
    request: {},
    policy_snapshot: {},
    intended_action: { summary: "Update inventory item" },
    trace_context: {},
    policy_hit: {},
    business_impact: {},
    audit_log: [],
    created_at: "2026-06-28T10:01:00Z",
    expires_at: "2026-06-28T13:00:00Z",
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    consumed_at: null,
    consumed_by_decision_id: null,
    ...overrides,
  };
}

function outcome(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "outcome_123",
    project_id: "proj_123",
    call_id: null,
    trace_id: "trace_123",
    runtime_policy_decision_id: "decision_mismatch",
    action_type: "inventory.item.update",
    connector_type: "generic_rest_api",
    system_ref: "item_123",
    verdict: "mismatched",
    reason: "field mismatch",
    amount_usd: null,
    currency: null,
    claimed: {},
    actual: {},
    comparison: {},
    idempotency_key: "idem_123",
    metadata: {},
    checked_at: "2026-06-28T11:30:00Z",
    created_at: "2026-06-28T11:30:00Z",
    ...overrides,
  };
}

function mutation(overrides: Partial<SourceMutationView> = {}): SourceMutationView {
  return {
    id: "mutation_123",
    project_id: "proj_123",
    source_system: "stripe",
    mutation_id: "mut_123",
    action_type: "refund",
    resource_type: "refund",
    resource_id: "rf_123",
    system_ref: "rf_123",
    actor_type: "agent",
    actor_id: "refund-agent",
    zroky_action_id: null,
    action_receipt_id: null,
    idempotency_key: null,
    classification: "policy_bypass",
    metadata: {},
    occurred_at: "2026-06-28T11:45:00Z",
    created_at: "2026-06-28T11:45:00Z",
    ...overrides,
  };
}

function attempt(overrides: Partial<ActionExecutionAttemptResponse> = {}): ActionExecutionAttemptResponse {
  return {
    attempt_id: "attempt_123",
    project_id: "proj_123",
    action_id: "act_stale",
    runner_id: "runner_123",
    attempt_number: 1,
    status: "planned",
    idempotency_key: "attempt_idem",
    credential_ref: "customer-runner-secret://ops/default",
    plan_digest: "sha256:plan",
    execution_plan: {},
    result_summary: {},
    error_message: null,
    protected_credential_returned: false,
    requested_by_subject: null,
    started_at: null,
    finished_at: null,
    created_at: "2026-06-28T10:00:00Z",
    updated_at: "2026-06-28T10:00:00Z",
    ...overrides,
  };
}

describe("buildDecisionQueue", () => {
  it("prioritizes mismatches and policy bypass ahead of approvals", () => {
    const rows = buildDecisionQueue({
      intents: [
        intent({ action_id: "act_mismatch", runtime_policy_decision_id: "decision_mismatch" }),
        intent({ action_id: "act_approval", runtime_policy_decision_id: "decision_123" }),
      ],
      approvals: [approval({ business_impact: { estimated_value_usd: 1260 } })],
      outcomes: [outcome()],
      mutations: [mutation()],
      staleAttempts: [],
      nowMs: now,
    });

    expect(rows.map((row) => row.kind)).toEqual(["mismatch", "bypass", "approval"]);
    expect(rows.map((row) => row.priority)).toEqual(["P0", "P0", "P0"]);
  });

  it("keeps guard-only runtime approvals visible as secondary queue rows", () => {
    const rows = buildDecisionQueue({
      intents: [],
      approvals: [approval({ id: "guard_decision", tool_name: "send_email", action_type: "email.send" })],
      outcomes: [],
      mutations: [],
      staleAttempts: [],
      nowMs: now,
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "guard_approval",
      priority: "P1",
      href: "/approvals?decision_id=guard_decision",
    });
  });

  it("dedupes stale attempts when the action already has a higher-priority row", () => {
    const rows = buildDecisionQueue({
      intents: [intent({ action_id: "act_123", proof_status: "not_verified" })],
      approvals: [],
      outcomes: [],
      mutations: [],
      staleAttempts: [attempt({ action_id: "act_123" })],
      nowMs: now,
    });

    expect(rows.map((row) => row.kind)).toEqual(["not_verified"]);
  });

  it("adds stale unclaimed attempts as P2", () => {
    const rows = buildDecisionQueue({
      intents: [intent({ action_id: "act_stale", runtime_policy_decision_id: null })],
      approvals: [],
      outcomes: [],
      mutations: [],
      staleAttempts: [attempt()],
      nowMs: now,
    });

    expect(rows[0]).toMatchObject({
      kind: "stale_attempt",
      priority: "P2",
      reason: "No runner claimed execution",
    });
  });
});

describe("home queue summary helpers", () => {
  it("builds verdict and counts", () => {
    const rows = buildDecisionQueue({
      intents: [],
      approvals: [],
      outcomes: [],
      mutations: [mutation()],
      staleAttempts: [],
      nowMs: now,
    });

    expect(homeVerdictForQueue(rows, true)).toMatchObject({
      title: "Action blocked / bypass risk",
      tone: "danger",
    });
    expect(queueCounts(rows)).toEqual({ all: 1, needsDecision: 0, bypass: 1 });
    expect(homeVerdictForQueue([], false).title).toBe("Setup required");
  });
});
