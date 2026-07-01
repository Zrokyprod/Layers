import type {
  ActionIntentProofStatus,
  ActionIntentReceiptStatus,
  ActionIntentResponse,
  ActionIntentStatus,
  RuntimePolicyDecisionStatus,
  SourceMutationClassification,
} from "@/lib/api";
import { humanize } from "@/lib/format";

export type ActionStatusKind =
  | "intent"
  | "proof"
  | "receipt"
  | "runtime_policy"
  | "source_mutation"
  | "generic";

export type StatusTone = "danger" | "warning" | "success" | "neutral";

export type LifecycleStageId =
  | "proposed"
  | "policy"
  | "approval"
  | "authorized"
  | "execution"
  | "verification"
  | "receipted"
  | "blocked";

export type LifecycleStage = {
  id: LifecycleStageId;
  label: string;
  detail: string;
  tone: StatusTone;
};

const LABELS: Record<string, string> = {
  approval_pending: "Approval pending",
  authorized: "Authorized",
  blocked: "Blocked",
  deciding: "Policy deciding",
  denied: "Denied",
  expired: "Expired",
  failed: "Failed",
  generated: "Generated",
  legacy_path: "Legacy path",
  matched: "Matched",
  matched_receipt: "Matched receipt",
  mismatched: "Mismatched",
  missing: "Missing",
  not_started: "Not started",
  not_verified: "Not verified",
  pending: "Pending",
  pending_approval: "Pending approval",
  policy_bypass: "Policy bypass",
  rejected: "Rejected",
  unmanaged_agent_action: "Unmanaged agent action",
  unknown_actor: "Unknown actor",
  validated: "Validated",
};

const DANGER = new Set([
  "blocked",
  "denied",
  "expired",
  "failed",
  "fail",
  "mismatched",
  "policy_bypass",
  "rejected",
  "unmanaged_agent_action",
  "unknown_actor",
]);

const WARNING = new Set([
  "approval_pending",
  "deciding",
  "legacy_path",
  "missing",
  "not_started",
  "not_verified",
  "pending",
  "pending_approval",
]);

const SUCCESS = new Set([
  "allow",
  "allowed",
  "approved",
  "authorized",
  "clear",
  "completed",
  "generated",
  "matched",
  "matched_receipt",
  "pass",
  "verified",
]);

function normalizeStatus(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

export function statusLabel(
  value: string | null | undefined,
  kind: ActionStatusKind = "generic",
  fallback = "Unknown",
): string {
  void kind;
  const normalized = normalizeStatus(value);
  if (!normalized) {
    return fallback;
  }
  return LABELS[normalized] ?? humanize(normalized, fallback);
}

export function statusTone(
  value: string | null | undefined,
  kind: ActionStatusKind = "generic",
): StatusTone {
  const normalized = normalizeStatus(value);
  if (!normalized) {
    return kind === "receipt" ? "warning" : "neutral";
  }
  if (DANGER.has(normalized)) {
    return "danger";
  }
  if (WARNING.has(normalized)) {
    return "warning";
  }
  if (SUCCESS.has(normalized)) {
    return "success";
  }
  return "neutral";
}

export function lifecycleStage(intent: Pick<ActionIntentResponse, "status" | "proof_status" | "receipt_status">): LifecycleStage {
  const status = normalizeStatus(intent.status as ActionIntentStatus | string);
  const proof = normalizeStatus(intent.proof_status as ActionIntentProofStatus | string);
  const receipt = normalizeStatus(intent.receipt_status as ActionIntentReceiptStatus | string);

  if (["denied", "expired"].includes(status)) {
    return {
      id: "blocked",
      label: statusLabel(status, "intent"),
      detail: "Action did not pass the policy gate.",
      tone: "danger",
    };
  }
  if (status === "approval_pending") {
    return {
      id: "approval",
      label: "Held for approval",
      detail: "Human approval is required before execution.",
      tone: "warning",
    };
  }
  if (status === "deciding") {
    return {
      id: "policy",
      label: "Policy deciding",
      detail: "Runtime policy is evaluating the proposed action.",
      tone: "warning",
    };
  }
  if (receipt === "generated") {
    return {
      id: "receipted",
      label: "Receipt generated",
      detail: proof === "matched" ? "Action proof is matched and receipted." : "Receipt records the final action state.",
      tone: statusTone(proof, "proof"),
    };
  }
  if (["matched", "mismatched", "not_verified"].includes(proof)) {
    return {
      id: "verification",
      label: statusLabel(proof, "proof"),
      detail: "Verification reached a terminal proof verdict.",
      tone: statusTone(proof, "proof"),
    };
  }
  if (status === "authorized") {
    return {
      id: proof === "pending" ? "verification" : "execution",
      label: proof === "pending" ? "Verification pending" : "Authorized for runner",
      detail: proof === "pending" ? "Backend worker is checking the source of record." : "A protected runner may execute the planned action.",
      tone: "warning",
    };
  }
  return {
    id: "proposed",
    label: statusLabel(status || "validated", "intent"),
    detail: "Action intent is recorded before policy release.",
    tone: statusTone(status || "validated", "intent"),
  };
}

export function runtimePolicyTone(status: RuntimePolicyDecisionStatus | string | null | undefined): StatusTone {
  return statusTone(status, "runtime_policy");
}

export function sourceMutationTone(status: SourceMutationClassification | string | null | undefined): StatusTone {
  return statusTone(status, "source_mutation");
}
