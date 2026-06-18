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
  passingGuardrailRate,
  replayReadyCount,
  verifiedCostCoverage,
} from "@/lib/agents-console";
import { getAnalyticsSummary, getCaptureHealth, listCalls, listIssues } from "@/lib/api";
import type { AgentScoreView } from "@/lib/api";
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
}): string {
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
): AgentLaunchpadRow[] {
  const statsByAgent = new Map<string, AgentStats>();
  const callsByAgent = new Map<string, CallListItem[]>();
  const scoreByAgent = new Map(scores.map((score) => [score.agent_name, score]));
  const issuesByAgent = new Map<string, IssueItem[]>();
  const names = new Set<string>();

  for (const call of calls) {
    const agentName = agentNameFromCall(call);
    names.add(agentName);
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

  return Array.from(names)
    .map((agentName) => {
      const score = scoreByAgent.get(agentName) ?? null;
      const stats = statsByAgent.get(agentName) ?? null;
      const sortedIssues = [...(issuesByAgent.get(agentName) ?? [])].sort(issuePriority);
      const latestIssue = sortedIssues[0] ?? null;
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
        successRate,
        costPerSuccessfulTask,
        replayCoverage,
        lastEventAt: stats?.lastEventAt ?? latestIssue?.last_seen_at ?? null,
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
    { label: "At least one call ingested", done: callsToday > 0 || (captureHealth?.calls_24h ?? 0) > 0 },
    { label: "Setup path opened", done: setupOpened },
  ];
  const completed = checklistItems.filter((item) => item.done).length;

  return (
    <section className="agents-setup-grid">
      <article className="agents-empty-card">
        <div className="agents-eyebrow">
          <Zap aria-hidden="true" />
          Setup required
        </div>
        <h2>Connect one real agent call to activate the control plane.</h2>
        <p>
          Once capture starts, this page ranks agents by health, open issue priority, replay proof, latency, and cost per successful task.
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
        <span />
        <strong />
        <p />
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
  const fallback = [
    { agent: "Refund", current: 6.1, previous: 4.4 },
    { agent: "Billing", current: 4.8, previous: 3.6 },
    { agent: "Order", current: 4.2, previous: 4.9 },
    { agent: "Return", current: 3.6, previous: 3.2 },
    { agent: "Support", current: 2.9, previous: 2.6 },
  ];
  const points =
    source.length >= 3
      ? source.map((score) => ({
          agent: score.agent_name,
          current: score.fail_rate * 100,
          previous: (score.prev_week_fail_rate ?? score.fail_rate) * 100,
        }))
      : fallback;
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
    <div className="agents-trend-chart" aria-label="Failure rate by agent">
      <div className="agents-chart-legend">
        <span>
          <i className="agents-legend-swatch is-current" aria-hidden="true" />
          Current
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
        <p className="agents-muted">No open issue blast radius yet.</p>
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
              <th>Cluster</th>
              <th>Occurrences</th>
              <th>Affected agents</th>
              <th>First seen</th>
              <th>Impact</th>
              <th>Replay</th>
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
        <p className="agents-muted">No issue clusters detected yet.</p>
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
        <p className="agents-muted">No captured traces yet.</p>
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
        <AgentHealthBadge score={row.healthScore} />
      </td>
      <td>
        <strong>{row.successRate == null ? "-" : formatPercent(row.successRate)}</strong>
        <span className="agents-cell-note">{row.successfulCalls > 0 ? `${formatCount(row.successfulCalls)} successful` : "No success sample"}</span>
      </td>
      <td>
        <strong>{row.costPerSuccessfulTask == null ? "-" : formatUsd(row.costPerSuccessfulTask)}</strong>
        <span className="agents-cell-note">per success</span>
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
          Release safety
        </div>
        <h1>Release Safety Console</h1>
        <p>
          Overview of reliability regressions, replay readiness, and blast radius across your production agents.
        </p>
      </div>
      <div className="agents-hero-actions">
        <button type="button" className="btn btn-soft" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
        <Link href="/replay" className="btn btn-primary">
          <RotateCcw aria-hidden="true" />
          Run replay
        </Link>
      </div>
      <div className="agents-hero-strip">
        <div>
          <span className={connected ? "agents-live-dot is-live" : "agents-live-dot"} aria-hidden="true" />
          <strong>{captureHealth?.status ?? "unknown"}</strong>
          <small>capture</small>
        </div>
        <div>
          <strong>{formatCount(callsToday)}</strong>
          <small>calls today</small>
        </div>
        <div>
          <strong>{formatCount(openIssues)}</strong>
          <small>active issues</small>
        </div>
        <div>
          <strong>{avgHealth == null ? "-" : Math.round(avgHealth)}</strong>
          <small>avg health</small>
        </div>
      </div>
    </section>
  );
}

function AgentsKpis({
  rows,
  openIssues,
  replayGaps,
  atRiskAgents,
}: {
  rows: AgentLaunchpadRow[];
  openIssues: number;
  replayGaps: number;
  atRiskAgents: number;
}) {
  const issueCost = sumIssueCost(rows);
  const replayReady = replayReadyCount(
    rows.map((row) => row.latestIssue).filter((issue): issue is IssueItem => issue != null),
  );
  const guardrailRate = passingGuardrailRate(rows);
  const protectedCost = verifiedCostCoverage(rows);
  const cards = [
    {
      icon: AlertTriangle,
      label: "Active issues",
      value: formatCount(openIssues),
      helper: `${formatCount(atRiskAgents)} at-risk agents`,
    },
    {
      icon: RotateCcw,
      label: "Replay ready",
      value: formatCount(replayReady),
      helper: `${formatCount(replayGaps)} still missing proof`,
    },
    {
      icon: ShieldCheck,
      label: "Guardrails passing",
      value: guardrailRate == null ? "-" : formatPercent(guardrailRate),
      helper: `${formatCount(rows.length)} monitored agents`,
    },
    {
      icon: Gauge,
      label: "Failure cost exposed",
      value: formatUsd(issueCost),
      helper: protectedCost > 0 ? `${formatUsd(protectedCost)} covered by passing replay` : "no verified cost coverage yet",
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
          <span>Issue focus</span>
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
                  <span>Trace ID</span>
                  <strong>{leadTrace?.trace_id ?? "Unavailable"}</strong>
                </div>
                <div>
                  <span>Replay status</span>
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
                  <dt>Cost impact</dt>
                  <dd>{formatUsd(issue.cost_impact_usd || issue.blast_radius_usd)}</dd>
                </div>
                <div>
                  <dt>Replay</dt>
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
                  View full trace
                </Link>
              </div>
            </>
          ) : (
            <div className="agents-issue-summary">
              <span>quiet agent</span>
              <h2>No open issue attached.</h2>
              <p>{focusRow.recommendedAction}</p>
              <div className="agents-inspector-actions">
                <Link href={`/calls?agent_name=${encodeURIComponent(focusRow.agentName)}`} className="btn btn-primary">
                  View calls
                  <ArrowRight aria-hidden="true" />
                </Link>
                <Link href="/contracts" className="btn btn-soft">
                  Promote contract
                </Link>
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="agents-muted">Connect capture to populate priority, trace evidence, and replay guidance.</p>
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
            <span>Failure rate by agent</span>
            <strong>Current versus previous 7 days</strong>
          </div>
          <Activity aria-hidden="true" />
        </div>
        <FailureRateChart scores={scores} />
      </article>

      <article className="agents-mini-panel">
        <div className="agents-panel-head">
          <div>
            <span>Cost of failure</span>
            <strong>Open issue blast radius by agent</strong>
          </div>
          <Gauge aria-hidden="true" />
        </div>
        <CostOfFailureChart rows={rows} />
      </article>

      <article className="agents-mini-panel">
        <div className="agents-panel-head">
          <div>
            <span>Trace timeline</span>
            <strong>Evidence from the selected issue</strong>
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
    ]);
  }, [callsQuery, captureHealthQuery, issuesQuery, leaderboardQuery, summaryQuery]);

  const rows = useMemo(
    () =>
      buildAgentRows(
        leaderboardQuery.data ?? [],
        callsQuery.data?.items ?? [],
        issuesQuery.data?.items ?? [],
      ),
    [callsQuery.data?.items, issuesQuery.data?.items, leaderboardQuery.data],
  );

  const loading =
    leaderboardQuery.isLoading ||
    callsQuery.isLoading ||
    issuesQuery.isLoading ||
    captureHealthQuery.isLoading;
  const hasRows = rows.length > 0;
  const callsToday = summaryQuery.data?.calls_today ?? 0;
  const openIssues = issuesQuery.data?.items.length ?? 0;
  const atRiskAgents = rows.filter((row) => row.healthScore != null && row.healthScore < 55).length;
  const replayGaps = rows.filter((row) => {
    const status = row.latestIssue?.replay_coverage_status;
    return status === "not_covered" || status === "fix_pending_replay" || status === "covered_not_run";
  }).length;
  const focusRow =
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
        replayGaps={replayGaps}
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
                <span>Signal clusters</span>
                <strong>Failure patterns grouped from live production issues</strong>
              </div>
              <Link href="/issues" className="agents-text-link">
                Open issues
                <ArrowRight aria-hidden="true" />
              </Link>
            </div>
            <SignalClustersTable issues={issuesQuery.data?.items ?? []} />
          </article>

          <article className="agents-chart-panel">
            <div className="agents-panel-head">
              <div>
                <span>Live agent matrix</span>
                <strong>Health, issue, replay, latency, and cost in one table</strong>
              </div>
              <span className="agents-table-count">{formatCount(rows.length)} agents</span>
            </div>
            <div className="agents-table-wrap">
              <table className="agents-table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Health</th>
                    <th>Success</th>
                    <th>Cost</th>
                    <th>Latency</th>
                    <th>Priority issue</th>
                    <th>Replay</th>
                    <th>Last event</th>
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
              <span>Capture quality</span>
              <strong>Warnings that affect attribution accuracy</strong>
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
            <strong>No capture validation warnings.</strong>
            <span>Agent attribution, source, and payload quality are clean for this window.</span>
          </div>
        </section>
      )}

      <section className="agents-footnote-panel">
        <Clock3 aria-hidden="true" />
        <span>
          Recommendations come from the Issue product object when available, then fall back to health score, success-rate, latency, and replay coverage.
        </span>
      </section>
    </div>
  );
}
