import type {
  ActionReceiptResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";

export type ActionReceiptArtifact = {
  artifact: "zroky.action_receipt";
  schema_version: string;
  receipt: ActionReceiptResponse;
  receipt_digest: string;
  signature: string;
  signature_algorithm: string;
  signing_key_id: string;
  evidence_hash: string | null;
  signature_valid: boolean;
};

export type RuntimePolicyEvidencePackArtifact = {
  artifact: "zroky.evidence_pack";
  schema_version: string;
  evidence_pack: RuntimePolicyEvidencePackResponse;
  decision_id: string;
  evidence_hash: string;
  hash_algorithm: string;
  verification_status: string;
};

export type EvidenceArtifact = ActionReceiptArtifact | RuntimePolicyEvidencePackArtifact;

export function buildEvidenceArtifact(
  input:
    | { kind: "receipt"; receipt: ActionReceiptResponse }
    | { kind: "evidence_pack"; pack: RuntimePolicyEvidencePackResponse },
): EvidenceArtifact {
  if (input.kind === "receipt") {
    return {
      artifact: "zroky.action_receipt",
      schema_version: String(input.receipt.receipt.schema_version ?? "zroky.action_receipt.v1"),
      receipt: input.receipt,
      receipt_digest: input.receipt.receipt_digest,
      signature: input.receipt.signature,
      signature_algorithm: input.receipt.signature_algorithm,
      signing_key_id: input.receipt.signing_key_id,
      evidence_hash: input.receipt.evidence_hash,
      signature_valid: input.receipt.signature_valid,
    };
  }
  return {
    artifact: "zroky.evidence_pack",
    schema_version: input.pack.schema_version,
    evidence_pack: input.pack,
    decision_id: input.pack.decision_id,
    evidence_hash: input.pack.evidence_hash,
    hash_algorithm: input.pack.hash_algorithm,
    verification_status: input.pack.verification_status,
  };
}
