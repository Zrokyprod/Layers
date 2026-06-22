"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock3,
  FileJson,
  Gauge,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { CaptureConnectPanel } from "@/components/capture-connect-panel";
import {
  buildCostExposureRows,
  buildSignalClusters,
  buildTimelineEntries,
  verifiedCostCoverage,
} from "@/lib/agents-console";
import {
  getAnalyticsSummary,
  getCaptureHealth,
  listCalls,
  listIssues,
  listOutcomeReconciliations,
  listRuntimePolicyApprovals,
} from "@/lib/api";
import type { AgentScoreView, OutcomeReconciliationView, RuntimePolicyDecisionResponse } from "@/lib/api";
import { formatCount, formatDateTime, formatPercent, formatUsd } from "@/lib/format";
import { replayLabel, severityRank } from "@/lib/issue-format";
import { useReliabilityLeaderboard } from "@/lib/hooks";
import { useDashboardStore } from "@/lib/store";
import type { CallListItem, CaptureHealthResponse, IssueItem } from "@/lib/types";

const ONBOARDING_WIZARD_OPENED_KEY = "zroky.onboardingWizardOpened";

type AgentStats = {
  callCount: number;
  successfulCalls: number;
  totalCostUsd: number;
  successfulCostUsd: number;
  lastEventAt: string | null;
  p95LatencyMs: number | null;
};

type AgentLaunchpadRow = {
  agentName: string;
  healthScore: number | null;
  latestIssue: IssueItem | null;
  successRate: number | null;
  costPerSuccessfulTask: number | null;
  replayCoverage: string;
  lastEventAt: string | null;
  recommendedAction: string;
  callCount: number;
  successfulCalls: number;
  p95LatencyMs: number | null;
  latestDecision: RuntimePolicyDecisionResponse | null;
  latestOutcome: OutcomeReconciliationView | null;
};

function agentNameFromCall(call: CallListItem): string {
  return call.agent_name?.trim() || "Unassigned agent";
}

function agentNameFromIssue(issue: IssueItem): string {
  return issue.affected_agent?.trim() || issue.agent_name?.trim() || "Unassigned agent";
}

function isSuccessfulCall(call: CallListItem): boolean {
  const status = call.status.toLowerCase();
  return ["success", "succeeded", "completed", "ok", "passed"].includes(status);
}

function latestDate(a: string | null, b: string | null): string | null {
  if (!a) return b;
  if (!b) return a;
  return new Date(a).getTime() >= new Date(b).getTime() ? a : b;
}

