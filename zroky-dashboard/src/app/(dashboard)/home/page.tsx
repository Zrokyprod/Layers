"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BellDot,
  CheckCircle2,
  ChevronRight,
  Circle,
  FileCheck2,
  KeyRound,
  LockKeyhole,
  Plug,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Workflow,
  XCircle,
} from "lucide-react";

import {
  fetchOutcomeGraphCoverage,
  getHomeSummary,
  listFinalIncidents,
  type ActionExecutionAttemptResponse,
  type ActionIntentResponse,
  type ActionRunnerResponse,
  type AgentProfileListResponse,
  type AgentProfileResponse,
  type HomeSummaryResponse,
  type FinalIncidentResponse,
  type OutcomeGraphCoverageSummary,
  type OutcomeReconciliationSummaryResponse,
  type OutcomeReconciliationView,
  type RuntimePolicyDecisionResponse,
  type SourceMutationSummaryResponse,
  type SourceMutationView,
  listMyProjects,
} from "@/lib/api";
import { formatCount, timeSince } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

import styles from "./home.module.css";

type HomeData = {
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  outcomeSummary: OutcomeReconciliationSummaryResponse | null;
  sourceSummary: SourceMutationSummaryResponse | null;
  mutations: SourceMutationView[];
  staleAttempts: ActionExecutionAttemptResponse[];
  agentProfiles: AgentProfileResponse[];
  agentProfileMeta: Pick<AgentProfileListResponse, "active_count" | "max_active_agents" | "limit_reached"> | null;
  actionRunners: ActionRunnerResponse[];
  apiKeys: ApiKeyResponse[];
  billingUsage: BillingUsageResponse | null;
  homeSummary: HomeSummaryResponse | null;
  outcomeGraphCoverage: OutcomeGraphCoverageSummary | null;
  incidents: FinalIncidentResponse[];
};

type HomeSource =
  | "homeSummary"
  | "incidents"
  | "intents"
  | "approvals"
  | "outcomes"
  | "outcomeSummary"
  | "sourceSummary"
  | "mutations"
  | "staleAttempts"
  | "agentProfiles"
  | "actionRunners"
  | "apiKeys"
  | "billingUsage";

type HomeAvailability = Record<HomeSource, boolean>;
type HomeRole = string | null;
type HomeLoadIssue = "auth" | "source" | null;
type PostureStatus = "INACTIVE" | "ACTIVE" | "DEGRADED" | "CRITICAL";
type BadgeStatus = "Ready" | "Blocked" | "Stale" | "Missing" | "Pending" | "Critical" | "Neutral";
type Priority = "P1" | "P2" | "P3";

type ProofStats = {
  totalActions: number;
  proven: number;
  mismatches: number;
  needsAttention: number;
  pendingApprovals: number;
  openIncidents: number;
  blockedAttempts: number;
  coveragePercent: number;
};

type ReadinessRow = {
  component: string;
  status: BadgeStatus;
  details: string;
  action: string;
  href: string;
  ownerOnly?: boolean;
};

type AttentionRow = {
  priority: Priority;
  item: string;
  source: string;
  workflow: string;
  age: string;
  action: string;
  href: string;
};

type ProofEvent = {
  tone: BadgeStatus;
  id: string;
  label: string;
  outcome: string;
  signature: string;
  time: string;
  href: string;
};

const DEFAULT_HOME_WINDOW_DAYS = 7;
const MS_PER_DAY = 86_400_000;
const DEMO_HOME_STORAGE_KEY = "zroky:demo-home";

const EMPTY_DATA: HomeData = {
  intents: [],
  approvals: [],
  outcomes: [],
  outcomeSummary: null,
  sourceSummary: null,
  mutations: [],
  staleAttempts: [],
  agentProfiles: [],
  agentProfileMeta: null,
  actionRunners: [],
  apiKeys: [],
  billingUsage: null,
  homeSummary: null,
  outcomeGraphCoverage: null,
  incidents: [],
};

const NO_SOURCES_AVAILABLE: HomeAvailability = {
  homeSummary: false,
  incidents: false,
  intents: false,
  approvals: false,
  outcomes: false,
  outcomeSummary: false,
  sourceSummary: false,
  mutations: false,
  staleAttempts: false,
  agentProfiles: false,
  actionRunners: false,
  apiKeys: false,
  billingUsage: false,
};

const ALL_SOURCES_AVAILABLE: HomeAvailability = {
  homeSummary: true,
  incidents: true,
  intents: true,
  approvals: true,
  outcomes: true,
  outcomeSummary: true,
  sourceSummary: true,
  mutations: true,
  staleAttempts: true,
  agentProfiles: true,
  actionRunners: true,
  apiKeys: true,
  billingUsage: true,
};

