import { replayLabel, severityRank } from "./issue-format";
import type { CallListItem, IssueItem } from "./types";

const PASSING_REPLAY_STATUSES = new Set([
  "verified_fix",
  "sanity_replay_passed",
  "real_replay_passed",
  "covered_passed",
]);

const REPLAY_READY_STATUSES = new Set(["covered_not_run", "fix_pending_replay", "replay_running"]);

type AgentIssueRow = {
  agentName: string;
  latestIssue: IssueItem | null;
};

export type CostExposureRow = {
  agentName: string;
  costUsd: number;
  issueTitle: string | null;
  issueId: string | null;
};

export type SignalClusterRow = {
  key: string;
  issueId: string;
  title: string;
  failureCode: string;
  occurrences: number;
  affectedAgents: number;
  firstSeenAt: string;
  severity: string;
  replayCoverage: string;
};

export type TimelineEntry = {
  key: string;
  label: string;
  detail: string;
  status: string;
  href: string;
  startedAt: string | null;
  latencyMs: number;
};

function agentNameFromCall(call: CallListItem): string {
  return call.agent_name?.trim() || "Unassigned agent";
}

function issuePriority(a: IssueItem, b: IssueItem): number {
  const severityDelta = severityRank(b.severity) - severityRank(a.severity);
  if (severityDelta !== 0) return severityDelta;
  const priorityDelta = b.priority_score - a.priority_score;
  if (priorityDelta !== 0) return priorityDelta;
  return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
}

export function isPassingReplay(status: string | null | undefined): boolean {
  return status != null && PASSING_REPLAY_STATUSES.has(status);
}

export function replayReadyCount(issues: readonly IssueItem[]): number {
  return issues.filter((issue) => REPLAY_READY_STATUSES.has(issue.replay_coverage_status)).length;
}

export function passingGuardrailRate(rows: readonly AgentIssueRow[]): number | null {
  if (rows.length === 0) {
    return null;
  }
  const protectedRows = rows.filter(
    (row) => row.latestIssue == null || isPassingReplay(row.latestIssue.replay_coverage_status),
  ).length;
  return (protectedRows / rows.length) * 100;
}

export function verifiedCostCoverage(rows: readonly AgentIssueRow[]): number {
  return rows.reduce((sum, row) => {
    if (!isPassingReplay(row.latestIssue?.replay_coverage_status)) {
      return sum;
    }
    return sum + (row.latestIssue?.cost_impact_usd ?? 0);
  }, 0);
}

export function buildCostExposureRows(rows: readonly AgentIssueRow[]): CostExposureRow[] {
  return rows
    .filter((row) => (row.latestIssue?.cost_impact_usd ?? 0) > 0)
    .map((row) => ({
      agentName: row.agentName,
      costUsd: row.latestIssue?.cost_impact_usd ?? 0,
      issueTitle: row.latestIssue?.title ?? null,
      issueId: row.latestIssue?.id ?? null,
    }))
    .sort((a, b) => b.costUsd - a.costUsd)
    .slice(0, 6);
}

export function buildSignalClusters(issues: readonly IssueItem[]): SignalClusterRow[] {
  const grouped = new Map<
    string,
    {
      representative: IssueItem;
      occurrences: number;
      firstSeenAt: string;
      agents: Set<string>;
    }
  >();

  for (const issue of issues) {
    const key = `${issue.failure_code}:${issue.title}`;
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {
        representative: issue,
        occurrences: issue.occurrence_count,
        firstSeenAt: issue.first_seen_at,
        agents: new Set(
          [issue.affected_agent, issue.agent_name].filter((value): value is string => Boolean(value?.trim())),
        ),
      });
      continue;
    }

    existing.occurrences += issue.occurrence_count;
    if (new Date(issue.first_seen_at).getTime() < new Date(existing.firstSeenAt).getTime()) {
      existing.firstSeenAt = issue.first_seen_at;
    }
    if (issuePriority(issue, existing.representative) < 0) {
      existing.representative = issue;
    }
    for (const agentName of [issue.affected_agent, issue.agent_name]) {
      if (agentName?.trim()) {
        existing.agents.add(agentName.trim());
      }
    }
  }

  return Array.from(grouped.entries())
    .map(([key, value]) => ({
      key,
      issueId: value.representative.id,
      title: value.representative.title,
      failureCode: value.representative.failure_code,
      occurrences: value.occurrences,
      affectedAgents: Math.max(value.agents.size, 1),
      firstSeenAt: value.firstSeenAt,
      severity: value.representative.severity,
      replayCoverage: replayLabel(value.representative.replay_coverage_status),
    }))
    .sort((a, b) => {
      const severityDelta = severityRank(b.severity) - severityRank(a.severity);
      if (severityDelta !== 0) {
        return severityDelta;
      }
      return b.occurrences - a.occurrences;
    })
    .slice(0, 6);
}

export function buildTimelineEntries(
  issue: IssueItem | null,
  fallbackAgentName: string | null,
  calls: readonly CallListItem[],
): TimelineEntry[] {
  const issueEvidence = issue?.evidence_traces ?? [];
  if (issueEvidence.length > 0) {
    return issueEvidence.slice(0, 6).map((trace, index) => ({
      key: trace.call_id ?? trace.trace_id ?? `trace-${index}`,
      label: trace.workflow_name ?? trace.trace_id ?? trace.call_id ?? "Captured trace",
      detail: [trace.provider, trace.model].filter(Boolean).join(" / ") || fallbackAgentName || "agent run",
      status: trace.status ?? "captured",
      href: "/evidence",
      startedAt: trace.created_at,
      latencyMs: trace.latency_ms ?? 1,
    }));
  }

  return calls.slice(0, 6).map((call) => ({
    key: call.call_id,
    label: agentNameFromCall(call),
    detail: [call.provider, call.model].filter(Boolean).join(" / ") || "captured call",
    status: call.status,
    href: "/evidence",
    startedAt: call.created_at,
    latencyMs: call.latency_ms ?? 1,
  }));
}
