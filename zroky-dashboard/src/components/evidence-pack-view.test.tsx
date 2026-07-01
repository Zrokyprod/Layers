import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { EvidencePackView } from "./evidence-pack-view";
import type {
  ActionReceiptResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";

function pack(): RuntimePolicyEvidencePackResponse {
  return {
    schema_version: "zroky.evidence_pack.v1",
    project_id: "proj_123",
    decision_id: "decision_123",
    verification_status: "pass",
    decision: {
      id: "decision_123",
      project_id: "proj_123",
      trace_id: "trace_123",
      call_id: "call_123",
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
      policy_snapshot: { mandate: "inventory-control" },
      intended_action: { summary: "Update inventory item" },
      trace_context: {},
      policy_hit: {},
      business_impact: {},
      approval_scope_hash: "scope_123",
      created_at: "2026-06-28T10:00:00Z",
      expires_at: null,
      resolved_at: null,
      resolved_by: null,
      resolution_reason: null,
      consumed_at: null,
      consumed_by_decision_id: null,
    },
    related_decisions: [],
    audit_log: [
      {
        id: "audit_123",
        decision_id: "decision_123",
        event_type: "approved",
        actor: "ops@example.com",
        reason: "approved for stock sync",
        before: null,
        after: { status: "approved" },
        created_at: "2026-06-28T10:02:00Z",
      },
    ],
    trace_policy_spans: [],
    outcome_reconciliation: [
      {
        id: "outcome_123",
        project_id: "proj_123",
        call_id: "call_123",
        trace_id: "trace_123",
        runtime_policy_decision_id: "decision_123",
        action_type: "inventory.item.update",
        connector_type: "generic_rest_api",
        system_ref: "item_123",
        verdict: "matched",
        reason: "matched",
        amount_usd: 12.5,
        currency: "USD",
        claimed: { status: "active" },
        actual: { status: "active" },
        comparison: { status: true },
        idempotency_key: "idem_123",
        metadata: {},
        checked_at: "2026-06-28T10:03:00Z",
        created_at: "2026-06-28T10:03:00Z",
      },
    ],
    call: null,
    generated_at: "2026-06-28T10:04:00Z",
    hash_algorithm: "sha256",
    evidence_hash: "sha256:evidence",
    hash_payload_excludes: ["signature"],
  };
}

function receipt(): ActionReceiptResponse {
  return {
    receipt_id: "receipt_123",
    project_id: "proj_123",
    action_id: "act_123",
    receipt_digest: "sha256:receipt",
    evidence_hash: "sha256:evidence",
    signature_algorithm: "hmac-sha256",
    signature: "sig",
    signing_key_id: "local",
    signature_valid: true,
    generated_at: "2026-06-28T10:04:00Z",
    receipt: {
      schema_version: "zroky.action_receipt.v1",
      project_id: "proj_123",
      final_status: "matched",
      action_id: "act_123",
      environment: "test",
      generated_at: "2026-06-28T10:04:00Z",
      action_contract: {
        id: "contract_123",
        contract_version: "inventory.item.update/v1",
        action_type: "inventory.item.update",
        operation_kind: "business_mutation",
        risk_class: "medium",
      },
      intent: {
        contract_version: "inventory.item.update/v1",
        action_type: "inventory.item.update",
        operation_kind: "business_mutation",
        idempotency_key: "idem_123",
        intent_digest: "sha256:intent",
        canonical_intent: { action_type: "inventory.item.update" },
        principal: { id: "inventory-agent" },
        actor_chain: [{ actor: "agent" }],
        purpose: { summary: "Update inventory item" },
        resource: { id: "item_123" },
        parameters: { quantity: 12 },
        verification_profile: "generic_rest",
        created_at: "2026-06-28T10:00:00Z",
        decided_at: "2026-06-28T10:01:00Z",
        authorized_at: "2026-06-28T10:02:00Z",
      },
      policy_decision: {
        id: "decision_123",
        decision: "allow",
        status: "allowed",
        reasons: ["policy checks passed"],
        approval_scope_hash: "scope_123",
        approval_id: null,
        resolved_by: "ops@example.com",
        resolved_at: "2026-06-28T10:02:00Z",
        consumed_at: "2026-06-28T10:02:10Z",
        required_approval_count: 1,
        approval_count: 1,
        approver_subjects: ["ops@example.com"],
      },
      runner_execution: {
        id: "attempt_123",
        runner_id: "runner_123",
        attempt_number: 1,
        status: "succeeded",
        idempotency_key: "idem_123",
        credential_ref: "inventory-prod",
        plan_digest: "sha256:plan",
        plan: { method: "PATCH", path: "/inventory/item_123" },
        protected_credential_returned: false,
        started_at: "2026-06-28T10:02:20Z",
        finished_at: "2026-06-28T10:02:30Z",
      },
      verification: {
        status: "matched",
        outcomes: [
          {
            id: "outcome_123",
            verdict: "matched",
            verification_status: "verified",
            reason: "matched",
            connector_type: "generic_rest_api",
            system_ref: "item_123",
            idempotency_key: "idem_123",
            checked_at: "2026-06-28T10:03:00Z",
          },
        ],
      },
      evidence: {
        hash_algorithm: "sha256",
        evidence_hash: "sha256:evidence",
      },
      timeline: [
        {
          id: "event_123",
          event_type: "receipt_generated",
          event_digest: "sha256:event",
          actor: "system",
          created_at: "2026-06-28T10:04:00Z",
        },
      ],
    },
  };
}

function mismatchedReceipt(): ActionReceiptResponse {
  const base = receipt();
  return {
    ...base,
    receipt: {
      ...base.receipt,
      final_status: "mismatched",
      verification: {
        status: "mismatched",
        outcomes: [
          {
            id: "outcome_bad",
            verdict: "mismatched",
            verification_status: "mismatched",
            reason: "quantity mismatch",
            connector_type: "generic_rest_api",
            system_ref: "item_123",
            idempotency_key: "idem_123",
            checked_at: "2026-06-28T10:03:00Z",
          },
        ],
      },
    },
  };
}

describe("EvidencePackView", () => {
  it("renders runtime policy evidence pack details", () => {
    render(<EvidencePackView pack={pack()} />);

    expect(screen.getByRole("region", { name: "Runtime policy Evidence Pack" })).toBeInTheDocument();
    expect(screen.getByText("Update inventory item")).toBeInTheDocument();
    expect(screen.getByText("sha256:evidence")).toBeInTheDocument();
    expect(screen.getByText("item_123")).toBeInTheDocument();
    expect(screen.getAllByText("Matched").length).toBeGreaterThan(0);
  });

  it("renders signed action receipt details", () => {
    render(<EvidencePackView receipt={receipt()} />);

    expect(screen.getByRole("region", { name: "Action Receipt" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Proof chain" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Action: recorded/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Policy: Allow/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Execution: Succeeded/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Verification: Matched/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Receipt: signed/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Proof seal" })).toBeInTheDocument();
    expect(screen.getAllByText("Signature valid").length).toBeGreaterThan(0);
    expect(screen.getByText("receipt_123")).toBeInTheDocument();
    expect(screen.getAllByText("Matched").length).toBeGreaterThan(0);
  });

  it("renders full runtime evidence pack regression fields", () => {
    render(<EvidencePackView pack={pack()} mode="full" />);

    expect(screen.getByText(/AI summaries are advisory and are not proof/i)).toBeInTheDocument();
    expect(screen.getByText("Mandate snapshot")).toBeInTheDocument();
    expect(screen.getByText(/inventory-control/)).toBeInTheDocument();
    expect(screen.getByText("Approval audit")).toBeInTheDocument();
    expect(screen.getByText(/ops@example.com/)).toBeInTheDocument();
    expect(screen.getByText(/approved for stock sync/)).toBeInTheDocument();
    expect(screen.getByText("Hash algorithm")).toBeInTheDocument();
    expect(screen.getByText("sha256")).toBeInTheDocument();
    expect(screen.getByText("Hash excludes")).toBeInTheDocument();
    expect(screen.getByText("signature")).toBeInTheDocument();
    expect(screen.getByText("12.5 USD")).toBeInTheDocument();
    expect(screen.getByText("Jun 28, 10:03 AM")).toBeInTheDocument();
    expect(screen.getByText("outcome_123")).toBeInTheDocument();
    expect(screen.getByText("trace_123")).toBeInTheDocument();
    expect(screen.getByText("call_123")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "trace_123" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "call_123" })).not.toBeInTheDocument();
  });

  it("renders full action receipt as a structured proof chain", () => {
    render(<EvidencePackView receipt={receipt()} mode="full" />);

    expect(screen.getByText(/This signed receipt is deterministic proof/i)).toBeInTheDocument();
    expect(screen.getByText("Action / Intent")).toBeInTheDocument();
    expect(screen.getByText("Policy decision")).toBeInTheDocument();
    expect(screen.getByText("Runner execution")).toBeInTheDocument();
    expect(screen.getAllByText("Verification").length).toBeGreaterThan(0);
    expect(screen.getByText("Evidence + Signature")).toBeInTheDocument();
    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getAllByText("Full receipt JSON").length).toBeGreaterThan(0);
    expect(screen.queryByText("Receipt payload")).not.toBeInTheDocument();
    expect(screen.getByText("Signature validity is verified by the backend; the browser never receives the signing secret.")).toBeInTheDocument();
    expect(screen.getAllByText("Receipt digest").length).toBeGreaterThan(0);
    expect(screen.getAllByText("sha256:receipt").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence hash").length).toBeGreaterThan(0);
    expect(screen.getAllByText("sha256:evidence").length).toBeGreaterThan(0);
    expect(screen.getByText("inventory-prod")).toBeInTheDocument();
    expect(screen.getAllByText("item_123").length).toBeGreaterThan(0);
    expect(screen.getByText("sha256:event")).toBeInTheDocument();
    expect(document.querySelectorAll(".evidence-receipt-accordion[open]")).toHaveLength(0);
  });

  it("auto-expands the failing receipt step and lets stepper nodes expand sections", () => {
    render(<EvidencePackView receipt={mismatchedReceipt()} mode="full" />);

    expect(document.querySelector("#receipt-section-verification")?.hasAttribute("open")).toBe(true);
    expect(document.querySelector("#receipt-section-policy-decision")?.hasAttribute("open")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /Policy: Allow/i }));

    expect(document.querySelector("#receipt-section-policy-decision")?.hasAttribute("open")).toBe(true);
  });
});