function demoHomeSummary(days: number): HomeSummaryResponse {
  const generatedAt = new Date().toISOString();
  const windowStart = new Date(Date.now() - days * MS_PER_DAY).toISOString();
  return {
    project_id: "demo_project",
    window_days: days,
    window_start: windowStart,
    generated_at: generatedAt,
    metrics: {
      controlled_actions: 300,
      pending_approvals: 6,
      verified_outcomes: 142,
      outcome_checks: 145,
      receipts_generated: 1248,
      bypass_mutations: 12,
      unreceipted_mutations: 0,
      sequence_risks: 2,
    },
    sources: {
      home_summary: true,
      intents: true,
      approvals: true,
      outcomes: true,
      outcome_summary: true,
      source_summary: true,
      mutations: true,
      stale_attempts: true,
      agent_profiles: true,
      action_runners: true,
      api_keys: true,
      billing_usage: true,
    },
    data: {
      intents: [],
      approvals: [],
      outcomes: [],
      outcome_summary: {
        window_days: days,
        total: 145,
        matched: 142,
        mismatched: 3,
        not_verified: 155,
        verified: 142,
        pending: 6,
        unverifiable: 155,
        cancelled: 0,
      },
      source_summary: {
        total: 12,
        matched_receipt: 142,
        authorized_external: 0,
        legacy_path: 0,
        unmanaged_agent_action: 0,
        policy_bypass: 12,
        unknown_actor: 0,
        unreceipted: 0,
        connected_feeds: 8,
        successful_pollers: 7,
      },
      mutations: [],
      stale_attempts: [],
      agent_profiles: [],
      agent_profile_meta: { active_count: 24, max_active_agents: 100, limit_reached: false },
      action_runners: [],
      api_keys: [],
      billing_usage: null,
      control_health: {
        active_agents: 24,
        policy_enforced_agents: 24,
        configured_action_packs: 3,
        online_runners: 2,
        active_sor_connectors: 8,
        tested_sor_connectors: 7,
        mcp_gateway_status: "active",
        mcp_gateway_test_status: "succeeded",
        runtime_enabled: true,
        kill_switch_enabled: false,
      },
    },
  };
}

function localDemoHomeEnabled(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  if (host !== "localhost" && host !== "127.0.0.1" && host !== "::1") return false;
  const demoParam = new URLSearchParams(window.location.search).get("demoHome");
  if (demoParam === "1") {
    window.localStorage.setItem(DEMO_HOME_STORAGE_KEY, "1");
    return true;
  }
  if (demoParam === "0") {
    window.localStorage.removeItem(DEMO_HOME_STORAGE_KEY);
    return false;
  }
  return process.env.NEXT_PUBLIC_ZROKY_DEMO_HOME === "1" || window.localStorage.getItem(DEMO_HOME_STORAGE_KEY) === "1";
}

const DEMO_ATTENTION_ROWS: AttentionRow[] = [
  {
    priority: "P1",
    item: "Mismatch in payroll export",
    source: "Workday Payroll",
    workflow: "Payroll Export WF",
    age: "12m",
    action: "Investigate",
    href: "/operations",
  },
  {
    priority: "P1",
    item: "Approval required: policy exception",
    source: "Vendor Payments",
    workflow: "Vendor Payments WF",
    age: "18m",
    action: "Review",
    href: "/operations",
  },
  {
    priority: "P2",
    item: "Unverifiable action detected",
    source: "Salesforce",
    workflow: "Quote Approval WF",
    age: "34m",
    action: "Analyze",
    href: "/operations",
  },
  {
    priority: "P2",
    item: "Connector test-read stale",
    source: "SAP S/4HANA",
    workflow: "ERP Ingestion WF",
    age: "47m",
    action: "Fix",
    href: "/integrations",
  },
  {
    priority: "P2",
    item: "Recovery job failed",
    source: "PostgreSQL",
    workflow: "DB Recovery WF",
    age: "1h 03m",
    action: "Retry",
    href: "/operations",
  },
  {
    priority: "P3",
    item: "Evidence generation failed",
    source: "S3 Archive",
    workflow: "Evidence Pack WF",
    age: "2h 11m",
    action: "Inspect",
    href: "/evidence",
  },
];

const DEMO_PROOF_EVENTS: ProofEvent[] = [
  { tone: "Critical", id: "run_pay_042", label: "Mismatch caught in payroll export", outcome: "mismatch", signature: "sig:9f42c1a8", time: "8m", href: "/evidence" },
  { tone: "Ready", id: "run_ref_318", label: "Action verified: Stripe refund", outcome: "verified", signature: "sig:71ad03be", time: "14m", href: "/evidence" },
  { tone: "Pending", id: "apr_118", label: "Approval required: policy exception", outcome: "pending", signature: "sig:e2019c4d", time: "18m", href: "/operations" },
  { tone: "Ready", id: "run_git_907", label: "Action verified: GitHub workflow", outcome: "verified", signature: "sig:4b88a119", time: "31m", href: "/evidence" },
  { tone: "Stale", id: "src_sap_22", label: "Connector read failed: SAP S/4HANA", outcome: "stale", signature: "sig:aa17d2c0", time: "47m", href: "/operations" },
];

function canChangeHomeSetup(role: HomeRole): boolean {
  const normalized = role?.trim().toLowerCase();
  return normalized === "owner" || normalized === "admin";
}

function homeWindowDays(dateRange: { from: Date | null; to: Date | null }): number {
  if (!dateRange.from || !dateRange.to) return DEFAULT_HOME_WINDOW_DAYS;
  const fromMs = new Date(dateRange.from).getTime();
  const toMs = new Date(dateRange.to).getTime();
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) return DEFAULT_HOME_WINDOW_DAYS;
  return Math.max(1, Math.min(90, Math.ceil((toMs - fromMs) / MS_PER_DAY)));
}