function timestamp(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

function evidencePackHref(decisionId: string): string {
  return `/evidence?decision_id=${encodeURIComponent(decisionId)}`;
}

function latestByDate<T>(
  current: T | null,
  next: T,
  getDate: (item: T) => string | null | undefined,
): T {
  if (!current) return next;
  return timestamp(getDate(next)) >= timestamp(getDate(current)) ? next : current;
}

function recordText(source: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = source?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function agentNameFromDecision(decision: RuntimePolicyDecisionResponse): string | null {
  return (
    decision.agent_name?.trim() ||
    recordText(decision.trace_context, "agent_name") ||
    recordText(decision.intended_action, "agent_name") ||
    recordText(decision.request, "agent_name")
  );
}

function outcomeAgentName(
  outcome: OutcomeReconciliationView,
  decisionsById: Map<string, RuntimePolicyDecisionResponse>,
  decisionsByCall: Map<string, RuntimePolicyDecisionResponse>,
  decisionsByTrace: Map<string, RuntimePolicyDecisionResponse>,
  callsById: Map<string, CallListItem>,
): string | null {
  const decision =
    (outcome.runtime_policy_decision_id ? decisionsById.get(outcome.runtime_policy_decision_id) : null) ??
    (outcome.call_id ? decisionsByCall.get(outcome.call_id) : null) ??
    (outcome.trace_id ? decisionsByTrace.get(outcome.trace_id) : null);
  const decisionAgent = decision ? agentNameFromDecision(decision) : null;
  if (decisionAgent) return decisionAgent;
  const call = outcome.call_id ? callsById.get(outcome.call_id) : null;
  return call ? agentNameFromCall(call) : null;
}

function decisionDisplay(decision: RuntimePolicyDecisionResponse | null): string {
  if (!decision) return "not_verified";
  if (decision.decision === "block" || decision.status === "blocked") return "BLOCK";
  if (decision.decision === "allow" || decision.status === "allowed") return "ALLOW";
  if (decision.status === "approved") return "APPROVED";
  if (decision.status === "rejected") return "REJECTED";
  if (decision.status === "expired") return "EXPIRED";
  return "HOLD";
}

function decisionTone(decision: RuntimePolicyDecisionResponse | null): string {
  if (!decision) return "badge-gray";
  if (decision.decision === "block" || decision.status === "blocked" || decision.status === "rejected") return "badge-red";
  if (decision.decision === "requires_approval" || decision.status === "pending_approval" || decision.status === "expired") return "badge-yellow";
  return "badge-green";
}

function outcomeDisplay(outcome: OutcomeReconciliationView | null): string {
  return outcome?.verdict ?? "not_verified";
}

function outcomeTone(outcome: OutcomeReconciliationView | null): string {
  if (!outcome || outcome.verdict === "not_verified") return "badge-yellow";
  if (outcome.verdict === "mismatched") return "badge-red";
  return "badge-green";
}

function outcomeRiskRank(outcome: OutcomeReconciliationView): number {
  if (outcome.verdict === "mismatched") return 3;
  if (outcome.verdict === "not_verified") return 2;
  return 1;
}

function higherPriorityOutcome(
  current: OutcomeReconciliationView | null,
  next: OutcomeReconciliationView,
): OutcomeReconciliationView {
  if (!current) return next;
  const riskDelta = outcomeRiskRank(next) - outcomeRiskRank(current);
  if (riskDelta > 0) return next;
  if (riskDelta < 0) return current;
  return latestByDate(current, next, (item) => item.checked_at ?? item.created_at);
}

function decisionDetail(decision: RuntimePolicyDecisionResponse | null): string {
  if (!decision) return "No runtime decision";
  return [decision.action_type, decision.tool_name, decision.status].filter(Boolean).join(" - ");
}

function outcomeDetail(outcome: OutcomeReconciliationView | null): string {
  if (!outcome) return "No system-of-record check";
  return [outcome.connector_type, outcome.system_ref].filter(Boolean).join(" - ") || outcome.reason || "Outcome checked";
}

function issuePriority(a: IssueItem, b: IssueItem): number {
  const severityDelta = severityRank(b.severity) - severityRank(a.severity);
  if (severityDelta !== 0) return severityDelta;
  const priorityDelta = b.priority_score - a.priority_score;
  if (priorityDelta !== 0) return priorityDelta;
  return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
}

function healthTone(score: number | null): { label: string; className: string } {
  if (score == null) return { label: "No score", className: "badge-gray" };
  if (score >= 80) return { label: "Healthy", className: "badge-green" };
  if (score >= 55) return { label: "Watch", className: "badge-yellow" };
  return { label: "At risk", className: "badge-red" };
}

function severityTone(severity: string | null | undefined): string {
  const value = (severity ?? "").toLowerCase();
  if (value === "critical" || value === "high") return "badge-red";
  if (value === "medium" || value === "warning") return "badge-yellow";
  if (value === "low") return "badge-blue";
  return "badge-gray";
}

function recommendedActionFor(row: {
  latestIssue: IssueItem | null;
  healthScore: number | null;
  successRate: number | null;
  replayCoverage: string;
  latestDecision?: RuntimePolicyDecisionResponse | null;
  latestOutcome?: OutcomeReconciliationView | null;
}): string {
  if (row.latestOutcome?.verdict === "mismatched") {
    return "Hold this agent path and review the system-of-record mismatch.";
  }
  if (!row.latestOutcome && row.latestDecision) {
    return "Run outcome reconciliation before marking this action verified.";
  }
  if (row.latestDecision?.status === "pending_approval") {
    return "Review the held runtime decision.";
  }
  if (row.latestIssue?.recommended_next_action) {
    return row.latestIssue.recommended_next_action;
  }
  if (row.healthScore != null && row.healthScore < 55) {
    return "Open recent calls and isolate the failing path.";
  }
  if (row.successRate != null && row.successRate < 95) {
    return "Review failures and add replay coverage.";
  }
  if (row.replayCoverage === "No open issue") {
    return "Monitor agent health.";
  }
  return "Review replay coverage.";
}

function percentileLatency(calls: CallListItem[]): number | null {
  const values = calls
    .map((call) => call.latency_ms)
    .filter((value): value is number => typeof value === "number")
    .sort((a, b) => a - b);
  if (values.length === 0) return null;
  const index = Math.min(values.length - 1, Math.ceil(values.length * 0.95) - 1);
  return values[index];
}

function formatLatency(value: number | null): string {
  if (value == null) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}

function averageScore(rows: AgentLaunchpadRow[]): number | null {
  const scores = rows
    .map((row) => row.healthScore)
    .filter((score): score is number => typeof score === "number");
  if (scores.length === 0) return null;
  return scores.reduce((sum, score) => sum + score, 0) / scores.length;
}

function sumIssueCost(rows: AgentLaunchpadRow[]): number {
  return rows.reduce((sum, row) => sum + (row.latestIssue?.cost_impact_usd ?? 0), 0);
}

function buildAgentRows(
  scores: AgentScoreView[],
  calls: CallListItem[],
  issues: IssueItem[],
  decisions: RuntimePolicyDecisionResponse[] = [],
  outcomes: OutcomeReconciliationView[] = [],
): AgentLaunchpadRow[] {
  const statsByAgent = new Map<string, AgentStats>();
  const callsByAgent = new Map<string, CallListItem[]>();
  const callsById = new Map<string, CallListItem>();
  const scoreByAgent = new Map(scores.map((score) => [score.agent_name, score]));
  const issuesByAgent = new Map<string, IssueItem[]>();
  const decisionsByAgent = new Map<string, RuntimePolicyDecisionResponse>();
  const decisionsById = new Map<string, RuntimePolicyDecisionResponse>();
  const decisionsByCall = new Map<string, RuntimePolicyDecisionResponse>();
  const decisionsByTrace = new Map<string, RuntimePolicyDecisionResponse>();
  const outcomesByAgent = new Map<string, OutcomeReconciliationView>();
  const names = new Set<string>();

  for (const call of calls) {
    const agentName = agentNameFromCall(call);
    names.add(agentName);
    callsById.set(call.call_id, call);
    const existing = statsByAgent.get(agentName) ?? {
      callCount: 0,
      successfulCalls: 0,
      totalCostUsd: 0,
      successfulCostUsd: 0,
      lastEventAt: null,
      p95LatencyMs: null,
    };
    const successful = isSuccessfulCall(call);
    existing.callCount += 1;
    existing.totalCostUsd += call.cost_usd;
    existing.lastEventAt = latestDate(existing.lastEventAt, call.created_at);
    if (successful) {
      existing.successfulCalls += 1;
      existing.successfulCostUsd += call.cost_usd;
    }
    statsByAgent.set(agentName, existing);
    callsByAgent.set(agentName, [...(callsByAgent.get(agentName) ?? []), call]);
  }

  for (const [agentName, agentCalls] of callsByAgent) {
    const stats = statsByAgent.get(agentName);
    if (stats) {
      stats.p95LatencyMs = percentileLatency(agentCalls);
    }
  }

  for (const score of scores) {
    names.add(score.agent_name);
  }

  for (const issue of issues) {
    const agentName = agentNameFromIssue(issue);
    names.add(agentName);
    const existing = issuesByAgent.get(agentName) ?? [];
    existing.push(issue);
    issuesByAgent.set(agentName, existing);
  }

  for (const decision of decisions) {
    decisionsById.set(decision.id, decision);
    if (decision.call_id) {
      decisionsByCall.set(decision.call_id, latestByDate(
        decisionsByCall.get(decision.call_id) ?? null,
        decision,
        (item) => item.created_at,
      ));
    }
    if (decision.trace_id) {
      decisionsByTrace.set(decision.trace_id, latestByDate(
        decisionsByTrace.get(decision.trace_id) ?? null,
        decision,
        (item) => item.created_at,
      ));
    }
    const agentName = agentNameFromDecision(decision);
    if (!agentName) continue;
    names.add(agentName);
    decisionsByAgent.set(agentName, latestByDate(
      decisionsByAgent.get(agentName) ?? null,
      decision,
      (item) => item.created_at,
    ));
  }

  for (const outcome of outcomes) {
    const agentName = outcomeAgentName(outcome, decisionsById, decisionsByCall, decisionsByTrace, callsById);
    if (!agentName) continue;
    names.add(agentName);
    outcomesByAgent.set(agentName, higherPriorityOutcome(
      outcomesByAgent.get(agentName) ?? null,
      outcome,
    ));
  }

  return Array.from(names)
    .map((agentName) => {
      const score = scoreByAgent.get(agentName) ?? null;
      const stats = statsByAgent.get(agentName) ?? null;
      const sortedIssues = [...(issuesByAgent.get(agentName) ?? [])].sort(issuePriority);
      const latestIssue = sortedIssues[0] ?? null;
      const latestDecision = decisionsByAgent.get(agentName) ?? null;
      const latestOutcome = outcomesByAgent.get(agentName) ?? null;
      const successRate =
        stats && stats.callCount > 0
          ? (stats.successfulCalls / stats.callCount) * 100
          : score
            ? Math.max(0, (1 - score.fail_rate) * 100)
            : null;
      const costPerSuccessfulTask =
        stats && stats.successfulCalls > 0
          ? stats.successfulCostUsd / stats.successfulCalls
          : null;
      const replayCoverage = latestIssue ? replayLabel(latestIssue.replay_coverage_status) : "No open issue";
      const row = {
        agentName,
        healthScore: score?.health_score ?? null,
        latestIssue,
        latestDecision,
        latestOutcome,
        successRate,
        costPerSuccessfulTask,
        replayCoverage,
        lastEventAt: [stats?.lastEventAt, latestIssue?.last_seen_at, latestDecision?.created_at, latestOutcome?.checked_at]
          .filter((value): value is string => Boolean(value))
          .sort((a, b) => timestamp(b) - timestamp(a))[0] ?? null,
        recommendedAction: "",
        callCount: stats?.callCount ?? score?.call_count ?? 0,
        successfulCalls: stats?.successfulCalls ?? 0,
        p95LatencyMs: stats?.p95LatencyMs ?? score?.p95_latency_ms ?? null,
      };
      return {
        ...row,
        recommendedAction: recommendedActionFor(row),
      };
    })
    .sort((a, b) => {
      const issueDelta = (b.latestIssue?.priority_score ?? -1) - (a.latestIssue?.priority_score ?? -1);
      if (issueDelta !== 0) return issueDelta;
      const healthDelta = (a.healthScore ?? 101) - (b.healthScore ?? 101);
      if (healthDelta !== 0) return healthDelta;
      return new Date(b.lastEventAt ?? 0).getTime() - new Date(a.lastEventAt ?? 0).getTime();
    });
}

function AgentsSetupState({
  captureHealth,
  callsToday,
  setupOpened,
  onRefresh,
  onMarkOpened,
}: {
  captureHealth: CaptureHealthResponse | null;
  callsToday: number;
  setupOpened: boolean;
  onRefresh: () => void;
  onMarkOpened: () => void;
}) {
  const connected = captureHealth?.status === "connected";
  const checklistItems = [
    { label: "Capture stream connected", done: connected },
    { label: "At least one agent action ingested", done: callsToday > 0 || (captureHealth?.calls_24h ?? 0) > 0 },
    { label: "Setup path opened", done: setupOpened },
  ];
  const completed = checklistItems.filter((item) => item.done).length;

  return (
    <section className="agents-setup-grid">
      <article className="agents-empty-card">
        <div className="agents-eyebrow">
          <Zap aria-hidden="true" />
          Protection setup
        </div>
        <h2>Connect one real agent action to start proof.</h2>
        <p>
          Once capture starts, Zroky ranks agents by mandate health, open proof gaps, outcome evidence, replay coverage, latency, and risk exposure.
        </p>
        <button type="button" className="btn btn-soft" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Check capture
        </button>
      </article>
      <CaptureConnectPanel
        captureHealth={captureHealth}
        checklistItems={checklistItems}
        completedCount={completed}
        totalCount={checklistItems.length}
        progressPct={Math.round((completed / checklistItems.length) * 100)}
        onRefresh={onRefresh}
        onMarkOpened={onMarkOpened}
      />
    </section>
  );
}

function AgentsLoadingState() {
  return (
    <div className="agents-screen">
      <section className="agents-hero-panel agents-skeleton-card">
        <div className="agents-hero-copy">
          <div className="agents-eyebrow">
            <Activity aria-hidden="true" />
            Protected agents
          </div>
          <h1>Agent accountability ledger</h1>
          <p>Loading mandate health, runtime decisions, outcome checks, and replay proof for this workspace.</p>
        </div>
      </section>
      <section className="agents-kpi-grid">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="agents-kpi-card agents-skeleton-card">
            <span />
            <strong />
            <p />
          </div>
        ))}
      </section>
      <section className="agents-layout-grid">
        <div className="agents-main-column">
          <article className="agents-chart-panel agents-skeleton-card" />
          <article className="agents-table-panel agents-skeleton-card" />
        </div>
        <aside className="agents-inspector-panel agents-skeleton-card" />
      </section>
    </div>
  );
}

