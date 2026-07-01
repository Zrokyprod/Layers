import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionReceiptResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";
import {
  lifecycleStage,
  statusLabel,
  statusTone,
  type LifecycleStage,
  type StatusTone,
} from "@/lib/action-status";
import { humanize } from "@/lib/format";

export type ActionView = {
  actionId: string;
  title: string;
  agentName: string;
  actionType: string;
  operationKind: string;
  environment: string;
  digest: string;
  status: string;
  statusLabel: string;
  statusTone: StatusTone;
  proofStatus: string;
  proofLabel: string;
  proofTone: StatusTone;
  receiptStatus: string;
  receiptLabel: string;
  receiptTone: StatusTone;
  lifecycle: LifecycleStage;
  systemRef: string;
  createdAt: string;
  linkedDecisionId: string | null;
  decision: RuntimePolicyDecisionResponse | null;
  outcome: OutcomeReconciliationView | null;
  receipt: ActionReceiptResponse | null;
  signatureValid: boolean | null;
};

export type ProofChainStepId = "action" | "policy" | "execution" | "verification" | "receipt";

export type ProofChainStep = {
  step: ProofChainStepId;
  label: string;
  status: string;
  tone: StatusTone;
  detail: string;
};

type BuildActionViewOptions = {
  decision?: RuntimePolicyDecisionResponse | null;
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  receipt?: ActionReceiptResponse | null;
};

type BuildProofChainOptions = {
  attempt?: ActionExecutionAttemptResponse | null;
  decision?: RuntimePolicyDecisionResponse | null;
  outcome?: OutcomeReconciliationView | null;
  receipt?: ActionReceiptResponse | null;
};

