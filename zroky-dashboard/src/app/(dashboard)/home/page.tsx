"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { KeyboardEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock3,
  FileJson,
  GitPullRequest,
  ListChecks,
  LockKeyhole,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";

import {
  EmptyQueue,
  FirstRunOnboarding,
  KpiCard,
  LockedUpgradeLink,
  SectionHeader,
} from "@/components/command-center-primitives";
import { hasPlanEntitlement } from "@/components/feature-gate";
import { StatusPill } from "@/components/status-pill";
import {
  ApiError,
  createReplayRunFromIssue,
  getAnalyticsSummary,
  getBillingMe,
  getCaptureHealth,
  getReplayQuota,
  listCalls,
  listGoldenSets,
  listIssues,
  listProjectApiKeys,
  listReplayRuns,
  type GoldenSetView,
  type ReplayQuotaResponse,
  type ReplayRunItem,
} from "@/lib/api";
import { detectorLabel } from "@/lib/detector-meta";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel, severityRank } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import { useDashboardStore } from "@/lib/store";
import type {
  AnalyticsSummaryResponse,
  ApiKeyResponse,
  BillingMeResponse,
  CallListItem,
  CaptureHealthResponse,
  IssueItem,
} from "@/lib/types";

type InboxData = {
  issues: IssueItem[];
  replayRuns: ReplayRunItem[];
  goldenSets: GoldenSetView[];
  billing: BillingMeResponse | null;
  quota: ReplayQuotaResponse | null;
  summary: AnalyticsSummaryResponse | null;
  calls: CallListItem[];
  captureHealth: CaptureHealthResponse | null;
  apiKeys: ApiKeyResponse[];
};

type IssueAction = "view" | "replay" | "open_goldens" | "upgrade";
type InboxLoadKey = keyof InboxData;
type InboxLoadErrors = Partial<Record<InboxLoadKey, string>>;
type InboxQueueFocus = "all" | "critical_high" | "replay_gap" | "impact" | "verified";
type PriorityTone = "danger" | "warning" | "success" | "neutral";
type QueueFocusControl = {
  id: InboxQueueFocus;
  label: string;
};

type PriorityRow = {
  id: string;
  priority: string;
  type: string;
  title: string;
  detail: string;
  impact: string;
  status: string;
  tone: PriorityTone;
  action: ReactNode;
  issueId?: string;
};

const refreshIntervalMs = 30_000;
const loadSourceLabels: Record<InboxLoadKey, string> = {
  issues: "Issues",
  replayRuns: "Replay runs",
  goldenSets: "Contracts",
  billing: "Billing",
  quota: "Replay quota",
  summary: "Analytics",
  calls: "Traces",
  captureHealth: "Capture health",
  apiKeys: "Project keys",
};

const GOLDEN_ELIGIBLE_REPLAY_STATUSES = new Set(["verified_fix"]);

const REPLAY_GAP_STATUSES = new Set([
  "not_covered",
  "covered_not_run",
  "fix_pending_replay",
  "replay_missing",
  "covered_failed",
  "sanity_replay_passed",
  "real_replay_missing_tool_proof",
  "stub_only",
  "not_verified",
  "tool_snapshot_missing",
  "inconclusive",
  "real_replay_passed",
  "covered_passed",
]);

const queueFocusControls: QueueFocusControl[] = [
  { id: "all", label: "All" },
  { id: "critical_high", label: "High risk" },
  { id: "replay_gap", label: "Missing proof" },
  { id: "impact", label: "Exposure" },
  { id: "verified", label: "Verified" },
];

function normalizedReplayStatus(issue: IssueItem): string {
  return issue.replay_coverage_status.trim().toLowerCase();
}

function hasTrustedGoldenReplay(issue: IssueItem): boolean {
  return GOLDEN_ELIGIBLE_REPLAY_STATUSES.has(normalizedReplayStatus(issue));
}

function isReplayGap(issue: IssueItem): boolean {
  return REPLAY_GAP_STATUSES.has(normalizedReplayStatus(issue));
}

function usableUsd(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function issueImpactUsd(issue: IssueItem): number | null {
  return usableUsd(issue.blast_radius_usd) ?? usableUsd(issue.cost_impact_usd);
}

function formatIssueImpact(issue: IssueItem): string {
  const impactUsd = issueImpactUsd(issue);
  return impactUsd == null ? "No cost data" : formatUsd(impactUsd);
}

function isAbortError(error: unknown): boolean {
  return (error as { name?: string }).name === "AbortError";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed.";
}

function isPlanGateError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 402;
}

async function settleLoad<T>(
  key: InboxLoadKey,
  promise: Promise<T>,
): Promise<{ key: InboxLoadKey; status: "fulfilled"; value: T } | { key: InboxLoadKey; status: "rejected"; reason: unknown }> {
  try {
    return { key, status: "fulfilled", value: await promise };
  } catch (reason) {
    return { key, status: "rejected", reason };
  }
}

function sortIssues(items: IssueItem[]): IssueItem[] {
  return [...items].sort((a, b) => {
    const severityDelta = severityRank(b.severity) - severityRank(a.severity);
    if (severityDelta !== 0) return severityDelta;

    const replayDelta = Number(isReplayGap(b)) - Number(isReplayGap(a));
    if (replayDelta !== 0) return replayDelta;

    const impactDelta = (issueImpactUsd(b) ?? 0) - (issueImpactUsd(a) ?? 0);
    if (impactDelta !== 0) return impactDelta;

    const occurrenceDelta = b.occurrence_count - a.occurrence_count;
    if (occurrenceDelta !== 0) return occurrenceDelta;

    const priorityDelta = b.priority_score - a.priority_score;
    if (priorityDelta !== 0) return priorityDelta;

    return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
  });
}

