import { describe, expect, it } from "vitest";

import { lifecycleStage, statusLabel, statusTone } from "./action-status";
import type { ActionIntentResponse } from "./api";

function intent(overrides: Partial<ActionIntentResponse>): ActionIntentResponse {
  return {
    action_id: "act_123",
    project_id: "proj_123",
    contract_version: "inventory.item.update/1.0",
    action_type: "inventory.item.update",
    operation_kind: "UPDATE",
    environment: "production",
    status: "validated",
    proof_status: "not_started",
    receipt_status: "missing",
    idempotency_key: "idem_123",
    intent_digest: "sha256:abc",
    canonical_intent: {},
    created_at: "2026-06-28T10:00:00Z",
    decided_at: null,
    authorized_at: null,
    runtime_policy_decision_id: null,
    deadline: null,
    status_url: "/v1/action-intents/act_123",
    ...overrides,
  };
}

describe("action status helpers", () => {
  it("labels kernel statuses consistently", () => {
    expect(statusLabel("approval_pending", "intent")).toBe("Approval pending");
    expect(statusLabel("not_verified", "proof")).toBe("Not verified");
    expect(statusLabel("matched_receipt", "source_mutation")).toBe("Matched receipt");
  });

  it("maps status tones honestly", () => {
    expect(statusTone("mismatched", "proof")).toBe("danger");
    expect(statusTone("not_verified", "proof")).toBe("warning");
    expect(statusTone("generated", "receipt")).toBe("success");
    expect(statusTone("validated", "intent")).toBe("neutral");
  });

  it("detects approval and receipt lifecycle stages", () => {
    expect(lifecycleStage(intent({ status: "approval_pending" })).id).toBe("approval");
    expect(
      lifecycleStage(
        intent({
          status: "authorized",
          proof_status: "matched",
          receipt_status: "generated",
        }),
      ),
    ).toMatchObject({
      id: "receipted",
      tone: "success",
    });
  });

  it("keeps failed proof and denied policy distinct", () => {
    expect(lifecycleStage(intent({ status: "denied" })).id).toBe("blocked");
    expect(
      lifecycleStage(
        intent({
          status: "authorized",
          proof_status: "mismatched",
          receipt_status: "generated",
        }),
      ),
    ).toMatchObject({
      id: "receipted",
      tone: "danger",
    });
  });
});
