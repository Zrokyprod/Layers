"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Wrench,
} from "lucide-react";

import { CaptureConnectPanel } from "@/components/capture-connect-panel";
import { getAnalyticsSummary, getCaptureHealth, listCalls, listIssues } from "@/lib/api";
import type { AgentScoreView } from "@/lib/api";
import { formatCount, formatDateTime, formatPercent, formatUsd } from "@/lib/format";
import { replayLabel, severityRank } from "@/lib/issue-format";
import { useReliabilityLeaderboard, useTriggerReliabilityCompute } from "@/lib/hooks";
import { useDashboardStore } from "@/lib/store";
import type { CallListItem, CaptureHealthResponse, IssueItem } from "@/lib/types";

const ONBOARDING_WIZARD_OPENED_KEY = "zroky.onboardingWizardOpened";

type AgentStats = {
  callCount: number;
  successfulCalls: number;
  totalCostUsd: number;
  successfulCostUsd: number;
  lastEventAt: string | null;
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

function buildAgentRows(
  scores: AgentScoreView[],
  calls: CallListItem[],
  issues: IssueItem[],
): AgentLaunchpadRow[] {
  const statsByAgent = new Map<string, AgentStats>();
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
    <div className="grid gap-4">
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Agents Launchpad setup</h3>
            <p>Connect one real agent call first. After data lands here, this page becomes your agent health table.</p>
          </div>
        </header>
      </section>
      <CaptureConnectPanel
        captureHealth={captureHealth}
        checklistItems={checklistItems}
        completedCount={completed}
        totalCount={checklistItems.length}
        progressPct={Math.round((completed / checklistItems.length) * 100)}
        onRefresh={onRefresh}
        onMarkOpened={onMarkOpened}
      />
    </div>
  );
}

function AgentHealthPill({ score }: { score: number | null }) {
  const tone = healthTone(score);
  return (
    <div style={{ display: "grid", gap: 4 }}>
      <span className={`alert-cat-badge ${tone.className}`} style={{ width: "fit-content" }}>
        {tone.label}
      </span>
      <strong>{score == null ? "-" : Math.round(score)}</strong>
    </div>
  );
}

function AgentRow({ row }: { row: AgentLaunchpadRow }) {
  return (
    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
      <td style={{ padding: "0.9rem", verticalAlign: "top" }}>
        <div style={{ display: "flex", gap: "0.65rem", alignItems: "flex-start" }}>
          <Bot aria-hidden="true" style={{ width: 18, height: 18, color: "var(--accent)" }} />
          <div>
            <strong>{row.agentName}</strong>
            <div className="notif-meta">{formatCount(row.callCount)} recent call{row.callCount === 1 ? "" : "s"}</div>
          </div>
        </div>
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top" }}>
        <AgentHealthPill score={row.healthScore} />
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top", minWidth: 220 }}>
        {row.latestIssue ? (
          <Link href={`/issues/${encodeURIComponent(row.latestIssue.id)}`} className="notif-action-link">
            {row.latestIssue.title}
          </Link>
        ) : (
          <span className="notif-meta">No open issue</span>
        )}
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top" }}>
        <strong>{row.successRate == null ? "-" : formatPercent(row.successRate)}</strong>
        <div className="notif-meta">
          {row.successfulCalls > 0 ? `${formatCount(row.successfulCalls)} successful` : "No success sample"}
        </div>
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top" }}>
        <strong>{row.costPerSuccessfulTask == null ? "-" : formatUsd(row.costPerSuccessfulTask)}</strong>
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top" }}>
        <span>{row.replayCoverage}</span>
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top" }}>
        <Clock3 aria-hidden="true" style={{ width: 14, height: 14, marginRight: 4, verticalAlign: -2 }} />
        {formatDateTime(row.lastEventAt)}
      </td>
      <td style={{ padding: "0.9rem", verticalAlign: "top", minWidth: 220 }}>
        <span>{row.recommendedAction}</span>
      </td>
    </tr>
  );
}

