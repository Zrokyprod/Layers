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
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { CaptureConnectPanel } from "@/components/capture-connect-panel";
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

type AgentsFilter = "all" | "needs_review" | "held" | "missing_outcome" | "evidence_ready";
type AgentHeroTone = "setup" | "danger" | "warning" | "success" | "neutral";

function coerceDate(value: unknown): Date | null {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === "string" || typeof value === "number") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}

function analyticsWindowDays(dateRange: { from?: unknown; to?: unknown } | null | undefined): number {
  const from = coerceDate(dateRange?.from);
  const to = coerceDate(dateRange?.to) ?? new Date();
  if (!from || from.getTime() >= to.getTime()) return 7;
  return Math.max(1, Math.min(90, Math.ceil((to.getTime() - from.getTime()) / 86_400_000)));
}

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

function rowHasHeldDecision(row: AgentLaunchpadRow): boolean {
  const decision = row.latestDecision;
  return Boolean(
    decision &&
      (
        decision.decision === "block" ||
        decision.decision === "requires_approval" ||
        decision.status === "blocked" ||
        decision.status === "pending_approval" ||
        decision.status === "rejected"
      ),
  );
}

function rowHasMissingOutcome(row: AgentLaunchpadRow): boolean {
  return Boolean(row.latestDecision && (!row.latestOutcome || row.latestOutcome.verdict === "not_verified"));
}

function rowHasEvidenceReady(row: AgentLaunchpadRow): boolean {
  return Boolean(row.latestDecision && row.latestOutcome?.verdict === "matched");
}

function rowNeedsReview(row: AgentLaunchpadRow): boolean {
  return rowHasHeldDecision(row) ||
    row.latestOutcome?.verdict === "mismatched" ||
    rowHasMissingOutcome(row) ||
    Boolean(row.latestIssue) ||
    (row.healthScore != null && row.healthScore < 55);
}

function agentPriority(row: AgentLaunchpadRow): number {
  if (row.latestOutcome?.verdict === "mismatched") return 700;
  if (rowHasHeldDecision(row)) return 600;
  if (rowHasMissingOutcome(row)) return 500;
  if (row.latestIssue) return 300 + severityRank(row.latestIssue.severity);
  if (row.healthScore != null && row.healthScore < 55) return 200;
  if (rowHasEvidenceReady(row)) return 100;
  return 0;
}

function sortAgentRows(rows: AgentLaunchpadRow[]): AgentLaunchpadRow[] {
  return [...rows].sort((a, b) => {
    const priorityDelta = agentPriority(b) - agentPriority(a);
    if (priorityDelta !== 0) return priorityDelta;
    return timestamp(b.lastEventAt) - timestamp(a.lastEventAt);
  });
}

function mandateRiskLabel(row: AgentLaunchpadRow): string {
  if (row.latestOutcome?.verdict === "mismatched") return "Outcome mismatch";
  if (rowHasHeldDecision(row)) return "Held / blocked";
  if (rowHasMissingOutcome(row)) return "Proof missing";
  if (row.latestIssue) return row.latestIssue.severity;
  if (row.healthScore != null && row.healthScore < 55) return "At risk";
  if (rowHasEvidenceReady(row)) return "Protected";
  return "Watching";
}

function mandateRiskTone(row: AgentLaunchpadRow): string {
  if (row.latestOutcome?.verdict === "mismatched") return "badge-red";
  if (rowHasHeldDecision(row)) return "badge-yellow";
  if (rowHasMissingOutcome(row)) return "badge-yellow";
  if (row.latestIssue) return severityTone(row.latestIssue.severity);
  if (row.healthScore != null && row.healthScore < 55) return "badge-red";
  if (rowHasEvidenceReady(row)) return "badge-green";
  return "badge-gray";
}

function evidenceReadyLabel(row: AgentLaunchpadRow): string {
  if (rowHasEvidenceReady(row)) return "Export ready";
  if (row.latestDecision && !row.latestOutcome) return "Outcome missing";
  if (row.latestOutcome?.verdict === "mismatched") return "Failed proof";
  if (row.latestOutcome?.verdict === "not_verified") return "Not verified";
  if (row.latestDecision) return "Needs proof";
  return "No decision";
}

