import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileListResponse,
  AgentProfileResponse,
  AgentScoreView,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";
import { statusLabel, type StatusTone } from "@/lib/action-status";
import {
  buildActionLifecycle,
  type ActionLifecycleRow,
} from "@/lib/action-lifecycle";

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
  held: number;
  executing: number;
  stalled: number;
  matched: number;
  mismatched: number;
  notVerified: number;
  receiptsGenerated: number;
  receiptsMissing: number;
};

export type AgentFleetRowStatus =
  | "profile_ready"
  | "watching"
  | "matched"
  | "approval_pending"
  | "not_verified"
  | "execution_stalled"
  | "mismatched";

export type AgentFleetRow = {
  id: string;
  kind: AgentFleetRowKind;
  agentName: string;
  profile: AgentProfileResponse | null;
  score: AgentScoreView | null;
  telemetryNames: string[];
  aliases: string[];
  status: AgentFleetRowStatus;
  statusLabel: string;
  tone: StatusTone;
  actionRollup: AgentActionRollup;
  runnerCount: number;
  runners: ActionRunnerResponse[];
  attemptSummary: AgentFleetAttemptSummary;
  latestActivityAt: string | null;
  healthScore: number | null;
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
  scores?: AgentScoreView[];
  intents?: ActionIntentResponse[];
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  runners?: ActionRunnerResponse[];
  attempts?: ActionExecutionAttemptResponse[];
  staleAttemptIds?: string[];
};

type MutableFleetRow = Omit<
  AgentFleetRow,
  | "status"
  | "statusLabel"
  | "tone"
  | "actionRollup"
  | "runnerCount"
  | "runners"
  | "attemptSummary"
  | "latestActivityAt"
  | "healthScore"
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

function latestByDate<T>(
  items: T[],
  dateOf: (item: T) => string | null | undefined,
): T | null {
  let latest: T | null = null;
  let latestMs = -1;
  for (const item of items) {
    const raw = dateOf(item);
    const ms = raw ? new Date(raw).getTime() : 0;
    if (Number.isFinite(ms) && ms > latestMs) {
      latest = item;
      latestMs = ms;
    }
  }
  return latest;
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

export function matchAgentToScore(
  profile: AgentProfileResponse,
  scores: AgentScoreView[],
): AgentScoreView | null {
  const aliases = profileAliases(profile);
  const matches = scores.filter((score) => hasAliasIntersection(aliases, nameAliases(score.agent_name)));
  return latestByDate(matches, (score) => score.computed_at ?? score.score_date);
}

function scoreForTelemetry(agentName: string, scores: AgentScoreView[]): AgentScoreView | null {
  const aliases = nameAliases(agentName);
  const matches = scores.filter((score) => hasAliasIntersection(aliases, nameAliases(score.agent_name)));
  return latestByDate(matches, (score) => score.computed_at ?? score.score_date);
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
  const actionIds = new Set(actionRows.map((actionRow) => actionRow.actionId).filter(Boolean));
  const linkedAttempts = attempts.filter((attempt) => actionIds.has(attempt.action_id));
  const linkedRunners = runners.filter((runner) => runnerMatchesRow(runner, row.profile, actionRows));

  return {
    id: row.id,
    kind: row.kind,
    agentName: row.agentName,
    profile: row.profile,
    score: row.score,
    telemetryNames: [...row.telemetrySet].sort(),
    aliases: [...row.aliasSet].sort(),
    ...status,
    actionRollup: rollup,
    runnerCount: linkedRunners.length,
    runners: linkedRunners,
    attemptSummary: attemptSummary(linkedAttempts, staleAttemptIds),
    latestActivityAt: latestTime([
      row.profile?.updated_at,
      row.score?.computed_at,
      ...actionRows.map((actionRow) => actionRow.updatedAt ?? actionRow.createdAt),
    ]),
    healthScore: row.score?.health_score ?? null,
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
  scores = [],
  intents = [],
  decisions = [],
  outcomes = [],
  runners = [],
  attempts = [],
  staleAttemptIds = [],
}: BuildAgentFleetInput): AgentFleetView {
  const activeProfiles = profiles.filter((profile) => profile.is_active);
  const activeCount = profileMeta?.active_count ?? activeProfiles.length;
  const maxActiveAgents = profileMeta?.max_active_agents ?? -1;
  const staleIds = new Set(staleAttemptIds);
  const aliasesByProfile = new Map(activeProfiles.map((profile) => [profile.id, profileAliases(profile)]));
  const rowsById = new Map<string, MutableFleetRow>();
  const lifecycleRows = buildActionLifecycle({ intents, decisions, outcomes, attempts, staleAttemptIds });

  for (const profile of activeProfiles) {
    rowsById.set(`profile:${profile.id}`, {
      id: `profile:${profile.id}`,
      kind: "profile",
      agentName: profile.display_name,
      profile,
      score: matchAgentToScore(profile, scores),
      telemetryNames: [],
      telemetrySet: new Set(),
      aliases: [],
      aliasSet: aliasesByProfile.get(profile.id) ?? new Set(),
      actionRows: [],
    });
  }

  for (const actionRow of lifecycleRows) {
    const boundAgentId = actionRow.intent?.agent_id;
    const profile = boundAgentId
      ? activeProfiles.find((item) => item.id === boundAgentId) ?? null
      : profileForTelemetry(actionRow.agentName, activeProfiles, aliasesByProfile);
    const id = profile ? `profile:${profile.id}` : `telemetry:${slugAgentToken(actionRow.agentName) || actionRow.agentName}`;
    let row = rowsById.get(id);
    if (!row) {
      const aliases = nameAliases(actionRow.agentName);
      row = {
        id,
        kind: "telemetry",
        agentName: actionRow.agentName,
        profile: null,
        score: scoreForTelemetry(actionRow.agentName, scores),
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
  }

  for (const score of scores) {
    const matchedProfile = profileForTelemetry(score.agent_name, activeProfiles, aliasesByProfile);
    const scoreAliases = nameAliases(score.agent_name);
    const alreadyRepresented = [...rowsById.values()].some((row) => (
      row.score === score ||
      (matchedProfile && row.profile?.id === matchedProfile.id) ||
      hasAliasIntersection(row.aliasSet, scoreAliases)
    ));
    if (alreadyRepresented) continue;
    rowsById.set(`telemetry:${slugAgentToken(score.agent_name) || score.agent_name}`, {
      id: `telemetry:${slugAgentToken(score.agent_name) || score.agent_name}`,
      kind: "telemetry",
      agentName: score.agent_name,
      profile: null,
      score,
      telemetryNames: [score.agent_name],
      telemetrySet: new Set([score.agent_name]),
      aliases: [],
      aliasSet: scoreAliases,
      actionRows: [],
    });
  }

  const rows = sortFleetRows(
    [...rowsById.values()].map((row) => finalizeRow(row, runners, attempts, staleIds)),
  );

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
    },
  };
}
