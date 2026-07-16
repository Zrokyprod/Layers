import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "@/lib/api";

export type HealthStatus = "healthy" | "degraded" | "critical" | "no-data";

export type AgentHealthAvailability = {
  runners: boolean;
  actions: boolean;
  policies: boolean;
  proof: boolean;
  mutations: boolean;
  attempts: boolean;
};

export type AgentHealthInput = {
  windowDays: number;
  windowStart: string;
  generatedAt: string;
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  mutations: SourceMutationView[];
  staleAttempts: ActionExecutionAttemptResponse[];
  actionRunners: ActionRunnerResponse[];
  availability: AgentHealthAvailability;
};

export type HealthSignal = {
  id: "runner" | "actions" | "policy" | "proof";
  label: string;
  value: number | null;
  displayValue: string;
  context: string;
  status: HealthStatus;
};

export type HealthTimelineSegment = {
  id: string;
  startMs: number;
  endMs: number;
  label: string;
  status: HealthStatus;
  actions: number;
  completed: number;
  attention: number;
  proofChecks: number;
};

export type AgentHealthSnapshot = {
  overallScore: number | null;
  overallStatus: HealthStatus;
  signals: HealthSignal[];
  timeline: HealthTimelineSegment[];
  runnerLabel: string;
  runnerStatus: HealthStatus;
  lastActionLabel: string;
  lastActionStatus: HealthStatus;
  openAttention: number | null;
  proofFreshnessLabel: string;
  proofFreshnessStatus: HealthStatus;
  pendingApprovals: number | null;
};

const MS_PER_HOUR = 3_600_000;
const MS_PER_DAY = 86_400_000;

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "UTC",
});

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function percentage(numerator: number, denominator: number): number | null {
  if (denominator <= 0) return null;
  return Math.round((numerator / denominator) * 100);
}

function statusForPercentage(value: number | null): HealthStatus {
  if (value == null) return "no-data";
  if (value >= 90) return "healthy";
  if (value >= 70) return "degraded";
  return "critical";
}

function isCompletedIntent(intent: ActionIntentResponse): boolean {
  const status = intent.status.toLowerCase();
  return (
    intent.receipt_status === "generated" ||
    intent.proof_status === "matched" ||
    ["completed", "executed", "succeeded", "verified"].includes(status)
  );
}

function isPassingDecision(decision: RuntimePolicyDecisionResponse): boolean {
  return decision.allowed || decision.decision === "allow" || ["allowed", "approved"].includes(decision.status);
}

function isPendingDecision(decision: RuntimePolicyDecisionResponse): boolean {
  return decision.status === "pending_approval" || decision.requires_approval;
}

function isMatchedOutcome(outcome: OutcomeReconciliationView): boolean {
  return outcome.verdict === "matched" || ["matched", "verified"].includes(outcome.verification_status ?? "");
}

function isMismatchedOutcome(outcome: OutcomeReconciliationView): boolean {
  return outcome.verdict === "mismatched" || outcome.verification_status === "mismatched";
}

function hasRiskMutation(mutation: SourceMutationView): boolean {
  return ["policy_bypass", "unmanaged_agent_action", "unknown_actor"].includes(mutation.classification);
}