export default function AgentsPage() {
  const [setupOpened, setSetupOpened] = useState(false);
  const setSdkConnected = useDashboardStore((state) => state.setSdkConnected);
  const leaderboardQuery = useReliabilityLeaderboard(100);
  const recompute = useTriggerReliabilityCompute();
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

  if (loading && !hasRows) {
    return <div className="loading" />;
  }

  if (!hasRows) {
    return (
      <AgentsSetupState
        captureHealth={captureHealthQuery.data ?? null}
        callsToday={callsToday}
        setupOpened={setupOpened}
        onRefresh={refreshAll}
        onMarkOpened={markSetupOpened}
      />
    );
  }

  return (
    <div className="grid gap-4">
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Agents Launchpad</h3>
            <p>One row per agent, ranked by open issue priority, low health, and most recent activity.</p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button type="button" className="btn btn-soft" onClick={refreshAll}>
              <RefreshCw aria-hidden="true" />
              Refresh
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => recompute.mutate()}
              disabled={recompute.isPending}
            >
              {recompute.isPending ? <Loader2 aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
              Recompute health
            </button>
          </div>
        </header>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "0.75rem" }}>
        <div className="panel panel-muted">
          <div className="notif-meta">Agents</div>
          <strong style={{ fontSize: "1.4rem" }}>{formatCount(rows.length)}</strong>
        </div>
        <div className="panel panel-muted">
          <div className="notif-meta">Open issues</div>
          <strong style={{ fontSize: "1.4rem" }}>{formatCount(openIssues)}</strong>
        </div>
        <div className="panel panel-muted">
          <div className="notif-meta">At-risk agents</div>
          <strong style={{ fontSize: "1.4rem" }}>{formatCount(atRiskAgents)}</strong>
        </div>
        <div className="panel panel-muted">
          <div className="notif-meta">Capture</div>
          <strong style={{ fontSize: "1.1rem" }}>{captureHealthQuery.data?.status ?? "unknown"}</strong>
        </div>
      </section>

      <section className="panel" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.86rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border)", color: "var(--color-muted)", textAlign: "left" }}>
              <th style={{ padding: "0.75rem 0.9rem" }}>Agent</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Health</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Latest issue</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Success rate</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Cost / success</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Replay coverage</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Last event</th>
              <th style={{ padding: "0.75rem 0.9rem" }}>Recommended action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <AgentRow key={row.agentName} row={row} />
            ))}
          </tbody>
        </table>
      </section>

      {captureHealthQuery.data?.validation_warnings?.length ? (
        <section className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Capture validation warnings</h3>
              <p>Fix these to improve agent-level attribution and launchpad accuracy.</p>
            </div>
          </header>
          <div className="list">
            {captureHealthQuery.data.validation_warnings.map((warning) => (
              <div key={warning.code} className="list-row">
                <div className="list-main">
                  <strong>
                    <AlertTriangle aria-hidden="true" style={{ width: 15, height: 15, marginRight: 6, verticalAlign: -2 }} />
                    {warning.label}
                  </strong>
                  <span>{warning.detail}</span>
                </div>
                <span className="mono">{warning.code}</span>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="panel panel-muted">
          <div style={{ display: "flex", gap: "0.65rem", alignItems: "center" }}>
            <CheckCircle2 aria-hidden="true" style={{ color: "var(--color-green)" }} />
            <span>No capture validation warnings.</span>
          </div>
        </section>
      )}

      <section className="panel panel-muted">
        <header className="panel-header">
          <div>
            <h3>Top action source</h3>
            <p>Recommended actions come from the Issue product object when available, then fall back to health and success-rate signals.</p>
          </div>
          <Link href="/issues" className="btn btn-soft">
            <Wrench aria-hidden="true" />
            Open Issues
          </Link>
        </header>
      </section>
    </div>
  );
}
