import { describe, expect, it } from "vitest";

import {
  actionLifecycleCounts,
  buildActionLifecycle,
  filterActionLifecycle,
} from "./action-lifecycle";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "./api";

function intent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_ready",
    project_id: "proj_123",
    contract_version: "inventory.item.update/1.0",
    action_type: "inventory.item.update",
    operation_kind: "UPDATE",
    environment: "production",
    status: "authorized",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "idem_ready",
    intent_digest: "sha256:intent-ready",
    canonical_intent: {
      principal: { id: "inventory-agent" },
      purpose: { summary: "Update inventory item" },
      resource: { id: "item_123" },
      trace_context: { agent_name: "inventory-agent", trace_id: "trace_ready", call_id: "call_ready" },
    },
    created_at: "2026-06-28T10:00:00Z",
    decided_at: "2026-06-28T10:01:00Z",
    authorized_at: "2026-06-28T10:02:00Z",
    runtime_policy_decision_id: "decision_ready",
    deadline: null,
    status_url: "/v1/action-intents/act_ready",
    ...overrides,
  };
}

function decision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_ready",
    project_id: "proj_123",
    trace_id: "trace_ready",
    call_id: "call_ready",
    agent_name: "inventory-agent",
    role: "agent",
    action_type: "inventory.item.update",
    tool_name: "inventory.item.update",
    decision: "allow",
    status: "allowed",
    allowed: true,
    requires_approval: false,
    reasons: ["runtime policy checks passed"],
    request: {},
    policy_snapshot: {},
    intended_action: { summary: "Update inventory item" },
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

function outcome(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "outcome_ready",
    project_id: "proj_123",
    call_id: "call_ready",
    trace_id: "trace_ready",
    runtime_policy_decision_id: "decision_ready",
    action_type: "inventory.item.update",
    connector_type: "generic_rest_api",
    system_ref: "item_123",
    verdict: "matched",
    reason: "matched",
    amount_usd: null,
    currency: null,
    claimed: { status: "active" },
    actual: { status: "active" },
    comparison: { status: true },
    idempotency_key: "idem_ready",
    metadata: {},
    checked_at: "2026-06-28T10:03:00Z",
    created_at: "2026-06-28T10:03:00Z",
    ...overrides,
  };
}

