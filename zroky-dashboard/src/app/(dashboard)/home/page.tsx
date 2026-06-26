"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { KeyboardEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileJson,
  GitPullRequest,
  ListChecks,
  LockKeyhole,
  Plug,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";

import {
  FirstRunOnboarding,
  LockedUpgradeLink,
} from "@/components/command-center-primitives";
import { hasPlanEntitlement } from "@/components/feature-gate";
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
type HomeSnapshotFilter = "action_signals" | "needs_decision" | "unverified_outcomes" | "failing_gates" | "evidence_readiness";
type PriorityTone = "danger" | "warning" | "success" | "neutral";
type DecisionKind = "ci_gate" | "issue" | "pending_replay" | "capture" | "evidence";

type DecisionRow = {
  id: string;
  kind: DecisionKind;
  urgency: string;
  signal: string;
  agentAction: string;
  detail: string;
  impact: string;
  proofState: string;
  proofTone: PriorityTone;
  nextStep: string;
  action: ReactNode;
  issueId?: string;
  runId?: string;
};

type ProofCheck = {
  label: string;
  value: string;
  tone: PriorityTone;
};

const refreshIntervalMs = 30_000;
const loadSourceLabels: Record<InboxLoadKey, string> = {
  issues: "Action signals",
  replayRuns: "Verification runs",
  goldenSets: "Evidence contracts",
  billing: "Billing",
  quota: "Replay quota",
  summary: "Usage summary",
  calls: "Agent captures",
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

function formatLastUpdated(value: number | null): string {
  if (!value) return "Not refreshed yet";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
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

function verdictBadgeLabel(tone: PriorityTone): string {
  if (tone === "danger") return "Blocked";
  if (tone === "warning") return "Action required";
  if (tone === "success") return "Protected";
  return "Checking";
}

function filterDecisionRows(rows: DecisionRow[], focus: HomeSnapshotFilter): DecisionRow[] {
  if (focus === "action_signals") {
    return rows.filter((row) => row.kind === "issue" || row.kind === "capture");
  }
  if (focus === "unverified_outcomes") {
    return rows.filter((row) => row.proofTone !== "success" && row.kind !== "ci_gate");
  }
  if (focus === "failing_gates") {
    return rows.filter((row) => row.kind === "ci_gate");
  }
  if (focus === "evidence_readiness") {
    return rows.filter((row) => row.kind === "evidence" || row.proofTone !== "success");
  }
  return rows;
}

function readinessLabel(ready: number, total: number): string {
  return `${formatCount(ready)}/${formatCount(total)} ready`;
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
  const dateRange = useDashboardStore((state) => state.dateRange);
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const summaryWindowDays = useMemo(() => analyticsWindowDays(dateRange), [dateRange]);
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
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [queueFocus, setQueueFocus] = useState<HomeSnapshotFilter>("needs_decision");
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
        settleLoad("summary", getAnalyticsSummary(summaryWindowDays, signal)),
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
  }, [selectedProject, summaryWindowDays]);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);

    const timer = realTimeEnabled
      ? window.setInterval(() => {
          if (document.visibilityState === "visible") {
            void load();
          }
        }, refreshIntervalMs)
      : null;

    function onVisibilityChange() {
      if (realTimeEnabled && document.visibilityState === "visible") {
        void load();
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      ctrl.abort();
      loadInFlightRef.current = false;
      if (timer) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [load, realTimeEnabled]);

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
  const criticalHighCount = data.issues.filter((issue) =>
    ["critical", "high"].includes(issue.severity.toLowerCase()),
  ).length;
  const needsTrustedReplayCount = data.issues.filter((issue) => !hasTrustedGoldenReplay(issue)).length;
  const openIssuesCount = data.issues.length;
  const trustedReplayCount = data.issues.filter(hasTrustedGoldenReplay).length;
  const pendingRuns = data.replayRuns.filter((run) => isPendingRun(run) && !isCiRun(run)).slice(0, 6);
  const failedCiRuns = data.replayRuns.filter(isFailedCiRun).slice(0, 6);
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
  const protectedGoldenCount = data.goldenSets.filter((set) => set.blocks_ci && !set.is_flaky).length;
  const openDecisionCount =
    needsTrustedReplayCount +
    pendingRuns.length +
    failedCiRuns.length +
    (captureHasProblem ? 1 : 0);
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
              <Link href="/policies" className="btn btn-primary btn-sm fi-btn-primary">
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
                <Link href="/agents" className="btn btn-primary btn-sm fi-btn-primary">
                  Open agents
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
  const evidenceChecklistReady = [
    capturedCallCount > 0,
    openIssuesCount > 0,
    trustedReplayCount > 0 || replayPassCount > 0,
    protectedGoldenCount > 0,
    protectedGoldenCount > 0 && failedCiRuns.length === 0,
  ].filter(Boolean).length;
  const evidenceReadinessPercent = Math.round((evidenceChecklistReady / 5) * 100);
  const snapshotFilters = [
    {
      id: "action_signals" as const,
      label: "Action signals",
      value: formatCount(failedRunsCount),
      helper: "Critical drift, failed calls, or stale capture.",
      tone: "danger" as const,
      icon: <ShieldAlert aria-hidden="true" />,
    },
    {
      id: "needs_decision" as const,
      label: "Needs decision",
      value: formatCount(openDecisionCount),
      helper: "Unified queue requiring owner action.",
      tone: "warning" as const,
      icon: <LockKeyhole aria-hidden="true" />,
    },
    {
      id: "unverified_outcomes" as const,
      label: "Unverified outcomes",
      value: formatCount(needsTrustedReplayCount),
      helper: "Actions missing trusted real outcome proof.",
      tone: "warning" as const,
      icon: <CheckCircle2 aria-hidden="true" />,
    },
    {
      id: "failing_gates" as const,
      label: "Failing gates",
      value: formatCount(failedCiRuns.length),
      helper: "Promotion gates currently blocking release.",
      tone: failedCiRuns.length > 0 ? ("danger" as const) : ("success" as const),
      icon: <GitPullRequest aria-hidden="true" />,
    },
    {
      id: "evidence_readiness" as const,
      label: "Evidence readiness",
      value: `${formatCount(evidenceReadinessPercent)}%`,
      helper: readinessLabel(evidenceChecklistReady, 5),
      tone: evidenceReadinessPercent >= 80 ? ("success" as const) : evidenceReadinessPercent >= 40 ? ("warning" as const) : ("neutral" as const),
      icon: <FileJson aria-hidden="true" />,
    },
  ];

  function focusQueue(nextFocus: HomeSnapshotFilter) {
    setQueueFocus(nextFocus);
  }

  async function onReplay(issue: IssueItem) {
    setActionError(null);
    setBusyIssueId(issue.id);
    try {
      await createReplayRunFromIssue(issue.id, {
        replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE,
      });
      router.push("/evidence");
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
        <Link href="/evidence" className="btn btn-primary btn-sm fi-btn-primary">
          <ShieldCheck aria-hidden="true" />
          Open evidence
        </Link>
      );
    }
    return (
      <Link href="/approvals" className="btn btn-primary btn-sm fi-btn-primary">
        <ArrowRight aria-hidden="true" />
        {options?.viewLabel ?? "View proof"}
      </Link>
    );
  }

  function onDecisionRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, row: DecisionRow) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setSelectedDecisionId(row.id);
  }

  const issueRows = sortedIssues.map((issue) => {
    const severity = issue.severity.toLowerCase();
    const urgency = severity === "critical" ? "P0" : severity === "high" ? "P1" : "P2";
    const replayGap = isReplayGap(issue);
    const agentLabel = issue.affected_agent?.trim() || issue.agent_name?.trim() || "Agent unknown";
    return {
      id: `issue:${issue.id}`,
      kind: "issue" as const,
      urgency,
      signal: severity === "critical" || severity === "high" ? "Critical action drift" : replayGap ? "Outcome proof missing" : "Evidence incomplete",
      agentAction: issue.title,
      detail: `${agentLabel}: ${evidenceSummary(issue)}`,
      impact: issueImpactUsd(issue) != null ? formatIssueImpact(issue) : `${formatCount(issue.occurrence_count)} calls`,
      proofState: replayLabel(issue.replay_coverage_status),
      proofTone: hasTrustedGoldenReplay(issue) ? ("success" as const) : severity === "critical" ? ("danger" as const) : replayGap ? ("warning" as const) : ("neutral" as const),
      nextStep: replayGap ? "Verify outcome" : hasTrustedGoldenReplay(issue) ? "Open evidence" : "Review proof",
      action: renderIssueAction(issue, { replayLabel: "Verify outcome", viewLabel: "View proof" }),
      issueId: issue.id,
    };
  });
  const ciRows = failedCiRuns.map((run) => ({
    id: `ci:${run.id}`,
    kind: "ci_gate" as const,
    urgency: "P0",
    signal: "CI gate failed",
    agentAction: run.golden_set_id,
    detail: run.git_sha ? `Blocking ${run.git_sha}` : "Verification gate needs review before promotion.",
    impact: "1 gate",
    proofState: statusLabel(run.status),
    proofTone: "danger" as const,
    nextStep: "Open gate",
    action: caps.canCi ? (
      <Link href="/policies" className="btn btn-soft btn-sm fi-btn-secondary">
        Open gate
      </Link>
    ) : (
      <LockedUpgradeLink label="Upgrade to unlock CI gates" />
    ),
    runId: run.id,
  }));
  const pendingReplayRows = pendingRuns.map((run) => ({
    id: `replay:${run.id}`,
    kind: "pending_replay" as const,
    urgency: "P1",
    signal: "Replay running",
    agentAction: run.golden_set_id,
    detail: `${run.replay_mode.replace(/_/g, " ")} verification created ${formatDateTime(run.created_at)}`,
    impact: "Pending proof",
    proofState: statusLabel(run.status),
    proofTone: "warning" as const,
    nextStep: "Review proof",
    action: (
      <Link href="/evidence" className="btn btn-soft btn-sm fi-btn-secondary">
        Review proof
      </Link>
    ),
    runId: run.id,
  }));
  const captureRows: DecisionRow[] = captureHasProblem
    ? [
        {
          id: "capture:health",
          kind: "capture",
          urgency: "P2",
          signal: captureStatus === "stale" ? "Capture stale" : "Connector backlog",
          agentAction: captureStatus === "stale" ? "Agent signal stale" : "Capture pipeline",
          detail: captureStatus === "stale" ? "No recent agent action captured for this project." : "Events are waiting to become outcome proof.",
          impact: captureBacklog > 0 ? `${formatCount(captureBacklog)} events` : captureLabel,
          proofState: captureStatus === "stale" ? "Stale" : "Backlog",
          proofTone: "warning",
          nextStep: "Open agents",
          action: (
            <Link href="/agents" className="btn btn-soft btn-sm fi-btn-secondary">
              Open agents
            </Link>
          ),
        },
      ]
    : [];
  const evidenceRows: DecisionRow[] =
    hasWorkspaceActivity && protectedGoldenCount === 0
      ? [
          {
            id: "evidence:incomplete",
            kind: "evidence",
            urgency: "P3",
            signal: "Evidence incomplete",
            agentAction: "Evidence export",
            detail: "No exportable proof pack is ready until a verified outcome and audit trail are linked.",
            impact: `${formatCount(evidenceReadinessPercent)}% ready`,
            proofState: "Needs proof",
            proofTone: "neutral",
            nextStep: "Open evidence",
            action: (
              <Link href="/evidence" className="btn btn-soft btn-sm fi-btn-secondary">
                Open evidence
              </Link>
            ),
          },
        ]
      : [];
  const decisionRows: DecisionRow[] = [...ciRows, ...issueRows, ...pendingReplayRows, ...captureRows, ...evidenceRows].slice(0, 12);
  const filteredDecisionRows = filterDecisionRows(decisionRows, queueFocus);

  useEffect(() => {
    if (loading) return;
    const selectedStillVisible = filteredDecisionRows.some((row) => row.id === selectedDecisionId);
    if (!selectedDecisionId || !selectedStillVisible) {
      setSelectedDecisionId(filteredDecisionRows[0]?.id ?? decisionRows[0]?.id ?? null);
    }
  }, [decisionRows, filteredDecisionRows, loading, selectedDecisionId]);
  const latestReplayRun = [...data.replayRuns].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
  const latestCall = data.calls[0] ?? null;
  const selectedDecision = decisionRows.find((row) => row.id === selectedDecisionId) ?? decisionRows[0] ?? null;
  const selectedIssue = selectedDecision?.issueId ? sortedIssues.find((issue) => issue.id === selectedDecision.issueId) ?? null : null;
  const selectedRun = selectedDecision?.runId ? data.replayRuns.find((run) => run.id === selectedDecision.runId) ?? null : null;
  const selectedEvidenceTrace = selectedIssue?.evidence_traces[0] ?? null;
  const selectedProofTitle = selectedDecision?.agentAction ?? "No selected decision";
  const selectedProofSummary = selectedIssue
    ? evidenceSummary(selectedIssue)
    : selectedRun
      ? `${selectedRun.replay_mode.replace(/_/g, " ")} run ${statusLabel(selectedRun.status).toLowerCase()} for ${selectedRun.golden_set_id}.`
      : selectedDecision?.kind === "capture"
        ? selectedDecision.detail
        : selectedDecision?.kind === "evidence"
          ? selectedDecision.detail
          : "Select a decision row to inspect evidence, outcome proof, and the recommended next action.";
  const selectedProofChecks: ProofCheck[] = selectedIssue
    ? [
        {
          label: "Affected agent",
          value: selectedIssue.affected_agent?.trim() || selectedIssue.agent_name?.trim() || "Unknown agent",
          tone: "neutral",
        },
        {
          label: "Sample trace",
          value: selectedEvidenceTrace?.trace_id ?? selectedEvidenceTrace?.call_id ?? selectedIssue.sample_call_id ?? "Missing",
          tone: selectedEvidenceTrace || selectedIssue.sample_call_id ? "success" : "warning",
        },
        {
          label: "Replay status",
          value: replayLabel(selectedIssue.replay_coverage_status),
          tone: hasTrustedGoldenReplay(selectedIssue) ? "success" : "warning",
        },
        {
          label: "System-of-record proof",
          value: hasTrustedGoldenReplay(selectedIssue) ? "Matched outcome" : "Outcome proof missing",
          tone: hasTrustedGoldenReplay(selectedIssue) ? "success" : "warning",
        },
        {
          label: "Evidence readiness",
          value: hasTrustedGoldenReplay(selectedIssue) && protectedGoldenCount > 0 ? "Export ready" : "Incomplete",
          tone: hasTrustedGoldenReplay(selectedIssue) && protectedGoldenCount > 0 ? "success" : "neutral",
        },
      ]
    : [
        {
          label: "Affected surface",
          value: selectedDecision?.agentAction ?? "Waiting for activity",
          tone: selectedDecision ? "neutral" : "warning",
        },
        {
          label: "Replay status",
          value: selectedRun ? statusLabel(selectedRun.status) : latestReplayRun ? statusLabel(latestReplayRun.status) : "No run",
          tone: selectedRun ? selectedDecision?.proofTone ?? "neutral" : latestReplayRun ? "neutral" : "warning",
        },
        {
          label: "System-of-record proof",
          value: captureHasProblem ? captureLabel : captureStatus === "connected" ? "Connected" : "Waiting",
          tone: captureHasProblem ? "warning" : captureStatus === "connected" ? "success" : "neutral",
        },
        {
          label: "Evidence readiness",
          value: `${formatCount(evidenceReadinessPercent)}%`,
          tone: evidenceReadinessPercent >= 80 ? "success" : evidenceReadinessPercent >= 40 ? "warning" : "neutral",
        },
        {
          label: "Recommended action",
          value: selectedDecision?.nextStep ?? "Connect capture",
          tone: selectedDecision?.proofTone ?? "neutral",
        },
      ];
  const systemHealthRows: ProofCheck[] = [
    {
      label: "Connector state",
      value: captureStatus === "connected" ? "Connected" : captureStatus === "stale" ? "Stale" : captureStatus === "no_data" ? "No data" : "Checking",
      tone: captureHasProblem ? "warning" : captureStatus === "connected" ? "success" : "neutral",
    },
    {
      label: "Last verified outcome",
      value: latestCall ? formatDateTime(latestCall.created_at) : "Waiting",
      tone: latestCall ? "success" : "neutral",
    },
    {
      label: "Capture backlog",
      value: formatCount(captureBacklog),
      tone: captureBacklog > 0 ? "warning" : "success",
    },
    {
      label: "Failed preflight",
      value: formatCount(data.captureHealth?.projection_failures_24h ?? data.captureHealth?.gateway_unhealthy_count ?? 0),
      tone: (data.captureHealth?.projection_failures_24h ?? data.captureHealth?.gateway_unhealthy_count ?? 0) > 0 ? "warning" : "success",
    },
  ];
  const pipelineStages = [
    {
      label: "Agents",
      value: formatCount(capturedCallCount),
      helper: captureLabel,
      tone: captureHasProblem ? "warning" : capturedCallCount > 0 ? "success" : "neutral",
      href: "/agents",
      Icon: ListChecks,
    },
    {
      label: "Policies",
      value: openIssuesCount > 0 ? `${formatCount(criticalHighCount)} critical/high` : "clear",
      helper: `${formatCount(openIssuesCount)} action signals`,
      tone: openIssuesCount > 0 ? "warning" : "success",
      href: "/policies",
      Icon: ShieldAlert,
    },
    {
      label: "Approvals",
      value: needsTrustedReplayCount > 0 ? `${formatCount(needsTrustedReplayCount)} review` : "clear",
      helper: "held actions and owner decisions",
      tone: needsTrustedReplayCount > 0 ? "warning" : "success",
      href: "/approvals",
      Icon: LockKeyhole,
    },
    {
      label: "Outcomes",
      value: `${formatCount(replayPassRate)}%`,
      helper: `${formatCount(needsTrustedReplayCount)} missing proof`,
      tone: replayFailCount > 0 || needsTrustedReplayCount > 0 ? "warning" : "success",
      href: "/outcomes",
      Icon: ShieldCheck,
    },
    {
      label: "Evidence",
      value: `${formatCount(evidenceReadinessPercent)}%`,
      helper: protectedGoldenCount > 0 ? "Evidence Pack ready" : "proof incomplete",
      tone: protectedGoldenCount > 0 ? "success" : "neutral",
      href: "/evidence",
      Icon: FileJson,
    },
    {
      label: "Connectors",
      value: captureStatus === "connected" ? "ready" : "review",
      helper: "system-of-record health",
      tone: captureHasProblem ? "warning" : captureStatus === "connected" ? "success" : "neutral",
      href: "/integrations",
      Icon: Plug,
    },
  ];

  return (
    <div className="fi-screen fi-home-v5 fi-home-option-a" aria-busy={loading || refreshing}>
      <section className="fi-a-verdict" data-tone={heroSignal.tone} aria-label="Current Home verdict">
        <div className="fi-a-verdict-copy">
          <span className="fi-a-kicker">{heroSignal.eyebrow}</span>
          <div className="fi-a-verdict-line" aria-live="polite">
            <h1>Agent action accountability</h1>
            <span className="fi-a-status-badge" data-tone={heroSignal.tone}>
              {verdictBadgeLabel(heroSignal.tone)}
            </span>
          </div>
          <strong>{heroSignal.title}</strong>
          <p>{heroSignal.summary}</p>
        </div>
        <div className="fi-a-verdict-side">
          <div className="fi-a-refresh-meta" aria-live="polite">
            <span>
              <Clock3 aria-hidden="true" />
              Updated {lastUpdatedLabel}
            </span>
            <span>
              <span className={`fi-a-live-dot${refreshing ? " is-refreshing" : ""}`} />
              {realTimeEnabled ? "Live refresh 30s" : "Live paused"}
            </span>
          </div>
          <div className="fi-a-verdict-actions">
            {heroSignal.action}
            {hasWorkspaceActivity && heroSignal.title !== "Evidence ready" && heroSignal.title !== "Safety loop ready" ? (
              <Link href="/evidence" className="btn btn-soft btn-sm fi-btn-secondary">
                Open evidence
              </Link>
            ) : null}
            <button
              type="button"
              className="btn btn-soft btn-sm fi-btn-secondary"
              onClick={() => void load()}
              disabled={refreshing}
            >
              <RefreshCw aria-hidden="true" className={refreshing ? "fi-spin" : undefined} />
              {refreshing ? "Refreshing" : "Refresh"}
            </button>
          </div>
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
        <div className="fi-a-first-run">
          <FirstRunOnboarding
            projectKeyCount={activeProjectKeyCount}
            capturedCallCount={capturedCallCount}
            captureStatus={captureStatus}
            replayUnlocked={caps.canReplay}
            goldensUnlocked={caps.canGoldens}
            ciUnlocked={caps.canCi}
          />
        </div>
      ) : (
        <>
          {loading ? (
            <section className="fi-a-snapshot-grid" aria-label="Loading Home summary" aria-busy="true">
              {Array.from({ length: 5 }, (_, index) => (
                <div className="fi-a-snapshot-card is-loading" key={index}>
                  <span />
                  <strong />
                  <small />
                </div>
              ))}
            </section>
          ) : (
            <section className="fi-a-snapshot-grid" aria-label="Home snapshot filters">
              {snapshotFilters.map((filter) => (
                <button
                  type="button"
                  className={`fi-a-snapshot-card${queueFocus === filter.id ? " is-active" : ""}`}
                  data-tone={filter.tone}
                  aria-pressed={queueFocus === filter.id}
                  onClick={() => focusQueue(filter.id)}
                  key={filter.id}
                >
                  <span className="fi-a-snapshot-icon">{filter.icon}</span>
                  <span className="fi-a-snapshot-label">{filter.label}</span>
                  <strong>{filter.value}</strong>
                  <small>{filter.helper}</small>
                </button>
              ))}
            </section>
          )}

          <section className="fi-a-workspace">
            <div className="fi-a-main-column">
              <section className="fi-a-queue-panel" aria-label="Decision queue">
                <div className="fi-a-panel-head">
                  <div>
                    <span className="fi-a-kicker">Decision queue</span>
                    <h2>Highest-risk agent actions</h2>
                  </div>
                  <p>CI blocks, critical drift, missing outcome proof, stale capture, and incomplete evidence in one queue.</p>
                </div>

                {loading ? (
                  <PriorityTableSkeleton />
                ) : filteredDecisionRows.length === 0 ? (
                  <div className="fi-a-empty">
                    <strong>No decision rows for this filter.</strong>
                    <span>Switch filters or wait for the next captured production action.</span>
                  </div>
                ) : (
                  <div className="fi-a-table-wrap">
                    <table className="fi-a-decision-table">
                      <thead>
                        <tr>
                          <th>Urgency</th>
                          <th>Signal</th>
                          <th>Agent / action</th>
                          <th>Impact</th>
                          <th>Proof state</th>
                          <th>Next step</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredDecisionRows.map((row) => (
                          <tr
                            key={row.id}
                            className={selectedDecisionId === row.id ? "is-selected" : undefined}
                            aria-selected={selectedDecisionId === row.id}
                            tabIndex={0}
                            onClick={() => setSelectedDecisionId(row.id)}
                            onKeyDown={(event) => onDecisionRowKeyDown(event, row)}
                          >
                            <td>
                              <span className="fi-a-priority-pill">{row.urgency}</span>
                            </td>
                            <td>
                              <span className="fi-a-row-signal">{row.signal}</span>
                            </td>
                            <td>
                              <div className="fi-a-agent-cell">
                                <strong>{row.agentAction}</strong>
                                <span>{row.detail}</span>
                              </div>
                            </td>
                            <td>
                              <strong className="fi-a-impact-value">{row.impact}</strong>
                            </td>
                            <td>
                              <StatusText value={row.proofState} tone={row.proofTone} />
                            </td>
                            <td>
                              <div className="fi-a-row-actions">{row.action}</div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {loading ? (
                <PipelineSkeleton />
              ) : (
                <section className="fi-a-loop-panel" aria-label="Action accountability loop">
                  <div className="fi-a-panel-head">
                    <div>
                      <span className="fi-a-kicker">Accountability loop</span>
                      <h2>Control to proof</h2>
                    </div>
                    <p>Each step opens the primary surface that controls, verifies, or proves the action.</p>
                  </div>
                  <div className="fi-a-loop">
                    {pipelineStages.map((stage) => {
                      const StageIcon = stage.Icon;
                      return (
                        <Link className="fi-a-loop-step" data-tone={stage.tone} href={stage.href} key={stage.label}>
                          <span className="fi-a-loop-node">
                            <StageIcon aria-hidden="true" />
                          </span>
                          <span>{stage.label}</span>
                          <strong>{stage.value}</strong>
                          <small>{stage.helper}</small>
                        </Link>
                      );
                    })}
                  </div>
                </section>
              )}
            </div>

            <aside className="fi-a-proof-panel" aria-label="Selected proof">
              {loading ? (
                <RailSkeleton />
              ) : (
                <>
                  <div className="fi-a-panel-head">
                    <div>
                      <span className="fi-a-kicker">Selected proof</span>
                      <h2>{selectedProofTitle}</h2>
                    </div>
                    {selectedDecision ? (
                      <span className="fi-a-status-badge" data-tone={selectedDecision.proofTone}>
                        {selectedDecision.proofState}
                      </span>
                    ) : null}
                  </div>
                  <p className="fi-a-proof-summary">{selectedProofSummary}</p>

                  <div className="fi-a-proof-list" aria-label="Selected proof details">
                    {selectedProofChecks.map((check) => (
                      <div className="fi-a-proof-row" data-tone={check.tone} key={check.label}>
                        <span>{check.label}</span>
                        <strong>{check.value}</strong>
                      </div>
                    ))}
                  </div>

                  {selectedDecision ? <div className="fi-a-proof-action">{selectedDecision.action}</div> : null}

                  <section className="fi-a-system-health" aria-label="System-of-record health">
                    <div className="fi-a-mini-head">
                      <Plug aria-hidden="true" />
                      <h3>System-of-record health</h3>
                    </div>
                    <div className="fi-a-proof-list">
                      {systemHealthRows.map((row) => (
                        <div className="fi-a-proof-row" data-tone={row.tone} key={row.label}>
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
        </>
      )}
    </div>
  );
}