function relativeTime(value: number | null, generatedAtMs: number): string {
  if (value == null) return "No data yet";
  const minutes = Math.max(0, Math.round((generatedAtMs - value) / 60_000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function freshnessStatus(value: number | null, generatedAtMs: number): HealthStatus {
  if (value == null) return "no-data";
  const ageHours = Math.max(0, (generatedAtMs - value) / MS_PER_HOUR);
  if (ageHours <= 24) return "healthy";
  if (ageHours <= 72) return "degraded";
  return "critical";
}

function timelineSegmentCount(windowDays: number): number {
  if (windowDays <= 1) return 24;
  return Math.min(24, Math.max(7, Math.round(windowDays)));
}

function timelineStatus(segment: Omit<HealthTimelineSegment, "status">): HealthStatus {
  const signalCount = segment.actions + segment.proofChecks + segment.attention;
  if (signalCount === 0) return "no-data";
  if (segment.attention > 0) return "critical";
  if (segment.actions > segment.completed) return "degraded";
  return "healthy";
}

function buildHealthTimeline(input: AgentHealthInput): HealthTimelineSegment[] {
  const generatedAtMs = parseTime(input.generatedAt) ?? Date.now();
  const windowStartMs = parseTime(input.windowStart) ?? generatedAtMs - Math.max(1, input.windowDays) * MS_PER_DAY;
  const segmentCount = timelineSegmentCount(input.windowDays);
  const segmentSize = Math.max(1, (generatedAtMs - windowStartMs) / segmentCount);
  const segments = Array.from({ length: segmentCount }, (_, index) => {
    const startMs = windowStartMs + index * segmentSize;
    const endMs = index === segmentCount - 1 ? generatedAtMs : windowStartMs + (index + 1) * segmentSize;
    return {
      id: `health-${index}`,
      startMs,
      endMs,
      label: `${dateTimeFormatter.format(startMs)} - ${dateTimeFormatter.format(endMs)} UTC`,
      actions: 0,
      completed: 0,
      attention: 0,
      proofChecks: 0,
    };
  });

  const updateSegment = (value: string | null | undefined, update: (segment: typeof segments[number]) => void) => {
    const time = parseTime(value);
    if (time == null || time < windowStartMs || time > generatedAtMs) return;
    const index = Math.min(segmentCount - 1, Math.floor((time - windowStartMs) / segmentSize));
    update(segments[index]);
  };

  for (const intent of input.intents) {
    updateSegment(intent.created_at, (segment) => {
      segment.actions += 1;
      if (isCompletedIntent(intent)) segment.completed += 1;
      if (["mismatched", "failed"].includes(intent.proof_status)) segment.attention += 1;
    });
  }
  for (const decision of input.approvals) {
    updateSegment(decision.created_at, (segment) => {
      if (isPendingDecision(decision) || decision.status === "blocked" || decision.status === "rejected") segment.attention += 1;
    });
  }
  for (const outcome of input.outcomes) {
    updateSegment(outcome.checked_at ?? outcome.created_at, (segment) => {
      segment.proofChecks += 1;
      if (isMismatchedOutcome(outcome)) segment.attention += 1;
    });
  }
  for (const mutation of input.mutations) {
    updateSegment(mutation.occurred_at ?? mutation.created_at, (segment) => {
      if (hasRiskMutation(mutation)) segment.attention += 1;
    });
  }
  for (const attempt of input.staleAttempts) {
    updateSegment(attempt.updated_at ?? attempt.created_at, (segment) => {
      segment.attention += 1;
    });
  }

  return segments.map((segment) => ({ ...segment, status: timelineStatus(segment) }));
}

/**
 * Temporary client-side score until Home Summary exposes a canonical backend score.
 * The score is emitted only when all four real dimensions are measurable.
 */
export function calculateOverallHealthScore(values: {
  runnerAvailability: number | null;
  actionSuccessRate: number | null;
  policyPassRate: number | null;
  proofIntegrity: number | null;
}): number | null {
  const dimensions = [values.runnerAvailability, values.actionSuccessRate, values.policyPassRate, values.proofIntegrity];
  if (dimensions.some((value) => value == null)) return null;
  return Math.round(
    values.runnerAvailability! * 0.3 +
    values.actionSuccessRate! * 0.3 +
    values.policyPassRate! * 0.2 +
    values.proofIntegrity! * 0.2,
  );
}

export function calculateAgentHealth(input: AgentHealthInput): AgentHealthSnapshot {
  const generatedAtMs = parseTime(input.generatedAt) ?? Date.now();
  const onlineRunners = input.actionRunners.filter((runner) => runner.status.toLowerCase() === "online");
  const completedActions = input.intents.filter(isCompletedIntent).length;
  const passingDecisions = input.approvals.filter(isPassingDecision).length;
  const matchedOutcomes = input.outcomes.filter(isMatchedOutcome).length;
  const pendingApprovals = input.availability.policies ? input.approvals.filter(isPendingDecision).length : null;

  const runnerAvailability = input.availability.runners
    ? percentage(onlineRunners.length, input.actionRunners.length) ?? (input.actionRunners.length === 0 ? 0 : null)
    : null;
  const actionSuccessRate = input.availability.actions ? percentage(completedActions, input.intents.length) : null;
  const policyPassRate = input.availability.policies ? percentage(passingDecisions, input.approvals.length) : null;
  const proofIntegrity = input.availability.proof ? percentage(matchedOutcomes, input.outcomes.length) : null;
  const overallScore = calculateOverallHealthScore({ runnerAvailability, actionSuccessRate, policyPassRate, proofIntegrity });

  const latestActionAt = Math.max(-Infinity, ...input.intents.map((intent) => parseTime(intent.created_at) ?? -Infinity));
  const latestProofAt = Math.max(-Infinity, ...input.outcomes.map((outcome) => parseTime(outcome.checked_at ?? outcome.created_at) ?? -Infinity));
  const actionTime = Number.isFinite(latestActionAt) ? latestActionAt : null;
  const proofTime = Number.isFinite(latestProofAt) ? latestProofAt : null;
  const mismatchCount = input.outcomes.filter(isMismatchedOutcome).length;
  const riskyMutationCount = input.mutations.filter(hasRiskMutation).length;
  const openAttention = input.availability.actions && input.availability.policies && input.availability.proof && input.availability.mutations && input.availability.attempts
    ? (pendingApprovals ?? 0) + mismatchCount + riskyMutationCount + input.staleAttempts.length
    : null;

  const signals: HealthSignal[] = [
    {
      id: "runner",
      label: "Runner availability",
      value: runnerAvailability,
      displayValue: runnerAvailability == null ? "—" : `${runnerAvailability}%`,
      context: !input.availability.runners ? "Runner data unavailable" : onlineRunners.length > 0 ? `${onlineRunners.length} runner${onlineRunners.length === 1 ? "" : "s"} connected` : "No runner connected",
      status: statusForPercentage(runnerAvailability),
    },
    {
      id: "actions",
      label: "Action success rate",
      value: actionSuccessRate,
      displayValue: actionSuccessRate == null ? "—" : `${actionSuccessRate}%`,
      context: !input.availability.actions ? "Action data unavailable" : input.intents.length > 0 ? `${completedActions} of ${input.intents.length} actions completed` : "No action data yet",
      status: statusForPercentage(actionSuccessRate),
    },
    {
      id: "policy",
      label: "Policy pass rate",
      value: policyPassRate,
      displayValue: policyPassRate == null ? "—" : `${policyPassRate}%`,
      context: !input.availability.policies ? "Policy data unavailable" : input.approvals.length > 0 ? `${passingDecisions} of ${input.approvals.length} decisions passed` : "No policy decisions yet",
      status: statusForPercentage(policyPassRate),
    },
    {
      id: "proof",
      label: "Proof integrity",
      value: proofIntegrity,
      displayValue: proofIntegrity == null ? "—" : `${proofIntegrity}%`,
      context: !input.availability.proof ? "Proof data unavailable" : input.outcomes.length > 0 ? `${matchedOutcomes} of ${input.outcomes.length} checks matched` : "No proof checks yet",
      status: statusForPercentage(proofIntegrity),
    },
  ];

  return {
    overallScore,
    overallStatus: statusForPercentage(overallScore),
    signals,
    timeline: buildHealthTimeline(input),
    runnerLabel: !input.availability.runners ? "Unavailable" : onlineRunners.length > 0 ? "Connected" : "Disconnected",
    runnerStatus: !input.availability.runners ? "no-data" : onlineRunners.length > 0 ? "healthy" : "critical",
    lastActionLabel: relativeTime(actionTime, generatedAtMs),
    lastActionStatus: actionTime == null ? "no-data" : freshnessStatus(actionTime, generatedAtMs),
    openAttention,
    proofFreshnessLabel: relativeTime(proofTime, generatedAtMs),
    proofFreshnessStatus: freshnessStatus(proofTime, generatedAtMs),
    pendingApprovals,
  };
}

export function healthStatusLabel(status: HealthStatus): string {
  if (status === "healthy") return "Healthy";
  if (status === "degraded") return "Degraded";
  if (status === "critical") return "Critical";
  return "No data";
}
