import { describe, expect, it } from "vitest";

import type {
  ActionReceiptResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { buildEvidenceArtifact } from "./evidence-artifact";

function receipt(): ActionReceiptResponse {
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
    receipt: {
      schema_version: "zroky.action_receipt.v1",
      final_status: "matched",
      action_id: "act_123",
    },
  };
}

function evidencePack(): RuntimePolicyEvidencePackResponse {
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
    audit_log: [],
    trace_policy_spans: [],
    outcome_reconciliation: [],
    call: null,
    generated_at: "2026-06-28T10:04:00Z",
    hash_algorithm: "sha256",
    evidence_hash: "sha256:evidence-pack",
    hash_payload_excludes: ["signature"],
  };
}

describe("buildEvidenceArtifact", () => {
  it("wraps the signed receipt without mutating the backend payload", () => {
    const signedReceipt = receipt();
    const artifact = buildEvidenceArtifact({ kind: "receipt", receipt: signedReceipt });

    expect(artifact.artifact).toBe("zroky.action_receipt");
    if (artifact.artifact !== "zroky.action_receipt") {
      throw new Error("Expected action receipt artifact.");
    }
    expect(artifact.receipt).toBe(signedReceipt);
    expect(artifact.receipt_digest).toBe("sha256:receipt");
    expect(artifact.signature).toBe("sig");
    expect(artifact.evidence_hash).toBe("sha256:evidence");
    expect(artifact.schema_version).toBe("zroky.action_receipt.v1");
    expect(artifact.verification).toMatchObject({
      method: "ed25519-public-key",
      public_key_url: "https://api.zroky.com/.well-known/zroky/action-receipt-signing-key",
      signed_payload_field: "signed_payload",
      signature_field: "signature",
    });
    expect(artifact.verification.instructions.join(" ")).toContain("independent audit");
  });

  it("wraps the runtime policy Evidence Pack without mutating the pack", () => {
    const pack = evidencePack();
    const artifact = buildEvidenceArtifact({ kind: "evidence_pack", pack });

    expect(artifact.artifact).toBe("zroky.evidence_pack");
    if (artifact.artifact !== "zroky.evidence_pack") {
      throw new Error("Expected Evidence Pack artifact.");
    }
    expect(artifact.evidence_pack).toBe(pack);
    expect(artifact.decision_id).toBe("decision_123");
    expect(artifact.evidence_hash).toBe("sha256:evidence-pack");
    expect(artifact.verification_status).toBe("pass");
  });
});
