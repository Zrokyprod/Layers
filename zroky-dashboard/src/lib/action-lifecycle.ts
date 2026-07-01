import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
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

export type ActionLifecycleRowKind = "action_intent" | "orphan_decision";

export type ActionLifecycleFilter = "all" | "held" | "executing" | "mismatched" | "not_verified";

export type ActionLifecycleStageId =
  | "proposed"
  | "policy"
  | "approval"
  | "authorized"
  | "execution"
  | "verification"
  | "receipted"
  | "blocked"
  | "no_runner"
  | "execution_stalled"
  | "guard_only";

export type ActionLifecycleStage = {
  id: ActionLifecycleStageId;
  label: string;
  detail: string;
  tone: StatusTone;
};

export type ActionLifecycleRow = {
  id: string;
  kind: ActionLifecycleRowKind;
  actionId: string | null;
  decisionId: string | null;
  outcomeId: string | null;
  attemptId: string | null;
  traceId: string | null;
  callId: string | null;
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
  proofStatus: string;
  proofLabel: string;
  proofTone: StatusTone;
  receiptStatus: string;
  receiptLabel: string;
  receiptTone: StatusTone;
  stage: ActionLifecycleStage;
  sourceLabel: string;
  createdAt: string | null;
  updatedAt: string | null;
  hrefs: {
    action: string | null;
    approvals: string | null;
    outcomes: string | null;
    evidence: string | null;
  };
  view: ActionView | null;
  intent: ActionIntentResponse | null;
  decision: RuntimePolicyDecisionResponse | null;
  outcome: OutcomeReconciliationView | null;
  attempt: ActionExecutionAttemptResponse | null;
  proofChain: ProofChainStep[];
};

export type ActionLifecycleCounts = {
  total: number;
  protectedActions: number;
  guardOnly: number;
  held: number;
  executing: number;
  mismatched: number;
  notVerified: number;
  stalled: number;
};