function evidenceReadyTone(row: AgentLaunchpadRow): string {
  if (rowHasEvidenceReady(row)) return "badge-green";
  if (row.latestOutcome?.verdict === "mismatched") return "badge-red";
  if (row.latestDecision) return "badge-yellow";
  return "badge-gray";
}

function impactLabel(row: AgentLaunchpadRow): string {
  const issueImpact = row.latestIssue?.cost_impact_usd || row.latestIssue?.blast_radius_usd;
  if (issueImpact) return formatUsd(issueImpact);
  if (row.callCount > 0) return `${formatCount(row.callCount)} actions`;
  return "No action data";
}

function nextStepLabel(row: AgentLaunchpadRow): string {
  if (row.latestOutcome?.verdict === "mismatched") return "Inspect outcome";
  if (rowHasHeldDecision(row)) return "Review held action";
  if (rowHasMissingOutcome(row)) return "Verify outcome";
  if (row.latestIssue) return "Open proof gap";
  if (rowHasEvidenceReady(row)) return "Open evidence";
  return "Inspect capture";
}

function nextStepHref(row: AgentLaunchpadRow): string {
  if (row.latestOutcome?.verdict === "mismatched" || rowHasMissingOutcome(row)) return "/outcomes";
  if (rowHasHeldDecision(row)) return "/approvals";
  if (row.latestIssue) return `/issues/${encodeURIComponent(row.latestIssue.id)}`;
  if (row.latestDecision) return evidencePackHref(row.latestDecision.id);
  return `/calls?agent_name=${encodeURIComponent(row.agentName)}`;
}

function filterAgentRows(rows: AgentLaunchpadRow[], filter: AgentsFilter): AgentLaunchpadRow[] {
  if (filter === "all") return rows;
  if (filter === "needs_review") return rows.filter(rowNeedsReview);
  if (filter === "held") return rows.filter(rowHasHeldDecision);
  if (filter === "missing_outcome") return rows.filter(rowHasMissingOutcome);
  return rows.filter(rowHasEvidenceReady);
}

