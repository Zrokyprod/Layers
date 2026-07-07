import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileListResponse,
  AgentProfileResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  SourceMutationView,
} from "@/lib/api";
import { statusLabel, type StatusTone } from "@/lib/action-status";
import {
  buildActionLifecycle,
  type ActionLifecycleRow,
} from "@/lib/action-lifecycle";
import { humanize } from "@/lib/format";

export type AgentFleetMode = "single" | "fleet";
export type AgentFleetRowKind = "profile" | "telemetry";

export type AgentFleetMeter = {
  active: number;
  cap: number;
  reached: boolean;
};

export type AgentFleetRunnerSummary = {
  total: number;
  online: number;
  degraded: number;
  offline: number;
  disabled: number;
  other: number;
};

export type AgentFleetAttemptSummary = {
  total: number;
  claimable: number;
  running: number;
  stalled: number;
};

export type AgentActionRollup = {
  total: number;
  protectedActions: number;
  bypassed: number;
  held: number;
  executing: number;
  stalled: number;
  matched: number;
  mismatched: number;
  notVerified: number;
  receiptsGenerated: number;
  receiptsMissing: number;
};

export type AgentCoverageSummary = {
  configured: number;
  protectedObserved: number;
  bypassedObserved: number;
  observed: number;
  percent: number | null;
  label: string;
  detail: string;
  tone: StatusTone;
};

export type AgentRiskSignalSummary = {
  bypassed: number;
  sequenceRisk: number;
  mismatched: number;
  label: string;
  tone: StatusTone;
};

export type AgentMandateSummary = {
  label: string;
  detail: string;
  actionTypes: string[];
  toolCount: number;
  verifierCount: number;
  runnerMode: string | null;
};

export type AgentFleetRowStatus =
  | "profile_ready"
  | "watching"
  | "matched"
  | "approval_pending"
  | "not_verified"
  | "execution_stalled"
  | "mismatched"
  | "policy_bypass";

export type AgentFleetRow = {
  id: string;
  kind: AgentFleetRowKind;
  agentName: string;
  profile: AgentProfileResponse | null;
  telemetryNames: string[];
  aliases: string[];
  status: AgentFleetRowStatus;
  statusLabel: string;
  tone: StatusTone;
  actionRollup: AgentActionRollup;
  coverage: AgentCoverageSummary;
  riskSignals: AgentRiskSignalSummary;
  mandate: AgentMandateSummary;
  runnerCount: number;
  runners: ActionRunnerResponse[];
  attemptSummary: AgentFleetAttemptSummary;
  latestActivityAt: string | null;
  actionRows: ActionLifecycleRow[];
  href: string;
};

export type AgentFleetTotals = {
  managedProfiles: number;
  telemetryOnly: number;
  held: number;
  mismatched: number;
  notVerified: number;
  receiptReady: number;
  coveragePercent: number | null;
  bypassed: number;
  sequenceRisk: number;
};

export type AgentFleetView = {
  mode: AgentFleetMode;
  meter: AgentFleetMeter;
  rows: AgentFleetRow[];
  runners: AgentFleetRunnerSummary;
  attempts: AgentFleetAttemptSummary;
  totals: AgentFleetTotals;
};

export type BuildAgentFleetInput = {
  profiles: AgentProfileResponse[];
  profileMeta?: Pick<
    AgentProfileListResponse,
    "active_count" | "max_active_agents" | "limit_reached"
  > | null;
  intents?: ActionIntentResponse[];
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  runners?: ActionRunnerResponse[];
  attempts?: ActionExecutionAttemptResponse[];
  staleAttemptIds?: string[];
  mutations?: SourceMutationView[];
};

type MutableFleetRow = Omit<
  AgentFleetRow,
  | "status"
  | "statusLabel"
  | "tone"
  | "actionRollup"
  | "coverage"
  | "riskSignals"
  | "mandate"
  | "runnerCount"
  | "runners"
  | "attemptSummary"
  | "latestActivityAt"
  | "href"
> & {
  aliasSet: Set<string>;
  telemetrySet: Set<string>;
};

function normalizeAgentToken(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\s+/g, " ").toLowerCase();
}