function missionDataFromSummary(summary: HomeSummaryResponse): HomeData {
  const details = summary.data;
  return {
    intents: details?.intents ?? [],
    approvals: details?.approvals ?? [],
    outcomes: details?.outcomes ?? [],
    outcomeSummary: details?.outcome_summary ?? null,
    sourceSummary: details?.source_summary ?? null,
    mutations: details?.mutations ?? [],
    staleAttempts: details?.stale_attempts ?? [],
    agentProfiles: details?.agent_profiles ?? [],
    agentProfileMeta: details?.agent_profile_meta ?? null,
    actionRunners: details?.action_runners ?? [],
    apiKeys: details?.api_keys ?? [],
    billingUsage: details?.billing_usage ?? null,
    homeSummary: summary,
    outcomeGraphCoverage: null,
    incidents: [],
  };
}

function availabilityFromSummary(summary: HomeSummaryResponse): HomeAvailability {
  const sources = summary.sources;
  if (!sources) return ALL_SOURCES_AVAILABLE;
  return {
    homeSummary: sources.home_summary,
    incidents: true,
    intents: sources.intents,
    approvals: sources.approvals,
    outcomes: sources.outcomes,
    outcomeSummary: sources.outcome_summary,
    sourceSummary: sources.source_summary,
    mutations: sources.mutations,
    staleAttempts: sources.stale_attempts,
    agentProfiles: sources.agent_profiles,
    actionRunners: sources.action_runners,
    apiKeys: sources.api_keys,
    billingUsage: sources.billing_usage,
  };
}

function unavailableSourceCount(availability: HomeAvailability): number {
  return Object.values(availability).filter((value) => !value).length;
}

function isUnauthorizedError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { status?: unknown }).status === 401;
}

function proofStats(data: HomeData, coverage: NonNullable<HomeData["outcomeGraphCoverage"]>): ProofStats {
  const counts = coverage.counts;
  const mismatches = (counts.wrong ?? 0) + (counts.missing ?? 0) + (counts.forbidden ?? 0) + (counts.duplicate ?? 0);
  const needsAttention = (counts.unknown ?? 0) + (counts.stale ?? 0) + (counts.conflicted ?? 0);
  return {
    totalActions: coverage.total,
    proven: counts.verified ?? 0,
    mismatches,
    needsAttention,
    pendingApprovals: data.homeSummary?.metrics.pending_approvals ?? 0,
    openIncidents: data.incidents.filter((item) => item.status !== "resolved").length,
    blockedAttempts: data.approvals.filter((item) => ["blocked", "rejected", "expired"].includes(item.status)).length,
    coveragePercent: Math.round(coverage.coverage_percent),
  };
}

function homePosture(stats: ProofStats, unavailableCount: number, readiness: ReadinessRow[]): PostureStatus {
  if (stats.totalActions === 0) return "INACTIVE";
  if (stats.openIncidents >= 5 || (stats.totalActions > 0 && stats.coveragePercent === 0 && stats.needsAttention > 0)) return "CRITICAL";
  if (
    stats.mismatches > 0 ||
    stats.openIncidents > 0 ||
    stats.needsAttention > 0 ||
    stats.pendingApprovals > 0 ||
    stats.blockedAttempts > 0 ||
    unavailableCount > 0 ||
    readiness.some((item) => ["Blocked", "Stale", "Missing"].includes(item.status))
  ) {
    return "DEGRADED";
  }
  return "ACTIVE";
}

function blockerText(status: PostureStatus, stats: ProofStats, readiness: ReadinessRow[]): string {
  if (status === "INACTIVE") return "Connector test-read missing";
  const blocked = readiness.find((item) => item.status === "Blocked" || item.status === "Missing" || item.status === "Stale");
  if (blocked) return blocked.details;
  if (stats.mismatches > 0) return `${formatCount(stats.mismatches)} source-of-truth mismatches require review`;
  if (stats.pendingApprovals > 0) return `${formatCount(stats.pendingApprovals)} approvals are waiting for an operator`;
  return "No current blocker";
}

function postureExplanation(status: PostureStatus): string {
  if (status === "INACTIVE") return "Verification is not active yet. Connect a source to start proving outcomes.";
  if (status === "CRITICAL") return "Source-of-truth evidence contradicts one or more agent success claims.";
  if (status === "DEGRADED") return "Verification is running, but one source cannot be independently read.";
  return "Current actions are proven against configured sources of truth.";
}

function primaryCta(status: PostureStatus, stats: ProofStats) {
  if (status === "INACTIVE") return { label: "Connect source", href: "/integrations" };
  if (stats.pendingApprovals > Math.max(stats.mismatches, stats.needsAttention)) return { label: "Open approvals", href: "/operations" };
  if (status === "CRITICAL") return { label: "Review incidents", href: "/operations" };
  if (status === "DEGRADED") return { label: "Resolve blocker", href: "/integrations" };
  return { label: "View evidence", href: "/evidence" };
}

function heroHeadline(stats: ProofStats): string {
  if (stats.mismatches > 0) return `${formatCount(stats.mismatches)} mismatches caught`;
  if (stats.totalActions > 0) return `${formatCount(stats.proven)} proven · ${stats.coveragePercent}% coverage`;
  return "Proof rail not configured";
}

function denominatorLine(stats: ProofStats): string {
  return `${formatCount(stats.totalActions)} actions · ${formatCount(stats.proven)} proven · ${formatCount(stats.mismatches)} mismatches · ${formatCount(stats.needsAttention)} need attention · ${formatCount(stats.pendingApprovals)} need approval`;
}