function AgentHealthBadge({ score }: { score: number | null }) {
  const tone = healthTone(score);
  return (
    <div className="agent-health-pill">
      <span className={`alert-cat-badge ${tone.className}`}>
        {tone.label}
      </span>
      <strong>{score == null ? "-" : Math.round(score)}</strong>
    </div>
  );
}

function FailureRateChart({ scores }: { scores: AgentScoreView[] }) {
  const source = scores.length > 0 ? [...scores].sort((a, b) => b.fail_rate - a.fail_rate).slice(0, 7) : [];
  const points = source.map((score) => ({
    agent: score.agent_name,
    current: score.fail_rate * 100,
    previous: (score.prev_week_fail_rate ?? score.fail_rate) * 100,
  }));

  if (points.length === 0) {
    return (
      <div className="agents-trend-chart" aria-label="Behavior drift by agent">
        <p className="agents-muted">No scored agent drift yet.</p>
      </div>
    );
  }

  const width = 640;
  const height = 240;
  const step = width / Math.max(points.length - 1, 1);

  const mapSeries = (values: number[]) =>
    values.map((value, index) => {
      const y = height - (Math.max(0, Math.min(12, value)) / 12) * 170 - 28;
      return [Math.round(index * step), Math.round(y)] as const;
    });

  const currentCoords = mapSeries(points.map((point) => point.current));
  const previousCoords = mapSeries(points.map((point) => point.previous));
  const buildPath = (coords: readonly (readonly [number, number])[]) =>
    coords.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`).join(" ");
  const currentLine = buildPath(currentCoords);
  const previousLine = buildPath(previousCoords);
  const currentArea = `${currentLine} L${width} ${height} L0 ${height} Z`;

  return (
    <div className="agents-trend-chart" aria-label="Behavior drift by agent">
      <div className="agents-chart-legend">
        <span>
          <i className="agents-legend-swatch is-current" aria-hidden="true" />
          Current risk
        </span>
        <span>
          <i className="agents-legend-swatch is-previous" aria-hidden="true" />
          Previous 7 days
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <path className="agents-trend-area" d={currentArea} />
        <path className="agents-trend-line agents-trend-line-previous" d={previousLine} />
        <path className="agents-trend-line" d={currentLine} />
        {currentCoords.map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="4" />
        ))}
      </svg>
      <div className="agents-chart-footer agents-chart-labels">
        {points.map((point) => (
          <span key={point.agent}>{point.agent}</span>
        ))}
      </div>
    </div>
  );
}

function CostOfFailureChart({ rows }: { rows: AgentLaunchpadRow[] }) {
  const costRows = buildCostExposureRows(rows);
  const maxCost = Math.max(...costRows.map((row) => row.costUsd), 1);

  return (
    <div className="agents-bar-list">
      {costRows.length > 0 ? (
        costRows.map((row) => {
          const content = (
            <>
              <div className="agents-bar-copy">
                <strong>{row.agentName}</strong>
                <span>{row.issueTitle ?? "Open issue impact"}</span>
              </div>
              <div className="agents-bar-track" aria-hidden="true">
                <span className="agents-bar-fill" style={{ width: `${Math.max(10, (row.costUsd / maxCost) * 100)}%` }} />
              </div>
              <strong className="agents-bar-value">{formatUsd(row.costUsd)}</strong>
            </>
          );

          return row.issueId ? (
            <Link key={`${row.agentName}-${row.issueId}`} href={`/issues/${encodeURIComponent(row.issueId)}`} className="agents-bar-row">
              {content}
            </Link>
          ) : (
            <div key={`${row.agentName}-${row.costUsd}`} className="agents-bar-row">
              {content}
            </div>
          );
        })
      ) : (
        <p className="agents-muted">No open outcome risk yet.</p>
      )}
    </div>
  );
}

function SignalClustersTable({ issues }: { issues: IssueItem[] }) {
  const clusters = buildSignalClusters(issues);

  return (
    <div className="agents-clusters-wrap">
      {clusters.length > 0 ? (
        <table className="agents-clusters-table">
          <thead>
            <tr>
              <th>Proof gap</th>
              <th>Events</th>
              <th>Affected agents</th>
              <th>First seen</th>
              <th>Risk</th>
              <th>Replay proof</th>
            </tr>
          </thead>
          <tbody>
            {clusters.map((cluster) => (
              <tr key={cluster.key}>
                <td>
                  <Link href={`/issues/${encodeURIComponent(cluster.issueId)}`} className="agents-cluster-link">
                    <span className={`alert-cat-badge ${severityTone(cluster.severity)}`}>{cluster.severity}</span>
                    <div>
                      <strong>{cluster.title}</strong>
                      <small>{cluster.failureCode.replace(/_/g, " ").toLowerCase()}</small>
                    </div>
                  </Link>
                </td>
                <td>{formatCount(cluster.occurrences)}</td>
                <td>{formatCount(cluster.affectedAgents)}</td>
                <td>{formatDateTime(cluster.firstSeenAt)}</td>
                <td>{cluster.severity}</td>
                <td>{cluster.replayCoverage}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="agents-muted">No proof gap clusters detected yet.</p>
      )}
    </div>
  );
}

function TraceTimeline({ focusRow, calls }: { focusRow: AgentLaunchpadRow | null; calls: CallListItem[] }) {
  const entries = buildTimelineEntries(focusRow?.latestIssue ?? null, focusRow?.agentName ?? null, calls);
  const maxLatency = Math.max(...entries.map((entry) => entry.latencyMs), 1);

  return (
    <div className="agents-timeline-list">
      {entries.length > 0 ? (
        entries.map((entry) => (
          <Link key={entry.key} href={entry.href} className="agents-timeline-row">
            <div className="agents-timeline-copy">
              <strong>{entry.label}</strong>
              <span>{entry.detail}</span>
            </div>
            <div className="agents-timeline-track" aria-hidden="true">
              <span
                className="agents-timeline-fill"
                style={{ width: `${Math.max(12, (entry.latencyMs / maxLatency) * 100)}%` }}
              />
            </div>
            <div className="agents-timeline-meta">
              <span>{entry.status}</span>
              <strong>{formatLatency(entry.latencyMs)}</strong>
              <small>{formatDateTime(entry.startedAt)}</small>
            </div>
          </Link>
        ))
      ) : (
        <p className="agents-muted">No evidence trail captured yet.</p>
      )}
    </div>
  );
}

function AgentRow({ row }: { row: AgentLaunchpadRow }) {
  return (
    <tr className="agents-table-row">
      <td>
        <div className="agents-name-cell">
          <span className="agents-agent-icon" aria-hidden="true">
            <Bot />
          </span>
          <div>
            <strong>{row.agentName}</strong>
            <span>{formatCount(row.callCount)} recent call{row.callCount === 1 ? "" : "s"}</span>
          </div>
        </div>
      </td>
      <td>
        <div className="agents-proof-cell">
          <span className={`alert-cat-badge ${decisionTone(row.latestDecision)}`}>
            {decisionDisplay(row.latestDecision)}
          </span>
          <span className="agents-cell-note">{decisionDetail(row.latestDecision)}</span>
        </div>
      </td>
      <td>
        <div className="agents-proof-cell">
          <span className={`alert-cat-badge ${outcomeTone(row.latestOutcome)}`}>
            {outcomeDisplay(row.latestOutcome)}
          </span>
          <span className="agents-cell-note">{outcomeDetail(row.latestOutcome)}</span>
        </div>
      </td>
      <td>
        {row.latestDecision ? (
          <div className="agents-proof-cell">
            <Link href={evidencePackHref(row.latestDecision.id)} className="agents-text-link">
              <FileJson aria-hidden="true" />
              Evidence Pack
            </Link>
            <span className="agents-cell-note">{row.latestDecision.id}</span>
          </div>
        ) : (
          <span className="agents-muted">No decision id</span>
        )}
      </td>
      <td>
        <AgentHealthBadge score={row.healthScore} />
      </td>
      <td>
        <strong>{row.successRate == null ? "-" : formatPercent(row.successRate)}</strong>
        <span className="agents-cell-note">{row.successfulCalls > 0 ? `${formatCount(row.successfulCalls)} successful` : "No success sample"}</span>
      </td>
      <td>
        <strong>{row.costPerSuccessfulTask == null ? "-" : formatUsd(row.costPerSuccessfulTask)}</strong>
        <span className="agents-cell-note">per verified success</span>
      </td>
      <td>
        <strong>{formatLatency(row.p95LatencyMs)}</strong>
        <span className="agents-cell-note">p95 latency</span>
      </td>
      <td>
        {row.latestIssue ? (
          <Link href={`/issues/${encodeURIComponent(row.latestIssue.id)}`} className="agents-issue-link">
            <span className={`alert-cat-badge ${severityTone(row.latestIssue.severity)}`}>
              {row.latestIssue.severity}
            </span>
            {row.latestIssue.title}
          </Link>
        ) : (
          <span className="agents-muted">No open issue</span>
        )}
      </td>
      <td>
        <span className="agents-muted">{row.replayCoverage}</span>
      </td>
      <td>
        <span className="agents-muted">{formatDateTime(row.lastEventAt)}</span>
      </td>
    </tr>
  );
}

function AgentsProofChain({ row }: { row: AgentLaunchpadRow }) {
  return (
    <div className="agents-proof-chain" aria-label="Selected agent proof chain">
      <div>
        <span>Runtime decision</span>
        <strong>{decisionDisplay(row.latestDecision)}</strong>
        <small>{decisionDetail(row.latestDecision)}</small>
      </div>
      <div>
        <span>Outcome verdict</span>
        <strong>{outcomeDisplay(row.latestOutcome)}</strong>
        <small>{outcomeDetail(row.latestOutcome)}</small>
      </div>
      <div>
        <span>Evidence Pack</span>
        {row.latestDecision ? (
          <Link href={evidencePackHref(row.latestDecision.id)} className="agents-text-link">
            Export JSON
            <ArrowRight aria-hidden="true" />
          </Link>
        ) : (
          <strong>not_verified</strong>
        )}
        <small>{row.latestDecision?.id ?? "No decision id"}</small>
      </div>
    </div>
  );
}

function AgentsHero({
  captureHealth,
  callsToday,
  openIssues,
  rows,
  onRefresh,
}: {
  captureHealth: CaptureHealthResponse | null;
  callsToday: number;
  openIssues: number;
  rows: AgentLaunchpadRow[];
  onRefresh: () => void;
}) {
  const connected = captureHealth?.status === "connected";
  const avgHealth = averageScore(rows);

  return (
    <section className="agents-hero-panel">
      <div className="agents-hero-copy">
        <div className="agents-eyebrow">
          <Activity aria-hidden="true" />
          Protected agents
        </div>
        <h1>Agent accountability ledger</h1>
        <p>
          Fleet view for autonomous agents that touch systems of record: mandate health, proof gaps, outcome evidence, replay coverage, and risk exposure.
        </p>
      </div>
      <div className="agents-hero-actions">
        <Link href="/replay" className="btn btn-primary">
          <RotateCcw aria-hidden="true" />
          Run replay
        </Link>
        <button type="button" className="btn btn-soft" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </div>
      <div className="agents-hero-strip">
        <div>
          <span className={connected ? "agents-live-dot is-live" : "agents-live-dot"} aria-hidden="true" />
          <strong>{captureHealth?.status ?? "unknown"}</strong>
          <small>capture stream</small>
        </div>
        <div>
          <strong>{formatCount(callsToday)}</strong>
          <small>actions today</small>
        </div>
        <div>
          <strong>{formatCount(openIssues)}</strong>
          <small>open proof gaps</small>
        </div>
        <div>
          <strong>{avgHealth == null ? "-" : Math.round(avgHealth)}</strong>
          <small>avg mandate health</small>
        </div>
      </div>
    </section>
  );
}

function AgentsKpis({
  rows,
  openIssues,
  atRiskAgents,
}: {
  rows: AgentLaunchpadRow[];
  openIssues: number;
  atRiskAgents: number;
}) {
  const issueCost = sumIssueCost(rows);
  const protectedCost = verifiedCostCoverage(rows);
  const runtimeHoldOrBlock = rows.filter((row) => {
    const decision = row.latestDecision;
    return decision?.decision === "block" || decision?.decision === "requires_approval" || decision?.status === "pending_approval";
  }).length;
  const outcomeRows = rows.filter((row) => row.latestOutcome);
  const matchedOutcomes = outcomeRows.filter((row) => row.latestOutcome?.verdict === "matched").length;
  const missingOutcomes = rows.filter((row) => row.latestDecision && !row.latestOutcome).length;
  const cards = [
    {
      icon: AlertTriangle,
      label: "Open proof gaps",
      value: formatCount(openIssues),
      helper: `${formatCount(atRiskAgents)} agents need attention`,
    },
    {
      icon: RotateCcw,
      label: "Held / blocked",
      value: formatCount(runtimeHoldOrBlock),
      helper: "runtime decisions that stopped or paused action",
    },
    {
      icon: ShieldCheck,
      label: "Outcomes matched",
      value: outcomeRows.length > 0 ? `${formatCount(matchedOutcomes)}/${formatCount(outcomeRows.length)}` : "0",
      helper: `${formatCount(missingOutcomes)} decision${missingOutcomes === 1 ? "" : "s"} still not_verified`,
    },
    {
      icon: Gauge,
      label: "Risk exposure",
      value: formatUsd(issueCost),
      helper: protectedCost > 0 ? `${formatUsd(protectedCost)} covered by verified proof` : "no verified cost coverage yet",
    },
  ];

  return (
    <section className="agents-kpi-grid" aria-label="Agent health metrics">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <article key={card.label} className="agents-kpi-card">
            <span className="agents-kpi-icon" aria-hidden="true">
              <Icon />
            </span>
            <div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <small>{card.helper}</small>
            </div>
          </article>
        );
      })}
    </section>
  );
}

function AgentsInspector({ focusRow }: { focusRow: AgentLaunchpadRow | null }) {
  const issue = focusRow?.latestIssue ?? null;
  const leadTrace = issue?.evidence_traces?.[0] ?? null;
  const traceHref = leadTrace?.call_id
    ? `/calls/${encodeURIComponent(leadTrace.call_id)}`
    : leadTrace?.trace_id
      ? `/trace/${encodeURIComponent(leadTrace.trace_id)}`
      : "/trace";
  const envLabel = (process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "staging").toUpperCase();

  return (
    <aside className="agents-inspector-panel">
      <div className="agents-panel-head">
        <div>
          <span>Agent proof focus</span>
          <strong>{focusRow?.agentName ?? "No agent selected"}</strong>
        </div>
        {issue ? <span className={`alert-cat-badge ${severityTone(issue.severity)}`}>{issue.severity}</span> : null}
      </div>

      {focusRow ? (
        <>
          <div className="agents-inspector-score">
            <div>
              <span>Health</span>
              <strong>{focusRow.healthScore == null ? "-" : Math.round(focusRow.healthScore)}</strong>
            </div>
            <div>
              <span>Success</span>
              <strong>{focusRow.successRate == null ? "-" : formatPercent(focusRow.successRate)}</strong>
            </div>
          </div>

          <AgentsProofChain row={focusRow} />

          {issue ? (
            <>
              <div className="agents-inspector-meta-grid">
                <div>
                  <span>Detected</span>
                  <strong>{formatDateTime(issue.created_at)}</strong>
                </div>
                <div>
                  <span>First seen</span>
                  <strong>{formatDateTime(issue.first_seen_at)}</strong>
                </div>
                <div>
                  <span>Occurrences</span>
                  <strong>{formatCount(issue.occurrence_count)}</strong>
                </div>
                <div>
                  <span>Environment</span>
                  <strong>{envLabel}</strong>
                </div>
                <div>
                  <span>Evidence ID</span>
                  <strong>{leadTrace?.trace_id ?? "Unavailable"}</strong>
                </div>
                <div>
                  <span>Replay proof</span>
                  <strong>{replayLabel(issue.replay_coverage_status)}</strong>
                </div>
              </div>

              <div className="agents-issue-summary">
                <span>{issue.failure_code.replace(/_/g, " ").toLowerCase()}</span>
                <h2>{issue.title}</h2>
                <p>{issue.root_cause || issue.user_impact}</p>
              </div>

              <dl className="agents-inspector-list">
                <div>
                  <dt>Occurrences</dt>
                  <dd>{formatCount(issue.occurrence_count)}</dd>
                </div>
                <div>
                  <dt>Risk exposure</dt>
                  <dd>{formatUsd(issue.cost_impact_usd || issue.blast_radius_usd)}</dd>
                </div>
                <div>
                  <dt>Replay proof</dt>
                  <dd>{focusRow.replayCoverage}</dd>
                </div>
                <div>
                  <dt>Last seen</dt>
                  <dd>{formatDateTime(issue.last_seen_at)}</dd>
                </div>
              </dl>

              <div className="agents-evidence-list">
                {(issue.evidence_traces ?? []).slice(0, 3).map((trace) => (
                  <Link
                    key={trace.call_id}
                    href={trace.call_id ? `/calls/${encodeURIComponent(trace.call_id)}` : "/calls"}
                    className="agents-evidence-row"
                  >
                    <span>{trace.status ?? "trace"}</span>
                    <strong>{trace.workflow_name ?? trace.trace_id ?? trace.call_id ?? "Captured call"}</strong>
                    <small>{formatLatency(trace.latency_ms)}</small>
                  </Link>
                ))}
              </div>

              <div className="agents-inspector-actions">
                <Link href="/replay" className="btn btn-primary">
                  Run replay
                  <RotateCcw aria-hidden="true" />
                </Link>
                <Link href={traceHref} className="btn btn-soft">
                  View evidence trace
                </Link>
              </div>
            </>
          ) : (
            <div className="agents-issue-summary">
              <span>quiet agent</span>
              <h2>No open proof gap attached.</h2>
              <p>{focusRow.recommendedAction}</p>
              <div className="agents-inspector-actions">
                <Link href={`/calls?agent_name=${encodeURIComponent(focusRow.agentName)}`} className="btn btn-primary">
                  View agent calls
                  <ArrowRight aria-hidden="true" />
                </Link>
                <Link href="/contracts" className="btn btn-soft">
                  Promote mandate
                </Link>
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="agents-muted">Connect capture to populate mandate health, trace evidence, and replay guidance.</p>
      )}
    </aside>
  );
}

function AgentsOperations({
  scores,
  rows,
  focusRow,
  calls,
}: {
  scores: AgentScoreView[];
  rows: AgentLaunchpadRow[];
  focusRow: AgentLaunchpadRow | null;
  calls: CallListItem[];
}) {
  return (
    <section className="agents-evidence-grid">
      <article className="agents-mini-panel">
        <div className="agents-panel-head">
          <div>
            <span>Behavior drift by agent</span>
            <strong>Failure-rate movement from captured runs</strong>
          </div>
          <Activity aria-hidden="true" />
        </div>
        <FailureRateChart scores={scores} />
      </article>

      <article className="agents-mini-panel">
        <div className="agents-panel-head">
          <div>
            <span>Risk exposure</span>
            <strong>Open proof gap blast radius by agent</strong>
          </div>
          <Gauge aria-hidden="true" />
        </div>
        <CostOfFailureChart rows={rows} />
      </article>

      <article className="agents-mini-panel">
        <div className="agents-panel-head">
          <div>
            <span>Evidence trail</span>
            <strong>System evidence from the selected proof gap</strong>
          </div>
          <Clock3 aria-hidden="true" />
        </div>
        <TraceTimeline focusRow={focusRow} calls={calls} />
      </article>
    </section>
  );
}

export default function AgentsPage() {
  const [setupOpened, setSetupOpened] = useState(false);
  const setSdkConnected = useDashboardStore((state) => state.setSdkConnected);
  const leaderboardQuery = useReliabilityLeaderboard(100);
  const callsQuery = useQuery({
    queryKey: ["agents", "recent-calls"],
    queryFn: ({ signal }) =>
      listCalls({ limit: 200, sort_by: "created_at", sort_order: "desc" }, signal),
    refetchInterval: 30_000,
  });
  const issuesQuery = useQuery({
    queryKey: ["agents", "open-issues"],
    queryFn: ({ signal }) => listIssues({ status: "open", limit: 100 }, signal),
    refetchInterval: 30_000,
  });
  const captureHealthQuery = useQuery({
    queryKey: ["agents", "capture-health"],
    queryFn: ({ signal }) => getCaptureHealth(signal),
    refetchInterval: 30_000,
  });
  const summaryQuery = useQuery({
    queryKey: ["agents", "analytics-summary", 1],
    queryFn: ({ signal }) => getAnalyticsSummary(1, signal),
    refetchInterval: 30_000,
  });
  const runtimeDecisionsQuery = useQuery({
    queryKey: ["agents", "runtime-policy", "decisions", "all"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
    refetchInterval: 30_000,
  });
  const outcomeChecksQuery = useQuery({
    queryKey: ["agents", "outcomes", "reconciliation"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ limit: 50 }, signal),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      setSetupOpened(window.localStorage.getItem(ONBOARDING_WIZARD_OPENED_KEY) === "1");
    }
  }, []);

  useEffect(() => {
    setSdkConnected(captureHealthQuery.data?.status === "connected");
  }, [captureHealthQuery.data?.status, setSdkConnected]);

  const markSetupOpened = useCallback(() => {
    setSetupOpened(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ONBOARDING_WIZARD_OPENED_KEY, "1");
    }
  }, []);

  const refreshAll = useCallback(() => {
    void Promise.all([
      leaderboardQuery.refetch(),
      callsQuery.refetch(),
      issuesQuery.refetch(),
      captureHealthQuery.refetch(),
      summaryQuery.refetch(),
      runtimeDecisionsQuery.refetch(),
      outcomeChecksQuery.refetch(),
    ]);
  }, [callsQuery, captureHealthQuery, issuesQuery, leaderboardQuery, outcomeChecksQuery, runtimeDecisionsQuery, summaryQuery]);

  const rows = useMemo(
    () =>
      buildAgentRows(
        leaderboardQuery.data ?? [],
        callsQuery.data?.items ?? [],
        issuesQuery.data?.items ?? [],
        runtimeDecisionsQuery.data?.items ?? [],
        outcomeChecksQuery.data?.items ?? [],
      ),
    [
      callsQuery.data?.items,
      issuesQuery.data?.items,
      leaderboardQuery.data,
      outcomeChecksQuery.data?.items,
      runtimeDecisionsQuery.data?.items,
    ],
  );

  const primaryQueries = [leaderboardQuery, callsQuery, issuesQuery, runtimeDecisionsQuery, outcomeChecksQuery];
  const loading = primaryQueries.every((query) => query.isLoading && query.data === undefined);
  const hasRows = rows.length > 0;
  const callsToday = summaryQuery.data?.calls_today ?? 0;
  const openIssues = issuesQuery.data?.items.length ?? 0;
  const atRiskAgents = rows.filter((row) => row.healthScore != null && row.healthScore < 55).length;
  const focusRow =
    rows.find((row) => row.latestOutcome?.verdict === "mismatched") ??
    rows.find((row) => row.latestDecision?.status === "pending_approval") ??
    rows.find((row) => row.latestIssue) ??
    rows.find((row) => row.healthScore != null && row.healthScore < 55) ??
    rows[0] ??
    null;

  if (loading && !hasRows) {
    return <AgentsLoadingState />;
  }

  if (!hasRows) {
    return (
      <div className="agents-screen">
        <AgentsHero
          captureHealth={captureHealthQuery.data ?? null}
          callsToday={callsToday}
          openIssues={openIssues}
          rows={rows}
          onRefresh={refreshAll}
        />
        <AgentsSetupState
          captureHealth={captureHealthQuery.data ?? null}
          callsToday={callsToday}
          setupOpened={setupOpened}
          onRefresh={refreshAll}
          onMarkOpened={markSetupOpened}
        />
      </div>
    );
  }

  return (
    <div className="agents-screen">
      <AgentsHero
        captureHealth={captureHealthQuery.data ?? null}
        callsToday={callsToday}
        openIssues={openIssues}
        rows={rows}
        onRefresh={refreshAll}
      />

      <AgentsKpis
        rows={rows}
        openIssues={openIssues}
        atRiskAgents={atRiskAgents}
      />

      <AgentsOperations
        scores={leaderboardQuery.data ?? []}
        rows={rows}
        focusRow={focusRow}
        calls={callsQuery.data?.items ?? []}
      />

      <section className="agents-layout-grid">
        <div className="agents-main-column">
          <article className="agents-table-panel">
            <div className="agents-panel-head">
              <div>
                <span>Proof gap clusters</span>
                <strong>Failure patterns grouped from production agent actions</strong>
              </div>
              <Link href="/issues" className="agents-text-link">
                Open incidents
                <ArrowRight aria-hidden="true" />
              </Link>
            </div>
            <SignalClustersTable issues={issuesQuery.data?.items ?? []} />
          </article>

          <article className="agents-chart-panel">
            <div className="agents-panel-head">
              <div>
                <span>Protected agent matrix</span>
                <strong>Runtime decision, outcome verdict, Evidence Pack, and reliability context</strong>
              </div>
              <span className="agents-table-count">{formatCount(rows.length)} agents</span>
            </div>
            <div className="agents-table-wrap">
              <table className="agents-table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Runtime decision</th>
                    <th>Outcome</th>
                    <th>Evidence Pack</th>
                    <th>Mandate health</th>
                    <th>Success</th>
                    <th>Cost / success</th>
                    <th>Latency</th>
                    <th>Proof gap</th>
                    <th>Replay proof</th>
                    <th>Last evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <AgentRow key={row.agentName} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <AgentsInspector focusRow={focusRow} />
      </section>

      {captureHealthQuery.data?.validation_warnings?.length ? (
        <section className="agents-warning-panel" id="capture-warnings">
          <div className="agents-panel-head">
            <div>
              <span>Evidence capture quality</span>
              <strong>Warnings that affect proof and attribution accuracy</strong>
            </div>
            <AlertTriangle aria-hidden="true" />
          </div>
          <div className="agents-warning-list">
            {captureHealthQuery.data.validation_warnings.map((warning) => (
              <div key={warning.code}>
                <strong>{warning.label}</strong>
                <span>{warning.detail}</span>
                <small className="mono">{warning.code}</small>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="agents-quality-panel">
          <CheckCircle2 aria-hidden="true" />
          <div>
            <strong>No evidence capture warnings.</strong>
            <span>Agent attribution, source, and payload quality are clean for this window.</span>
          </div>
        </section>
      )}

      <section className="agents-footnote-panel">
        <Clock3 aria-hidden="true" />
        <span>
          Recommendations use issue objects when available, then fall back to mandate health, success rate, latency, and replay coverage.
        </span>
      </section>
    </div>
  );
}