function slugAgentToken(value: string | null | undefined): string {
  return normalizeAgentToken(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function addAlias(target: Set<string>, value: string | null | undefined): void {
  const normalized = normalizeAgentToken(value);
  const slug = slugAgentToken(value);
  if (normalized) target.add(normalized);
  if (slug) target.add(slug);
}

function stringFrom(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function recordFrom(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function profileAliases(profile: AgentProfileResponse): Set<string> {
  const aliases = new Set<string>();
  addAlias(aliases, profile.id);
  addAlias(aliases, profile.slug);
  addAlias(aliases, profile.display_name);
  addAlias(aliases, stringFrom(profile.metadata.agent_name));
  addAlias(aliases, stringFrom(profile.metadata.slug));
  return aliases;
}

function nameAliases(agentName: string | null | undefined): Set<string> {
  const aliases = new Set<string>();
  addAlias(aliases, agentName);
  return aliases;
}

function hasAliasIntersection(a: Set<string>, b: Set<string>): boolean {
  for (const value of a) {
    if (b.has(value)) return true;
  }
  return false;
}

function latestTime(values: Array<string | null | undefined>): string | null {
  return values
    .filter((value): value is string => Boolean(value))
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0] ?? null;
}

function rowTime(row: ActionLifecycleRow): number {
  const raw = row.updatedAt ?? row.createdAt;
  const time = raw ? new Date(raw).getTime() : 0;
  return Number.isFinite(time) ? time : 0;
}

function sortActionRows(rows: ActionLifecycleRow[]): ActionLifecycleRow[] {
  return [...rows].sort((a, b) => rowTime(b) - rowTime(a));
}

function runnerStatusSummary(runners: ActionRunnerResponse[]): AgentFleetRunnerSummary {
  const summary: AgentFleetRunnerSummary = {
    total: runners.length,
    online: 0,
    degraded: 0,
    offline: 0,
    disabled: 0,
    other: 0,
  };
  for (const runner of runners) {
    const status = normalizeAgentToken(runner.status);
    if (status === "online") summary.online += 1;
    else if (status === "degraded") summary.degraded += 1;
    else if (status === "offline") summary.offline += 1;
    else if (status === "disabled") summary.disabled += 1;
    else summary.other += 1;
  }
  return summary;
}

function attemptSummary(
  attempts: ActionExecutionAttemptResponse[],
  staleAttemptIds: Set<string>,
): AgentFleetAttemptSummary {
  const summary: AgentFleetAttemptSummary = {
    total: attempts.length,
    claimable: 0,
    running: 0,
    stalled: 0,
  };
  for (const attempt of attempts) {
    const status = normalizeAgentToken(attempt.status);
    if (staleAttemptIds.has(attempt.attempt_id)) summary.stalled += 1;
    if (status === "planned") summary.claimable += 1;
    if (["claimed", "dispatched", "running"].includes(status)) summary.running += 1;
  }
  return summary;
}

function actionRollup(rows: ActionLifecycleRow[]): AgentActionRollup {
  const rollup: AgentActionRollup = {
    total: rows.length,
    protectedActions: 0,
    bypassed: 0,
    held: 0,
    executing: 0,
    stalled: 0,
    matched: 0,
    mismatched: 0,
    notVerified: 0,
    receiptsGenerated: 0,
    receiptsMissing: 0,
  };

  for (const row of rows) {
    if (row.kind === "bypass_mutation") rollup.bypassed += 1;
    else rollup.protectedActions += 1;
    if (row.stage.id === "approval" || row.status === "approval_pending") rollup.held += 1;
    if (["authorized", "execution", "no_runner", "execution_stalled"].includes(row.stage.id)) {
      rollup.executing += 1;
    }
    if (["no_runner", "execution_stalled"].includes(row.stage.id)) rollup.stalled += 1;
    if (row.proofStatus === "matched" || row.status === "matched") rollup.matched += 1;
    if (row.proofStatus === "mismatched" || row.status === "mismatched") rollup.mismatched += 1;
    if (
      ["not_verified", "pending", "missing", "not_started"].includes(row.proofStatus) ||
      ["not_verified", "pending", "missing"].includes(row.status)
    ) {
      rollup.notVerified += 1;
    }
    if (row.receiptStatus === "generated") rollup.receiptsGenerated += 1;
    if (["missing", "failed"].includes(row.receiptStatus)) rollup.receiptsMissing += 1;
  }

  return rollup;
}

function rowStatus(rollup: AgentActionRollup, profile: AgentProfileResponse | null): Pick<AgentFleetRow, "status" | "statusLabel" | "tone"> {
  if (rollup.bypassed > 0) {
    return { status: "policy_bypass", statusLabel: "Control bypass", tone: "danger" };
  }
  if (rollup.mismatched > 0) {
    return { status: "mismatched", statusLabel: "Mismatched proof", tone: "danger" };
  }
  if (rollup.stalled > 0) {
    return { status: "execution_stalled", statusLabel: "Execution stalled", tone: "danger" };
  }
  if (rollup.held > 0) {
    return { status: "approval_pending", statusLabel: statusLabel("approval_pending"), tone: "warning" };
  }
  if (rollup.notVerified > 0) {
    return { status: "not_verified", statusLabel: statusLabel("not_verified"), tone: "warning" };
  }
  if (rollup.total > 0 && rollup.matched === rollup.total && rollup.receiptsGenerated === rollup.total) {
    return { status: "matched", statusLabel: statusLabel("matched"), tone: "success" };
  }
  if (rollup.total === 0 && profile) {
    return { status: "profile_ready", statusLabel: "Profile ready", tone: "neutral" };
  }
  return { status: "watching", statusLabel: "Watching", tone: "neutral" };
}

function hasSequenceRiskSignal(row: ActionLifecycleRow): boolean {
  const decision = row.decision;
  if (!decision) return false;
  const reasonHit = decision.reasons.some((reason) => reason.toLowerCase().includes("sequence risk"));
  const policyHit = Object.prototype.hasOwnProperty.call(decision.policy_hit ?? {}, "sequence_risk");
  return reasonHit || policyHit;
}

function coverageSummary(
  rollup: AgentActionRollup,
  profile: AgentProfileResponse | null,
): AgentCoverageSummary {
  const configured = profile?.allowed_action_types.length ?? 0;
  const observed = rollup.protectedActions + rollup.bypassed;
  const percent = observed > 0
    ? Math.round((rollup.protectedActions / observed) * 100)
    : null;
  const tone: StatusTone = rollup.bypassed > 0
    ? "danger"
    : percent === 100
      ? "success"
      : observed > 0
        ? "warning"
        : configured > 0
          ? "neutral"
          : "warning";
  const label = observed > 0 && percent != null
    ? `${percent}% covered`
    : configured > 0
      ? `${configured} mandated`
      : "No coverage yet";
  const detail = observed > 0
    ? `${rollup.protectedActions} protected / ${rollup.bypassed} bypassed observed`
    : configured > 0
      ? `${configured} protected action ${configured === 1 ? "type" : "types"} configured`
      : "No protected action mandate configured";

  return {
    configured,
    protectedObserved: rollup.protectedActions,
    bypassedObserved: rollup.bypassed,
    observed,
    percent,
    label,
    detail,
    tone,
  };
}

function riskSignalSummary(rollup: AgentActionRollup, rows: ActionLifecycleRow[]): AgentRiskSignalSummary {
  const sequenceRisk = rows.filter(hasSequenceRiskSignal).length;
  const total = rollup.bypassed + sequenceRisk + rollup.mismatched;
  const tone: StatusTone = rollup.bypassed > 0 || rollup.mismatched > 0
    ? "danger"
    : sequenceRisk > 0
      ? "warning"
      : "success";
  return {
    bypassed: rollup.bypassed,
    sequenceRisk,
    mismatched: rollup.mismatched,
    label: total > 0 ? `${total} signal${total === 1 ? "" : "s"}` : "No risky drift",
    tone,
  };
}

function mandateSummary(profile: AgentProfileResponse | null): AgentMandateSummary {
  if (!profile) {
    return {
      label: "No mandate",
      detail: "Telemetry identity is not managed by AgentProfile yet.",
      actionTypes: [],
      toolCount: 0,
      verifierCount: 0,
      runnerMode: null,
    };
  }

  const actionTypes = profile.allowed_action_types.map((type) => humanize(type));
  const visibleActions = actionTypes.slice(0, 2);
  const runnerMode = stringFrom(recordFrom(profile.metadata.runner_verification).runner_mode);
  const label = visibleActions.length > 0
    ? visibleActions.join(" / ")
    : "Mandate not scoped";
  const remaining = Math.max(actionTypes.length - visibleActions.length, 0);
  const detailParts = [
    remaining > 0 ? `+${remaining} more action ${remaining === 1 ? "type" : "types"}` : null,
    profile.verification_connectors.length > 0
      ? `${profile.verification_connectors.length} verifier${profile.verification_connectors.length === 1 ? "" : "s"}`
      : "no verifier",
    profile.tool_names.length > 0 ? `${profile.tool_names.length} tools` : "no tools listed",
  ].filter(Boolean);

  return {
    label,
    detail: detailParts.join(" / "),
    actionTypes,
    toolCount: profile.tool_names.length,
    verifierCount: profile.verification_connectors.length,
    runnerMode,
  };
}

function profileForTelemetry(
  agentName: string,
  profiles: AgentProfileResponse[],
  aliasesByProfile: Map<string, Set<string>>,
): AgentProfileResponse | null {
  const aliases = nameAliases(agentName);
  for (const profile of profiles) {
    if (hasAliasIntersection(aliasesByProfile.get(profile.id) ?? new Set(), aliases)) {
      return profile;
    }
  }
  return null;
}

function operationKinds(rows: ActionLifecycleRow[]): Set<string> {
  const kinds = new Set<string>();
  for (const row of rows) {
    const value = row.operationKind?.trim().toLowerCase();
    if (value) kinds.add(value);
  }
  return kinds;
}

function runnerMatchesRow(
  runner: ActionRunnerResponse,
  profile: AgentProfileResponse | null,
  rows: ActionLifecycleRow[],
): boolean {
  const kinds = operationKinds(rows);
  if (kinds.size === 0) return false;

  const profileEnv = normalizeAgentToken(profile?.environment);
  const runnerEnv = normalizeAgentToken(runner.environment);
  if (profileEnv && runnerEnv && profileEnv !== runnerEnv && runnerEnv !== "all") {
    return false;
  }

  const supported = runner.supported_operation_kinds.map((kind) => kind.trim().toLowerCase()).filter(Boolean);
  if (supported.length === 0) return true;
  return supported.some((kind) => kinds.has(kind));
}

function rowHref(row: MutableFleetRow): string {
  if (row.profile) return `/agents/${encodeURIComponent(row.profile.id)}`;
  return `/agents?agent_name=${encodeURIComponent(row.agentName)}`;
}

function finalizeRow(
  row: MutableFleetRow,
  runners: ActionRunnerResponse[],
  attempts: ActionExecutionAttemptResponse[],
  staleAttemptIds: Set<string>,
): AgentFleetRow {
  const actionRows = sortActionRows(row.actionRows);
  const rollup = actionRollup(actionRows);
  const status = rowStatus(rollup, row.profile);
  const coverage = coverageSummary(rollup, row.profile);
  const riskSignals = riskSignalSummary(rollup, actionRows);
  const mandate = mandateSummary(row.profile);
  const actionIds = new Set(actionRows.map((actionRow) => actionRow.actionId).filter(Boolean));
  const linkedAttempts = attempts.filter((attempt) => actionIds.has(attempt.action_id));
  const linkedRunners = runners.filter((runner) => runnerMatchesRow(runner, row.profile, actionRows));

  return {
    id: row.id,
    kind: row.kind,
    agentName: row.agentName,
    profile: row.profile,
    telemetryNames: [...row.telemetrySet].sort(),
    aliases: [...row.aliasSet].sort(),
    ...status,
    actionRollup: rollup,
    coverage,
    riskSignals,
    mandate,
    runnerCount: linkedRunners.length,
    runners: linkedRunners,
    attemptSummary: attemptSummary(linkedAttempts, staleAttemptIds),
    latestActivityAt: latestTime([
      row.profile?.updated_at,
      ...actionRows.map((actionRow) => actionRow.updatedAt ?? actionRow.createdAt),
    ]),
    actionRows,
    href: rowHref(row),
  };
}

function sortFleetRows(rows: AgentFleetRow[]): AgentFleetRow[] {
  const toneRank: Record<StatusTone, number> = {
    danger: 3,
    warning: 2,
    neutral: 1,
    success: 0,
  };
  return [...rows].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "profile" ? -1 : 1;
    const toneDelta = toneRank[b.tone] - toneRank[a.tone];
    if (toneDelta !== 0) return toneDelta;
    return new Date(b.latestActivityAt ?? 0).getTime() - new Date(a.latestActivityAt ?? 0).getTime();
  });
}

export function buildFleetView({
  profiles,
  profileMeta,
  intents = [],
  decisions = [],
  outcomes = [],
  runners = [],
  attempts = [],
  staleAttemptIds = [],
  mutations = [],
}: BuildAgentFleetInput): AgentFleetView {
  const activeProfiles = profiles.filter((profile) => profile.is_active);
  const activeCount = profileMeta?.active_count ?? activeProfiles.length;
  const maxActiveAgents = profileMeta?.max_active_agents ?? -1;
  const staleIds = new Set(staleAttemptIds);
  const aliasesByProfile = new Map(activeProfiles.map((profile) => [profile.id, profileAliases(profile)]));
  const rowsById = new Map<string, MutableFleetRow>();
  const lifecycleRows = buildActionLifecycle({
    intents,
    decisions,
    outcomes,
    attempts,
    staleAttemptIds,
    mutations,
  });

  for (const profile of activeProfiles) {
    rowsById.set(`profile:${profile.id}`, {
      id: `profile:${profile.id}`,
      kind: "profile",
      agentName: profile.display_name,
      profile,
      telemetryNames: [],
      telemetrySet: new Set(),
      aliases: [],
      aliasSet: aliasesByProfile.get(profile.id) ?? new Set(),
      actionRows: [],
    });
  }

  for (const actionRow of lifecycleRows) {
    const boundAgentId = actionRow.intent?.agent_id;
    const matchAgentName = actionRow.mutation?.actor_id ?? actionRow.agentName;
    const profile = boundAgentId
      ? activeProfiles.find((item) => item.id === boundAgentId) ?? null
      : profileForTelemetry(matchAgentName, activeProfiles, aliasesByProfile);
    const id = profile ? `profile:${profile.id}` : `telemetry:${slugAgentToken(actionRow.agentName) || actionRow.agentName}`;
    let row = rowsById.get(id);
    if (!row) {
      const aliases = nameAliases(matchAgentName);
      row = {
        id,
        kind: "telemetry",
        agentName: actionRow.agentName,
        profile: null,
        telemetryNames: [],
        telemetrySet: new Set(),
        aliases: [],
        aliasSet: aliases,
        actionRows: [],
      };
      rowsById.set(id, row);
    }
    row.actionRows.push(actionRow);
    row.telemetrySet.add(actionRow.agentName);
    addAlias(row.aliasSet, actionRow.agentName);
    addAlias(row.aliasSet, matchAgentName);
  }

  const rows = sortFleetRows(
    [...rowsById.values()].map((row) => finalizeRow(row, runners, attempts, staleIds)),
  );
  const totalObservedCoverage = rows.reduce((sum, row) => sum + row.coverage.observed, 0);
  const totalProtectedObserved = rows.reduce((sum, row) => sum + row.coverage.protectedObserved, 0);

  return {
    mode: activeCount === 1 ? "single" : "fleet",
    meter: {
      active: activeCount,
      cap: maxActiveAgents,
      reached: profileMeta?.limit_reached ?? (maxActiveAgents !== -1 && activeCount >= maxActiveAgents),
    },
    rows,
    runners: runnerStatusSummary(runners),
    attempts: attemptSummary(attempts, staleIds),
    totals: {
      managedProfiles: activeCount,
      telemetryOnly: rows.filter((row) => row.kind === "telemetry").length,
      held: rows.reduce((sum, row) => sum + row.actionRollup.held, 0),
      mismatched: rows.reduce((sum, row) => sum + row.actionRollup.mismatched, 0),
      notVerified: rows.reduce((sum, row) => sum + row.actionRollup.notVerified, 0),
      receiptReady: rows.reduce((sum, row) => sum + row.actionRollup.receiptsGenerated, 0),
      coveragePercent: totalObservedCoverage > 0
        ? Math.round((totalProtectedObserved / totalObservedCoverage) * 100)
        : null,
      bypassed: rows.reduce((sum, row) => sum + row.riskSignals.bypassed, 0),
      sequenceRisk: rows.reduce((sum, row) => sum + row.riskSignals.sequenceRisk, 0),
    },
  };
}