function isCiRun(run: ReplayRunItem): boolean {
  return run.trigger === "github" || run.golden_set_id.startsWith("regression-ci:");
}

function isPendingRun(run: ReplayRunItem): boolean {
  return run.status === "pending" || run.status === "running";
}

function isFailedCiRun(run: ReplayRunItem): boolean {
  return isCiRun(run) && ["fail", "failed", "error", "not_verified"].includes(run.status);
}

function needsGoldenReview(set: GoldenSetView): boolean {
  return set.trace_count === 0 || set.is_flaky || !set.blocks_ci;
}

function chooseIssueAction(
  issue: IssueItem,
  caps: { canReplay: boolean; canGoldens: boolean },
): IssueAction {
  if (hasTrustedGoldenReplay(issue) && issue.sample_call_id) {
    return caps.canGoldens ? "open_goldens" : "upgrade";
  }
  if (isReplayGap(issue) || issue.sample_call_id) {
    return caps.canReplay ? "replay" : "upgrade";
  }
  return "view";
}

function planLimitText(quota: ReplayQuotaResponse | null): string {
  if (!quota) return "Replay quota unavailable";
  if (!quota.enabled) return "Replay disabled on current plan";
  if (quota.limit === -1) return `${formatCount(quota.used)} used / unlimited`;
  return `${formatCount(quota.used)} used / ${formatCount(quota.limit)} runs`;
}

function captureStatusLabel(status: CaptureHealthResponse["status"] | "unknown", capturedCallCount: number): string {
  if (capturedCallCount > 0) return `${formatCount(capturedCallCount)} captured`;
  if (status === "connected") return "Live capture";
  if (status === "stale") return "Capture stale";
  if (status === "no_data") return "No capture yet";
  return "Checking capture";
}

function evidenceSummary(issue: IssueItem): string {
  return (
    issue.evidence_traces.find((trace) => trace.evidence_summary)?.evidence_summary ??
    issue.root_cause ??
    issue.user_impact ??
    "No evidence summary captured yet."
  );
}

function filterIssuesForFocus(items: IssueItem[], focus: InboxQueueFocus): IssueItem[] {
  if (focus === "critical_high") {
    return items.filter((issue) => ["critical", "high"].includes(issue.severity.toLowerCase()));
  }
  if (focus === "replay_gap") {
    return items.filter((issue) => !hasTrustedGoldenReplay(issue));
  }
  if (focus === "impact") {
    return [...items]
      .filter((issue) => issueImpactUsd(issue) != null)
      .sort((a, b) => (issueImpactUsd(b) ?? 0) - (issueImpactUsd(a) ?? 0));
  }
  if (focus === "verified") {
    return items.filter(hasTrustedGoldenReplay);
  }
  return items;
}

function queueFocusDescription(focus: InboxQueueFocus): string {
  if (focus === "critical_high") return "High-risk agent actions that need a decision before anyone trusts the outcome.";
  if (focus === "replay_gap") return "Actions where the agent reported success but Zroky cannot prove the real outcome yet.";
  if (focus === "impact") return "The same queue sorted by estimated customer or spend exposure.";
  if (focus === "verified") return "Actions with verified outcome proof ready for an Evidence Pack.";
  return "The highest-risk actions, missing proof, and customer-impact signals in one queue.";
}

function formatLastUpdated(value: number | null): string {
  if (!value) return "Not refreshed yet";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function percentDelta(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (typeof current !== "number" || typeof previous !== "number" || !Number.isFinite(current) || !Number.isFinite(previous) || previous <= 0) {
    return null;
  }
  return Math.round(((current - previous) / previous) * 100);
}

function statusLabel(value: string): string {
  const normalized = value.replace(/_/g, " ").trim().toLowerCase();
  return normalized ? `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}` : "Unknown";
}

function isFailureCall(call: CallListItem): boolean {
  const status = call.status.toLowerCase();
  return status.includes("fail") || status.includes("error") || Boolean(call.error_code);
}

function runPassed(run: ReplayRunItem): boolean {
  const status = run.status.toLowerCase();
  return status.includes("pass") || status === "completed" || run.summary.verified_fix === true;
}

function runFailed(run: ReplayRunItem): boolean {
  const status = run.status.toLowerCase();
  return status.includes("fail") || status.includes("error") || status === "not_verified";
}

function averageLatencyMs(calls: CallListItem[]): number | null {
  const latencies = calls.map((call) => call.latency_ms).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (latencies.length === 0) return null;
  return Math.round(latencies.reduce((sum, value) => sum + value, 0) / latencies.length);
}

function KpiSkeletonRow() {
  return (
    <section className="fi-kpi-grid fi-command-metrics fi-kpi-skeleton-grid" aria-label="Loading Home summary" aria-busy="true">
      {Array.from({ length: 5 }, (_, index) => (
        <div className="fi-kpi-card fi-kpi-skeleton-card" key={index}>
          <div className="fi-skeleton-line is-label" />
          <div className="fi-skeleton-line is-value" />
          <div className="fi-skeleton-line is-helper" />
        </div>
      ))}
    </section>
  );
}

function PriorityTableSkeleton() {
  return (
    <div className="fi-loading-skeleton fi-table-skeleton" aria-label="Loading priority queue" aria-busy="true">
      <div className="fi-skeleton-line is-wide" />
      <div className="fi-skeleton-line" />
      <div className="fi-skeleton-table">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="fi-skeleton-row" key={index}>
            <span />
            <span />
            <span />
            <span />
          </div>
        ))}
      </div>
    </div>
  );
}

