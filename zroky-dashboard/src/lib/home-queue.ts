import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "@/lib/api";
import type { StatusTone } from "@/lib/action-status";
import { buildActionView } from "@/lib/action-view";
import { field, humanize, timeSince, timeUntil } from "@/lib/format";

export type HomeQueueKind =
  | "approval"
  | "guard_approval"
  | "mismatch"
  | "not_verified"
  | "bypass"
  | "unmanaged"
  | "stale_attempt";

export type HomeQueuePriority = "P0" | "P1" | "P2";

export type HomeQueueRow = {
  id: string;
  kind: HomeQueueKind;
  priority: HomeQueuePriority;
  sortScore: number;
  tone: StatusTone;
  title: string;
  agentName: string;
  reason: string;
  detail: string;
  status: string;
  actionLabel: string;
  href: string;
  createdAt: string | null;
  actionId: string | null;
  decisionId: string | null;
};

export type BuildDecisionQueueInput = {
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  mutations: SourceMutationView[];
  staleAttempts: ActionExecutionAttemptResponse[];
  nowMs?: number;
};

function stringFrom(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberFrom(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function amountUsd(decision: RuntimePolicyDecisionResponse): number | null {
  return (
    numberFrom(decision.business_impact.amount_usd) ??
    numberFrom(decision.business_impact.estimated_value_usd) ??
    numberFrom(decision.request.amount_usd) ??
    numberFrom(decision.intended_action.amount_usd)
  );
}

function looksFinancial(decision: RuntimePolicyDecisionResponse): boolean {
  const haystack = [
    decision.action_type,
    decision.tool_name,
    field(decision.intended_action),
    field(decision.business_impact),
    field(decision.request),
  ].join(" ").toLowerCase();
  return ["refund", "payment", "payout", "transfer", "invoice", "credit", "debit", "charge"].some((term) => haystack.includes(term));
}

function isExpiring(decision: RuntimePolicyDecisionResponse, nowMs: number): boolean {
  if (!decision.expires_at) return false;
  const expiresAt = new Date(decision.expires_at).getTime();
  if (!Number.isFinite(expiresAt)) return false;
  return expiresAt - nowMs <= 30 * 60_000;
}

function decisionTitle(decision: RuntimePolicyDecisionResponse): string {
  return (
    stringFrom(decision.intended_action.summary) ??
    stringFrom(decision.tool_name) ??
    stringFrom(decision.action_type) ??
    decision.id
  );
}

function decisionAgent(decision: RuntimePolicyDecisionResponse): string {
  return decision.agent_name ?? stringFrom(decision.request.agent_name) ?? "Guard-only action";
}

function mutationTitle(mutation: SourceMutationView): string {
  return mutation.system_ref ?? mutation.resource_id ?? mutation.mutation_id;
}

function ageDetail(value: string | null, nowMs: number): string {
  return value ? timeSince(value, nowMs) : "-";
}

function addIfUnique(rows: HomeQueueRow[], row: HomeQueueRow, queuedActionIds: Set<string>) {
  if (row.actionId) {
    queuedActionIds.add(row.actionId);
  }
  rows.push(row);
}

export function buildDecisionQueue({
  intents,
  approvals,
  outcomes,
  mutations,
  staleAttempts,
  nowMs = Date.now(),
}: BuildDecisionQueueInput): HomeQueueRow[] {
  const rows: HomeQueueRow[] = [];
  const queuedActionIds = new Set<string>();
  const intentByDecision = new Map<string, ActionIntentResponse>();
  const intentById = new Map<string, ActionIntentResponse>();

  for (const intent of intents) {
    intentById.set(intent.action_id, intent);
    if (intent.runtime_policy_decision_id) {
      intentByDecision.set(intent.runtime_policy_decision_id, intent);
    }
  }

  for (const outcome of outcomes) {
    if (outcome.verdict !== "mismatched") continue;
    const linkedIntent = outcome.runtime_policy_decision_id ? intentByDecision.get(outcome.runtime_policy_decision_id) ?? null : null;
    addIfUnique(rows, {
      id: `mismatch:${outcome.id}`,
      kind: "mismatch",
      priority: "P0",
      sortScore: 0,
      tone: "danger",
      title: linkedIntent ? buildActionView(linkedIntent, { outcomes: [outcome] }).title : outcome.system_ref ?? humanize(outcome.action_type) ?? "Mismatched action",
      agentName: linkedIntent ? buildActionView(linkedIntent).agentName : "Unlinked action",
      reason: "Source-of-record mismatch",
      detail: outcome.reason ? humanize(outcome.reason) : `${outcome.connector_type} did not match the claimed outcome.`,
      status: outcome.verdict,
      actionLabel: "Review proof",
      href: "/outcomes",
      createdAt: outcome.checked_at,
      actionId: linkedIntent?.action_id ?? null,
      decisionId: outcome.runtime_policy_decision_id,
    }, queuedActionIds);
  }

  for (const mutation of mutations) {
    if (!["policy_bypass", "unmanaged_agent_action"].includes(mutation.classification)) continue;
    const isBypass = mutation.classification === "policy_bypass";
    addIfUnique(rows, {
      id: `mutation:${mutation.id}`,
      kind: isBypass ? "bypass" : "unmanaged",
      priority: isBypass ? "P0" : "P1",
      sortScore: isBypass ? 1 : 40,
      tone: isBypass ? "danger" : "warning",
      title: mutationTitle(mutation),
      agentName: mutation.actor_id ?? mutation.actor_type ?? "Unknown actor",
      reason: isBypass ? "Policy bypass mutation" : "Unmanaged agent action",
      detail: `${humanize(mutation.source_system)} / ${humanize(mutation.action_type ?? mutation.resource_type)}`,
      status: mutation.classification,
      actionLabel: "Review bypass",
      href: "/outcomes",
      createdAt: mutation.occurred_at,
      actionId: mutation.zroky_action_id,
      decisionId: null,
    }, queuedActionIds);
  }

  for (const approval of approvals) {
    if (approval.status !== "pending_approval") continue;
    const intent = intentByDecision.get(approval.id) ?? null;
    const highRisk = looksFinancial(approval) || amountUsd(approval) != null || isExpiring(approval, nowMs);
    const priority: HomeQueuePriority = highRisk ? "P0" : "P1";
    const expiring = isExpiring(approval, nowMs);
    addIfUnique(rows, {
      id: `${intent ? "approval" : "guard"}:${approval.id}`,
      kind: intent ? "approval" : "guard_approval",
      priority,
      sortScore: highRisk ? 2 : 30,
      tone: "warning",
      title: intent ? buildActionView(intent, { decision: approval }).title : decisionTitle(approval),
      agentName: intent ? buildActionView(intent).agentName : decisionAgent(approval),
      reason: expiring ? "Approval expiring" : intent ? "Action held for approval" : "Guard-only approval hold",
      detail: approval.reasons[0] ?? (approval.expires_at ? `Expires ${timeUntil(approval.expires_at, nowMs)}` : "Human decision required."),
      status: approval.status,
      actionLabel: "Review",
      href: `/approvals?decision_id=${encodeURIComponent(approval.id)}`,
      createdAt: approval.created_at,
      actionId: intent?.action_id ?? null,
      decisionId: approval.id,
    }, queuedActionIds);
  }

  for (const intent of intents) {
    if (queuedActionIds.has(intent.action_id)) continue;
    if (intent.proof_status !== "not_verified") continue;
    const view = buildActionView(intent);
    addIfUnique(rows, {
      id: `not_verified:${intent.action_id}`,
      kind: "not_verified",
      priority: "P1",
      sortScore: 50,
      tone: "warning",
      title: view.title,
      agentName: view.agentName,
      reason: "Proof not verified",
      detail: `${view.statusLabel} / ${view.receiptLabel}`,
      status: intent.proof_status,
      actionLabel: "Open action",
      href: `/actions?action_id=${encodeURIComponent(intent.action_id)}`,
      createdAt: intent.created_at,
      actionId: intent.action_id,
      decisionId: intent.runtime_policy_decision_id,
    }, queuedActionIds);
  }

  for (const attempt of staleAttempts) {
    if (queuedActionIds.has(attempt.action_id)) continue;
    const intent = intentById.get(attempt.action_id) ?? null;
    const view = intent ? buildActionView(intent) : null;
    addIfUnique(rows, {
      id: `stale:${attempt.attempt_id}`,
      kind: "stale_attempt",
      priority: "P2",
      sortScore: 80,
      tone: "neutral",
      title: view?.title ?? attempt.action_id,
      agentName: view?.agentName ?? attempt.runner_id,
      reason: attempt.status === "planned" ? "No runner claimed execution" : "Runner did not finish",
      detail: `Attempt ${attempt.attempt_number} ${attempt.status} / ${ageDetail(attempt.updated_at, nowMs)}`,
      status: attempt.status,
      actionLabel: "Open action",
      href: `/actions?action_id=${encodeURIComponent(attempt.action_id)}`,
      createdAt: attempt.updated_at,
      actionId: attempt.action_id,
      decisionId: intent?.runtime_policy_decision_id ?? null,
    }, queuedActionIds);
  }

  return rows.sort((a, b) => {
    if (a.sortScore !== b.sortScore) return a.sortScore - b.sortScore;
    const timeA = a.createdAt ? new Date(a.createdAt).getTime() : 0;
    const timeB = b.createdAt ? new Date(b.createdAt).getTime() : 0;
    return timeB - timeA;
  });
}

export function homeVerdictForQueue(
  rows: HomeQueueRow[],
  hasSetup: boolean,
  missingControl?: { detail: string; href: string },
): {
  title: string;
  detail: string;
  tone: StatusTone;
  ctaLabel: string;
  ctaHref: string;
} {
  if (!hasSetup) {
    return {
      title: "Setup required",
      detail: "Protect your first agent action before trusting production autonomy.",
      tone: "neutral",
      ctaLabel: "Set up agent",
      ctaHref: "/agents/setup",
    };
  }
  const first = rows[0];
  if (!first) {
    if (missingControl) {
      return {
        title: "Control coverage incomplete",
        detail: missingControl.detail,
        tone: "warning",
        ctaLabel: "Complete control",
        ctaHref: missingControl.href,
      };
    }
    return {
      title: "Protected",
      detail: "No agent action needs your decision right now.",
      tone: "success",
      ctaLabel: "View actions",
      ctaHref: "/actions",
    };
  }
  if (first.priority === "P0") {
    return {
      title: first.kind === "mismatch" ? "Action mismatch" : first.kind === "bypass" ? "Action blocked / bypass risk" : "Needs decision",
      detail: first.reason,
      tone: first.tone,
      ctaLabel: first.actionLabel,
      ctaHref: first.href,
    };
  }
  return {
    title: "Needs decision",
    detail: first.reason,
    tone: first.tone,
    ctaLabel: first.actionLabel,
    ctaHref: first.href,
  };
}

export function queueCounts(rows: HomeQueueRow[]) {
  return {
    all: rows.length,
    needsDecision: rows.filter((row) => ["approval", "guard_approval", "mismatch", "not_verified", "stale_attempt"].includes(row.kind)).length,
    bypass: rows.filter((row) => ["bypass", "unmanaged"].includes(row.kind)).length,
  };
}
