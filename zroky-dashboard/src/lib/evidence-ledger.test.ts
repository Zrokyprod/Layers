import { describe, expect, it } from "vitest";

import {
  buildEvidenceLedger,
  evidenceLedgerCounts,
  filterEvidenceLedger,
  resolveEvidenceLedgerDeepLink,
} from "./evidence-ledger";
import type {
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
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

describe("buildEvidenceLedger", () => {
  it("builds receipt-first rows and keeps digest separate from system reference", () => {
    const rows = buildEvidenceLedger({
      intents: [
        intent({ action_id: "act_missing", receipt_status: "missing", proof_status: "not_verified", idempotency_key: "idem_missing", intent_digest: "sha256:intent-missing", runtime_policy_decision_id: "decision_missing" }),
        intent(),
      ],
      decisions: [
        decision(),
        decision({ id: "decision_missing", trace_id: "trace_missing", call_id: "call_missing" }),
        decision({ id: "guard_decision", agent_name: "guard-agent", trace_id: "trace_guard", call_id: "call_guard", intended_action: { summary: "Send customer email" } }),
      ],
      outcomes: [
        outcome(),
        outcome({ id: "outcome_guard", runtime_policy_decision_id: "guard_decision", trace_id: "trace_guard", call_id: "call_guard", system_ref: "email_123" }),
      ],
    });

    expect(rows.map((row) => row.kind)).toEqual([
      "action_receipt",
      "action_receipt",
      "orphan_decision",
    ]);
    const ready = rows.find((row) => row.actionId === "act_ready");
    expect(ready).toMatchObject({
      status: "matched",
      statusLabel: "Matched",
      exportable: true,
      exportKind: "receipt",
      digest: "sha256:intent-ready",
      systemRef: "item_123",
      href: "/evidence?action_id=act_ready",
    });
    expect(ready?.systemRef).not.toBe(ready?.digest);
  });

  it("keeps guard-only runtime decisions as secondary Evidence Pack rows", () => {
    const rows = buildEvidenceLedger({
      intents: [],
      decisions: [
        decision({ id: "guard_decision", agent_name: "guard-agent", action_type: "email.send", tool_name: "send_email", intended_action: { summary: "Send customer email" } }),
      ],
      outcomes: [
        outcome({ id: "outcome_guard", runtime_policy_decision_id: "guard_decision", system_ref: "email_123", action_type: "email.send" }),
      ],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "orphan_decision",
      title: "Send customer email",
      agentName: "guard-agent",
      status: "matched",
      exportable: true,
      exportKind: "evidence_pack",
      sourceLabel: "Guard-only Evidence Pack",
      href: "/evidence?decision_id=guard_decision",
    });
  });

  it("keeps unlinked outcomes visible but non-exportable", () => {
    const rows = buildEvidenceLedger({
      intents: [],
      decisions: [],
      outcomes: [
        outcome({
          id: "outcome_unlinked",
          runtime_policy_decision_id: null,
          verdict: "not_verified",
          system_ref: "crm:CUS-1001",
          action_type: "customer_record.update",
        }),
      ],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "unlinked_outcome",
      status: "not_verified",
      tone: "warning",
      systemRef: "crm:CUS-1001",
      exportable: false,
      exportKind: null,
      detail: "Not linked to an action intent in this evidence window",
    });
  });

  it("classifies counts and filters with one status vocabulary", () => {
    const rows = buildEvidenceLedger({
      intents: [
        intent(),
        intent({ action_id: "act_unverified", proof_status: "not_verified", receipt_status: "generated", idempotency_key: "idem_unverified", runtime_policy_decision_id: "decision_unverified" }),
        intent({ action_id: "act_mismatch", proof_status: "mismatched", receipt_status: "generated", idempotency_key: "idem_mismatch", runtime_policy_decision_id: "decision_mismatch" }),
      ],
      decisions: [
        decision(),
        decision({ id: "decision_unverified" }),
        decision({ id: "decision_mismatch" }),
      ],
      outcomes: [
        outcome(),
        outcome({ id: "outcome_mismatch", runtime_policy_decision_id: "decision_mismatch", idempotency_key: "idem_mismatch", verdict: "mismatched" }),
      ],
    });

    expect(evidenceLedgerCounts(rows)).toEqual({
      exportReady: 1,
      needsVerification: 1,
      exceptions: 1,
      total: 3,
    });
    expect(filterEvidenceLedger(rows, "matched").map((row) => row.actionId)).toEqual(["act_ready"]);
    expect(filterEvidenceLedger(rows, "needs_verification").map((row) => row.actionId)).toEqual(["act_unverified"]);
    expect(filterEvidenceLedger(rows, "exceptions").map((row) => row.actionId)).toEqual(["act_mismatch"]);
  });

  it("resolves action, decision, trace, and call deep links to ledger rows", () => {
    const rows = buildEvidenceLedger({
      intents: [intent()],
      decisions: [
        decision(),
        decision({ id: "guard_decision", trace_id: "trace_guard", call_id: "call_guard", intended_action: { summary: "Guard action" } }),
      ],
      outcomes: [
        outcome(),
        outcome({ id: "outcome_guard", runtime_policy_decision_id: "guard_decision", trace_id: "trace_guard", call_id: "call_guard" }),
      ],
    });

    expect(resolveEvidenceLedgerDeepLink(rows, { actionId: "act_ready" })?.actionId).toBe("act_ready");
    expect(resolveEvidenceLedgerDeepLink(rows, { decisionId: "guard_decision" })?.decisionId).toBe("guard_decision");
    expect(resolveEvidenceLedgerDeepLink(rows, { traceId: "trace_guard" })?.decisionId).toBe("guard_decision");
    expect(resolveEvidenceLedgerDeepLink(rows, { callId: "call_ready" })?.actionId).toBe("act_ready");
  });
});