function agentFilterLabel(filter: AgentsFilter): string {
  if (filter === "needs_review") return "Agents needing review";
  if (filter === "held") return "Held/runtime decisions";
  if (filter === "missing_outcome") return "Missing outcome proof";
  if (filter === "evidence_ready") return "Evidence-ready agents";
  return "Protected agents";
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
    { label: "System-of-record connector selected", done: (captureHealth?.outcome_events_24h ?? 0) > 0 },
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
          Once capture starts, Zroky ranks agents by mandate health, held actions, outcome proof, Evidence Pack readiness, and system-of-record coverage.
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
          <h1>Protected agents</h1>
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

function AgentRow({
  row,
  selected,
  onSelect,
}: {
  row: AgentLaunchpadRow;
  selected: boolean;
  onSelect: (agentName: string) => void;
}) {
  return (
    <tr
      className={`agents-table-row${selected ? " is-selected" : ""}`}
      aria-selected={selected}
      tabIndex={0}
      onClick={() => onSelect(row.agentName)}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        onSelect(row.agentName);
      }}
    >
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
          <span className={`alert-cat-badge ${mandateRiskTone(row)}`}>
            {mandateRiskLabel(row)}
          </span>
          <span className="agents-cell-note">
            {row.healthScore == null ? "No baseline yet" : `Health ${Math.round(row.healthScore)}`}
          </span>
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
        <div className="agents-proof-cell">
          <span className={`alert-cat-badge ${evidenceReadyTone(row)}`}>
            {evidenceReadyLabel(row)}
          </span>
          {row.latestDecision ? (
            <Link href={evidencePackHref(row.latestDecision.id)} className="agents-text-link">
              Evidence Pack
            </Link>
          ) : (
            <span className="agents-cell-note">No decision id</span>
          )}
        </div>
      </td>
      <td>
        <strong>{impactLabel(row)}</strong>
        <span className="agents-cell-note">
          {row.latestIssue?.title ?? `${row.successRate == null ? "-" : formatPercent(row.successRate)} success`}
        </span>
      </td>
      <td>
        <Link href={nextStepHref(row)} className="btn btn-soft btn-sm agents-row-action">
          {nextStepLabel(row)}
        </Link>
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
  rows,
  onRefresh,
}: {
  captureHealth: CaptureHealthResponse | null;
  callsToday: number;
  rows: AgentLaunchpadRow[];
  onRefresh: () => void;
}) {
  const connected = captureHealth?.status === "connected";
  const needsReview = rows.filter(rowNeedsReview).length;
  const held = rows.filter(rowHasHeldDecision).length;
  const missingOutcome = rows.filter(rowHasMissingOutcome).length;
  const mismatched = rows.filter((row) => row.latestOutcome?.verdict === "mismatched").length;
  const evidenceReady = rows.filter(rowHasEvidenceReady).length;
  const firstEvidenceDecision = rows.find(rowHasEvidenceReady)?.latestDecision?.id ?? rows.find((row) => row.latestDecision)?.latestDecision?.id;
  const verdict: {
    tone: AgentHeroTone;
    eyebrow: string;
    title: string;
    body: string;
    ctaLabel: string;
    ctaHref: string;
  } = rows.length === 0
    ? {
        tone: "setup",
        eyebrow: "Agent safety status",
        title: "Setup required",
        body: "Connect a captured agent action and a system-of-record connector before this fleet can produce outcome proof.",
        ctaLabel: "Connect agent",
        ctaHref: "/settings",
      }
    : mismatched > 0
      ? {
          tone: "danger",
          eyebrow: "Current safety verdict",
          title: "Outcome mismatch",
          body: `${formatCount(mismatched)} protected agent${mismatched === 1 ? "" : "s"} reported success, but the system-of-record proof does not match.`,
          ctaLabel: "Inspect outcome",
          ctaHref: "/outcomes",
        }
      : held > 0
        ? {
            tone: "warning",
            eyebrow: "Current safety verdict",
            title: "Held actions pending",
            body: `${formatCount(held)} runtime decision${held === 1 ? "" : "s"} stopped or paused action before commit.`,
            ctaLabel: "Review held action",
            ctaHref: "/approvals",
          }
        : missingOutcome > 0
          ? {
              tone: "warning",
              eyebrow: "Current safety verdict",
              title: "Proof missing",
              body: `${formatCount(missingOutcome)} decision${missingOutcome === 1 ? "" : "s"} still need outcome reconciliation before export proof is honest.`,
              ctaLabel: "Verify outcome",
              ctaHref: "/outcomes",
            }
          : needsReview > 0
            ? {
                tone: "warning",
                eyebrow: "Current safety verdict",
                title: "Protection gaps",
                body: `${formatCount(needsReview)} agent${needsReview === 1 ? "" : "s"} need mandate, replay, or proof review before unattended operation.`,
                ctaLabel: "Review agents",
                ctaHref: "/agents",
              }
            : {
                tone: "success",
                eyebrow: "Current safety verdict",
                title: "Protected",
                body: "Runtime decisions and outcome proof are clean for the loaded agent fleet.",
                ctaLabel: "Open evidence",
                ctaHref: firstEvidenceDecision ? evidencePackHref(firstEvidenceDecision) : "/evidence",
              };

  return (
    <section className="agents-hero-panel" data-tone={verdict.tone}>
      <div className="agents-hero-copy">
        <div className="agents-eyebrow">
          <Activity aria-hidden="true" />
          {verdict.eyebrow}
        </div>
        <h1>{verdict.title}</h1>
        <p>{verdict.body}</p>
      </div>
      <div className="agents-hero-actions">
        <Link href={verdict.ctaHref} className="btn btn-primary">
          {verdict.ctaLabel}
          <ArrowRight aria-hidden="true" />
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
          <strong>{formatCount(needsReview)}</strong>
          <small>needs review</small>
        </div>
        <div>
          <strong>{formatCount(evidenceReady)}</strong>
          <small>evidence ready</small>
        </div>
      </div>
    </section>
  );
}

