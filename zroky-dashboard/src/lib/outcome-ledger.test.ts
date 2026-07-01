import { describe, expect, it } from "vitest";

import type { OutcomeReconciliationView, SourceMutationView } from "@/lib/api";
import { buildClaimedActualDiff, buildOutcomeLedger } from "./outcome-ledger";

function check(overrides: Partial<OutcomeReconciliationView> = {}): OutcomeReconciliationView {
  return {
    id: "check_1",
    project_id: "proj_1",
    call_id: "call_1",
    trace_id: "trace_1",
    runtime_policy_decision_id: "decision_1",
    action_type: "inventory.item.delete",
    connector_type: "generic_rest",
    system_ref: "inventory:item_1",
    verdict: "matched",
    verification_status: "verified",
    reason: "all_compared_fields_matched",
    amount_usd: null,
    currency: null,
    claimed: { item_id: "item_1", status: "deleted" },
    actual: { item_id: "item_1", status: "deleted" },
    comparison: {
      compared_fields: [
        { field: "status", claimed: "deleted", actual: "deleted", matched: true },
      ],
      mismatches: [],
    },
    idempotency_key: "idem_1",
    metadata: { agent_name: "ops-agent" },
    checked_at: "2026-06-20T09:00:00Z",
    created_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function mutation(overrides: Partial<SourceMutationView> = {}): SourceMutationView {
  return {
    id: "mutation_1",
    project_id: "proj_1",
    source_system: "stripe",
    mutation_id: "evt_1",
    action_type: "refund",
    resource_type: "refund",
    resource_id: "rf_1",
    system_ref: "stripe:rf_1",
    actor_type: "ai_agent",
    actor_id: "refund-agent",
    zroky_action_id: null,
    action_receipt_id: null,
    idempotency_key: null,
    classification: "policy_bypass",
    metadata: {},
    occurred_at: "2026-06-20T09:00:00Z",
    created_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

describe("outcome-ledger", () => {
  it("sorts damage first and keeps not_verified distinct from mismatched", () => {
    const ledger = buildOutcomeLedger({
      checks: [
        check({ id: "matched", verdict: "matched", checked_at: "2026-06-20T09:03:00Z" }),
        check({ id: "not_verified", verdict: "not_verified", reason: "connector_down", checked_at: "2026-06-20T09:02:00Z" }),
        check({
          id: "mismatched",
          verdict: "mismatched",
          comparison: { mismatches: [{ field: "amount_usd" }] },
          checked_at: "2026-06-20T09:01:00Z",
        }),
      ],
    });

    expect(ledger.rows.map((row) => row.id)).toEqual(["mismatched", "not_verified", "matched"]);
    expect(ledger.rows[0]?.tone).toBe("danger");
    expect(ledger.rows[1]?.tone).toBe("warning");
    expect(ledger.counts).toMatchObject({ matched: 1, mismatched: 1, notVerified: 1, total: 3, verifiedRate: 33 });
  });

  it("builds bypass rows from unreceipted source mutations", () => {
    const ledger = buildOutcomeLedger({ checks: [], mutations: [mutation()] });

    expect(ledger.counts.bypass).toBe(1);
    expect(ledger.bypassRows[0]).toMatchObject({
      actorLabel: "refund-agent",
      title: "stripe:rf_1",
      tone: "danger",
    });
  });

  it("creates a field-level claimed-vs-actual diff from compared_fields", () => {
    const diff = buildClaimedActualDiff(check({
      verdict: "mismatched",
      comparison: {
        compared_fields: [
          { field: "amount_usd", claimed: 42.5, actual: 41.5, matched: false },
          { field: "currency", claimed: "USD", actual: "USD", matched: true },
        ],
        mismatches: [{ field: "amount_usd" }],
      },
    }));

    expect(diff).toEqual([
      { field: "amount_usd", claimed: "42.5", actual: "41.5", status: "mismatched", tone: "danger" },
      { field: "currency", claimed: "USD", actual: "USD", status: "matched", tone: "success" },
    ]);
  });

  it("falls back to record keys when comparison rows are missing", () => {
    const diff = buildClaimedActualDiff(check({
      comparison: { mismatches: [{ field: "status" }] },
      claimed: { id: "1", status: "refunded" },
      actual: { id: "1", status: "failed" },
    }));

    expect(diff.find((row) => row.field === "status")).toMatchObject({
      status: "mismatched",
      tone: "danger",
    });
  });

  it("filters by verdict and search", () => {
    const ledger = buildOutcomeLedger({
      checks: [
        check({ id: "a", verdict: "matched", system_ref: "inventory:item_1" }),
        check({ id: "b", verdict: "mismatched", system_ref: "ledger:refund_1" }),
      ],
      filter: "mismatched",
      search: "refund",
    });

    expect(ledger.rows.map((row) => row.id)).toEqual(["b"]);
  });
});