function RailSkeleton() {
  return (
    <div className="fi-rail-skeleton" aria-label="Loading evidence and readiness" aria-busy="true">
      {Array.from({ length: 2 }, (_, panelIndex) => (
        <div className="fi-section" key={panelIndex}>
          <div className="fi-skeleton-line is-wide" />
          <div className="fi-skeleton-stack">
            {Array.from({ length: panelIndex === 0 ? 4 : 3 }, (_, rowIndex) => (
              <div className="fi-skeleton-row-card" key={rowIndex}>
                <span />
                <span />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PipelineSkeleton() {
  return (
    <section className="fi-section fi-pipeline-section" aria-label="Loading reliability pipeline" aria-busy="true">
      <div className="fi-skeleton-line is-wide" />
      <div className="fi-pipeline fi-pipeline-skeleton">
        {Array.from({ length: 5 }, (_, index) => (
          <div className="fi-pipeline-stage" key={index}>
            <div className="fi-pipeline-node" />
            <div>
              <span />
              <strong />
              <small />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function StatusText({ value, tone }: { value: string; tone: PriorityTone }) {
  return (
    <span className="fi-status-text" data-tone={tone}>
      <span aria-hidden="true" />
      {value}
    </span>
  );
}

export default function HomePage() {
  const router = useRouter();
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const [data, setData] = useState<InboxData>({
    issues: [],
    replayRuns: [],
    goldenSets: [],
    billing: null,
    quota: null,
    summary: null,
    calls: [],
    captureHealth: null,
    apiKeys: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadErrors, setLoadErrors] = useState<InboxLoadErrors>({});
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyIssueId, setBusyIssueId] = useState<string | null>(null);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [queueFocus, setQueueFocus] = useState<InboxQueueFocus>("all");
  const loadInFlightRef = useRef(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    if (!signal?.aborted) {
      setRefreshing(true);
      setError(null);
    }

    try {
      const results = await Promise.all([
        settleLoad("issues", listIssues({ status: "open", limit: 50 }, signal)),
        settleLoad("replayRuns", listReplayRuns({ limit: 50 }, signal)),
        settleLoad("goldenSets", listGoldenSets({ limit: 50 }, signal)),
        settleLoad("billing", getBillingMe(signal)),
        settleLoad("quota", getReplayQuota(signal)),
        settleLoad("summary", getAnalyticsSummary(1, signal)),
        settleLoad("calls", listCalls({ limit: 10, sort_by: "created_at", sort_order: "desc" }, signal)),
        settleLoad("captureHealth", getCaptureHealth(signal)),
        settleLoad("apiKeys", selectedProject ? listProjectApiKeys(selectedProject, signal) : Promise.resolve([])),
      ]);

      if (signal?.aborted || results.every((result) => result.status === "rejected" && isAbortError(result.reason))) {
        return;
      }

      const nextErrors: InboxLoadErrors = {};
      const updates: Partial<InboxData> = {};
      let successCount = 0;

      for (const result of results) {
        if (result.status === "rejected") {
          if (result.key === "replayRuns" && isPlanGateError(result.reason)) {
            updates.replayRuns = [];
            successCount += 1;
            continue;
          }
          if (result.key === "goldenSets" && isPlanGateError(result.reason)) {
            updates.goldenSets = [];
            successCount += 1;
            continue;
          }
          if (!isAbortError(result.reason)) {
            nextErrors[result.key] = errorMessage(result.reason);
          }
          continue;
        }

        successCount += 1;
        if (result.key === "issues") {
          updates.issues = (result.value as { items: IssueItem[] }).items;
        } else if (result.key === "replayRuns") {
          updates.replayRuns = (result.value as { items: ReplayRunItem[] }).items;
        } else if (result.key === "goldenSets") {
          updates.goldenSets = (result.value as { items: GoldenSetView[] }).items;
        } else if (result.key === "billing") {
          updates.billing = result.value as BillingMeResponse;
        } else if (result.key === "quota") {
          updates.quota = result.value as ReplayQuotaResponse;
        } else if (result.key === "summary") {
          updates.summary = result.value as AnalyticsSummaryResponse;
        } else if (result.key === "calls") {
          updates.calls = (result.value as { items: CallListItem[] }).items;
        } else if (result.key === "captureHealth") {
          updates.captureHealth = result.value as CaptureHealthResponse;
        } else if (result.key === "apiKeys") {
          updates.apiKeys = result.value as ApiKeyResponse[];
        }
      }

      setData((prev) => ({ ...prev, ...updates }));
      setLoadErrors(nextErrors);
      if (successCount > 0) {
        setLastUpdatedAt(Date.now());
      } else {
        setError("Home could not refresh. Showing the last loaded state.");
      }
    } catch (loadError) {
      if (!signal?.aborted) {
        setError(errorMessage(loadError));
      }
    } finally {
      loadInFlightRef.current = false;
      if (!signal?.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [selectedProject]);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);

    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void load();
      }
    }, refreshIntervalMs);

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void load();
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      ctrl.abort();
      loadInFlightRef.current = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [load]);

  const planTemplate = data.billing?.plan_template;
  const caps = useMemo(
    () => ({
      canDiagnose: hasPlanEntitlement(planTemplate, "pilot.root_cause_diagnosis"),
      canReplay: hasPlanEntitlement(planTemplate, "pilot.replay_stub"),
      canGoldens: hasPlanEntitlement(planTemplate, "pilot.goldens_basic"),
      canCi:
        hasPlanEntitlement(planTemplate, "pro.ci_gate_nonblocking") ||
        hasPlanEntitlement(planTemplate, "pro.ci_gate_blocking"),
    }),
    [planTemplate],
  );

  const sortedIssues = useMemo(() => sortIssues(data.issues), [data.issues]);
  const focusedIssues = useMemo(() => filterIssuesForFocus(sortedIssues, queueFocus), [queueFocus, sortedIssues]);
  const protectedAgentCount = useMemo(() => {
    const names = new Set<string>();
    for (const call of data.calls) {
      const name = call.agent_name?.trim();
      if (name) names.add(name);
    }
    for (const issue of data.issues) {
      const name = issue.affected_agent?.trim() || issue.agent_name?.trim();
      if (name) names.add(name);
    }
    return names.size;
  }, [data.calls, data.issues]);

  useEffect(() => {
    if (loading || sortedIssues.length === 0) return;
    const selectedStillVisible = focusedIssues.some((issue) => issue.id === selectedIssueId);
    if (!selectedIssueId || !selectedStillVisible) {
      setSelectedIssueId(focusedIssues[0]?.id ?? sortedIssues[0].id);
    }
  }, [focusedIssues, loading, selectedIssueId, sortedIssues]);

  const criticalHighCount = data.issues.filter((issue) =>
    ["critical", "high"].includes(issue.severity.toLowerCase()),
  ).length;
  const needsTrustedReplayCount = data.issues.filter((issue) => !hasTrustedGoldenReplay(issue)).length;
  const openIssuesCount = data.issues.length;
  const trustedReplayCount = data.issues.filter(hasTrustedGoldenReplay).length;
  const pendingRuns = data.replayRuns.filter((run) => isPendingRun(run) && !isCiRun(run)).slice(0, 6);
  const failedCiRuns = data.replayRuns.filter(isFailedCiRun).slice(0, 6);
  const goldensNeedingReview = data.goldenSets.filter(needsGoldenReview).slice(0, 6);
  const activeProjectKeyCount = data.apiKeys.filter((key) => !key.revoked && !key.expired).length;
  const captureStatus = data.captureHealth?.status ?? "unknown";
  const capturedCallCount = Math.max(data.captureHealth?.calls_24h ?? 0, data.calls.length);
  const captureLabel = captureStatusLabel(captureStatus, capturedCallCount);
  const captureBacklog = data.captureHealth?.gateway_spool_backlog ?? 0;
  const captureHasProblem =
    captureStatus === "stale" ||
    (data.captureHealth?.gateway_unhealthy_count ?? 0) > 0 ||
    captureBacklog > 0 ||
    (data.captureHealth?.gateway_loss_count ?? 0) > 0;
  const failedRunsCount = Math.max(data.calls.filter(isFailureCall).length, criticalHighCount);
  const replayPassCount = data.replayRuns.filter(runPassed).length;
  const replayFailCount = data.replayRuns.filter(runFailed).length;
  const replayCompletedCount = replayPassCount + replayFailCount;
  const replayPassRate =
    replayCompletedCount > 0
      ? Math.round((replayPassCount / replayCompletedCount) * 100)
      : openIssuesCount > 0
        ? Math.round((trustedReplayCount / openIssuesCount) * 100)
        : 0;
  const costTrend = percentDelta(data.summary?.cost_today_usd, data.summary?.cost_yesterday_usd);
  const latencyAverage = averageLatencyMs(data.calls);
  const protectedGoldenCount = data.goldenSets.filter((set) => set.blocks_ci && !set.is_flaky).length;
  const openDecisionCount =
    needsTrustedReplayCount +
    pendingRuns.length +
    failedCiRuns.length +
    (captureHasProblem ? 1 : 0);
  const evidenceReadyCount = [
    capturedCallCount > 0,
    sortedIssues.length > 0,
    data.replayRuns.length > 0,
    protectedGoldenCount > 0,
  ].filter(Boolean).length;
  const hasLoadedIssues = sortedIssues.length > 0;
  const hasWorkspaceActivity = capturedCallCount > 0 || hasLoadedIssues || data.replayRuns.length > 0 || data.goldenSets.length > 0;
  const headerSubtitle = hasWorkspaceActivity
    ? "Runtime decisions, outcome checks, and Evidence Packs for production agent actions."
    : "Connect your first agent and system of record to start outcome proof.";
  const blockingCiRun = failedCiRuns[0] ?? null;
  const firstUnprotectedIssue = sortedIssues.find((issue) => !hasTrustedGoldenReplay(issue)) ?? sortedIssues[0] ?? null;
  const heroSignal = loading
    ? {
        eyebrow: "Checking safety",
        title: "Loading agent safety",
        summary: "Fetching runtime decisions, held actions, outcome proof, and Evidence Pack status.",
        tone: "neutral" as const,
        action: null,
      }
    : !hasWorkspaceActivity
      ? {
          eyebrow: "Setup required",
          title: "Connect first agent",
          summary: headerSubtitle,
          tone: "neutral" as const,
          action: (
            <Link href="/settings/keys" className="btn btn-primary btn-sm fi-btn-primary">
              Create project key
            </Link>
          ),
        }
      : blockingCiRun
        ? {
            eyebrow: "Highest priority",
            title: "Deployment blocked",
            summary: `${formatCount(failedCiRuns.length)} verification gate${failedCiRuns.length === 1 ? "" : "s"} failing on ${blockingCiRun.golden_set_id}.`,
            tone: "danger" as const,
            action: caps.canCi ? (
              <Link href={`/ci-gates/${blockingCiRun.id}`} className="btn btn-primary btn-sm fi-btn-primary">
                <GitPullRequest aria-hidden="true" />
                Open gate
              </Link>
            ) : (
              <LockedUpgradeLink label="Upgrade to unlock CI gates" />
            ),
          }
      : needsTrustedReplayCount > 0 && firstUnprotectedIssue
        ? {
            eyebrow: "Outcome proof missing",
            title: `${formatCount(needsTrustedReplayCount)} action${needsTrustedReplayCount === 1 ? "" : "s"} not verified`,
            summary: "Verify the real-world outcome before this action becomes audit-ready evidence.",
            tone: "warning" as const,
            action: renderIssueAction(firstUnprotectedIssue, { replayLabel: "Verify outcome", viewLabel: "View proof" }),
          }
        : captureHasProblem
          ? {
              eyebrow: "Capture health",
              title: captureStatus === "stale" ? "Agent signal stale" : "Connector backlog needs review",
              summary: captureStatus === "stale" ? "No recent agent action was captured for this project." : "Gateway events are waiting to become outcome proof.",
              tone: "warning" as const,
              action: (
                <Link href="/trace" className="btn btn-primary btn-sm fi-btn-primary">
                  Inspect capture
                  </Link>
                ),
              }
        : {
            eyebrow: "Protected",
            title: protectedGoldenCount > 0 ? "Evidence ready" : "Safety loop ready",
            summary:
              protectedGoldenCount > 0
                ? "Loaded actions have verified proof and no high-risk production signal needs review."
                : headerSubtitle,
            tone: "success" as const,
            action: (
              <Link href="/evidence" className="btn btn-primary btn-sm fi-btn-primary">
                    Open evidence
                  </Link>
                ),
              };
  const loadErrorKeys = Object.keys(loadErrors) as InboxLoadKey[];
  const loadErrorText = loadErrorKeys.map((key) => loadSourceLabels[key]).join(", ");
  const issuesLoadFailed = loadErrorKeys.includes("issues");
  const showFirstRunOnboarding = !loading && !error && !issuesLoadFailed && !hasWorkspaceActivity;
  const lastUpdatedLabel = formatLastUpdated(lastUpdatedAt);
  const homeStatusTiles = [
    {
      label: "Action signals",
      value: formatCount(failedRunsCount),
      helper: "Blocked, failed, or high-risk records loaded.",
      tone: "danger" as const,
      icon: <ShieldAlert aria-hidden="true" />,
    },
    {
      label: "Needs review",
      value: formatCount(openDecisionCount),
      helper: "Held actions, missing proof, stale capture, or failing gates.",
      tone: "warning" as const,
      icon: <LockKeyhole aria-hidden="true" />,
    },
    {
      label: "Verified outcomes",
      value: replayCompletedCount > 0 || openIssuesCount > 0 ? `${formatCount(replayPassRate)}%` : formatCount(trustedReplayCount),
      helper: replayCompletedCount > 0 ? "Replay-backed outcome verification." : "Verified records in the loaded queue.",
      tone: "success" as const,
      icon: <CheckCircle2 aria-hidden="true" />,
    },
    {
      label: "Protected agents",
      value: formatCount(protectedAgentCount),
      helper: protectedAgentCount > 0 ? `${formatCount(capturedCallCount)} captured actions in scope.` : "Waiting for the first captured agent.",
      tone: "info" as const,
      icon: <Bot aria-hidden="true" />,
    },
  ];

  function focusQueue(nextFocus: InboxQueueFocus) {
    setQueueFocus(nextFocus);
    const nextItems = filterIssuesForFocus(sortedIssues, nextFocus);
    setSelectedIssueId(nextItems[0]?.id ?? sortedIssues[0]?.id ?? null);
  }

  async function onReplay(issue: IssueItem) {
    setActionError(null);
    setBusyIssueId(issue.id);
    try {
      const run = await createReplayRunFromIssue(issue.id, {
        replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE,
      });
      router.push(`/replay/${run.id}`);
    } catch (replayError) {
      setActionError(replayError instanceof Error ? replayError.message : "Failed to create replay run.");
    } finally {
      setBusyIssueId(null);
    }
  }

  function renderIssueAction(issue: IssueItem, options?: { replayLabel?: string; viewLabel?: string }) {
    const action = chooseIssueAction(issue, caps);
    if (action === "upgrade") {
      return <LockedUpgradeLink label="Upgrade to unlock this action" />;
    }
    if (action === "replay") {
      return (
        <button
          type="button"
          className="btn btn-primary btn-sm fi-btn-primary"
          onClick={() => void onReplay(issue)}
          disabled={busyIssueId === issue.id}
        >
          <RotateCcw aria-hidden="true" />
          {busyIssueId === issue.id ? "Creating..." : options?.replayLabel ?? "Verify outcome"}
        </button>
      );
    }
    if (action === "open_goldens") {
      return (
        <Link href="/contracts" className="btn btn-primary btn-sm fi-btn-primary">
          <ShieldCheck aria-hidden="true" />
          Open evidence
        </Link>
      );
    }
    return (
      <Link href={`/issues/${issue.id}`} className="btn btn-primary btn-sm fi-btn-primary">
        <ArrowRight aria-hidden="true" />
        {options?.viewLabel ?? "View proof"}
      </Link>
    );
  }

  function onIssueRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, issue: IssueItem) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setSelectedIssueId(issue.id);
  }

  const priorityIssueSource = queueFocus === "all" ? sortedIssues : focusedIssues;
  const priorityRows: PriorityRow[] = [
    ...priorityIssueSource.slice(0, 3).map((issue) => {
      const severity = issue.severity.toLowerCase();
      const priority = severity === "critical" ? "P0" : severity === "high" ? "P1" : "P2";
      return {
        id: issue.id,
        priority,
        type: severity === "critical" || severity === "high" ? "High-risk action" : "Needs proof",
        title: issue.title,
        detail: evidenceSummary(issue),
        impact: issueImpactUsd(issue) != null ? formatIssueImpact(issue) : `${formatCount(issue.occurrence_count)} calls`,
        status: replayLabel(issue.replay_coverage_status),
        tone: severity === "critical" ? "danger" : isReplayGap(issue) ? "warning" : "neutral",
        action: renderIssueAction(issue, { replayLabel: "Verify outcome", viewLabel: "View proof" }),
        issueId: issue.id,
      } satisfies PriorityRow;
    }),
    ...pendingRuns.slice(0, 1).map((run) => ({
      id: run.id,
      priority: "P1",
      type: "Verification running",
      title: run.golden_set_id,
      detail: `${run.replay_mode.replace(/_/g, " ")} verification created ${formatDateTime(run.created_at)}`,
      impact: "Pending proof",
      status: statusLabel(run.status),
      tone: "warning" as const,
      action: (
        <Link href={`/replay/${run.id}`} className="btn btn-soft btn-sm fi-btn-secondary">
          Review proof
        </Link>
      ),
    })),
    ...failedCiRuns.slice(0, 1).map((run) => ({
      id: run.id,
      priority: "P2",
      type: "Release gate",
      title: run.golden_set_id,
      detail: run.git_sha ? `Blocking ${run.git_sha}` : "Verification gate needs review",
      impact: "1 gate",
      status: statusLabel(run.status),
      tone: "danger" as const,
      action: caps.canCi ? (
        <Link href={`/ci-gates/${run.id}`} className="btn btn-soft btn-sm fi-btn-secondary">
          Open gate
        </Link>
      ) : (
        <LockedUpgradeLink label="Upgrade to unlock CI gates" />
      ),
    })),
    ...(captureHasProblem
      ? [
          {
            id: "capture-health",
            priority: "P2",
            type: "Connector health",
            title: captureStatus === "stale" ? "Agent signal stale" : "Gateway backlog",
            detail: captureStatus === "stale" ? "No recent agent action captured." : "Events not yet processed into proof.",
            impact: captureBacklog > 0 ? `${formatCount(captureBacklog)} events` : captureLabel,
            status: captureStatus === "stale" ? "stale" : "backlog",
            tone: "warning" as const,
            action: (
              <Link href="/trace" className="btn btn-soft btn-sm fi-btn-secondary">
                Inspect capture
              </Link>
            ),
          },
        ]
      : []),
  ].slice(0, 5);
  const latestReplayRun = [...data.replayRuns].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
  const latestGoldenSet = [...data.goldenSets].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  )[0];
  const latestCall = data.calls[0] ?? null;
  const recentEvidenceRows = [
    {
      label: "Runtime decision",
      title: latestCall?.agent_name ?? latestCall?.call_id ?? "No agent action yet",
      detail: latestCall ? formatDateTime(latestCall.created_at) : "Waiting for capture",
      status: latestCall?.status ?? "waiting",
    },
    {
      label: "Outcome record",
      title: sortedIssues[0]?.title ?? "No outcome mismatch",
      detail: sortedIssues[0] ? detectorLabel(sortedIssues[0].failure_code) : "No open proof gaps",
      status: sortedIssues[0]?.severity ?? "stable",
    },
    {
      label: "Verification proof",
      title: latestReplayRun?.golden_set_id ?? "No verification run",
      detail: latestReplayRun ? formatDateTime(latestReplayRun.created_at) : planLimitText(data.quota),
      status: latestReplayRun?.status ?? (caps.canReplay ? "pending" : "locked"),
    },
    {
      label: "Evidence hash",
      title: latestGoldenSet?.name ?? "No exportable pack",
      detail: latestGoldenSet ? `${formatCount(latestGoldenSet.trace_count)} records` : "Waiting for verified outcome",
      status: latestGoldenSet?.blocks_ci ? "protected" : latestGoldenSet ? "review" : "waiting",
    },
  ];
  const releaseReadinessRows = [
    { label: "Agent capture", value: captureHasProblem ? captureLabel : "linked", tone: captureHasProblem ? "warning" : "success" },
    { label: "Outcome verifier", value: formatCount(needsTrustedReplayCount), tone: needsTrustedReplayCount > 0 ? "warning" : "success" },
    { label: "Release guard", value: failedCiRuns.length > 0 ? `${formatCount(failedCiRuns.length)} blocking` : "healthy", tone: failedCiRuns.length > 0 ? "danger" : "success" },
    { label: "Audit export", value: protectedGoldenCount > 0 ? "ready" : "needs proof", tone: protectedGoldenCount > 0 ? "success" : "neutral" },
  ];
  const pipelineStages = [
    { label: "Attempt", value: formatCount(capturedCallCount), helper: `${captureLabel}`, tone: captureHasProblem ? "warning" : capturedCallCount > 0 ? "success" : "neutral" },
    { label: "Decision", value: `${formatCount(openIssuesCount)} open`, helper: `${formatCount(needsTrustedReplayCount)} need proof`, tone: openIssuesCount > 0 ? "warning" : "success" },
    { label: "Outcome", value: `${formatCount(replayPassRate)}% verified`, helper: `${formatCount(replayFailCount)} failed checks`, tone: replayFailCount > 0 || needsTrustedReplayCount > 0 ? "warning" : "success" },
    { label: "Evidence", value: `${formatCount(protectedGoldenCount)} ready`, helper: `${formatCount(goldensNeedingReview.length)} need review`, tone: goldensNeedingReview.length > 0 ? "warning" : protectedGoldenCount > 0 ? "success" : "neutral" },
    { label: "Export", value: failedCiRuns.length > 0 ? `${formatCount(failedCiRuns.length)} blocked` : "ready", helper: caps.canCi ? "audit proof active" : "upgrade required", tone: failedCiRuns.length > 0 ? "danger" : caps.canCi ? "success" : "neutral" },
  ];

  return (
    <div className="fi-screen fi-home-v5" aria-busy={loading || refreshing}>
      <section className="fi-hero fi-command-hero" data-tone={heroSignal.tone}>
        <div className="fi-hero-main">
          <h1>Agent safety status</h1>
          <div className="fi-hero-signal" aria-live="polite">
            <span className="fi-hero-eyebrow">{heroSignal.eyebrow}</span>
            <strong>{heroSignal.title}</strong>
          </div>
          <p>{heroSignal.summary}</p>
          {heroSignal.action ? <div className="fi-hero-primary-action">{heroSignal.action}</div> : null}
        </div>
        <div className="fi-hero-actions">
          <div className="fi-home-status-grid" aria-label="Agent safety snapshot">
            {homeStatusTiles.map((tile) => (
              <div className="fi-home-status-tile" data-tone={tile.tone} key={tile.label}>
                <span className="fi-home-status-icon">{tile.icon}</span>
                <div>
                  <span>{tile.label}</span>
                  <strong>{tile.value}</strong>
                  <small>{tile.helper}</small>
                </div>
              </div>
            ))}
          </div>
          <div className="fi-refresh-meta" aria-live="polite">
            <span>
              <Clock3 aria-hidden="true" />
              Updated {lastUpdatedLabel}
            </span>
            <span>
              <span className={`fi-live-dot${refreshing ? " is-refreshing" : ""}`} />
              Auto-refresh 30s
            </span>
          </div>
          <button
            type="button"
            className="btn btn-soft btn-sm fi-btn-secondary"
            onClick={() => void load()}
            disabled={refreshing}
          >
            <RefreshCw aria-hidden="true" className={refreshing ? "fi-spin" : undefined} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
          {hasWorkspaceActivity ? (
            <Link href="/approvals" className="btn btn-soft btn-sm fi-btn-secondary">
              Review decisions
            </Link>
          ) : null}
        </div>
      </section>

      {error ? (
        <section className="fi-notice fi-notice-error" role="alert">
          <p>{error}</p>
          <button type="button" className="btn btn-soft btn-sm fi-btn-secondary" onClick={() => void load()} disabled={refreshing}>
            Retry
          </button>
        </section>
      ) : null}

      {!error && loadErrorKeys.length > 0 ? (
        <section className="fi-notice fi-notice-warning" role="status" aria-live="polite">
          <p>
            Partial refresh: {loadErrorText} failed. Showing latest successful data for the rest.
          </p>
          <button type="button" className="btn btn-soft btn-sm fi-btn-secondary" onClick={() => void load()} disabled={refreshing}>
            Retry failed sources
          </button>
        </section>
      ) : null}

      {actionError ? (
        <section className="fi-notice fi-notice-error" role="alert">
          <p>{actionError}</p>
        </section>
      ) : null}

      {showFirstRunOnboarding ? (
        <FirstRunOnboarding
          projectKeyCount={activeProjectKeyCount}
          capturedCallCount={capturedCallCount}
          captureStatus={captureStatus}
          replayUnlocked={caps.canReplay}
          goldensUnlocked={caps.canGoldens}
          ciUnlocked={caps.canCi}
        />
      ) : (
        <>
      {loading ? (
        <KpiSkeletonRow />
      ) : (
        <section className="fi-kpi-grid fi-command-metrics" aria-label="Home summary">
          <KpiCard
            icon={<ShieldAlert aria-hidden="true" />}
            label="Action signals"
            value={formatCount(failedRunsCount)}
            helper={data.calls.length > 0 ? "Failed or errored traces in the latest sample." : "Highest-risk loaded records."}
            tone="danger"
            active={queueFocus === "critical_high"}
            onClick={() => focusQueue("critical_high")}
          />
          <KpiCard
            icon={<LockKeyhole aria-hidden="true" />}
            label="Needs review"
            value={formatCount(openDecisionCount)}
            helper={`${formatCount(needsTrustedReplayCount)} actions still need outcome proof.`}
            tone="warning"
            active={queueFocus === "all"}
            onClick={() => focusQueue("all")}
          />
          <KpiCard
            icon={<CheckCircle2 aria-hidden="true" />}
            label="Verified outcomes"
            value={replayCompletedCount > 0 || openIssuesCount > 0 ? `${formatCount(replayPassRate)}% verified` : "Replay pending"}
            helper={replayCompletedCount > 0 || openIssuesCount > 0 ? `${formatCount(replayFailCount)} failing or not verified.` : "Run a replay to protect this flow."}
            tone="success"
            active={queueFocus === "replay_gap"}
            onClick={() => focusQueue("replay_gap")}
          />
          <KpiCard
            icon={<Bot aria-hidden="true" />}
            label="Protected agents"
            value={formatCount(protectedAgentCount)}
            helper={protectedAgentCount > 0 ? `${formatCount(capturedCallCount)} captured actions in scope.` : "Connect an agent to start live protection."}
            tone="info"
          />
          <KpiCard
            icon={<FileJson aria-hidden="true" />}
            label="Evidence packs"
            value={formatCount(evidenceReadyCount)}
            helper={latencyAverage == null ? "Capture traces to calculate latency." : `${formatCount(latencyAverage)}ms average latency.`}
            tone="neutral"
            trend={costTrend == null ? null : "vs yesterday"}
          />
        </section>
      )}

      <section className="fi-ops-layout">
        <section className="fi-section fi-priority-section">
          <SectionHeader
            title="Needs your decision"
            description={queueFocusDescription(queueFocus)}
            action={
              <div className="fi-queue-tabs" role="tablist" aria-label="Decision queue focus">
                {queueFocusControls.map((control) => (
                  <button
                    type="button"
                    key={control.id}
                    role="tab"
                    aria-selected={queueFocus === control.id}
                    className={`fi-queue-tab${queueFocus === control.id ? " is-active" : ""}`}
                    onClick={() => focusQueue(control.id)}
                  >
                    {control.label}
                  </button>
                ))}
              </div>
            }
          />

          {loading ? (
            <PriorityTableSkeleton />
          ) : priorityRows.length === 0 ? (
            <EmptyQueue>No high-risk action needs review right now.</EmptyQueue>
          ) : (
            <div className="fi-table-wrap">
              <table className="fi-issues-table">
                <thead>
                  <tr>
                    <th>Urgency</th>
                    <th>Signal</th>
                    <th>Agent / action</th>
                    <th>Risk</th>
                    <th>Outcome state</th>
                    <th>Next step</th>
                  </tr>
                </thead>
                <tbody>
                  {priorityRows.map((row) => (
                    <tr
                      key={row.id}
                      className={row.issueId && selectedIssueId === row.issueId ? "is-selected" : undefined}
                      aria-selected={row.issueId ? selectedIssueId === row.issueId : undefined}
                      tabIndex={row.issueId ? 0 : undefined}
                      onClick={row.issueId ? () => setSelectedIssueId(row.issueId ?? null) : undefined}
                      onKeyDown={
                        row.issueId
                          ? (event) => {
                              const issue = sortedIssues.find((item) => item.id === row.issueId);
                              if (issue) onIssueRowKeyDown(event, issue);
                            }
                          : undefined
                      }
                    >
                      <td>
                        <span className="fi-priority-pill">{row.priority}</span>
                      </td>
                      <td>
                        <span className="fi-row-type">{row.type}</span>
                      </td>
                      <td>
                        <div className="fi-issue-cell">
                          <strong>{row.title}</strong>
                          <span>{row.detail}</span>
                        </div>
                      </td>
                      <td>
                        <strong className="fi-impact-value">{row.impact}</strong>
                      </td>
                      <td>
                        <StatusText value={row.status} tone={row.tone} />
                      </td>
                      <td>
                        <div className="fi-row-actions">{row.action}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="fi-ops-rail" aria-label="Evidence proof rail">
          {loading ? (
            <RailSkeleton />
          ) : (
            <>
              <section className="fi-section fi-recent-evidence fi-evidence-pack-rail" aria-label="Evidence packs">
                <SectionHeader
                  title="Evidence Pack"
                  description="Latest decision, outcome proof, and audit export status."
                  action={
                    <Link href="/evidence" className="btn btn-soft btn-sm fi-btn-secondary">
                      Download JSON
                    </Link>
                  }
                />
                <div className="fi-evidence-list">
                  {recentEvidenceRows.map((row) => (
                    <div className="fi-evidence-row" key={row.label}>
                      <div>
                        <span>{row.label}</span>
                        <strong>{row.title}</strong>
                        <small>{row.detail}</small>
                      </div>
                      <StatusPill value={row.status} />
                    </div>
                  ))}
                </div>
              </section>

              <section className="fi-section fi-release-readiness fi-proof-gap-rail" aria-label="Proof gaps by connector">
                <SectionHeader title="System-of-record proof" description="Signals that decide pass, warn, fail, or not_verified." />
                <div className="fi-readiness-list">
                  {releaseReadinessRows.map((row) => (
                    <div className="fi-readiness-row" data-tone={row.tone} key={row.label}>
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </aside>
      </section>

      {loading ? (
        <PipelineSkeleton />
      ) : (
        <section className="fi-section fi-pipeline-section" aria-label="Outcome verification chain">
          <SectionHeader title="Action accountability loop" description="Attempt, decision, outcome proof, evidence, export." />
          <div className="fi-pipeline">
            {pipelineStages.map((stage, index) => (
              <div className="fi-pipeline-stage" data-tone={stage.tone} key={stage.label}>
                <div className="fi-pipeline-node">
                  {index === 0 ? <ListChecks aria-hidden="true" /> : null}
                  {index === 1 ? <AlertTriangle aria-hidden="true" /> : null}
                  {index === 2 ? <RotateCcw aria-hidden="true" /> : null}
                  {index === 3 ? <ShieldCheck aria-hidden="true" /> : null}
                  {index === 4 ? <GitPullRequest aria-hidden="true" /> : null}
                </div>
                <div>
                  <span>{stage.label}</span>
                  <strong>{stage.value}</strong>
                  <small>{stage.helper}</small>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
        </>
      )}
    </div>
  );
}