function quotaWarning(usage: BillingUsageResponse | null): string | null {
  if (!usage) return null;
  const meters: Array<[string, BillingUsageMeter]> = [
    ["Governed actions", usage.protected_actions],
    ["Runner executions", usage.runner_executions],
    ["Evidence receipts", usage.action_receipts],
    ["Verification checks", usage.verification_checks],
  ];
  for (const [label, meter] of meters) {
    if (!meter || meter.unlimited || meter.limit == null || meter.limit <= 0) continue;
    const ratio = meter.used / meter.limit;
    const state = (meter.state ?? "").toLowerCase();
    if ((meter.overage != null && meter.overage > 0) || state.includes("exceeded") || state.includes("over")) {
      return `${label} quota exceeded`;
    }
    if (ratio >= 0.9) return `${label} quota ${Math.round(ratio * 100)}% used`;
  }
  return null;
}

function buildReadinessRows(data: HomeData, availability: HomeAvailability): ReadinessRow[] {
  const connectedFeeds = data.sourceSummary?.connected_feeds ?? 0;
  const successfulPollers = data.sourceSummary?.successful_pollers ?? 0;
  const health = data.homeSummary?.data?.control_health ?? null;
  const receipts = data.homeSummary?.metrics.receipts_generated ?? data.intents.filter((intent) => intent.receipt_status === "generated").length;
  const activeConnectors = health?.active_sor_connectors ?? 0;
  const testedConnectors = health?.tested_sor_connectors ?? 0;
  const configuredPacks = health?.configured_action_packs ?? 0;
  const onlineRunners = health?.online_runners ?? 0;
  const policyReady = Boolean(
    health
    && health.active_agents > 0
    && health.policy_enforced_agents >= health.active_agents
    && health.runtime_enabled
    && !health.kill_switch_enabled,
  );

  return [
    {
      component: "Source freshness",
      status: !availability.sourceSummary ? "Stale" : connectedFeeds === 0 ? "Missing" : successfulPollers < connectedFeeds ? "Stale" : "Ready",
      details:
        connectedFeeds === 0
          ? "No source connected"
          : `${successfulPollers}/${connectedFeeds} source pollers successful`,
      action: "Review",
      href: "/integrations",
    },
    {
      component: "Connector test-read",
      status: !health ? "Stale" : activeConnectors > 0 && testedConnectors >= activeConnectors ? "Ready" : "Blocked",
      details: !health
        ? "Control health unavailable"
        : `${formatCount(testedConnectors)} of ${formatCount(activeConnectors)} connectors tested`,
      action: "Fix",
      href: "/integrations",
      ownerOnly: true,
    },
    {
      component: "Evidence signer",
      status: receipts > 0 ? "Ready" : "Missing",
      details: receipts > 0 ? `${formatCount(receipts)} signed bundles generated` : "No signed receipt generated yet",
      action: "View",
      href: "/evidence",
    },
    {
      component: "Executor / recovery rail",
      status: !health ? "Stale" : onlineRunners > 0 ? "Ready" : "Missing",
      details: !health ? "Control health unavailable" : `${formatCount(onlineRunners)} runners online`,
      action: "View",
      href: "/operations",
    },
    {
      component: "Policy engine",
      status: !health ? "Stale" : policyReady ? "Ready" : "Blocked",
      details: !health
        ? "Control health unavailable"
        : health.kill_switch_enabled
          ? "Kill switch enabled"
          : `${formatCount(health.policy_enforced_agents)} of ${formatCount(health.active_agents)} agents enforced`,
      action: "Inspect",
      href: "/policies",
    },
    {
      component: "Assurance Pack binding",
      status: !health ? "Stale" : configuredPacks > 0 ? "Ready" : "Missing",
      details: !health ? "Control health unavailable" : `${formatCount(configuredPacks)} configured action packs`,
      action: "Bind",
      href: "/workflows",
      ownerOnly: true,
    },
    {
      component: "Observation intake",
      status: !health ? "Stale" : activeConnectors > 0 ? "Ready" : "Missing",
      details: !health ? "Control health unavailable" : `${formatCount(activeConnectors)} active source connectors`,
      action: "Open",
      href: "/operations",
    },
    {
      component: "Outbox / async worker",
      status: data.staleAttempts.length > 0 ? "Stale" : "Ready",
      details: data.staleAttempts.length > 0 ? `${formatCount(data.staleAttempts.length)} jobs delayed` : "No delayed verification jobs",
      action: "Retry",
      href: "/operations",
      ownerOnly: true,
    },
  ];
}

function buildAttentionRows(data: HomeData): AttentionRow[] {
  const rows: AttentionRow[] = [];

  data.incidents
    .filter((incident) => incident.status !== "resolved")
    .slice(0, 2)
    .forEach((incident) => {
      const detail = incident.incident;
      rows.push({
        priority: incident.severity === "critical" || incident.severity === "high" ? "P1" : "P2",
        item: typeof detail.deviation_type === "string" ? detail.deviation_type : "Outcome proof requires attention",
        source: typeof detail.source_system === "string" ? detail.source_system : "Source of truth",
        workflow: typeof detail.workflow_key === "string" ? detail.workflow_key : incident.outcome_graph_id,
        age: timeSince(incident.created_at),
        action: "Investigate",
        href: "/operations",
      });
    });

  data.approvals
    .filter((approval) => approval.status === "pending_approval")
    .slice(0, 2)
    .forEach((approval) => {
      rows.push({
        priority: "P1",
        item: "Approval required: policy exception",
        source: approval.tool_name ?? approval.action_type ?? "Policy engine",
        workflow: approval.agent_name ?? "Agent workflow",
        age: timeSince(approval.created_at),
        action: "Review",
        href: "/operations",
      });
    });

  data.staleAttempts.slice(0, 2).forEach((attempt) => {
    rows.push({
      priority: "P2",
      item: "Recovery job failed",
      source: attempt.runner_id,
      workflow: attempt.action_id,
      age: timeSince(attempt.updated_at),
      action: "Retry",
      href: "/operations",
    });
  });

  data.mutations
    .filter((mutation) => ["policy_bypass", "unmanaged_agent_action", "unknown_actor"].includes(mutation.classification))
    .slice(0, 2)
    .forEach((mutation) => {
      rows.push({
        priority: "P2",
        item: "Unverifiable action detected",
        source: mutation.source_system,
        workflow: mutation.action_type ?? mutation.resource_type ?? "Unknown workflow",
        age: timeSince(mutation.occurred_at),
        action: "Analyze",
        href: "/operations",
      });
    });

  return rows.slice(0, 6);
}