function recordFrom(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function listFrom(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => item != null && typeof item === "object" && !Array.isArray(item)) : [];
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

function normalized(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function attemptTone(status: string | null | undefined): StatusTone {
  const value = normalized(status);
  if (["failed", "ambiguous", "dead", "cancelled", "timed_out"].includes(value)) {
    return "danger";
  }
  if (["succeeded", "success", "completed", "finished"].includes(value)) {
    return "success";
  }
  if (["planned", "dispatched", "claimed", "running", "started"].includes(value)) {
    return "warning";
  }
  return "neutral";
}

function executionStatusForAttempt(attempt: ActionExecutionAttemptResponse | null | undefined): ProofChainStep {
  if (!attempt) {
    return {
      step: "execution",
      label: "Execution",
      status: "Awaiting runner",
      tone: "warning",
      detail: "No protected runner execution attempt is attached yet.",
    };
  }
  const status = attempt.status || "unknown";
  return {
    step: "execution",
    label: "Execution",
    status: statusLabel(status),
    tone: attemptTone(status),
    detail: attempt.runner_id
      ? `Runner ${attempt.runner_id} reported ${statusLabel(status).toLowerCase()}.`
      : `Execution attempt ${attempt.attempt_id} reported ${statusLabel(status).toLowerCase()}.`,
  };
}

function titleForIntent(intent: ActionIntentResponse): string {
  const canonical = recordFrom(intent.canonical_intent);
  const purpose = recordFrom(canonical.purpose);
  const resource = recordFrom(canonical.resource);
  return (
    stringFrom(purpose.summary) ??
    stringFrom(purpose.code) ??
    stringFrom(resource.id) ??
    `${humanize(intent.action_type)} ${intent.action_id.slice(0, 8)}`
  );
}

function agentForIntent(intent: ActionIntentResponse): string {
  if (intent.agent_profile?.display_name) {
    return intent.agent_profile.display_name;
  }
  const canonical = recordFrom(intent.canonical_intent);
  const principal = recordFrom(canonical.principal);
  const traceContext = recordFrom(canonical.trace_context);
  const actorChain = listFrom(canonical.actor_chain);
  return (
    stringFrom(traceContext.agent_name) ??
    stringFrom(principal.id) ??
    stringFrom(actorChain[0]?.id) ??
    stringFrom(actorChain[0]?.name) ??
    "Unknown agent"
  );
}

function systemRefForIntent(intent: ActionIntentResponse, outcome: OutcomeReconciliationView | null): string {
  if (outcome?.system_ref) {
    return outcome.system_ref;
  }
  const canonical = recordFrom(intent.canonical_intent);
  const resource = recordFrom(canonical.resource);
  return stringFrom(resource.id) ?? intent.action_id;
}

function resolveDecision(
  intent: ActionIntentResponse,
  options: BuildActionViewOptions,
): RuntimePolicyDecisionResponse | null {
  if (options.decision) {
    return options.decision;
  }
  if (!options.decisions?.length || !intent.runtime_policy_decision_id) {
    return null;
  }
  return options.decisions.find((decision) => decision.id === intent.runtime_policy_decision_id) ?? null;
}

function resolveOutcome(
  intent: ActionIntentResponse,
  decision: RuntimePolicyDecisionResponse | null,
  outcomes: OutcomeReconciliationView[] | undefined,
): OutcomeReconciliationView | null {
  const rows = outcomes ?? [];
  if (rows.length === 0) {
    return null;
  }
  const linkedDecisionIds = new Set(
    [intent.runtime_policy_decision_id, decision?.id].filter(
      (value): value is string => typeof value === "string" && value.length > 0,
    ),
  );
  const byDecision = rows.filter((outcome) => Boolean(outcome.runtime_policy_decision_id && linkedDecisionIds.has(outcome.runtime_policy_decision_id)));
  if (byDecision.length > 0) {
    return latestByDate(byDecision, (outcome) => outcome.checked_at);
  }
  const byIdempotency = rows.filter((outcome) => outcome.idempotency_key === intent.idempotency_key);
  if (byIdempotency.length > 0) {
    return latestByDate(byIdempotency, (outcome) => outcome.checked_at);
  }
  return null;
}

export function buildActionView(
  intent: ActionIntentResponse,
  options: BuildActionViewOptions = {},
): ActionView {
  const decision = resolveDecision(intent, options);
  const outcome = resolveOutcome(intent, decision, options.outcomes);
  const lifecycle = lifecycleStage(intent);
  return {
    actionId: intent.action_id,
    title: titleForIntent(intent),
    agentName: agentForIntent(intent),
    actionType: humanize(intent.action_type),
    operationKind: intent.operation_kind,
    environment: intent.environment,
    digest: intent.intent_digest,
    status: intent.status,
    statusLabel: statusLabel(intent.status, "intent"),
    statusTone: statusTone(intent.status, "intent"),
    proofStatus: intent.proof_status,
    proofLabel: statusLabel(intent.proof_status, "proof"),
    proofTone: statusTone(intent.proof_status, "proof"),
    receiptStatus: intent.receipt_status,
    receiptLabel: statusLabel(intent.receipt_status, "receipt"),
    receiptTone: statusTone(intent.receipt_status, "receipt"),
    lifecycle,
    systemRef: systemRefForIntent(intent, outcome),
    createdAt: intent.created_at,
    linkedDecisionId: intent.runtime_policy_decision_id,
    decision,
    outcome,
    receipt: options.receipt ?? null,
    signatureValid: options.receipt?.signature_valid ?? null,
  };
}

export function buildProofChain(
  view: ActionView,
  options: BuildProofChainOptions = {},
): ProofChainStep[] {
  const decision = options.decision ?? view.decision;
  const outcome = options.outcome ?? view.outcome;
  const receipt = options.receipt ?? view.receipt;
  const receiptStatus = receipt
    ? receipt.signature_valid
      ? view.receiptStatus || "generated"
      : "signature_invalid"
    : view.receiptStatus;

  return [
    {
      step: "action",
      label: "Action",
      status: view.statusLabel,
      tone: view.statusTone,
      detail: `Intent digest ${view.digest}.`,
    },
    {
      step: "policy",
      label: "Policy",
      status: decision ? statusLabel(decision.status, "runtime_policy") : statusLabel(view.status, "intent"),
      tone: decision ? statusTone(decision.status, "runtime_policy") : view.statusTone,
      detail: decision
        ? `Runtime policy decision ${decision.id}.`
        : "No linked runtime-policy decision was returned with this action.",
    },
    executionStatusForAttempt(options.attempt),
    {
      step: "verification",
      label: "Verification",
      status: outcome ? statusLabel(outcome.verdict, "proof") : view.proofLabel,
      tone: outcome ? statusTone(outcome.verdict, "proof") : view.proofTone,
      detail: outcome
        ? `Source-of-record verdict from ${outcome.connector_type}.`
        : "No independent source-of-record outcome is linked yet.",
    },
    {
      step: "receipt",
      label: "Receipt",
      status: receipt?.signature_valid === false ? "Signature invalid" : statusLabel(receiptStatus, "receipt"),
      tone: receipt?.signature_valid === false ? "danger" : statusTone(receiptStatus, "receipt"),
      detail: receipt
        ? `Signed receipt ${receipt.receipt_id}.`
        : "Signed action receipt has not been fetched or generated yet.",
    },
  ];
}

export function buildGuardOnlyProofChain(
  decision: RuntimePolicyDecisionResponse,
  outcome: OutcomeReconciliationView | null = null,
): ProofChainStep[] {
  return [
    {
      step: "action",
      label: "Action",
      status: "Guard-only",
      tone: "neutral",
      detail: "Runtime-policy guard did not create an Action Intent.",
    },
    {
      step: "policy",
      label: "Policy",
      status: statusLabel(decision.status, "runtime_policy"),
      tone: statusTone(decision.status, "runtime_policy"),
      detail: `Runtime policy decision ${decision.id}.`,
    },
    {
      step: "execution",
      label: "Execution",
      status: "Not via kernel",
      tone: "neutral",
      detail: "No protected runner execution is available for guard-only decisions.",
    },
    {
      step: "verification",
      label: "Verification",
      status: outcome ? statusLabel(outcome.verdict, "proof") : "Not verified",
      tone: outcome ? statusTone(outcome.verdict, "proof") : "warning",
      detail: outcome
        ? `Source-of-record verdict from ${outcome.connector_type}.`
        : "No linked source-of-record outcome is available.",
    },
    {
      step: "receipt",
      label: "Receipt",
      status: "Not via kernel",
      tone: "neutral",
      detail: "Guard-only decisions use an Evidence Pack, not an Action Receipt.",
    },
  ];
}
