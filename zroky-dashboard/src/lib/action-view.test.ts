import { describe, expect, it } from "vitest";

import { buildActionView, buildGuardOnlyProofChain, buildProofChain } from "./action-view";
import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionReceiptResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "./api";

function intent(overrides: Partial<ActionIntentResponse> = {}): ActionIntentResponse {
  return {
    action_id: "act_123",
    project_id: "proj_123",
    contract_version: "inventory.item.update/1.0",
    action_type: "inventory.item.update",
    operation_kind: "UPDATE",
    environment: "production",
    status: "authorized",
    proof_status: "matched",
    receipt_status: "generated",
    idempotency_key: "idem_123",
    intent_digest: "sha256:abc",
    canonical_intent: {
      principal: { id: "inventory-agent" },
      purpose: { summary: "Update inventory item" },
      resource: { id: "item_123" },
      trace_context: { agent_name: "trace-agent" },
    },
    created_at: "2026-06-28T10:00:00Z",
    decided_at: "2026-06-28T10:01:00Z",
    authorized_at: "2026-06-28T10:02:00Z",
    runtime_policy_decision_id: "decision_allowed",
    deadline: null,
    status_url: "/v1/action-intents/act_123",
    ...overrides,
  };
}

function decision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_allowed",
    project_id: "proj_123",
    trace_id: "trace_123",
    call_id: null,
    agent_name: "inventory-agent",
    role: "agent",
    action_type: "inventory.item.update",
    tool_name: "inventory.item.update",
    decision: "allow",
    status: "allowed",
    allowed: true,
    requires_approval: false,
    reasons: ["human approval accepted"],
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
    id: "outcome_123",
    project_id: "proj_123",
    call_id: null,
    trace_id: "trace_123",
    runtime_policy_decision_id: "decision_allowed",
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
    idempotency_key: "idem_123",
    metadata: {},
    checked_at: "2026-06-28T10:03:00Z",
    created_at: "2026-06-28T10:03:00Z",
    ...overrides,
  };
}

function receipt(overrides: Partial<ActionReceiptResponse> = {}): ActionReceiptResponse {
  return {
    receipt_id: "receipt_123",
    project_id: "proj_123",
    action_id: "act_123",
    receipt_digest: "sha256:receipt",
    evidence_hash: "sha256:evidence",
    signature_algorithm: "Ed25519",
    signature: "sig",
    signing_key_id: "local",
    signature_valid: true,
    generated_at: "2026-06-28T10:04:00Z",
    receipt: { final_status: "matched" },
    ...overrides,
  };
}

function attempt(overrides: Partial<ActionExecutionAttemptResponse> = {}): ActionExecutionAttemptResponse {
  return {
    attempt_id: "attempt_123",
    project_id: "proj_123",
    action_id: "act_123",
    runner_id: "runner_123",
    attempt_number: 1,
    status: "succeeded",
    idempotency_key: "idem_123",
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

describe("buildActionView", () => {
  it("builds an intent-first view with linked decision, outcome, and receipt", () => {
    const view = buildActionView(intent(), {
      decisions: [decision()],
      outcomes: [outcome()],
      receipt: receipt(),
    });

    expect(view.title).toBe("Update inventory item");
    expect(view.agentName).toBe("trace-agent");
    expect(view.statusLabel).toBe("Authorized");
    expect(view.proofLabel).toBe("Matched");
    expect(view.receiptLabel).toBe("Generated");
    expect(view.lifecycle.id).toBe("receipted");
    expect(view.decision?.id).toBe("decision_allowed");
    expect(view.outcome?.id).toBe("outcome_123");
    expect(view.signatureValid).toBe(true);
    expect(view.systemRef).toBe("item_123");
  });

  it("uses idempotency-linked outcomes when no decision link exists", () => {
    const view = buildActionView(
      intent({ runtime_policy_decision_id: null, proof_status: "not_verified", receipt_status: "generated" }),
      {
        outcomes: [outcome({ runtime_policy_decision_id: null, verdict: "not_verified" })],
      },
    );

    expect(view.outcome?.id).toBe("outcome_123");
    expect(view.proofTone).toBe("warning");
    expect(view.lifecycle.id).toBe("receipted");
  });

  it("builds a normalized proof chain from an action view", () => {
    const view = buildActionView(intent(), {
      decisions: [decision()],
      outcomes: [outcome()],
      receipt: receipt(),
    });
    const chain = buildProofChain(view, { attempt: attempt() });

    expect(chain.map((step) => step.step)).toEqual([
      "action",
      "policy",
      "execution",
      "verification",
      "receipt",
    ]);
    expect(chain.map((step) => step.tone)).toEqual([
      "success",
      "success",
      "success",
      "success",
      "success",
    ]);
    expect(chain.find((step) => step.step === "execution")?.status).toBe("Succeeded");
  });

  it("builds an honest partial proof chain for guard-only decisions", () => {
    const chain = buildGuardOnlyProofChain(
      decision({ id: "guard_decision", status: "approved" }),
      outcome({ runtime_policy_decision_id: "guard_decision", verdict: "not_verified" }),
    );

    expect(chain.find((step) => step.step === "action")).toMatchObject({
      status: "Guard-only",
      tone: "neutral",
    });
    expect(chain.find((step) => step.step === "execution")).toMatchObject({
      status: "Not via kernel",
      tone: "neutral",
    });
    expect(chain.find((step) => step.step === "verification")).toMatchObject({
      status: "Not verified",
      tone: "warning",
    });
    expect(chain.find((step) => step.step === "receipt")?.status).toBe("Not via kernel");
  });
});
