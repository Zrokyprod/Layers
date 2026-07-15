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

export type ActionLifecycleRowKind = "action_intent" | "orphan_decision" | "bypass_mutation";

export type ActionLifecycleFilter =
  | "all"
  | "needs_action"
  | "awaiting_runner"
  | "in_progress"
  | "completed"
  | "stopped"
  | "bypassed";

export type ActionLifecycleStageId =
  | "proposed"
  | "policy"
  | "approval"
  | "authorized"
  | "execution"
  | "verification"
  | "receipted"
  | "blocked"
  | "bypassed"
  | "awaiting_runner"
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
  agentIdentityKnown: boolean;
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
  verificationIssue: {
    title: string;
    detail: string;
    fields: Array<{ field: string; claimed: string; actual: string }>;
  } | null;
  bypassDetail: {
    title: string;
    detail: string;
    classification: string;
    actor: string;
  } | null;
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
  mutation: SourceMutationView | null;
  proofChain: ProofChainStep[];
};

export type ActionLifecycleCounts = {
  total: number;
  protectedActions: number;
  guardOnly: number;
  needsAction: number;
  held: number;
  awaitingRunner: number;
  inProgress: number;
  executing: number;
  completed: number;
  stopped: number;
  mismatched: number;
  notVerified: number;
  stalled: number;
  bypassed: number;
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

function fieldValue(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
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

function mutationMatchesKnownAction(
  mutation: SourceMutationView,
  knownActionIds: Set<string>,
  knownReceipts: Set<string>,
): boolean {
  return Boolean(
    (mutation.zroky_action_id && knownActionIds.has(mutation.zroky_action_id)) ||
      (mutation.action_receipt_id && knownReceipts.has(mutation.action_receipt_id)),
  );
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

const UNKNOWN_AGENT_NAMES = new Set([
  "",
  "unknown",
  "unknown agent",
  "unknown-agent",
  "unknown_agent",
  "unidentified",
  "unidentified runtime",
]);

function agentIdentity(value: string | null | undefined, fallback = "Unidentified runtime") {
  const name = value?.trim() ?? "";
  return UNKNOWN_AGENT_NAMES.has(name.toLowerCase())
    ? { name: fallback, known: false }
    : { name, known: true };
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
        id: "awaiting_runner",
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

function verificationIssueForOutcome(outcome: OutcomeReconciliationView | null): ActionLifecycleRow["verificationIssue"] {
  if (!outcome || (outcome.verdict !== "mismatched" && outcome.verification_status !== "mismatched")) {
    return null;
  }
  const claimed = recordFrom(outcome.claimed);
  const actual = recordFrom(outcome.actual);
  const comparison = recordFrom(outcome.comparison);
  const mismatchItems = Array.isArray(comparison.mismatches) ? comparison.mismatches : [];
  const fields = mismatchItems
    .map((item) => {
      const field = stringFrom(recordFrom(item).field);
      return field
        ? {
            field,
            claimed: fieldValue(claimed[field]),
            actual: fieldValue(actual[field]),
          }
        : null;
    })
    .filter((item): item is { field: string; claimed: string; actual: string } => Boolean(item));
  const compared = Array.isArray(comparison.compared_fields) ? comparison.compared_fields : [];
  const fallbackFields = fields.length > 0
    ? fields
    : compared
        .map((item) => stringFrom(typeof item === "string" ? item : recordFrom(item).field))
        .filter((field): field is string => Boolean(field))
        .filter((field) => fieldValue(claimed[field]) !== fieldValue(actual[field]))
        .map((field) => ({ field, claimed: fieldValue(claimed[field]), actual: fieldValue(actual[field]) }));

  return {
    title: "Verification failed",
    detail: outcome.reason || "Claimed action result does not match the source of record.",
    fields: fallbackFields.slice(0, 4),
  };
}

function isHeld(row: ActionLifecycleRow): boolean {
  return row.status === "approval_pending" || row.stage.id === "approval";
}

function isExecuting(row: ActionLifecycleRow): boolean {
  return ["planned", "dispatched", "running", "claimed"].includes(normalized(row.attempt?.status));
}

function isMismatched(row: ActionLifecycleRow): boolean {
  return row.proofStatus === "mismatched" || row.status === "mismatched";
}

function isNotVerified(row: ActionLifecycleRow): boolean {
  if (row.kind !== "action_intent" || isStopped(row)) return false;
  const executionFinished = ["succeeded", "success", "completed", "finished"].includes(normalized(row.attempt?.status));
  const verificationExpected = executionFinished || row.outcome != null || row.stage.id === "verification";
  return verificationExpected && ["not_verified", "pending", "missing", "not_started"].includes(row.proofStatus);
}

function isBypassed(row: ActionLifecycleRow): boolean {
  return row.kind === "bypass_mutation";
}

function isAwaitingRunner(row: ActionLifecycleRow): boolean {
  return ["awaiting_runner", "no_runner", "execution_stalled"].includes(row.stage.id);
}

function isCompleted(row: ActionLifecycleRow): boolean {
  return row.kind === "action_intent"
    && row.proofStatus === "matched"
    && row.receiptStatus === "generated";
}

function isStopped(row: ActionLifecycleRow): boolean {
  return row.stage.id === "blocked"
    || ["blocked", "denied", "expired", "rejected"].includes(normalized(row.status))
    || ["failed", "ambiguous", "dead", "cancelled", "timed_out"].includes(normalized(row.attempt?.status));
}

function isInProgress(row: ActionLifecycleRow): boolean {
  if (row.kind !== "action_intent" || isCompleted(row) || isStopped(row)) return false;
  return [
    "proposed",
    "policy",
    "approval",
    "authorized",
    "awaiting_runner",
    "no_runner",
    "execution_stalled",
    "execution",
    "verification",
  ].includes(row.stage.id);
}

function isNeedsAction(row: ActionLifecycleRow): boolean {
  return row.kind === "orphan_decision"
    || isBypassed(row)
    || isHeld(row)
    || isAwaitingRunner(row)
    || isMismatched(row)
    || isNotVerified(row)
    || ["failed", "ambiguous", "dead", "cancelled", "timed_out"].includes(normalized(row.attempt?.status));
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

function titleForMutation(mutation: SourceMutationView): string {
  return `Bypass: ${mutation.system_ref ?? mutation.resource_id ?? mutation.mutation_id}`;
}

function proofChainForBypass(mutation: SourceMutationView): ProofChainStep[] {
  return [
    { step: "action", label: "Action", status: "No Zroky intent", detail: "No protected action intent is linked.", tone: "danger" },
    { step: "policy", label: "Policy", status: "Bypassed", detail: "The runtime policy gate did not see this mutation.", tone: "danger" },
    { step: "execution", label: "Execution", status: "Source mutation", detail: mutation.source_system, tone: "warning" },
    { step: "verification", label: "Verification", status: humanize(mutation.classification), detail: "Source mutation needs receipt matching or exception review.", tone: "warning" },
    { step: "receipt", label: "Receipt", status: "Missing", detail: "No Zroky receipt is attached.", tone: "danger" },
  ];
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
  mutations = [],
}: BuildActionLifecycleInput): ActionLifecycleRow[] {
  const rows: ActionLifecycleRow[] = [];
  const actionDecisionIds = new Set(
    intents.map((intent) => intent.runtime_policy_decision_id).filter((id): id is string => Boolean(id)),
  );
  const actionIds = new Set(intents.map((intent) => intent.action_id));
  const receiptIds = new Set(intents.map((intent) => intent.action_id).filter(Boolean));
  const decisionById = new Map(decisions.map((decision) => [decision.id, decision]));
  const { byDecision, byIdempotency } = buildOutcomeIndexes(outcomes);
  const attemptsByAction = buildAttemptIndex(attempts);
  const staleIds = new Set(staleAttemptIds);

  let linkedDecisionAdded = true;
  while (linkedDecisionAdded) {
    linkedDecisionAdded = false;
    for (const decision of decisions) {
      const consumedBy = decision.consumed_by_decision_id;
      if (!consumedBy || (!actionDecisionIds.has(decision.id) && !actionDecisionIds.has(consumedBy))) continue;
      if (!actionDecisionIds.has(decision.id)) {
        actionDecisionIds.add(decision.id);
        linkedDecisionAdded = true;
      }
      if (!actionDecisionIds.has(consumedBy)) {
        actionDecisionIds.add(consumedBy);
        linkedDecisionAdded = true;
      }
    }
  }

  for (const intent of intents) {
    const decision = intent.runtime_policy_decision_id ? decisionById.get(intent.runtime_policy_decision_id) ?? null : null;
    const outcome = latestOutcomeForIntent(intent, byDecision, byIdempotency);
    const attempt = latestAttemptForAction(intent.action_id, attemptsByAction);
    const view = buildActionView(intent, {
      decision,
      outcomes: outcome ? [outcome] : [],
    });
    const status = statusForIntent(intent);
    const stage = stageForAttempt(view, attempt, staleIds);
    const stoppedBeforeExecution = stage.id === "blocked";
    const waitingBeforeExecution = ["proposed", "policy", "approval", "awaiting_runner", "no_runner"].includes(stage.id);
    const proofStatus = stoppedBeforeExecution ? "not_required" : waitingBeforeExecution ? "not_started" : view.proofStatus;
    const receiptStatus = stoppedBeforeExecution ? "evidence_only" : waitingBeforeExecution ? "not_generated" : view.receiptStatus;
    const proofChain = buildProofChain(view, { attempt, decision, outcome }).map((step) => {
      if (!waitingBeforeExecution) return step;
      if (step.step === "verification") {
        return {
          ...step,
          status: "Not started",
          tone: "neutral" as const,
          detail: "Verification starts only after a protected execution.",
        };
      }
      if (step.step === "receipt") {
        return {
          ...step,
          status: "Not generated",
          tone: "neutral" as const,
          detail: "A receipt can be generated only after protected execution.",
        };
      }
      return step;
    });
    const agent = agentIdentity(view.agentName);

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
      agentName: agent.name,
      agentIdentityKnown: agent.known,
      actionType: view.actionType,
      operationKind: view.operationKind,
      environment: view.environment,
      digest: view.digest,
      systemRef: view.systemRef,
      ...rowStatus(status),
      proofStatus,
      proofLabel: stoppedBeforeExecution ? "Not required" : waitingBeforeExecution ? "Not started" : view.proofLabel,
      proofTone: stoppedBeforeExecution || waitingBeforeExecution ? "neutral" : view.proofTone,
      receiptStatus,
      receiptLabel: stoppedBeforeExecution ? "Evidence only" : waitingBeforeExecution ? "Not generated" : view.receiptLabel,
      receiptTone: stoppedBeforeExecution || waitingBeforeExecution ? "neutral" : view.receiptTone,
      stage: {
        ...stage,
        tone: rowTone(status, stage),
      },
      sourceLabel: "Action Intent",
      verificationIssue: verificationIssueForOutcome(outcome),
      bypassDetail: null,
      createdAt: intent.created_at,
      updatedAt: attempt?.updated_at ?? outcome?.checked_at ?? intent.authorized_at ?? intent.decided_at ?? intent.created_at,
      hrefs: {
        action: `/actions?action_id=${encodeURIComponent(intent.action_id)}`,
        approvals: intent.runtime_policy_decision_id
          ? `/approvals?decision_id=${encodeURIComponent(intent.runtime_policy_decision_id)}`
          : null,
        outcomes: outcome?.id ? `/outcomes?check_id=${encodeURIComponent(outcome.id)}` : "/outcomes",
        evidence: `/evidence?action_id=${encodeURIComponent(intent.action_id)}`,
      },
      view,
      intent,
      decision,
      outcome,
      attempt,
      mutation: null,
      proofChain,
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
    const agent = agentIdentity(decision.agent_name);

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
      agentName: agent.name,
      agentIdentityKnown: agent.known,
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
      verificationIssue: verificationIssueForOutcome(outcome),
      bypassDetail: null,
      createdAt: decision.created_at,
      updatedAt: outcome?.checked_at ?? decision.resolved_at ?? decision.created_at,
      hrefs: {
        action: null,
        approvals: `/approvals?decision_id=${encodeURIComponent(decision.id)}`,
        outcomes: outcome?.id ? `/outcomes?check_id=${encodeURIComponent(outcome.id)}` : "/outcomes",
        evidence: `/evidence?decision_id=${encodeURIComponent(decision.id)}`,
      },
      view: null,
      intent: null,
      decision,
      outcome,
      attempt: null,
      mutation: null,
      proofChain: buildGuardOnlyProofChain(decision, outcome),
    });
  }

  for (const mutation of mutations) {
    if (mutationMatchesKnownAction(mutation, actionIds, receiptIds)) {
      continue;
    }
    const actor = [mutation.actor_type, mutation.actor_id].filter(Boolean).join(":") || "Unknown actor";
    const actorIdentity = agentIdentity(actor, "Unidentified actor");
    rows.push({
      id: `mutation:${mutation.id}`,
      kind: "bypass_mutation",
      actionId: null,
      decisionId: null,
      outcomeId: null,
      attemptId: null,
      traceId: null,
      callId: null,
      title: titleForMutation(mutation),
      agentName: actorIdentity.name,
      agentIdentityKnown: actorIdentity.known,
      actionType: humanize(mutation.action_type ?? mutation.resource_type, "Source mutation"),
      operationKind: null,
      environment: null,
      digest: null,
      systemRef: mutation.system_ref ?? mutation.resource_id ?? mutation.mutation_id,
      ...rowStatus("policy_bypass"),
      proofStatus: "not_verified",
      proofLabel: "Bypass",
      proofTone: "danger",
      receiptStatus: "missing",
      receiptLabel: "No receipt",
      receiptTone: "danger",
      stage: {
        id: "bypassed",
        label: "Bypassed control",
        detail: "Source-of-record mutation has no matching Zroky action intent or receipt.",
        tone: "danger",
      },
      sourceLabel: "Source Mutation",
      verificationIssue: null,
      bypassDetail: {
        title: "Control bypass detected",
        detail: "The source system changed without a matching protected action receipt.",
        classification: mutation.classification,
        actor,
      },
      createdAt: mutation.occurred_at,
      updatedAt: mutation.created_at,
      hrefs: {
        action: null,
        approvals: null,
        outcomes: "/outcomes",
        evidence: "/evidence",
      },
      view: null,
      intent: null,
      decision: null,
      outcome: null,
      attempt: null,
      mutation,
      proofChain: proofChainForBypass(mutation),
    });
  }

  return rows.sort((a, b) => {
    const rank = { bypass_mutation: 0, action_intent: 1, orphan_decision: 2 } satisfies Record<ActionLifecycleRowKind, number>;
    if (rank[a.kind] !== rank[b.kind]) return rank[a.kind] - rank[b.kind];
    return latestRowTime(b) - latestRowTime(a);
  });
}

export function filterActionLifecycle(
  rows: ActionLifecycleRow[],
  filter: ActionLifecycleFilter,
): ActionLifecycleRow[] {
  if (filter === "all") return rows;
  if (filter === "needs_action") return rows.filter(isNeedsAction);
  if (filter === "awaiting_runner") return rows.filter(isAwaitingRunner);
  if (filter === "in_progress") return rows.filter(isInProgress);
  if (filter === "completed") return rows.filter(isCompleted);
  if (filter === "stopped") return rows.filter(isStopped);
  if (filter === "bypassed") return rows.filter(isBypassed);
  return rows;
}

export function actionLifecycleCounts(rows: ActionLifecycleRow[]): ActionLifecycleCounts {
  return {
    total: rows.length,
    protectedActions: rows.filter((row) => row.kind === "action_intent").length,
    guardOnly: rows.filter((row) => row.kind === "orphan_decision").length,
    needsAction: rows.filter(isNeedsAction).length,
    held: rows.filter(isHeld).length,
    awaitingRunner: rows.filter(isAwaitingRunner).length,
    inProgress: rows.filter(isInProgress).length,
    executing: rows.filter(isExecuting).length,
    completed: rows.filter(isCompleted).length,
    stopped: rows.filter(isStopped).length,
    mismatched: rows.filter(isMismatched).length,
    notVerified: rows.filter(isNotVerified).length,
    stalled: rows.filter((row) => row.stage.id === "no_runner" || row.stage.id === "execution_stalled").length,
    bypassed: rows.filter(isBypassed).length,
  };
}