function activityExists(stats: ProofStats): boolean {
  return stats.totalActions > 0 || stats.proven > 0 || stats.mismatches > 0 || stats.pendingApprovals > 0 || stats.needsAttention > 0;
}

function renderStatusIcon(status: BadgeStatus | PostureStatus, size = 12) {
  if (status === "Ready" || status === "ACTIVE") return <CheckCircle2 size={size} aria-hidden="true" />;
  if (status === "Blocked" || status === "Critical" || status === "CRITICAL") return <XCircle size={size} aria-hidden="true" />;
  if (status === "Stale" || status === "Missing" || status === "Pending" || status === "DEGRADED") {
    return <AlertTriangle size={size} aria-hidden="true" />;
  }
  return <Circle size={size} aria-hidden="true" />;
}

function StatusBadge({ status }: { status: BadgeStatus | PostureStatus }) {
  return (
    <span className="zh-status-badge" data-status={status.toLowerCase()}>
      {renderStatusIcon(status)}
      {status}
    </span>
  );
}

function PermissionGate({
  canAct,
  ownerOnly,
  href,
  children,
  className = "zh-btn zh-btn-ghost",
}: {
  canAct: boolean;
  ownerOnly?: boolean;
  href: string;
  children: ReactNode;
  className?: string;
}) {
  if (!ownerOnly || canAct) {
    return (
      <Link className={className} href={href}>
        {children}
      </Link>
    );
  }
  return (
    <span className={`${className} is-disabled`} aria-disabled="true" title="Read-only role cannot perform this action">
      {children}
    </span>
  );
}