function attempt(overrides: Partial<ActionExecutionAttemptResponse> = {}): ActionExecutionAttemptResponse {
  return {
    attempt_id: "attempt_ready",
    project_id: "proj_123",
    action_id: "act_ready",
    runner_id: "runner_inventory",
    attempt_number: 1,
    status: "succeeded",
    idempotency_key: "idem_ready",
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

function mutation(overrides: Partial<SourceMutationView> = {}): SourceMutationView {
  return {
    id: "mutation_123",
    project_id: "proj_123",
    source_system: "generic_rest",
    mutation_id: "mut_123",
    action_type: "inventory.item.update",
    resource_type: "inventory_item",
    resource_id: "item_123",
    system_ref: "item_123",
    actor_type: "agent",
    actor_id: "inventory-agent",
    zroky_action_id: null,
    action_receipt_id: null,
    idempotency_key: null,
    classification: "policy_bypass",
    metadata: {},
    occurred_at: "2026-06-28T10:04:00Z",
    created_at: "2026-06-28T10:04:00Z",
    ...overrides,
  };
}

describe("buildActionLifecycle", () => {
  it("keeps action intents primary and dedupes linked runtime decisions", () => {
    const rows = buildActionLifecycle({
      intents: [intent()],
      decisions: [decision()],
      outcomes: [outcome()],
      mutations: [mutation()],
    });

    const actionRow = rows.find((row) => row.kind === "action_intent");
    const bypassRow = rows.find((row) => row.kind === "bypass_mutation");

    expect(rows).toHaveLength(2);
    expect(actionRow).toMatchObject({
      kind: "action_intent",
      actionId: "act_ready",
      decisionId: "decision_ready",
      outcomeId: "outcome_ready",
      digest: "sha256:intent-ready",
      systemRef: "item_123",
      status: "matched",
      sourceLabel: "Action Intent",
    });
    expect(actionRow?.proofChain.map((step) => step.step)).toEqual([
      "action",
      "policy",
      "execution",
      "verification",
      "receipt",
    ]);
    expect(bypassRow).toMatchObject({
      kind: "bypass_mutation",
      status: "policy_bypass",
      stage: { id: "bypassed", tone: "danger" },
      receiptStatus: "missing",
      bypassDetail: {
        title: "Control bypass detected",
      },
    });
  });

  it("keeps guard-only decisions visible as secondary partial chains", () => {
    const rows = buildActionLifecycle({
      intents: [],
      decisions: [
        decision({
          id: "guard_decision",
          agent_name: "guard-agent",
          trace_id: "trace_guard",
          call_id: "call_guard",
          intended_action: { summary: "Send customer email" },
        }),
      ],
      outcomes: [
        outcome({
          id: "outcome_guard",
          runtime_policy_decision_id: "guard_decision",
          trace_id: "trace_guard",
          call_id: "call_guard",
          verdict: "not_verified",
          system_ref: "email_123",
        }),
      ],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "orphan_decision",
      actionId: null,
      decisionId: "guard_decision",
      stage: { id: "guard_only" },
      digest: null,
      status: "not_verified",
      sourceLabel: "Guard-only Decision",
    });
    expect(rows[0].proofChain.find((step) => step.step === "execution")).toMatchObject({
      status: "Not via kernel",
      tone: "neutral",
    });
    expect(rows[0].proofChain.find((step) => step.step === "receipt")?.status).toBe("Not via kernel");
  });

  it("treats policy-denied actions as stopped before execution", () => {
    const rows = buildActionLifecycle({
      intents: [
        intent({
          status: "denied",
          proof_status: "not_started",
          receipt_status: "missing",
        }),
      ],
      decisions: [decision({ status: "blocked", decision: "block", allowed: false })],
      outcomes: [],
    });

    expect(rows[0]).toMatchObject({
      stage: { id: "blocked" },
      proofStatus: "not_required",
      proofLabel: "Not required",
      receiptStatus: "evidence_only",
      receiptLabel: "Evidence only",
    });
    expect(rows[0].proofChain.find((step) => step.step === "execution")?.status).toBe("Prevented");
    expect(rows[0].proofChain.find((step) => step.step === "verification")?.status).toBe("Not required");
    expect(rows[0].proofChain.find((step) => step.step === "receipt")?.status).toBe("Evidence only");
    expect(filterActionLifecycle(rows, "stopped")).toHaveLength(1);
    expect(filterActionLifecycle(rows, "needs_action")).toHaveLength(0);
  });

  it("dedupes approval decisions consumed by an action's final release decision", () => {
    const rows = buildActionLifecycle({
      intents: [intent({ runtime_policy_decision_id: "decision_release" })],
      decisions: [
        decision({ id: "decision_release", status: "allowed" }),
        decision({
          id: "decision_approval",
          status: "approved",
          consumed_by_decision_id: "decision_release",
        }),
      ],
      outcomes: [],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "action_intent", decisionId: "decision_release" });
  });

  it("uses fresh runner attempts for the current execution stage", () => {
    const rows = buildActionLifecycle({
      intents: [intent({ proof_status: "not_started", receipt_status: "missing" })],
      decisions: [decision()],
      outcomes: [],
      attempts: [attempt({ status: "running" })],
      staleAttemptIds: [],
    });

    expect(rows[0]).toMatchObject({
      attemptId: "attempt_ready",
      stage: { id: "execution", label: "Runner executing" },
    });
    expect(actionLifecycleCounts(rows)).toMatchObject({ executing: 1, awaitingRunner: 0 });
    expect(filterActionLifecycle(rows, "in_progress")).toHaveLength(1);
  });

  it("uses one lifecycle row for stale attempts instead of creating attempt sibling rows", () => {
    const rows = buildActionLifecycle({
      intents: [
        intent({
          action_id: "act_planned",
          idempotency_key: "idem_planned",
          runtime_policy_decision_id: "decision_planned",
          proof_status: "not_started",
          receipt_status: "missing",
          intent_digest: "sha256:planned",
        }),
        intent({
          action_id: "act_running",
          idempotency_key: "idem_running",
          runtime_policy_decision_id: "decision_running",
          proof_status: "pending",
          receipt_status: "pending",
          intent_digest: "sha256:running",
        }),
      ],
      decisions: [
        decision({ id: "decision_planned" }),
        decision({ id: "decision_running" }),
      ],
      outcomes: [],
      attempts: [
        attempt({
          attempt_id: "attempt_planned",
          action_id: "act_planned",
          status: "planned",
          updated_at: "2026-06-28T10:08:00Z",
        }),
        attempt({
          attempt_id: "attempt_running",
          action_id: "act_running",
          status: "running",
          updated_at: "2026-06-28T10:09:00Z",
        }),
      ],
      staleAttemptIds: ["attempt_planned", "attempt_running"],
    });

    expect(rows).toHaveLength(2);
    expect(rows.find((row) => row.actionId === "act_planned")).toMatchObject({
      attemptId: "attempt_planned",
      stage: { id: "no_runner", tone: "warning" },
    });
    expect(rows.find((row) => row.actionId === "act_running")).toMatchObject({
      attemptId: "attempt_running",
      stage: { id: "execution_stalled", tone: "danger" },
    });
  });

  it("classifies mismatched and not-verified actions with shared status vocabulary", () => {
    const rows = buildActionLifecycle({
      intents: [
        intent(),
        intent({
          action_id: "act_mismatch",
          idempotency_key: "idem_mismatch",
          runtime_policy_decision_id: "decision_mismatch",
          proof_status: "mismatched",
          receipt_status: "generated",
          intent_digest: "sha256:mismatch",
        }),
        intent({
          action_id: "act_unverified",
          idempotency_key: "idem_unverified",
          runtime_policy_decision_id: "decision_unverified",
          proof_status: "not_verified",
          receipt_status: "generated",
          intent_digest: "sha256:unverified",
        }),
      ],
      decisions: [
        decision(),
        decision({ id: "decision_mismatch" }),
        decision({ id: "decision_unverified" }),
      ],
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

    expect(rows.find((row) => row.actionId === "act_mismatch")).toMatchObject({
      status: "mismatched",
      statusTone: "danger",
      stage: { tone: "danger" },
    });
    expect(rows.find((row) => row.actionId === "act_unverified")).toMatchObject({
      status: "not_verified",
      statusTone: "warning",
      stage: { tone: "warning" },
    });
    expect(filterActionLifecycle(rows, "needs_action").map((row) => row.actionId)).toEqual([
      "act_mismatch",
      "act_unverified",
    ]);
    expect(filterActionLifecycle(rows, "completed").map((row) => row.actionId)).toEqual(["act_ready"]);
    expect(rows.find((row) => row.actionId === "act_mismatch")?.verificationIssue).toMatchObject({
      title: "Verification failed",
    });
    expect(actionLifecycleCounts(rows)).toMatchObject({
      protectedActions: 3,
      mismatched: 1,
      notVerified: 1,
    });
  });

  it("filters held and executing lifecycle stages", () => {
    const rows = buildActionLifecycle({
      intents: [
        intent({
          action_id: "act_held",
          status: "approval_pending",
          proof_status: "not_started",
          receipt_status: "missing",
          runtime_policy_decision_id: "decision_held",
          idempotency_key: "idem_held",
        }),
        intent({
          action_id: "act_executing",
          proof_status: "pending",
          receipt_status: "pending",
          runtime_policy_decision_id: "decision_executing",
          idempotency_key: "idem_executing",
        }),
      ],
      decisions: [
        decision({ id: "decision_held", status: "pending_approval", decision: "requires_approval", requires_approval: true, allowed: false }),
        decision({ id: "decision_executing" }),
      ],
      outcomes: [],
      attempts: [
        attempt({
          attempt_id: "attempt_executing",
          action_id: "act_executing",
          status: "running",
        }),
      ],
    });

    expect(filterActionLifecycle(rows, "needs_action").map((row) => row.actionId)).toEqual(["act_held"]);
    expect(filterActionLifecycle(rows, "in_progress").map((row) => row.actionId)).toEqual([
      "act_executing",
      "act_held",
    ]);
  });

  it("filters bypassed source mutations as first-class lifecycle rows", () => {
    const rows = buildActionLifecycle({
      intents: [],
      decisions: [],
      outcomes: [],
      mutations: [mutation()],
    });

    expect(filterActionLifecycle(rows, "bypassed").map((row) => row.id)).toEqual(["mutation:mutation_123"]);
    expect(actionLifecycleCounts(rows)).toMatchObject({
      bypassed: 1,
      protectedActions: 0,
    });
  });
});
