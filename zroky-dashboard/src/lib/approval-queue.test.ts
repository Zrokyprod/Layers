import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  approvalQueueCounts,
  buildApprovalQueue,
} from "./approval-queue";
import type {
  ActionIntentResponse,
  RuntimePolicyDecisionResponse,
} from "./api";

function decision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "Inventory agent",
    role: "agent",
    action_type: "inventory.item.delete",
    tool_name: "inventory.item.delete",
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["delete_requires_approval"],
    request: { item_id: "item_123" },
    policy_snapshot: {},
    intended_action: { summary: "Archive inventory item", item_id: "item_123" },
    trace_context: {},
    policy_hit: { risk_class: "destructive" },
    business_impact: {},
    audit_log: [],
    created_at: "2026-06-28T10:00:00Z",
    expires_at: "2026-06-28T10:30:00Z",
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
    action_id: "act_1",
    project_id: "proj_1",
    contract_version: "inventory.item.delete/1.0",
    action_type: "inventory.item.delete",
    operation_kind: "DELETE",
    environment: "production",
    status: "approval_pending",
    proof_status: "not_started",
    receipt_status: "missing",
    idempotency_key: "idem_1",
    intent_digest: "sha256:intent",
    canonical_intent: {
      principal: { id: "inventory-agent" },
      purpose: { summary: "Archive inventory item" },
      resource: { id: "item_123" },
      trace_context: { agent_name: "Inventory agent" },
    },
    created_at: "2026-06-28T10:00:00Z",
    decided_at: null,
    authorized_at: null,
    runtime_policy_decision_id: "decision_1",
    deadline: "2026-06-28T10:30:00Z",
    status_url: "/v1/action-intents/act_1",
    ...overrides,
  };
}

describe("buildApprovalQueue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-28T10:10:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("frames linked runtime-policy decisions as held action intents", () => {
    const rows = buildApprovalQueue({
      decisions: [decision()],
      intents: [intent()],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "action_intent_hold",
      decisionId: "decision_1",
      actionId: "act_1",
      title: "Archive inventory item",
      digest: "sha256:intent",
      status: "pending_approval",
      statusLabel: "Pending approval",
      proofStatus: "not_started",
      receiptStatus: "missing",
      holdReason: {
        title: "Held by runtime policy",
        detail: "Delete requires approval",
      },
      approvalAction: "DELETE: Archive inventory item on item_123",
      approverSubjects: [],
      requiredApprovalCount: 1,
      recordedApprovalCount: 0,
    });
    expect(rows[0].proofChain.map((step) => step.step)).toEqual([
      "action",
      "policy",
      "execution",
      "verification",
      "receipt",
    ]);
  });

  it("keeps guard-only decisions visible as secondary partial chains", () => {
    const rows = buildApprovalQueue({
      decisions: [
        decision({
          id: "guard_decision",
          agent_name: "Guard agent",
          intended_action: { summary: "Send customer email" },
          action_type: "email.send",
          tool_name: "email.send",
        }),
      ],
      intents: [],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "guard_only_hold",
      actionId: null,
      decisionId: "guard_decision",
      title: "Send customer email",
      digest: null,
      approvalProgress: "Approval required",
    });
    expect(rows[0].proofChain.find((step) => step.step === "execution")).toMatchObject({
      status: "Not via kernel",
      tone: "neutral",
    });
  });

  it("prioritizes expiring, sequence-risk, and money-touching holds without keyword guessing", () => {
    const rows = buildApprovalQueue({
      decisions: [
        decision({
          id: "normal_hold",
          intended_action: { summary: "Update CRM record" },
          action_type: "customer_record.update",
          expires_at: "2026-06-28T10:40:00Z",
        }),
        decision({
          id: "money_hold",
          intended_action: { summary: "Credit account" },
          action_type: "account.credit",
          business_impact: { amount_usd: 1200 },
          expires_at: "2026-06-28T11:00:00Z",
        }),
        decision({
          id: "sequence_hold",
          intended_action: { summary: "Send exported customer file" },
          action_type: "customer.email.send",
          policy_hit: {
            sequence_risk: {
              pattern: "sensitive_read_then_external_send",
              reason: "a sensitive/bulk read was followed by an external send/export in the same run - data-exfiltration shape",
              recommended: "hold_for_approval",
            },
          },
          expires_at: "2026-06-28T11:00:00Z",
        }),
        decision({
          id: "expiring_hold",
          intended_action: { summary: "Restart workflow" },
          action_type: "workflow.restart",
          expires_at: "2026-06-28T10:20:00Z",
        }),
      ],
      intents: [],
    });

    expect(rows.map((row) => row.decisionId)).toEqual([
      "expiring_hold",
      "sequence_hold",
      "money_hold",
      "normal_hold",
    ]);
    expect(rows[0].priority).toMatchObject({ label: "P0", detail: "expiring hold" });
    expect(rows[1].priority).toMatchObject({ label: "P0", detail: "sequence-risk hold" });
    expect(rows[1].holdReason).toMatchObject({
      title: "Sequence risk: bulk read -> external send",
      source: "sequence",
    });
    expect(rows[2].priority).toMatchObject({ label: "P0", detail: "money-touching hold" });
    expect(rows[3].priority).toMatchObject({ label: "P1", detail: "needs decision" });
  });

  it("counts pending, stopped, evidence-linked, expiring, sequence-risk, money-touching, and guard-only rows", () => {
    const rows = buildApprovalQueue({
      decisions: [
        decision({ expires_at: "2026-06-28T10:20:00Z" }),
        decision({ id: "blocked", status: "blocked", business_impact: { amount_usd: 50 }, trace_id: null, call_id: null }),
        decision({
          id: "rejected",
          status: "rejected",
          trace_id: null,
          call_id: null,
          policy_hit: { sequence_risk: { pattern: "rapid_repeated_money_movement" } },
        }),
      ],
      intents: [intent()],
    });

    expect(approvalQueueCounts(rows)).toEqual({
      total: 3,
      pending: 1,
      damageStopped: 2,
      moneyTouching: 1,
      expiringSoon: 1,
      sequenceRisk: 1,
      evidenceLinked: 1,
      guardOnly: 2,
    });
  });

  it("shows dual-approval progress for partially approved holds", () => {
    const rows = buildApprovalQueue({
      decisions: [
        decision({
          id: "dual_hold",
          required_approval_count: 2,
          approval_count: 1,
          approver_subjects: ["ops@example.com"],
        }),
      ],
      intents: [intent({ runtime_policy_decision_id: "dual_hold" })],
    });

    expect(rows[0]).toMatchObject({
      approvalProgress: "1/2 approvals",
      approverSubjects: ["ops@example.com"],
      requiredApprovalCount: 2,
      recordedApprovalCount: 1,
      hrefs: {
        approvals: "/approvals?decision_id=dual_hold",
        evidence: "/evidence?decision_id=dual_hold",
        action: "/operations?action_id=act_1",
      },
    });
  });

  it("keeps approved decisions as released-with-audit rows", () => {
    const rows = buildApprovalQueue({
      decisions: [
        decision({
          id: "approved_decision",
          status: "approved",
          resolved_at: "2026-06-28T10:12:00Z",
          resolved_by: "ops@example.com",
          resolution_reason: "verified externally",
        }),
      ],
      intents: [],
    });

    expect(rows[0]).toMatchObject({
      decisionId: "approved_decision",
      kind: "guard_only_hold",
      approvalProgress: "Approved",
      priority: {
        label: "P2",
        detail: "released with audit",
        tone: "success",
      },
      statusLabel: "Approved",
      statusTone: "success",
    });
  });
});
