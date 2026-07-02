import type {
  ActionIntentResponse,
  RuntimePolicyDecisionStatus,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";
import { statusLabel, statusTone, type StatusTone } from "@/lib/action-status";
import {
  buildActionView,
  buildGuardOnlyProofChain,
  buildProofChain,
  type ActionView,
  type ProofChainStep,
} from "@/lib/action-view";
import { humanize } from "@/lib/format";

export type ApprovalQueueRowKind = "action_intent_hold" | "guard_only_hold";

export type ApprovalQueueRow = {
  id: string;
  kind: ApprovalQueueRowKind;
  decisionId: string;
  actionId: string | null;
  title: string;
  agentName: string;
  actionType: string;
  operationKind: string | null;
  environment: string | null;
  digest: string | null;
  systemRef: string | null;
  status: string;
  statusLabel: string;
  statusTone: StatusTone;
  intentStatus: string | null;
  proofStatus: string | null;
  receiptStatus: string | null;
  impactValueUsd: number | null;
  impactLabel: string;
  riskLabel: string;
  approvalProgress: string;
  approvalAction: string;
  approverSubjects: string[];
  requiredApprovalCount: number;
  recordedApprovalCount: number;
  holdReason: {
    title: string;
    detail: string;
    tone: StatusTone;
    source: "sequence" | "policy" | "reason" | "fallback";
  };
  isExpiringSoon: boolean;
  isExpired: boolean;
  isSequenceRisk: boolean;
  priority: {
    score: number;
    label: string;
    detail: string;
    tone: StatusTone;
  };
  createdAt: string;
  expiresAt: string | null;
  hrefs: {
    approvals: string;
    evidence: string;
    action: string | null;
  };
  view: ActionView | null;
  intent: ActionIntentResponse | null;
  decision: RuntimePolicyDecisionResponse;
  proofChain: ProofChainStep[];
};

type BuildApprovalQueueInput = {
  decisions: RuntimePolicyDecisionResponse[];
  intents: ActionIntentResponse[];
};

function recordFrom(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringFrom(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberFrom(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function amountForDecision(decision: RuntimePolicyDecisionResponse): number | null {
  return (
    numberFrom(decision.business_impact.amount_usd) ??
    numberFrom(decision.business_impact.estimated_value_usd) ??
    numberFrom(decision.request.amount_usd) ??
    numberFrom(decision.intended_action.amount_usd) ??
    numberFrom(decision.policy_hit.amount_usd)
  );
}

function moneyLabel(amount: number | null): string {
  if (amount == null) return "No money amount";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(amount);
}

function readableReason(value: string | null | undefined): string | null {
  const raw = stringFrom(value);
  if (!raw) return null;
  const stripped = raw.replace(/^sequence risk:\s*/i, "");
  return humanize(stripped);
}

function titleForDecision(decision: RuntimePolicyDecisionResponse): string {
  const intendedAction = recordFrom(decision.intended_action);
  return (
    stringFrom(intendedAction.summary) ??
    decision.tool_name ??
    decision.action_type ??
    decision.id
  );
}

function riskLabelForDecision(decision: RuntimePolicyDecisionResponse): string {
  return (
    stringFrom(decision.business_impact.risk_category) ??
    stringFrom(decision.business_impact.risk_class) ??
    stringFrom(decision.policy_hit.risk_class) ??
    stringFrom(decision.policy_hit.policy) ??
    humanize(decision.action_type ?? decision.tool_name, "High-stakes action")
  );
}

function actionTypeForDecision(decision: RuntimePolicyDecisionResponse): string {
  return humanize(decision.action_type ?? decision.tool_name, "Agent action");
}

function impactLabel(decision: RuntimePolicyDecisionResponse, amount: number | null): string {
  if (amount != null) return moneyLabel(amount);
  const risk = riskLabelForDecision(decision);
  return risk === "-" ? "Policy-controlled" : humanize(risk);
}

function requiredApprovals(decision: RuntimePolicyDecisionResponse): number {
  return Math.max(1, decision.required_approval_count ?? 1);
}

function approvalCount(decision: RuntimePolicyDecisionResponse): number {
  return Math.max(0, decision.approval_count ?? 0);
}

function approvalProgress(decision: RuntimePolicyDecisionResponse): string {
  const required = requiredApprovals(decision);
  const current = approvalCount(decision);
  if (decision.status !== "pending_approval") {
    return statusLabel(decision.status, "runtime_policy");
  }
  return required > 1 ? `${current}/${required} approvals` : "Approval required";
}

function sequenceRiskHit(decision: RuntimePolicyDecisionResponse): Record<string, unknown> | null {
  const hit = recordFrom(decision.policy_hit).sequence_risk;
  const record = recordFrom(hit);
  return Object.keys(record).length > 0 ? record : null;
}

function sequencePatternLabel(pattern: string | null): string {
  if (pattern === "sensitive_read_then_external_send") return "bulk read -> external send";
  if (pattern === "rapid_repeated_money_movement") return "rapid money movement";
  if (pattern === "credential_change_then_external_transfer") return "credential change -> external send";
  return pattern ? humanize(pattern) : "cross-action pattern";
}

function holdReasonForDecision(decision: RuntimePolicyDecisionResponse): ApprovalQueueRow["holdReason"] {
  const sequence = sequenceRiskHit(decision);
  if (sequence) {
    const pattern = sequencePatternLabel(stringFrom(sequence.pattern));
    const detail = readableReason(stringFrom(sequence.reason)) ?? "Multiple individually safe actions matched a risky sequence.";
    return {
      title: `Sequence risk: ${pattern}`,
      detail,
      tone: stringFrom(sequence.recommended) === "block" ? "danger" : "warning",
      source: "sequence",
    };
  }

  const reason = readableReason(decision.reasons[0]);
  if (reason) {
    return {
      title: "Held by runtime policy",
      detail: reason,
      tone: statusTone(decision.status, "runtime_policy"),
      source: "reason",
    };
  }

  const policyHit = recordFrom(decision.policy_hit);
  const policy = stringFrom(policyHit.policy) ?? stringFrom(policyHit.rule) ?? stringFrom(policyHit.risk_class);
  if (policy) {
    return {
      title: `Held by rule: ${humanize(policy)}`,
      detail: "The runtime policy matched this action before execution.",
      tone: statusTone(decision.status, "runtime_policy"),
      source: "policy",
    };
  }

  return {
    title: "Held by runtime gate",
    detail: "Zroky paused this action before execution so a human can review the decision.",
    tone: statusTone(decision.status, "runtime_policy"),
    source: "fallback",
  };
}

function approversForDecision(decision: RuntimePolicyDecisionResponse): string[] {
  return (decision.approver_subjects ?? [])
    .map((item) => String(item).trim())
    .filter(Boolean);
}

function approvalActionForDecision(
  decision: RuntimePolicyDecisionResponse,
  intent: ActionIntentResponse | null,
  amount: number | null,
): string {
  const summary = titleForDecision(decision);
  const operation = intent?.operation_kind ? humanize(intent.operation_kind) : humanize(decision.action_type ?? decision.tool_name, "Action");
  const resource = recordFrom(intent?.canonical_intent?.resource);
  const resourceId = stringFrom(resource.id) ?? stringFrom(resource.external_id) ?? stringFrom(decision.call_id);
  const amountText = amount != null ? ` for ${moneyLabel(amount)}` : "";
  const target = resourceId ? ` on ${resourceId}` : "";
  return `${operation}: ${summary}${target}${amountText}`;
}

function expiresSoon(expiresAt: string | null, nowMs: number): boolean {
  if (!expiresAt) return false;
  const time = new Date(expiresAt).getTime();
  if (!Number.isFinite(time)) return false;
  return time - nowMs <= 15 * 60_000;
}

function isExpired(expiresAt: string | null, nowMs: number): boolean {
  if (!expiresAt) return false;
  const time = new Date(expiresAt).getTime();
  return Number.isFinite(time) && time <= nowMs;
}

function priorityForDecision(
  decision: RuntimePolicyDecisionResponse,
  amount: number | null,
  nowMs: number,
): ApprovalQueueRow["priority"] {
  if (decision.status === "pending_approval" && isExpired(decision.expires_at, nowMs)) {
    return { score: 0, label: "P0", detail: "expired hold", tone: "danger" };
  }
  if (decision.status === "pending_approval" && expiresSoon(decision.expires_at, nowMs)) {
    return { score: 1, label: "P0", detail: "expiring hold", tone: "warning" };
  }
  if (decision.status === "pending_approval" && sequenceRiskHit(decision)) {
    return { score: 2, label: "P0", detail: "sequence-risk hold", tone: "warning" };
  }
  if (decision.status === "pending_approval" && amount != null) {
    return { score: 3, label: "P0", detail: "money-touching hold", tone: "warning" };
  }
  if (decision.status === "blocked" || decision.status === "rejected") {
    return { score: 4, label: "P0", detail: "damage stopped", tone: "danger" };
  }
  if (decision.status === "pending_approval") {
    return { score: 5, label: "P1", detail: "needs decision", tone: "warning" };
  }
  if (decision.status === "approved") {
    return { score: 6, label: "P2", detail: "released with audit", tone: "success" };
  }
  return { score: 7, label: "P3", detail: "audit only", tone: statusTone(decision.status, "runtime_policy") };
}

function linkedIntentForDecision(
  decision: RuntimePolicyDecisionResponse,
  intents: ActionIntentResponse[],
): ActionIntentResponse | null {
  return (
    intents.find((intent) => intent.runtime_policy_decision_id === decision.id) ??
    intents.find((intent) => decision.consumed_by_decision_id && intent.runtime_policy_decision_id === decision.consumed_by_decision_id) ??
    null
  );
}

function latestRowTime(row: ApprovalQueueRow): number {
  const raw = row.expiresAt ?? row.createdAt;
  const time = raw ? new Date(raw).getTime() : 0;
  return Number.isFinite(time) ? time : 0;
}

export function buildApprovalQueue({
  decisions,
  intents,
}: BuildApprovalQueueInput): ApprovalQueueRow[] {
  const nowMs = Date.now();
  const rows = decisions.map((decision): ApprovalQueueRow => {
    const intent = linkedIntentForDecision(decision, intents);
    const amount = amountForDecision(decision);
    const priority = priorityForDecision(decision, amount, nowMs);
    const status = decision.status;
    const view = intent ? buildActionView(intent, { decision }) : null;
    const requiredCount = requiredApprovals(decision);
    const recordedCount = approvalCount(decision);
    return {
      id: `decision:${decision.id}`,
      kind: intent ? "action_intent_hold" : "guard_only_hold",
      decisionId: decision.id,
      actionId: intent?.action_id ?? null,
      title: view?.title ?? titleForDecision(decision),
      agentName: view?.agentName ?? decision.agent_name ?? "Unknown agent",
      actionType: view?.actionType ?? actionTypeForDecision(decision),
      operationKind: view?.operationKind ?? null,
      environment: view?.environment ?? null,
      digest: view?.digest ?? null,
      systemRef: view?.systemRef ?? decision.call_id ?? decision.trace_id,
      status,
      statusLabel: statusLabel(status, "runtime_policy"),
      statusTone: statusTone(status, "runtime_policy"),
      intentStatus: intent?.status ?? null,
      proofStatus: intent?.proof_status ?? null,
      receiptStatus: intent?.receipt_status ?? null,
      impactValueUsd: amount,
      impactLabel: impactLabel(decision, amount),
      riskLabel: riskLabelForDecision(decision),
      approvalProgress: approvalProgress(decision),
      approvalAction: approvalActionForDecision(decision, intent, amount),
      approverSubjects: approversForDecision(decision),
      requiredApprovalCount: requiredCount,
      recordedApprovalCount: recordedCount,
      holdReason: holdReasonForDecision(decision),
      isExpiringSoon: status === "pending_approval" && expiresSoon(decision.expires_at, nowMs),
      isExpired: status === "pending_approval" && isExpired(decision.expires_at, nowMs),
      isSequenceRisk: Boolean(sequenceRiskHit(decision)),
      priority,
      createdAt: decision.created_at,
      expiresAt: decision.expires_at,
      hrefs: {
        approvals: `/approvals?decision_id=${encodeURIComponent(decision.id)}`,
        evidence: `/evidence?decision_id=${encodeURIComponent(decision.id)}`,
        action: intent ? `/actions?action_id=${encodeURIComponent(intent.action_id)}` : null,
      },
      view,
      intent,
      decision,
      proofChain: view ? buildProofChain(view, { decision }) : buildGuardOnlyProofChain(decision),
    };
  });

  return rows.sort((a, b) => {
    if (a.priority.score !== b.priority.score) return a.priority.score - b.priority.score;
    if (a.kind !== b.kind) return a.kind === "action_intent_hold" ? -1 : 1;
    return latestRowTime(a) - latestRowTime(b);
  });
}

export function approvalQueueCounts(rows: ApprovalQueueRow[]) {
  return {
    total: rows.length,
    pending: rows.filter((row) => row.status === "pending_approval").length,
    damageStopped: rows.filter((row) => row.status === "blocked" || row.status === "rejected").length,
    moneyTouching: rows.filter((row) => row.impactValueUsd != null).length,
    expiringSoon: rows.filter((row) => row.isExpiringSoon).length,
    sequenceRisk: rows.filter((row) => row.isSequenceRisk).length,
    evidenceLinked: rows.filter((row) => row.decision.trace_id || row.decision.call_id || row.actionId).length,
    guardOnly: rows.filter((row) => row.kind === "guard_only_hold").length,
  };
}

export function filterApprovalQueue(
  rows: ApprovalQueueRow[],
  filter: RuntimePolicyDecisionStatus | "all",
): ApprovalQueueRow[] {
  if (filter === "all") return rows;
  return rows.filter((row) => row.status === filter);
}
