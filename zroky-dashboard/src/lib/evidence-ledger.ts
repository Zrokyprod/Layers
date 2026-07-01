import type {
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";
import { statusLabel, statusTone, type StatusTone } from "@/lib/action-status";
import { buildActionView } from "@/lib/action-view";
import { humanize } from "@/lib/format";

export type EvidenceLedgerRowKind = "action_receipt" | "orphan_decision" | "unlinked_outcome";

export type EvidenceLedgerFilter = "all" | "matched" | "needs_verification" | "exceptions";

export type EvidenceLedgerRow = {
  id: string;
  kind: EvidenceLedgerRowKind;
  actionId: string | null;
  decisionId: string | null;
  outcomeId: string | null;
  traceId: string | null;
  callId: string | null;
  title: string;
  agentName: string;
  actionType: string;
  status: string;
  statusLabel: string;
  tone: StatusTone;
  digest: string | null;
  systemRef: string | null;
  sourceLabel: string;
  checkedAt: string | null;
  href: string;
  exportable: boolean;
  exportKind: "receipt" | "evidence_pack" | null;
  detail: string;
};

export type EvidenceLedgerCounts = {
  exportReady: number;
  needsVerification: number;
  exceptions: number;
  total: number;
};

type BuildEvidenceLedgerInput = {
  intents: ActionIntentResponse[];
  decisions: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
};

type DeepLinkInput = {
  actionId?: string | null;
  decisionId?: string | null;
  traceId?: string | null;
  callId?: string | null;
};

function recordFrom(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringFrom(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function latestByDate<T>(items: T[], dateOf: (item: T) => string | null | undefined): T | null {
  let latest: T | null = null;
  let latestTime = -1;
  for (const item of items) {
    const raw = dateOf(item);
    const time = raw ? new Date(raw).getTime() : 0;
    if (Number.isFinite(time) && time > latestTime) {
      latest = item;
      latestTime = time;
    }
  }
  return latest;
}

function canonicalTraceContext(intent: ActionIntentResponse): Record<string, unknown> {
  return recordFrom(recordFrom(intent.canonical_intent).trace_context);
}

function traceIdForIntent(intent: ActionIntentResponse, decision: RuntimePolicyDecisionResponse | null, outcome: OutcomeReconciliationView | null): string | null {
  return outcome?.trace_id ?? decision?.trace_id ?? stringFrom(canonicalTraceContext(intent).trace_id);
}

function callIdForIntent(intent: ActionIntentResponse, decision: RuntimePolicyDecisionResponse | null, outcome: OutcomeReconciliationView | null): string | null {
  return outcome?.call_id ?? decision?.call_id ?? stringFrom(canonicalTraceContext(intent).call_id);
}

function statusForIntent(intent: ActionIntentResponse): string {
  if (intent.proof_status === "mismatched" || intent.proof_status === "not_verified") {
    return intent.proof_status;
  }
  if (intent.proof_status === "matched" && intent.receipt_status === "generated") {
    return "matched";
  }
  if (intent.receipt_status === "missing" || intent.receipt_status === "failed") {
    return intent.receipt_status;
  }
  if (intent.proof_status === "pending" || intent.receipt_status === "pending") {
    return "pending";
  }
  return intent.proof_status || intent.receipt_status || intent.status || "not_verified";
}

function statusForDecision(
  decision: RuntimePolicyDecisionResponse,
  outcome: OutcomeReconciliationView | null,
): string {
  if (outcome?.verdict) {
    return outcome.verdict;
  }
  if (["blocked", "denied", "rejected", "expired", "failed"].includes(decision.status)) {
    return decision.status;
  }
  return "not_verified";
}

function statusForOutcome(outcome: OutcomeReconciliationView): string {
  return outcome.verdict || "not_verified";
}

function rowStatus(value: string): Pick<EvidenceLedgerRow, "status" | "statusLabel" | "tone"> {
  return {
    status: value,
    statusLabel: statusLabel(value),
    tone: statusTone(value),
  };
}

function isNeedsVerification(row: EvidenceLedgerRow): boolean {
  return ["missing", "not_started", "not_verified", "pending"].includes(row.status);
}

function isException(row: EvidenceLedgerRow): boolean {
  return row.tone === "danger" || ["mismatched", "failed", "signature_invalid"].includes(row.status);
}

function actionHref(actionId: string): string {
  return `/evidence?action_id=${encodeURIComponent(actionId)}`;
}

function decisionHref(decisionId: string): string {
  return `/evidence?decision_id=${encodeURIComponent(decisionId)}`;
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

function buildOutcomeIndexes(outcomes: OutcomeReconciliationView[]) {
  const byDecision = new Map<string, OutcomeReconciliationView[]>();
  const byIdempotency = new Map<string, OutcomeReconciliationView[]>();

  for (const outcome of outcomes) {
    if (outcome.runtime_policy_decision_id) {
      byDecision.set(outcome.runtime_policy_decision_id, [
        ...(byDecision.get(outcome.runtime_policy_decision_id) ?? []),
        outcome,
      ]);
    }
    if (outcome.idempotency_key) {
      byIdempotency.set(outcome.idempotency_key, [
        ...(byIdempotency.get(outcome.idempotency_key) ?? []),
        outcome,
      ]);
    }
  }

  return { byDecision, byIdempotency };
}

function latestOutcomeForIntent(
  intent: ActionIntentResponse,
  byDecision: Map<string, OutcomeReconciliationView[]>,
  byIdempotency: Map<string, OutcomeReconciliationView[]>,
): OutcomeReconciliationView | null {
  const candidates = [
    ...(intent.runtime_policy_decision_id ? byDecision.get(intent.runtime_policy_decision_id) ?? [] : []),
    ...(byIdempotency.get(intent.idempotency_key) ?? []),
  ];
  return latestByDate(candidates, (outcome) => outcome.checked_at ?? outcome.created_at);
}

function latestOutcomeForDecision(
  decision: RuntimePolicyDecisionResponse,
  byDecision: Map<string, OutcomeReconciliationView[]>,
): OutcomeReconciliationView | null {
  return latestByDate(byDecision.get(decision.id) ?? [], (outcome) => outcome.checked_at ?? outcome.created_at);
}

export function buildEvidenceLedger({
  intents,
  decisions,
  outcomes,
}: BuildEvidenceLedgerInput): EvidenceLedgerRow[] {
  const rows: EvidenceLedgerRow[] = [];
  const actionDecisionIds = new Set<string>();
  const linkedOutcomeIds = new Set<string>();
  const decisionById = new Map(decisions.map((decision) => [decision.id, decision]));
  const { byDecision, byIdempotency } = buildOutcomeIndexes(outcomes);

  for (const intent of intents) {
    if (intent.runtime_policy_decision_id) {
      actionDecisionIds.add(intent.runtime_policy_decision_id);
    }
    const decision = intent.runtime_policy_decision_id ? decisionById.get(intent.runtime_policy_decision_id) ?? null : null;
    const outcome = latestOutcomeForIntent(intent, byDecision, byIdempotency);
    if (outcome) {
      linkedOutcomeIds.add(outcome.id);
    }
    const view = buildActionView(intent, {
      decision,
      outcomes: outcome ? [outcome] : [],
    });
    const status = statusForIntent(intent);
    rows.push({
      id: `action:${intent.action_id}`,
      kind: "action_receipt",
      actionId: intent.action_id,
      decisionId: intent.runtime_policy_decision_id,
      outcomeId: outcome?.id ?? null,
      traceId: traceIdForIntent(intent, decision, outcome),
      callId: callIdForIntent(intent, decision, outcome),
      title: view.title,
      agentName: view.agentName,
      actionType: view.actionType,
      ...rowStatus(status),
      digest: intent.intent_digest,
      systemRef: outcome?.system_ref ?? view.systemRef,
      sourceLabel: "Action Receipt",
      checkedAt: outcome?.checked_at ?? intent.created_at,
      href: actionHref(intent.action_id),
      exportable: intent.receipt_status === "generated",
      exportKind: "receipt",
      detail: intent.receipt_status === "generated" ? "Signed receipt available" : "Receipt not generated yet",
    });
  }

  for (const decision of decisions) {
    if (actionDecisionIds.has(decision.id)) {
      continue;
    }
    const outcome = latestOutcomeForDecision(decision, byDecision);
    if (outcome) {
      linkedOutcomeIds.add(outcome.id);
    }
    const status = statusForDecision(decision, outcome);
    rows.push({
      id: `decision:${decision.id}`,
      kind: "orphan_decision",
      actionId: null,
      decisionId: decision.id,
      outcomeId: outcome?.id ?? null,
      traceId: outcome?.trace_id ?? decision.trace_id,
      callId: outcome?.call_id ?? decision.call_id,
      title: titleForDecision(decision),
      agentName: decision.agent_name ?? "Guard-only action",
      actionType: humanize(decision.action_type ?? decision.tool_name),
      ...rowStatus(status),
      digest: null,
      systemRef: outcome?.system_ref ?? decision.call_id ?? decision.trace_id,
      sourceLabel: "Guard-only Evidence Pack",
      checkedAt: outcome?.checked_at ?? decision.resolved_at ?? decision.created_at,
      href: decisionHref(decision.id),
      exportable: true,
      exportKind: "evidence_pack",
      detail: outcome ? "Runtime decision linked to outcome proof" : "Runtime decision has no linked outcome proof",
    });
  }

  for (const outcome of outcomes) {
    if (linkedOutcomeIds.has(outcome.id)) {
      continue;
    }
    const status = statusForOutcome(outcome);
    rows.push({
      id: `outcome:${outcome.id}`,
      kind: "unlinked_outcome",
      actionId: null,
      decisionId: outcome.runtime_policy_decision_id,
      outcomeId: outcome.id,
      traceId: outcome.trace_id,
      callId: outcome.call_id,
      title: outcome.system_ref ?? outcome.id,
      agentName: "Unlinked outcome",
      actionType: humanize(outcome.action_type),
      ...rowStatus(status),
      digest: null,
      systemRef: outcome.system_ref,
      sourceLabel: "Unlinked outcome",
      checkedAt: outcome.checked_at ?? outcome.created_at,
      href: "/outcomes",
      exportable: false,
      exportKind: null,
      detail: "Not linked to an action intent in this evidence window",
    });
  }

  return rows.sort((a, b) => {
    const rank = { action_receipt: 0, orphan_decision: 1, unlinked_outcome: 2 } satisfies Record<EvidenceLedgerRowKind, number>;
    if (rank[a.kind] !== rank[b.kind]) return rank[a.kind] - rank[b.kind];
    const timeA = a.checkedAt ? new Date(a.checkedAt).getTime() : 0;
    const timeB = b.checkedAt ? new Date(b.checkedAt).getTime() : 0;
    return timeB - timeA;
  });
}

export function filterEvidenceLedger(rows: EvidenceLedgerRow[], filter: EvidenceLedgerFilter): EvidenceLedgerRow[] {
  if (filter === "all") {
    return rows;
  }
  if (filter === "matched") {
    return rows.filter((row) => row.status === "matched");
  }
  if (filter === "needs_verification") {
    return rows.filter(isNeedsVerification);
  }
  return rows.filter(isException);
}

export function evidenceLedgerCounts(rows: EvidenceLedgerRow[]): EvidenceLedgerCounts {
  return {
    exportReady: rows.filter((row) => row.exportable && row.status === "matched").length,
    needsVerification: rows.filter(isNeedsVerification).length,
    exceptions: rows.filter(isException).length,
    total: rows.length,
  };
}

export function resolveEvidenceLedgerDeepLink(
  rows: EvidenceLedgerRow[],
  { actionId, decisionId, traceId, callId }: DeepLinkInput,
): EvidenceLedgerRow | null {
  if (actionId) {
    return rows.find((row) => row.actionId === actionId) ?? null;
  }
  if (decisionId) {
    return rows.find((row) => row.decisionId === decisionId) ?? null;
  }
  if (traceId) {
    return rows.find((row) => row.traceId === traceId) ?? null;
  }
  if (callId) {
    return rows.find((row) => row.callId === callId) ?? null;
  }
  return null;
}