function VerdictHero({
  stats,
  status,
  blocker,
  canAct,
  errorCount,
  quota,
  currentWindowDays,
  onWindowChange,
  onRefresh,
}: {
  stats: ProofStats;
  status: PostureStatus;
  blocker: string;
  canAct: boolean;
  errorCount: number;
  quota: string | null;
  currentWindowDays: number;
  onWindowChange: (days: number) => void;
  onRefresh: () => void;
}) {
  const cta = primaryCta(status, stats);
  const windows = [
    ["24h", 1],
    ["7d", 7],
    ["30d", 30],
  ] as const;

  return (
    <section className="zh-card zh-proof-posture zh-verdict-hero" aria-label="Proof posture">
      <div className="zh-proof-top">
        <div className="zh-proof-status">
          <p className="zh-kicker">Proof posture</p>
          <div className="zh-posture-line">
            <h2>{status}</h2>
            <StatusBadge status={status} />
          </div>
          <p>{postureExplanation(status)}</p>
          {errorCount > 0 ? <span className="zh-inline-alert">{errorCount} source feed unavailable</span> : null}
          {quota ? <span className="zh-inline-alert">{quota}</span> : null}
        </div>

        <div className="zh-proof-summary" aria-label="Proof denominator">
          <strong>{heroHeadline(stats)}</strong>
          <span>{denominatorLine(stats)}</span>
          <div className="zh-window-switch" aria-label="Home time window">
            {windows.map(([label, days]) => (
              <button
                key={label}
                type="button"
                className={currentWindowDays === days ? "is-active" : undefined}
                onClick={() => onWindowChange(days)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="zh-proof-actions">
        <p>
          <AlertCircle size={14} aria-hidden="true" />
          <span>{blocker}</span>
        </p>
        <div>
          <PermissionGate canAct={canAct} ownerOnly href={cta.href} className="zh-btn zh-btn-primary">
            {cta.label}
          </PermissionGate>
          <Link className="zh-btn zh-btn-outline" href="/operations">
            Go to Operations
          </Link>
          <Link className="zh-btn zh-btn-ghost" href="/evidence">
            View evidence
          </Link>
          <button className="zh-icon-btn" type="button" aria-label="Refresh Home dashboard" onClick={onRefresh}>
            <RotateCcw size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>
  );
}

function ProofMetricsStrip({ stats, loading }: { stats: ProofStats; loading: boolean }) {
  const cells = [
    { label: "Mismatches caught", value: stats.mismatches, href: "/operations", tone: "critical", Icon: ShieldAlert },
    { label: "Proven outcomes", value: stats.proven, href: "/evidence", tone: "ready", Icon: ShieldCheck },
    { label: "Needs attention", value: stats.needsAttention, href: "/evidence?filter=needs_attention", tone: "stale", Icon: AlertTriangle },
    { label: "Open incidents", value: stats.openIncidents, href: "/operations?view=incidents", tone: "critical", Icon: BellDot },
    { label: "Pending approvals", value: stats.pendingApprovals, href: "/operations", tone: "pending", Icon: LockKeyhole },
    { label: "Coverage", value: `${stats.coveragePercent}%`, href: "/evidence", tone: "neutral", Icon: BarChart3 },
  ];

  return (
    <section className="zh-metric-strip" aria-label="Proof metrics">
      {cells.map(({ label, value, href, tone, Icon }) => (
        <Link className="zh-metric-cell" data-tone={tone} href={href} key={label}>
          <span>
            <Icon size={15} aria-hidden="true" />
            {label}
          </span>
          <strong>{loading ? "—" : typeof value === "number" ? formatCount(value) : value}</strong>
          <small>Open detail <ChevronRight size={11} aria-hidden="true" /></small>
        </Link>
      ))}
    </section>
  );
}

function CompactAttentionQueue({ rows, canAct, loading }: { rows: AttentionRow[]; canAct: boolean; loading: boolean }) {
  if (loading) {
    return (
      <section className="zh-card zh-table-card zh-attention zh-attention-compact" aria-label="Attention queue">
        <PanelHeader title="Attention queue" meta="Syncing" action="View all" href="/operations" />
        <div className="zh-skeleton-list" aria-hidden="true">
          {Array.from({ length: 5 }).map((_, index) => <span key={index} />)}
        </div>
      </section>
    );
  }

  return (
    <section className="zh-card zh-table-card zh-attention zh-attention-compact" aria-label="Attention queue">
      <PanelHeader title="Attention queue" meta={`${rows.length} items`} action="View all" href="/operations" />
      <div className="zh-attention-list">
        {rows.slice(0, 6).map((row, index) => (
          <div
            className="zh-attention-item"
            key={`${row.priority}-${row.item}-${row.age}-${index}`}
            aria-label={`${row.priority} ${row.item}. ${row.source}. ${row.workflow}. ${row.age}.`}
          >
            <span className="zh-severity-dot" data-priority={row.priority} aria-label={row.priority} />
            <div className="zh-attention-copy">
              <div className="zh-attention-title">
                <span className="zh-type-chip">{row.priority}</span>
                <Link href={row.href} className="zh-row-link">{row.item}</Link>
              </div>
              <small>{row.source} · {row.workflow}</small>
            </div>
            <time className="zh-mono">{row.age}</time>
            <PermissionGate canAct={canAct} ownerOnly href={row.href}>
              Open
            </PermissionGate>
          </div>
        ))}
      </div>
    </section>
  );
}

function TrustMachineHealth({ rows }: { rows: ReadinessRow[] }) {
  const core = ["Source freshness", "Connector test-read", "Evidence signer", "Executor / recovery rail"];
  const healthRows = core
    .map((component) => rows.find((row) => row.component === component))
    .filter((row): row is ReadinessRow => Boolean(row));

  return (
    <section className="zh-card zh-table-card zh-trust-health" aria-label="Trust-machine health">
      <PanelHeader title="Trust-machine health" meta="Source · executor · signer · test-read" action="Review" href="/integrations" />
      <div className="zh-health-list">
        {healthRows.map((row) => (
          <div className="zh-health-row" key={row.component}>
            <div className="zh-health-copy">
              <strong>{row.component}</strong>
              <small>{row.details}</small>
            </div>
            <StatusBadge status={row.status} />
          </div>
        ))}
      </div>
    </section>
  );
}

function RecentProof({ events, empty }: { events: ProofEvent[]; empty: boolean }) {
  return (
    <section className="zh-card zh-side-card" aria-label="Recent control events">
      <PanelHeader title="Recent control events" action="Operations" href="/operations" />
      {empty ? (
        <div className="zh-empty-inline">
          <FileCheck2 size={18} aria-hidden="true" />
          <strong>No events yet</strong>
          <span>Connect a source and verify the first run to start the proof log.</span>
        </div>
      ) : (
        <>
          <div className="zh-proof-events">
            {events.map((event, index) => {
              return (
                <Link href={event.href} className="zh-proof-event" key={`${event.label}-${event.time}-${index}`}>
                  {renderStatusIcon(event.tone, 14)}
                  <code>{event.id}</code>
                  <span>{event.label}</span>
                  <em>{event.outcome}</em>
                  <small>{event.signature}</small>
                  <time>{event.time}</time>
                </Link>
              );
            })}
          </div>
          <div className="zh-proof-footer">
            <span>Durable records</span>
            <time>Latest event {events[0]?.time}</time>
          </div>
        </>
      )}
    </section>
  );
}

function PanelHeader({ title, meta, action, href }: { title: string; meta?: string; action?: string; href?: string }) {
  return (
    <div className="zh-panel-header">
      <div>
        <h2>{title}</h2>
        {meta ? <p>{meta}</p> : null}
      </div>
      {action && href ? (
        <Link href={href}>
          {action}
          <ArrowRight size={12} aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}

function AgentRecoveryPressure({ stats }: { stats: ProofStats }) {
  return (
    <section className="zh-card zh-side-card zh-recovery-pressure" aria-label="Recovery snapshot">
      <PanelHeader title="Recovery snapshot" meta="Current durable state" action="Operations" href="/operations" />
      <div className="zh-pressure-summary">
        <div>
          <strong>{formatCount(stats.mismatches)}</strong>
          <span>mismatches</span>
        </div>
        <div>
          <strong>{formatCount(stats.openIncidents)}</strong>
          <span>open incidents</span>
        </div>
        <div>
          <strong>{formatCount(stats.blockedAttempts)}</strong>
          <span>blocked</span>
        </div>
        <div>
          <strong>{formatCount(stats.needsAttention)}</strong>
          <span>needs attention</span>
        </div>
      </div>
    </section>
  );
}

function buildProofEvents(data: HomeData): ProofEvent[] {
  const outcomeEvents = data.outcomes.slice(0, 3).map((outcome): ProofEvent => ({
    tone: outcome.verdict === "mismatched" || outcome.verification_status === "mismatched" ? "Critical" : "Ready",
    id: outcome.id,
    label:
      outcome.verdict === "mismatched" || outcome.verification_status === "mismatched"
        ? `Mismatch caught in ${outcome.action_type ?? "agent action"}`
        : `Action verified: ${outcome.action_type ?? "agent action"}`,
    outcome: outcome.verdict === "mismatched" ? "mismatch" : "verified",
    signature: outcome.idempotency_key ?? outcome.id,
    time: timeSince(outcome.checked_at),
    href: "/evidence",
  }));
  const approvalEvents = data.approvals.slice(0, 2).map((approval): ProofEvent => ({
    tone: approval.status === "approved" ? "Ready" : "Pending",
    id: approval.id,
    label: approval.status === "approved" ? "Approval granted: budget exception" : "Approval required: policy exception",
    outcome: approval.status.replaceAll("_", " "),
    signature: approval.id,
    time: timeSince(approval.created_at),
    href: "/operations",
  }));
  const staleEvents = data.staleAttempts.slice(0, 1).map((attempt): ProofEvent => ({
    tone: "Stale",
    id: attempt.attempt_id,
    label: `Connector read failed: ${attempt.runner_id}`,
    outcome: attempt.status,
    signature: attempt.plan_digest.slice(0, 12),
    time: timeSince(attempt.updated_at),
    href: "/operations",
  }));
  return [...outcomeEvents, ...approvalEvents, ...staleEvents].slice(0, 6);
}

function FirstRunSetup({ canAct }: { canAct: boolean }) {
  const steps = [
    ["Connect a source", "/integrations", Plug],
    ["Define an Assurance Pack", "/workflows", Workflow],
    ["Connect an agent", "/workflows", KeyRound],
    ["See first verified run", "/operations", ShieldCheck],
  ] as const;
  return (
    <section className="zh-card zh-first-run" aria-label="First-run setup">
      <div>
        <p className="zh-kicker">Verification readiness</p>
        <h2>Build the proof rail before trusting automated work</h2>
        <p>Connect a source, bind an Assurance Pack, connect an agent, then verify the first real run.</p>
        <PermissionGate canAct={canAct} ownerOnly href="/integrations" className="zh-btn zh-btn-primary">
          Connect source
        </PermissionGate>
      </div>
      <ol>
        {steps.map(([label, href, Icon], index) => (
          <li key={label}>
            <Icon size={15} aria-hidden="true" />
            <code>{String(index + 1).padStart(2, "0")}</code>
            <span>{label}</span>
            <PermissionGate canAct={canAct} ownerOnly href={href}>
              Open
            </PermissionGate>
          </li>
        ))}
      </ol>
    </section>
  );
}

function HomeUnavailable({ errorCount, onRefresh }: { errorCount: number; onRefresh: () => void }) {
  return (
    <section className="zh-card zh-home-unavailable" aria-label="Home unavailable">
      <AlertTriangle size={18} aria-hidden="true" />
      <div>
        <p className="zh-kicker">Proof posture unavailable</p>
        <h2>{errorCount} source feed unavailable</h2>
        <p>Zroky could not load verified actions and incidents. No status is being inferred.</p>
      </div>
      <button className="zh-btn zh-btn-primary" type="button" onClick={onRefresh}>
        Retry
      </button>
    </section>
  );
}

function HomeAuthRequired() {
  return (
    <section className="zh-card zh-home-unavailable" aria-label="Home authentication required">
      <LockKeyhole size={18} aria-hidden="true" />
      <div>
        <p className="zh-kicker">Session required</p>
        <h2>Sign in to continue</h2>
        <p>Your session has ended. Sign in again to view verified actions and incidents.</p>
      </div>
      <Link className="zh-btn zh-btn-primary" href="/login?next=%2Fhome">
        Sign in
      </Link>
    </section>
  );
}

export default function HomePage() {
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const dateRange = useDashboardStore((state) => state.dateRange);
  const setDateRange = useDashboardStore((state) => state.setDateRange);
  const summaryDays = useMemo(() => homeWindowDays(dateRange), [dateRange]);
  const [data, setData] = useState<HomeData>(EMPTY_DATA);
  const [availability, setAvailability] = useState<HomeAvailability>(NO_SOURCES_AVAILABLE);
  const [isLoading, setIsLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState(0);
  const [loadIssue, setLoadIssue] = useState<HomeLoadIssue>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const [projectRole, setProjectRole] = useState<HomeRole>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      if (localDemoHomeEnabled()) {
        const summary = demoHomeSummary(summaryDays);
        if (signal?.aborted) return;
        setData({
          ...missionDataFromSummary(summary),
          outcomeGraphCoverage: {
            counts: {
              conflicted: 0,
              duplicate: 0,
              forbidden: 0,
              missing: 0,
              pending: 6,
              stale: 0,
              unknown: 0,
              verified: 142,
              wrong: 3,
            },
            coverage_percent: 94,
            total: 151,
          },
          incidents: [
            {
              id: "incident_demo_payroll",
              project_id: "demo_project",
              environment: "production",
              outcome_graph_id: "graph_demo_payroll",
              severity: "high",
              status: "open",
              incident: {
                deviation_type: "Mismatch in payroll export",
                source_system: "Workday Payroll",
                workflow_key: "Payroll Export WF",
              },
              created_at: new Date(Date.now() - 12 * 60_000).toISOString(),
              resolved_at: null,
            },
          ],
        });
        setAvailability(availabilityFromSummary(summary));
        setLoadErrors(0);
        setLoadIssue(null);
        setLastLoadedAt(summary.generated_at);
        setProjectRole("owner");
        return;
      }
      const [summary, coverage, incidents, projects] = await Promise.all([
        getHomeSummary(summaryDays, signal),
        fetchOutcomeGraphCoverage(signal).catch(() => null),
        listFinalIncidents(signal).catch(() => null),
        listMyProjects(signal).catch(() => []),
      ]);
      if (signal?.aborted) return;
      if (coverage === null || incidents === null) {
        throw new Error("Proof ledger summary is unavailable.");
      }
      const project = selectedProject
        ? projects.find((item) => item.project_id === selectedProject) ?? null
        : projects[0] ?? null;
      const nextAvailability = availabilityFromSummary(summary);
      setData({ ...missionDataFromSummary(summary), outcomeGraphCoverage: coverage, incidents });
      setAvailability(nextAvailability);
      setLoadErrors(unavailableSourceCount(nextAvailability));
      setLoadIssue(null);
      setLastLoadedAt(summary.generated_at ?? new Date().toISOString());
      setProjectRole(project?.role ?? null);
    } catch (error) {
      if (signal?.aborted) return;
      setAvailability(NO_SOURCES_AVAILABLE);
      setData(EMPTY_DATA);
      setLoadErrors(isUnauthorizedError(error) ? 0 : unavailableSourceCount(NO_SOURCES_AVAILABLE));
      setLoadIssue(isUnauthorizedError(error) ? "auth" : "source");
      setLastLoadedAt(null);
    } finally {
      if (!signal?.aborted) setIsLoading(false);
    }
  }, [selectedProject, summaryDays]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (!realTimeEnabled) return;
    const interval = window.setInterval(() => {
      const controller = new AbortController();
      void load(controller.signal);
    }, 30_000);
    return () => window.clearInterval(interval);
  }, [load, realTimeEnabled]);

  const canAct = canChangeHomeSetup(projectRole);
  const demoMode = localDemoHomeEnabled();
  const stats = data.outcomeGraphCoverage ? proofStats(data, data.outcomeGraphCoverage) : null;
  const readiness = buildReadinessRows(data, availability);
  const status = stats ? homePosture(stats, loadErrors, readiness) : null;
  const blocker = stats && status ? blockerText(status, stats, readiness) : "";
  const active = stats ? activityExists(stats) : false;
  const attentionRows = buildAttentionRows(data);
  const displayedAttentionRows = demoMode ? DEMO_ATTENTION_ROWS : attentionRows;
  const proofEvents = buildProofEvents(data);
  const displayedProofEvents = demoMode ? DEMO_PROOF_EVENTS : proofEvents;
  const loading = isLoading && lastLoadedAt == null;
  const authRequired = loadIssue === "auth" && lastLoadedAt == null && !loading;
  const loadFailed = loadIssue === "source" && loadErrors > 0 && lastLoadedAt == null && !loading;
  const firstRun = stats !== null && !active && !loading && !loadFailed && !authRequired;

  function setWindowDays(days: number) {
    const to = new Date();
    const from = new Date(to);
    from.setDate(to.getDate() - days);
    setDateRange({ from, to });
  }

  return (
    <main className={`${styles.homeDashboard} zh-home`} aria-label="ZROKY Home dashboard">
      <div className="zh-page-title">
        <div>
          <h1>Home</h1>
          <p>Proof, verification and governance overview</p>
        </div>
      </div>

      {authRequired ? <HomeAuthRequired /> : null}
      {loadFailed ? <HomeUnavailable errorCount={loadErrors} onRefresh={() => void load()} /> : null}
      {firstRun ? <FirstRunSetup canAct={canAct} /> : null}
      {loading && stats === null ? (
        <section className="zh-card zh-home-unavailable" aria-label="Loading verified Home data" aria-busy="true">
          <div>
            <p className="zh-kicker">Loading</p>
            <h2>Loading verified data</h2>
            <p>Waiting for verified actions and incidents.</p>
          </div>
        </section>
      ) : null}

      {stats !== null && status !== null && !firstRun && !loadFailed && !authRequired ? (
        <>
          <VerdictHero
            stats={stats}
            status={status}
            blocker={blocker}
            canAct={canAct}
            errorCount={loadErrors}
            quota={quotaWarning(data.billingUsage)}
            currentWindowDays={summaryDays}
            onWindowChange={setWindowDays}
            onRefresh={() => void load()}
          />

          <ProofMetricsStrip stats={stats} loading={loading} />

          <div className="zh-operational-grid">
            <div className="zh-left-stack">
              <CompactAttentionQueue rows={displayedAttentionRows} canAct={canAct} loading={loading} />
              <TrustMachineHealth rows={readiness} />
            </div>

            <aside className="zh-right-stack" aria-label="Home side panels">
              <AgentRecoveryPressure stats={stats} />
              <RecentProof events={displayedProofEvents} empty={displayedProofEvents.length === 0} />
            </aside>
          </div>
        </>
      ) : null}
    </main>
  );
}
