import type {
  ActionReceiptResponse,
  RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { actionReceiptPublicKeyUrl } from "@/lib/evidence-verification";

type IndependentVerification = {
  method: "ed25519-public-key";
  public_key_url: string;
  signed_payload_field: "signed_payload";
  signature_field: "signature";
  instructions: string[];
};

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
  signed_payload?: string;
  verification: IndependentVerification;
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
      signed_payload: input.receipt.signed_payload,
      verification: {
        method: "ed25519-public-key",
        public_key_url: actionReceiptPublicKeyUrl(),
        signed_payload_field: "signed_payload",
        signature_field: "signature",
        instructions: [
          "Fetch the published Ed25519 public key from public_key_url.",
          "Verify signature over the exact signed_payload string.",
          "Treat signature_valid as Zroky's server-side attestation; independent audit should verify the signature again.",
        ],
      },
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