type BuildActionLifecycleInput = {
  intents: ActionIntentResponse[];
  decisions: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  attempts?: ActionExecutionAttemptResponse[];
  staleAttemptIds?: string[];
  mutations?: SourceMutationView[];
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

function latestAttemptForAction(
  actionId: string,
  attemptsByAction: Map<string, ActionExecutionAttemptResponse[]>,
): ActionExecutionAttemptResponse | null {
  return latestByDate(attemptsByAction.get(actionId) ?? [], (attempt) => (
    attempt.finished_at ?? attempt.started_at ?? attempt.updated_at ?? attempt.created_at
  ));
}

function buildAttemptIndex(attempts: ActionExecutionAttemptResponse[]): Map<string, ActionExecutionAttemptResponse[]> {
  const byAction = new Map<string, ActionExecutionAttemptResponse[]>();
  for (const attempt of attempts) {
    byAction.set(attempt.action_id, [...(byAction.get(attempt.action_id) ?? []), attempt]);
  }
  return byAction;
}

function canonicalTraceContext(intent: ActionIntentResponse): Record<string, unknown> {
  return recordFrom(recordFrom(intent.canonical_intent).trace_context);
}

function traceIdForIntent(
  intent: ActionIntentResponse,
  decision: RuntimePolicyDecisionResponse | null,
  outcome: OutcomeReconciliationView | null,
): string | null {
  return outcome?.trace_id ?? decision?.trace_id ?? stringFrom(canonicalTraceContext(intent).trace_id);
}

function callIdForIntent(
  intent: ActionIntentResponse,
  decision: RuntimePolicyDecisionResponse | null,
  outcome: OutcomeReconciliationView | null,
): string | null {
  return outcome?.call_id ?? decision?.call_id ?? stringFrom(canonicalTraceContext(intent).call_id);
}

function statusForIntent(intent: ActionIntentResponse): string {
  if (intent.proof_status === "mismatched" || intent.proof_status === "not_verified") {
    return intent.proof_status;
  }
  if (intent.status === "approval_pending" || intent.status === "denied" || intent.status === "expired") {
    return intent.status;
  }
  if (intent.proof_status === "matched" && intent.receipt_status === "generated") {
    return "matched";
  }
  if (intent.receipt_status === "failed" || intent.receipt_status === "missing") {
    return intent.receipt_status;
  }
  if (intent.proof_status === "pending" || intent.receipt_status === "pending") {
    return "pending";
  }
  return intent.status || intent.proof_status || "not_started";
}

function statusForDecision(
  decision: RuntimePolicyDecisionResponse,
  outcome: OutcomeReconciliationView | null,
): string {
  if (outcome?.verdict) {
    return outcome.verdict;
  }
  if (decision.status === "approved" || decision.status === "allowed") {
    return "not_verified";
  }
  return decision.status;
}

function rowStatus(value: string): Pick<ActionLifecycleRow, "status" | "statusLabel" | "statusTone"> {
  return {
    status: value,
    statusLabel: statusLabel(value),
    statusTone: statusTone(value),
  };
}

function toLifecycleStage(view: ActionView): ActionLifecycleStage {
  return {
    id: view.lifecycle.id,
    label: view.lifecycle.label,
    detail: view.lifecycle.detail,
    tone: view.lifecycle.tone,
  };
}

function normalized(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function stageForAttempt(
  view: ActionView,
  attempt: ActionExecutionAttemptResponse | null,
  staleAttemptIds: Set<string>,
): ActionLifecycleStage {
  const base = toLifecycleStage(view);
  if (!attempt) {
    if (view.status === "authorized" && ["not_started", "pending"].includes(view.proofStatus)) {
      return {
        id: "execution",
        label: "Awaiting runner",
        detail: "Action is authorized, but no protected runner attempt is attached yet.",
        tone: "warning",
      };
    }
    return base;
  }

  const status = normalized(attempt.status);
  const stale = staleAttemptIds.has(attempt.attempt_id);
  if (stale && status === "planned") {
    return {
      id: "no_runner",
      label: "No runner claimed",
      detail: "A planned execution attempt passed the claim timeout.",
      tone: "warning",
    };
  }
  if (stale && ["dispatched", "running", "claimed"].includes(status)) {
    return {
      id: "execution_stalled",
      label: "Execution stalled",
      detail: "A runner claimed the action but did not finish within the expected window.",
      tone: "danger",
    };
  }
  if (["planned", "dispatched", "running", "claimed"].includes(status)) {
    return {
      id: "execution",
      label: status === "planned" ? "Runner planned" : "Runner executing",
      detail: `Execution attempt ${attempt.attempt_id} is ${statusLabel(attempt.status).toLowerCase()}.`,
      tone: "warning",
    };
  }
  if (["failed", "ambiguous", "dead", "cancelled", "timed_out"].includes(status)) {
    return {
      id: "execution",
      label: statusLabel(attempt.status),
      detail: `Execution attempt ${attempt.attempt_id} ended as ${statusLabel(attempt.status).toLowerCase()}.`,
      tone: "danger",
    };
  }
  return base;
}

function rowTone(status: string, stage: ActionLifecycleStage): StatusTone {
  const tone = statusTone(status);
  if (tone === "danger" || stage.tone === "danger") return "danger";
  if (tone === "warning" || stage.tone === "warning") return "warning";
  if (tone === "success" || stage.tone === "success") return "success";
  return "neutral";
}

function isHeld(row: ActionLifecycleRow): boolean {
  return row.status === "approval_pending" || row.stage.id === "approval";
}

function isExecuting(row: ActionLifecycleRow): boolean {
  return ["authorized", "execution", "no_runner", "execution_stalled"].includes(row.stage.id);
}

function isMismatched(row: ActionLifecycleRow): boolean {
  return row.proofStatus === "mismatched" || row.status === "mismatched";
}

function isNotVerified(row: ActionLifecycleRow): boolean {
  return ["not_verified", "pending", "missing", "not_started"].includes(row.proofStatus)
    || ["not_verified", "pending", "missing"].includes(row.status);
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

function latestRowTime(row: ActionLifecycleRow): number {
  const raw = row.updatedAt ?? row.createdAt;
  const time = raw ? new Date(raw).getTime() : 0;
  return Number.isFinite(time) ? time : 0;
}

export function buildActionLifecycle({
  intents,
  decisions,
  outcomes,
  attempts = [],
  staleAttemptIds = [],
}: BuildActionLifecycleInput): ActionLifecycleRow[] {
  const rows: ActionLifecycleRow[] = [];
  const actionDecisionIds = new Set<string>();
  const decisionById = new Map(decisions.map((decision) => [decision.id, decision]));
  const { byDecision, byIdempotency } = buildOutcomeIndexes(outcomes);
  const attemptsByAction = buildAttemptIndex(attempts);
  const staleIds = new Set(staleAttemptIds);

  for (const intent of intents) {
    if (intent.runtime_policy_decision_id) {
      actionDecisionIds.add(intent.runtime_policy_decision_id);
    }
    const decision = intent.runtime_policy_decision_id ? decisionById.get(intent.runtime_policy_decision_id) ?? null : null;
    const outcome = latestOutcomeForIntent(intent, byDecision, byIdempotency);
    const attempt = latestAttemptForAction(intent.action_id, attemptsByAction);
    const view = buildActionView(intent, {
      decision,
      outcomes: outcome ? [outcome] : [],
    });
    const status = statusForIntent(intent);
    const stage = stageForAttempt(view, attempt, staleIds);

    rows.push({
      id: `action:${intent.action_id}`,
      kind: "action_intent",
      actionId: intent.action_id,
      decisionId: intent.runtime_policy_decision_id,
      outcomeId: outcome?.id ?? null,
      attemptId: attempt?.attempt_id ?? null,
      traceId: traceIdForIntent(intent, decision, outcome),
      callId: callIdForIntent(intent, decision, outcome),
      title: view.title,
      agentName: view.agentName,
      actionType: view.actionType,
      operationKind: view.operationKind,
      environment: view.environment,
      digest: view.digest,
      systemRef: view.systemRef,
      ...rowStatus(status),
      proofStatus: view.proofStatus,
      proofLabel: view.proofLabel,
      proofTone: view.proofTone,
      receiptStatus: view.receiptStatus,
      receiptLabel: view.receiptLabel,
      receiptTone: view.receiptTone,
      stage: {
        ...stage,
        tone: rowTone(status, stage),
      },
      sourceLabel: "Action Intent",
      createdAt: intent.created_at,
      updatedAt: attempt?.updated_at ?? outcome?.checked_at ?? intent.authorized_at ?? intent.decided_at ?? intent.created_at,
      hrefs: {
        action: `/actions?action_id=${encodeURIComponent(intent.action_id)}`,
        approvals: intent.runtime_policy_decision_id
          ? `/approvals?decision_id=${encodeURIComponent(intent.runtime_policy_decision_id)}`
          : null,
        outcomes: outcome?.id ? `/outcomes?outcome_id=${encodeURIComponent(outcome.id)}` : "/outcomes",
        evidence: `/evidence?action_id=${encodeURIComponent(intent.action_id)}`,
      },
      view,
      intent,
      decision,
      outcome,
      attempt,
      proofChain: buildProofChain(view, { attempt, decision, outcome }),
    });
  }

  for (const decision of decisions) {
    if (actionDecisionIds.has(decision.id)) {
      continue;
    }
    const outcome = latestOutcomeForDecision(decision, byDecision);
    const status = statusForDecision(decision, outcome);
    const proofTone = statusTone(outcome?.verdict ?? "not_verified", "proof");
    const stage: ActionLifecycleStage = {
      id: "guard_only",
      label: "Guard-only decision",
      detail: "This runtime-policy decision was not routed through an Action Intent.",
      tone: rowTone(status, {
        id: "guard_only",
        label: "Guard-only decision",
        detail: "",
        tone: statusTone(status),
      }),
    };

    rows.push({
      id: `decision:${decision.id}`,
      kind: "orphan_decision",
      actionId: null,
      decisionId: decision.id,
      outcomeId: outcome?.id ?? null,
      attemptId: null,
      traceId: outcome?.trace_id ?? decision.trace_id,
      callId: outcome?.call_id ?? decision.call_id,
      title: titleForDecision(decision),
      agentName: decision.agent_name ?? "Guard-only action",
      actionType: humanize(decision.action_type ?? decision.tool_name),
      operationKind: null,
      environment: null,
      digest: null,
      systemRef: outcome?.system_ref ?? decision.call_id ?? decision.trace_id,
      ...rowStatus(status),
      proofStatus: outcome?.verdict ?? "not_verified",
      proofLabel: statusLabel(outcome?.verdict ?? "not_verified", "proof"),
      proofTone,
      receiptStatus: "guard_only",
      receiptLabel: "Evidence Pack",
      receiptTone: "neutral",
      stage,
      sourceLabel: "Guard-only Decision",
      createdAt: decision.created_at,
      updatedAt: outcome?.checked_at ?? decision.resolved_at ?? decision.created_at,
      hrefs: {
        action: null,
        approvals: `/approvals?decision_id=${encodeURIComponent(decision.id)}`,
        outcomes: outcome?.id ? `/outcomes?outcome_id=${encodeURIComponent(outcome.id)}` : "/outcomes",
        evidence: `/evidence?decision_id=${encodeURIComponent(decision.id)}`,
      },
      view: null,
      intent: null,
      decision,
      outcome,
      attempt: null,
      proofChain: buildGuardOnlyProofChain(decision, outcome),
    });
  }

  return rows.sort((a, b) => {
    const rank = { action_intent: 0, orphan_decision: 1 } satisfies Record<ActionLifecycleRowKind, number>;
    if (rank[a.kind] !== rank[b.kind]) return rank[a.kind] - rank[b.kind];
    return latestRowTime(b) - latestRowTime(a);
  });
}

export function filterActionLifecycle(
  rows: ActionLifecycleRow[],
  filter: ActionLifecycleFilter,
): ActionLifecycleRow[] {
  if (filter === "all") return rows;
  if (filter === "held") return rows.filter(isHeld);
  if (filter === "executing") return rows.filter(isExecuting);
  if (filter === "mismatched") return rows.filter(isMismatched);
  return rows.filter(isNotVerified);
}

export function actionLifecycleCounts(rows: ActionLifecycleRow[]): ActionLifecycleCounts {
  return {
    total: rows.length,
    protectedActions: rows.filter((row) => row.kind === "action_intent").length,
    guardOnly: rows.filter((row) => row.kind === "orphan_decision").length,
    held: rows.filter(isHeld).length,
    executing: rows.filter(isExecuting).length,
    mismatched: rows.filter(isMismatched).length,
    notVerified: rows.filter(isNotVerified).length,
    stalled: rows.filter((row) => row.stage.id === "no_runner" || row.stage.id === "execution_stalled").length,
  };
}