function AgentsKpis({
  rows,
  activeFilter,
  onFilterChange,
}: {
  rows: AgentLaunchpadRow[];
  activeFilter: AgentsFilter;
  onFilterChange: (filter: AgentsFilter) => void;
}) {
  const needsReview = rows.filter(rowNeedsReview).length;
  const held = rows.filter(rowHasHeldDecision).length;
  const missingOutcome = rows.filter(rowHasMissingOutcome).length;
  const evidenceReady = rows.filter(rowHasEvidenceReady).length;
  const failingGates = rows.filter((row) => row.latestOutcome?.verdict === "mismatched").length;
  const cards = [
    {
      filter: "all" as const,
      icon: Bot,
      label: "Protected agents",
      value: formatCount(rows.length),
      helper: "Captured agents in this workspace",
      tone: "neutral",
    },
    {
      filter: "needs_review" as const,
      icon: AlertTriangle,
      label: "Needs review",
      value: formatCount(needsReview),
      helper: `${formatCount(failingGates)} failing outcome gate${failingGates === 1 ? "" : "s"}`,
      tone: needsReview > 0 ? "danger" : "success",
    },
    {
      filter: "held" as const,
      icon: RotateCcw,
      label: "Held decisions",
      value: formatCount(held),
      helper: "Runtime block or approval queue",
      tone: held > 0 ? "warning" : "neutral",
    },
    {
      filter: "missing_outcome" as const,
      icon: Clock3,
      label: "Missing outcome proof",
      value: formatCount(missingOutcome),
      helper: "Decision exists, proof not verified",
      tone: missingOutcome > 0 ? "warning" : "success",
    },
    {
      filter: "evidence_ready" as const,
      icon: ShieldCheck,
      label: "Evidence ready",
      value: formatCount(evidenceReady),
      helper: "Matched outcome with export path",
      tone: "success",
    },
  ];

  return (
    <section className="agents-kpi-grid" aria-label="Agent safety filters">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <button
            key={card.label}
            type="button"
            className={`agents-kpi-card${activeFilter === card.filter ? " is-active" : ""}`}
            data-tone={card.tone}
            aria-pressed={activeFilter === card.filter}
            onClick={() => onFilterChange(card.filter)}
          >
            <span className="agents-kpi-icon" aria-hidden="true">
              <Icon />
            </span>
            <div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <small>{card.helper}</small>
            </div>
          </button>
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
          <span>Selected agent proof</span>
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

function AgentsAccountabilityLoop() {
  const stages = [
    { label: "Capture", detail: "Agent action enters Zroky", href: "/calls" },
    { label: "Detect", detail: "Mandate and risk signal", href: "/issues" },
    { label: "Verify", detail: "System-of-record proof", href: "/outcomes" },
    { label: "Promote", detail: "Golden behavior contract", href: "/contracts" },
    { label: "Gate", detail: "Policy stops unsafe action", href: "/policies" },
    { label: "Export", detail: "Evidence Pack for audit", href: "/evidence" },
  ];

  return (
    <article className="agents-loop-panel" aria-label="Accountability loop">
      <div className="agents-panel-head">
        <div>
          <span>Accountability loop</span>
          <strong>{"Capture -> Detect -> Verify -> Promote -> Gate -> Export"}</strong>
        </div>
      </div>
      <div className="agents-loop-chain">
        {stages.map((stage, index) => (
          <Link key={stage.label} href={stage.href} className="agents-loop-step">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{stage.label}</strong>
            <small>{stage.detail}</small>
          </Link>
        ))}
      </div>
    </article>
  );
}

function captureHealthTone(captureHealth: CaptureHealthResponse | null): string {
  if (!captureHealth || captureHealth.status === "no_data") return "warning";
  if (captureHealth.status === "stale") return "danger";
  return "success";
}

function AgentsSystemHealth({
  captureHealth,
  focusRow,
}: {
  captureHealth: CaptureHealthResponse | null;
  focusRow: AgentLaunchpadRow | null;
}) {
  const warningCount = captureHealth?.validation_warnings?.length ?? 0;
  const backlogCount = captureHealth?.gateway_spool_backlog ?? 0;
  const lossCount = captureHealth?.gateway_loss_count ?? 0;
  const outcomeEvents = captureHealth?.outcome_events_24h ?? 0;
  const latestOutcome = focusRow?.latestOutcome ?? null;
  const connectorLabel = latestOutcome
    ? outcomeDetail(latestOutcome)
    : outcomeEvents > 0
      ? `${formatCount(outcomeEvents)} outcome event${outcomeEvents === 1 ? "" : "s"} in window`
      : "Connector proof not loaded";
  const streamLabel = captureHealth?.status === "connected"
    ? "Connected"
    : captureHealth?.status === "stale"
      ? "Stale"
      : "Missing";

  return (
    <article className="agents-system-health-panel" aria-label="System-of-record health">
      <div className="agents-panel-head">
        <div>
          <span>System-of-record health</span>
          <strong>Capture, connector proof, and export readiness</strong>
        </div>
        <Link href="/integrations" className="agents-text-link">
          Open connectors
          <ArrowRight aria-hidden="true" />
        </Link>
      </div>
      <div className="agents-system-health-grid">
        <Link href="/calls" className="agents-system-health-card" data-tone={captureHealthTone(captureHealth)}>
          <span>Capture stream</span>
          <strong>{streamLabel}</strong>
          <small>
            {captureHealth?.last_seen_at
              ? `Last event ${formatDateTime(captureHealth.last_seen_at)}`
              : "No captured action loaded"}
          </small>
        </Link>
        <Link
          href="/outcomes"
          className="agents-system-health-card"
          data-tone={latestOutcome?.verdict === "mismatched" ? "danger" : latestOutcome ? "success" : "warning"}
        >
          <span>Outcome events</span>
          <strong>{formatCount(outcomeEvents)}</strong>
          <small>{connectorLabel}</small>
        </Link>
        <Link href="/integrations" className="agents-system-health-card" data-tone={backlogCount + lossCount > 0 ? "danger" : "neutral"}>
          <span>Gateway backlog</span>
          <strong>{formatCount(backlogCount + lossCount)}</strong>
          <small>{formatCount(backlogCount)} queued, {formatCount(lossCount)} lost</small>
        </Link>
        {warningCount > 0 ? (
          <a href="#capture-warnings" className="agents-system-health-card" data-tone="warning">
            <span>Capture warnings</span>
            <strong>{formatCount(warningCount)}</strong>
            <small>Proof quality needs review</small>
          </a>
        ) : (
          <div className="agents-system-health-card" data-tone="success">
            <span>Capture warnings</span>
            <strong>0</strong>
            <small>Attribution fields are clean</small>
          </div>
        )}
      </div>
    </article>
  );
}

export default function AgentsPage() {
  const [setupOpened, setSetupOpened] = useState(false);
  const [activeFilter, setActiveFilter] = useState<AgentsFilter>("needs_review");
  const [selectedAgentName, setSelectedAgentName] = useState<string | null>(null);
  const setSdkConnected = useDashboardStore((state) => state.setSdkConnected);
  const dateRange = useDashboardStore((state) => state.dateRange);
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const summaryWindowDays = useMemo(() => analyticsWindowDays(dateRange), [dateRange]);
  const refreshInterval = realTimeEnabled ? 30_000 : false;
  const leaderboardQuery = useReliabilityLeaderboard(100);
  const callsQuery = useQuery({
    queryKey: ["agents", "recent-calls"],
    queryFn: ({ signal }) =>
      listCalls({ limit: 200, sort_by: "created_at", sort_order: "desc" }, signal),
    refetchInterval: refreshInterval,
  });
  const issuesQuery = useQuery({
    queryKey: ["agents", "open-issues"],
    queryFn: ({ signal }) => listIssues({ status: "open", limit: 100 }, signal),
    refetchInterval: refreshInterval,
  });
  const captureHealthQuery = useQuery({
    queryKey: ["agents", "capture-health"],
    queryFn: ({ signal }) => getCaptureHealth(signal),
    refetchInterval: refreshInterval,
  });
  const summaryQuery = useQuery({
    queryKey: ["agents", "analytics-summary", summaryWindowDays],
    queryFn: ({ signal }) => getAnalyticsSummary(summaryWindowDays, signal),
    refetchInterval: refreshInterval,
  });
  const runtimeDecisionsQuery = useQuery({
    queryKey: ["agents", "runtime-policy", "decisions", "all"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
    refetchInterval: refreshInterval,
  });
  const outcomeChecksQuery = useQuery({
    queryKey: ["agents", "outcomes", "reconciliation"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ limit: 50 }, signal),
    refetchInterval: refreshInterval,
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
  const sortedRows = useMemo(() => sortAgentRows(rows), [rows]);
  const filteredRows = useMemo(() => filterAgentRows(sortedRows, activeFilter), [activeFilter, sortedRows]);
  const reviewRowsCount = useMemo(() => sortedRows.filter(rowNeedsReview).length, [sortedRows]);

  useEffect(() => {
    if (!selectedAgentName) return;
    if (!rows.some((row) => row.agentName === selectedAgentName)) {
      setSelectedAgentName(null);
    }
  }, [rows, selectedAgentName]);

  useEffect(() => {
    if (activeFilter === "needs_review" && sortedRows.length > 0 && reviewRowsCount === 0) {
      setActiveFilter("all");
    }
  }, [activeFilter, reviewRowsCount, sortedRows.length]);

  const primaryQueries = [leaderboardQuery, callsQuery, issuesQuery, runtimeDecisionsQuery, outcomeChecksQuery];
  const loading = primaryQueries.every((query) => query.isLoading && query.data === undefined);
  const hasRows = rows.length > 0;
  const callsToday = summaryQuery.data?.calls_today ?? 0;
  const priorityFocusRow = sortedRows[0] ?? null;
  const focusRow =
    sortedRows.find((row) => row.agentName === selectedAgentName) ??
    filteredRows[0] ??
    priorityFocusRow ??
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
        rows={rows}
        onRefresh={refreshAll}
      />

      <AgentsKpis
        rows={rows}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
      />

      <section className="agents-layout-grid">
        <div className="agents-main-column">
          <article className="agents-chart-panel">
            <div className="agents-panel-head">
              <div>
                <span>{agentFilterLabel(activeFilter)}</span>
                <strong>Needs your decision</strong>
              </div>
              <span className="agents-table-count">{formatCount(filteredRows.length)} of {formatCount(rows.length)} agents</span>
            </div>
            <div className="agents-table-wrap">
              <table className="agents-table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Mandate / risk</th>
                    <th>Runtime decision</th>
                    <th>Outcome proof</th>
                    <th>Evidence readiness</th>
                    <th>Impact</th>
                    <th>Next step</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length > 0 ? (
                    filteredRows.map((row) => (
                      <AgentRow
                        key={row.agentName}
                        row={row}
                        selected={focusRow?.agentName === row.agentName}
                        onSelect={setSelectedAgentName}
                      />
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>
                        <div className="agents-empty-filter">
                          <strong>No agents match this filter.</strong>
                          <span>
                            {activeFilter === "needs_review"
                              ? "No loaded agent currently needs a runtime decision, outcome fix, or proof review."
                              : "Switch filters to inspect the rest of the loaded protected-agent fleet."}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <AgentsAccountabilityLoop />

          <AgentsSystemHealth
            captureHealth={captureHealthQuery.data ?? null}
            focusRow={focusRow}
          />
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
    </div>
  );
}
