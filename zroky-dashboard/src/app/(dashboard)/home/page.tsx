"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { KeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  DollarSign,
  GitPullRequest,
  ListChecks,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";

import {
  DecisionChip,
  DetailMetric,
  EmptyQueue,
  FirstRunOnboarding,
  KpiCard,
  LockedUpgradeLink,
  ProofStep,
  QueueList,
  ReadinessStep,
  SectionHeader,
  type ReadinessState,
} from "@/components/command-center-primitives";
import { hasPlanEntitlement } from "@/components/feature-gate";
import { StatusPill } from "@/components/status-pill";
import {
  ApiError,
  createReplayRunFromIssue,
  getAnalyticsSummary,
  getBillingMe,
  getReplayQuota,
  listGoldenSets,
  listIssues,
  listReplayRuns,
  resolveIssue,
  type GoldenSetView,
  type ReplayQuotaResponse,
  type ReplayRunItem,
} from "@/lib/api";
import { detectorLabel, severityBadgeColor } from "@/lib/detector-meta";
import { formatCount, formatDateTime, formatUsd } from "@/lib/format";
import { replayLabel, severityRank } from "@/lib/issue-format";
import { DEFAULT_VERIFICATION_REPLAY_MODE } from "@/lib/replay-mode";
import type { AnalyticsSummaryResponse, BillingMeResponse, IssueItem } from "@/lib/types";

type InboxData = {
  issues: IssueItem[];
  replayRuns: ReplayRunItem[];
  goldenSets: GoldenSetView[];
  billing: BillingMeResponse | null;
  quota: ReplayQuotaResponse | null;
  summary: AnalyticsSummaryResponse | null;
};

type IssueAction = "view" | "replay" | "open_goldens" | "upgrade";
type InboxLoadKey = keyof InboxData;
type InboxLoadErrors = Partial<Record<InboxLoadKey, string>>;
type InboxQueueFocus = "all" | "critical_high" | "replay_gap" | "impact" | "verified";

const refreshIntervalMs = 30_000;
const loadSourceLabels: Record<InboxLoadKey, string> = {
  issues: "Issues",
  replayRuns: "Replay runs",
  goldenSets: "Goldens",
  billing: "Billing",
  quota: "Replay quota",
  summary: "Analytics",
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
  return impactUsd == null ? "\u2014" : formatUsd(impactUsd);
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

function goldenReviewReason(set: GoldenSetView): string {
  if (set.trace_count === 0) return "No traces yet";
  if (set.is_flaky) return "Marked flaky";
  if (!set.blocks_ci) return "Not blocking CI";
  return "Needs review";
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

function issueAgent(issue: IssueItem): string {
  return issue.affected_agent ?? issue.agent_name ?? "Agent not captured";
}

function issueEnvironment(): string {
  const envLabel = process.env.NEXT_PUBLIC_DASHBOARD_ENV ?? "production";
  return envLabel.charAt(0).toUpperCase() + envLabel.slice(1);
}

function issueNumber(issue: IssueItem): string {
  const parts = issue.id.split(/[_-]/);
  return parts[parts.length - 1] || issue.id;
}

function evidenceSummary(issue: IssueItem): string {
  return (
    issue.evidence_traces.find((trace) => trace.evidence_summary)?.evidence_summary ??
    issue.root_cause ??
    issue.user_impact ??
    "No evidence summary captured yet."
  );
}

function nextActionTitle(action: IssueAction): string {
  if (action === "replay") return "Run trusted replay";
  if (action === "open_goldens") return "Open Goldens";
  if (action === "upgrade") return "Upgrade to unlock action";
  return "View issue";
}

function nextActionOutcome(action: IssueAction): string {
  if (action === "replay") {
    return "Next: replay the exact failed scenario, compare the candidate fix, then make it eligible for a Golden.";
  }
  if (action === "open_goldens") {
    return "Next: choose a Golden set, add the verified behavior, then use it as release protection.";
  }
  if (action === "upgrade") {
    return "Next: unlock replay and Golden actions before this issue can protect releases.";
  }
  return "Next: inspect the full issue, evidence, root cause, and available remediation path.";
}

function hasEvidence(issue: IssueItem): boolean {
  return issue.evidence_traces.length > 0 || Boolean(issue.sample_call_id);
}

function hasRootCause(issue: IssueItem): boolean {
  return Boolean(issue.root_cause?.trim()) || Boolean(issue.evidence_traces.find((trace) => trace.evidence_summary));
}

function goldenReady(issue: IssueItem): boolean {
  return hasTrustedGoldenReplay(issue) && Boolean(issue.sample_call_id);
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
  if (focus === "critical_high") return "Showing critical and high severity issues.";
  if (focus === "replay_gap") return "Showing issues that cannot become Goldens or block CI yet.";
  if (focus === "impact") return "Showing issues with cost impact, sorted by spend exposure.";
  if (focus === "verified") return "Showing issues with verified fixes ready for Golden coverage.";
  return "Sorted by severity, impact, and replay trust gaps.";
}

function formatLastUpdated(value: number | null): string {
  if (!value) return "Not refreshed yet";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function readinessState(count: number, total: number, inverted = false): ReadinessState {
  if (total === 0) return "neutral";
  if (inverted) return count === 0 ? "good" : "blocked";
  if (count === total) return "good";
  if (count > 0) return "warn";
  return "blocked";
}

function severityBadge(issue: IssueItem) {
  return (
    <span className={`alert-cat-badge badge-${severityBadgeColor(issue.severity)} fi-severity-badge`}>
      <AlertTriangle aria-hidden="true" />
      {issue.severity}
    </span>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [data, setData] = useState<InboxData>({
    issues: [],
    replayRuns: [],
    goldenSets: [],
    billing: null,
    quota: null,
    summary: null,
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
        }
      }

      setData((prev) => ({ ...prev, ...updates }));
      setLoadErrors(nextErrors);
      if (successCount > 0) {
        setLastUpdatedAt(Date.now());
      } else {
        setError("Command Center could not refresh. Showing the last loaded state.");
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
  }, []);

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
  const selectedIssue = useMemo(
    () => focusedIssues.find((issue) => issue.id === selectedIssueId) ?? focusedIssues[0] ?? sortedIssues[0] ?? null,
    [focusedIssues, selectedIssueId, sortedIssues],
  );
  const nextBestIssue = useMemo(() => {
    return sortedIssues.find((issue) => chooseIssueAction(issue, caps) !== "view") ?? sortedIssues[0] ?? null;
  }, [caps, sortedIssues]);

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
  const diagnosedCount = data.issues.filter(hasRootCause).length;
  const evidenceCount = data.issues.filter(hasEvidence).length;
  const trustedReplayCount = data.issues.filter(hasTrustedGoldenReplay).length;
  const goldenReadyCount = data.issues.filter(goldenReady).length;
  const loadedIssueImpactUsd = data.issues.reduce((sum, issue) => sum + (issueImpactUsd(issue) ?? 0), 0);
  const verifiedFixesCount = data.issues.filter(hasTrustedGoldenReplay).length;
  const pendingRuns = data.replayRuns.filter((run) => isPendingRun(run) && !isCiRun(run)).slice(0, 6);
  const failedCiRuns = data.replayRuns.filter(isFailedCiRun).slice(0, 6);
  const goldensNeedingReview = data.goldenSets.filter(needsGoldenReview).slice(0, 6);
  const planLabel = data.billing?.plan_code ? data.billing.plan_code.toUpperCase() : "PLAN";
  const hasLoadedIssues = sortedIssues.length > 0;
  const headerSubtitle = hasLoadedIssues
    ? `${formatCount(needsTrustedReplayCount)} issues need trusted replay before they can become Goldens or block CI.`
    : "Start by capturing one agent call. Zroky turns failed runs into issues, stub replay, verified replay, Goldens, and CI gates.";
  const loadErrorKeys = Object.keys(loadErrors) as InboxLoadKey[];
  const loadErrorText = loadErrorKeys.map((key) => loadSourceLabels[key]).join(", ");
  const issuesLoadFailed = loadErrorKeys.includes("issues");
  const showFirstRunOnboarding = !loading && !error && !issuesLoadFailed && !hasLoadedIssues;
  const lastUpdatedLabel = formatLastUpdated(lastUpdatedAt);

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

  async function onResolve(issue: IssueItem) {
    setActionError(null);
    setBusyIssueId(issue.id);
    try {
      const updated = await resolveIssue(issue.id, { resolution_source: "manual" });
      setData((prev) => ({
        ...prev,
        issues: prev.issues.filter((item) => item.id !== updated.id),
      }));
      setLastUpdatedAt(Date.now());
    } catch (resolveError) {
      setActionError(resolveError instanceof Error ? resolveError.message : "Failed to resolve issue.");
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
          {busyIssueId === issue.id ? "Creating..." : options?.replayLabel ?? "Replay"}
        </button>
      );
    }
    if (action === "open_goldens") {
      return (
        <Link href="/goldens" className="btn btn-primary btn-sm fi-btn-primary">
          <ShieldCheck aria-hidden="true" />
          Open Goldens
        </Link>
      );
    }
    return (
      <Link href={`/issues/${issue.id}`} className="btn btn-primary btn-sm fi-btn-primary">
        <ArrowRight aria-hidden="true" />
        {options?.viewLabel ?? "View Issue"}
      </Link>
    );
  }

  function onIssueRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, issue: IssueItem) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setSelectedIssueId(issue.id);
  }

  const nextAction = nextBestIssue ? chooseIssueAction(nextBestIssue, caps) : "view";
  const selectedEvidence = selectedIssue?.evidence_traces ?? [];
  const selectedPrimaryEvidence = selectedEvidence[0] ?? null;

  return (
    <div className="fi-screen">
      <section className="fi-hero">
        <div className="fi-hero-main">
          <div className="fi-eyebrow">
            <AlertTriangle aria-hidden="true" />
            Production failure queue
          </div>
          <h1>Command Center</h1>
          <p>{loading ? "Loading trusted replay gaps for open production issues." : headerSubtitle}</p>
        </div>
        <div className="fi-hero-actions">
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
          <Link href="/issues" className="btn btn-soft btn-sm fi-btn-secondary">
            View all issues
          </Link>
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
        <FirstRunOnboarding />
      ) : (
        <>
      <section className="fi-command-overview" aria-label="Failure command overview">
        <section className="fi-next-card" aria-label="Next best action">
          <div className="fi-next-content">
            <span className="fi-section-kicker">Next best action</span>
            {nextBestIssue ? (
              <>
                <h2>
                  {nextActionTitle(nextAction)} for {nextBestIssue.title}
                </h2>
                <div className="fi-next-reasons" aria-label="Next action decision reasons">
                  <DecisionChip label="Severity" value={nextBestIssue.severity} />
                  <DecisionChip label="Impact" value={formatIssueImpact(nextBestIssue)} />
                  <DecisionChip label="Affected calls" value={formatCount(nextBestIssue.occurrence_count)} />
                  <DecisionChip label="Replay proof" value={replayLabel(nextBestIssue.replay_coverage_status)} />
                </div>
                <p className="fi-next-outcome">{nextActionOutcome(nextAction)}</p>
              </>
            ) : (
              <>
                <h2>No open issue needs action.</h2>
                <p className="fi-next-outcome">
                  Open production issues will appear here when they need replay proof, Golden coverage, or CI protection.
                </p>
              </>
            )}
          </div>
          {nextBestIssue ? (
            <div className="fi-next-action">
              {renderIssueAction(nextBestIssue, { replayLabel: "Run trusted replay" })}
            </div>
          ) : null}
        </section>

        <section className="fi-readiness-rail" aria-label="Failure readiness pipeline">
          <ReadinessStep
            icon={<AlertTriangle aria-hidden="true" />}
            label="Captured failures"
            value={loading ? "-" : formatCount(openIssuesCount)}
            helper={loading ? "Checking capture evidence." : `${formatCount(evidenceCount)} with sample call or trace evidence.`}
            state={readinessState(openIssuesCount, Math.max(openIssuesCount, 1), true)}
            href="/issues"
          />
          <ReadinessStep
            icon={<ListChecks aria-hidden="true" />}
            label="Diagnosed"
            value={loading ? "-" : `${formatCount(diagnosedCount)} / ${formatCount(openIssuesCount)}`}
            helper="Root cause or evidence summary is attached."
            state={readinessState(diagnosedCount, openIssuesCount)}
            href="/issues"
          />
          <ReadinessStep
            icon={<RotateCcw aria-hidden="true" />}
            label="Replay proof"
            value={loading ? "-" : `${formatCount(trustedReplayCount)} / ${formatCount(openIssuesCount)}`}
            helper="Verified fixes can move toward Goldens."
            state={readinessState(trustedReplayCount, openIssuesCount)}
            href="/replay"
          />
          <ReadinessStep
            icon={<ShieldCheck aria-hidden="true" />}
            label="Golden ready"
            value={loading ? "-" : formatCount(goldenReadyCount)}
            helper="Verified traces ready for regression coverage."
            state={readinessState(goldenReadyCount, openIssuesCount)}
            href="/goldens"
          />
          <ReadinessStep
            icon={<GitPullRequest aria-hidden="true" />}
            label="CI risk"
            value={loading ? "-" : formatCount(failedCiRuns.length)}
            helper="Failed or not_verified gate runs need review."
            state={readinessState(failedCiRuns.length, Math.max(failedCiRuns.length, 1), true)}
            href="/ci-gates"
          />
        </section>
      </section>

      <section className="fi-kpi-grid" aria-label="Command Center summary">
        <KpiCard
          icon={<AlertTriangle aria-hidden="true" />}
          label="Critical & high"
          value={loading ? "-" : formatCount(criticalHighCount)}
          helper="Highest-risk loaded open issues."
          active={queueFocus === "critical_high"}
          onClick={() => focusQueue("critical_high")}
        />
        <KpiCard
          icon={<RotateCcw aria-hidden="true" />}
          label="Needs trusted replay"
          value={loading ? "-" : formatCount(needsTrustedReplayCount)}
          helper="Cannot become Goldens or block CI yet."
          active={queueFocus === "replay_gap"}
          onClick={() => focusQueue("replay_gap")}
        />
        <KpiCard
          icon={<DollarSign aria-hidden="true" />}
          label="Loaded issue impact"
          value={loading ? "-" : formatUsd(loadedIssueImpactUsd)}
          helper="Cost signal from loaded open issues."
          active={queueFocus === "impact"}
          onClick={() => focusQueue("impact")}
        />
        <KpiCard
          icon={<ShieldCheck aria-hidden="true" />}
          label="Verified fixes"
          value={loading ? "-" : formatCount(verifiedFixesCount)}
          helper="Eligible for Golden creation when a sample call exists."
          active={queueFocus === "verified"}
          onClick={() => focusQueue("verified")}
        />
      </section>

      <section className="fi-command-grid">
        <section className="fi-section fi-priority-section">
          <SectionHeader
            title="Failure queue"
            description={queueFocusDescription(queueFocus)}
            action={
              queueFocus === "all" ? undefined : (
                <button type="button" className="btn btn-soft btn-sm fi-btn-secondary" onClick={() => focusQueue("all")}>
                  Clear focus
                </button>
              )
            }
          />

          {loading ? (
            <div className="fi-loading" aria-label="Loading Command Center" />
          ) : focusedIssues.length === 0 ? (
            <EmptyQueue>No open failures loaded.</EmptyQueue>
          ) : (
            <div className="fi-table-wrap">
              <table className="fi-issues-table">
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Impact</th>
                    <th>Replay proof</th>
                    <th>Last seen</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {focusedIssues.map((issue) => (
                    <tr
                      key={issue.id}
                      className={selectedIssue?.id === issue.id ? "is-selected" : undefined}
                      aria-selected={selectedIssue?.id === issue.id}
                      tabIndex={0}
                      onClick={() => setSelectedIssueId(issue.id)}
                      onKeyDown={(event) => onIssueRowKeyDown(event, issue)}
                    >
                      <td>
                        <div className="fi-issue-cell">
                          {severityBadge(issue)}
                          <button type="button" className="fi-issue-title-button" onClick={() => setSelectedIssueId(issue.id)}>
                            {issue.title}
                          </button>
                          <span>
                            {detectorLabel(issue.failure_code)} - {issueAgent(issue)} - {formatCount(issue.occurrence_count)} affected calls
                          </span>
                        </div>
                      </td>
                      <td>
                        <strong className="fi-impact-value">{formatIssueImpact(issue)}</strong>
                      </td>
                      <td>
                        <span className="fi-replay-state">{replayLabel(issue.replay_coverage_status)}</span>
                      </td>
                      <td>{formatDateTime(issue.last_seen_at)}</td>
                      <td>
                        <div className="fi-row-actions">{renderIssueAction(issue)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="fi-section fi-detail-panel" aria-label="Selected issue detail">
          {selectedIssue ? (
            <>
              <div className="fi-detail-head">
                <span className="fi-section-kicker">Issue #{issueNumber(selectedIssue)}</span>
                <h2>{selectedIssue.title}</h2>
                {severityBadge(selectedIssue)}
              </div>

              <div className="fi-detail-grid">
                <DetailMetric label="Detected" value={formatDateTime(selectedIssue.last_seen_at)} />
                <DetailMetric label="First seen" value={formatDateTime(selectedIssue.first_seen_at)} />
                <DetailMetric label="Occurrences" value={formatCount(selectedIssue.occurrence_count)} />
                <DetailMetric label="Affected agent" value={issueAgent(selectedIssue)} />
                <DetailMetric label="Environment" value={issueEnvironment()} />
                <DetailMetric label="Replay proof" value={replayLabel(selectedIssue.replay_coverage_status)} />
              </div>

              <div className="fi-detail-block">
                <span>Root cause</span>
                <p>{selectedIssue.root_cause || evidenceSummary(selectedIssue)}</p>
              </div>

              <div className="fi-detail-block">
                <span>Cost impact</span>
                <p>
                  {formatIssueImpact(selectedIssue)} from {formatCount(selectedIssue.occurrence_count)} affected calls
                </p>
              </div>

              <div className="fi-detail-block">
                <span>Example trace</span>
                {selectedPrimaryEvidence ? (
                  <p>
                    {selectedPrimaryEvidence.evidence_summary ??
                      `${selectedPrimaryEvidence.workflow_name ?? "Workflow not captured"} on ${
                        selectedPrimaryEvidence.provider ?? "unknown provider"
                      }/${selectedPrimaryEvidence.model ?? "unknown model"}`}
                  </p>
                ) : (
                  <p>No trace evidence attached to this issue yet.</p>
                )}
              </div>

              <div className="fi-proof-ladder" aria-label="Selected issue proof ladder">
                <ProofStep
                  icon={<ListChecks aria-hidden="true" />}
                  label="Evidence captured"
                  helper={hasEvidence(selectedIssue) ? "Sample call or trace evidence is available." : "Capture data is missing."}
                  state={hasEvidence(selectedIssue) ? "good" : "blocked"}
                />
                <ProofStep
                  icon={<AlertTriangle aria-hidden="true" />}
                  label="Diagnosis ready"
                  helper={hasRootCause(selectedIssue) ? "Diagnosis has an explainable failure reason." : "Diagnosis needs evidence before replay."}
                  state={hasRootCause(selectedIssue) ? "good" : "warn"}
                />
                <ProofStep
                  icon={<RotateCcw aria-hidden="true" />}
                  label="Trusted replay"
                  helper={hasTrustedGoldenReplay(selectedIssue) ? "Replay verified the fix." : replayLabel(selectedIssue.replay_coverage_status)}
                  state={hasTrustedGoldenReplay(selectedIssue) ? "good" : "blocked"}
                />
                <ProofStep
                  icon={<ShieldCheck aria-hidden="true" />}
                  label="Golden coverage"
                  helper={goldenReady(selectedIssue) ? "Ready to become a regression guard." : "Needs verified replay and a sample call."}
                  state={goldenReady(selectedIssue) ? "good" : "warn"}
                />
                <ProofStep
                  icon={<GitPullRequest aria-hidden="true" />}
                  label="CI gate"
                  helper={goldenReady(selectedIssue) && caps.canCi ? "Can protect pull requests." : "Needs Golden coverage before CI can block regressions."}
                  state={goldenReady(selectedIssue) && caps.canCi ? "good" : "neutral"}
                />
              </div>

              <div className="fi-detail-actions">
                {renderIssueAction(selectedIssue, { replayLabel: "Run trusted replay" })}
                <Link href={`/issues/${selectedIssue.id}`} className="btn btn-soft btn-sm fi-btn-secondary">
                  View issue
                </Link>
                <button
                  type="button"
                  className="btn btn-soft btn-sm fi-btn-secondary"
                  onClick={() => void onResolve(selectedIssue)}
                  disabled={busyIssueId === selectedIssue.id}
                >
                  <CheckCircle2 aria-hidden="true" />
                  Resolve
                </button>
              </div>
            </>
          ) : (
            <EmptyQueue>No issue selected.</EmptyQueue>
          )}
        </aside>
      </section>

      <section className="fi-section fi-trace-section">
        <SectionHeader
          title="Trace evidence"
          description="Evidence timeline for the selected issue."
          icon={<ListChecks aria-hidden="true" />}
        />
        {selectedIssue && selectedEvidence.length > 0 ? (
          <div className="fi-trace-list">
            {selectedEvidence.slice(0, 4).map((trace, index) => (
              <div key={`${trace.call_id ?? trace.trace_id ?? index}`} className="fi-trace-row">
                <div>
                  <strong>{trace.evidence_summary ?? trace.workflow_name ?? "Trace evidence"}</strong>
                  <span>
                    {trace.provider ?? "unknown provider"} / {trace.model ?? "unknown model"} - {trace.status ?? "unknown status"}
                  </span>
                </div>
                <div className="fi-trace-meta">
                  <span>{trace.created_at ? formatDateTime(trace.created_at) : "Time not captured"}</span>
                  <span>{trace.call_id ?? trace.trace_id ?? "Trace id unavailable"}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyQueue>No trace evidence attached.</EmptyQueue>
        )}
      </section>

      <section className="fi-grid fi-secondary-grid" aria-label="Secondary system cards">
        <article className="fi-section fi-secondary-card">
          <SectionHeader
            title="Pending replay runs"
            description="Replay work still waiting or running."
            action={
              caps.canReplay ? (
                <Link href="/replay" className="btn btn-soft btn-sm fi-btn-secondary">
                  Replay
                </Link>
              ) : (
                <LockedUpgradeLink label="Upgrade to unlock replay" />
              )
            }
          />
          <QueueList
            items={pendingRuns}
            empty="No pending replay runs."
            renderItem={(run) => (
              <Link key={run.id} href={`/replay/${run.id}`} className="fi-queue-row">
                <div className="fi-queue-main">
                  <strong>{run.replay_mode.replace(/_/g, " ")} replay</strong>
                  <span>{run.golden_set_id} - created {formatDateTime(run.created_at)}</span>
                </div>
                <StatusPill value={run.status} />
              </Link>
            )}
          />
        </article>

        <article className="fi-section fi-secondary-card">
          <SectionHeader
            title="Failed/not_verified CI gates"
            description="Regression CI runs that need human review."
            icon={<GitPullRequest aria-hidden="true" />}
          />
          <QueueList
            items={failedCiRuns}
            empty="No failed or not_verified CI gates."
            renderItem={(run) => (
              <div key={run.id} className="fi-queue-row">
                <div className="fi-queue-main">
                  <strong>{run.status === "not_verified" ? "Not verified" : "CI gate failed"}</strong>
                  <span>{run.git_sha ?? run.id} - {formatDateTime(run.created_at)}</span>
                </div>
                <div className="fi-row-actions">
                  <StatusPill value={run.status} />
                  {caps.canCi ? (
                    <Link href={`/ci-gates/${run.id}`} className="btn btn-primary btn-sm fi-btn-primary">
                      Review CI run
                    </Link>
                  ) : (
                    <LockedUpgradeLink label="Upgrade to unlock CI actions" />
                  )}
                </div>
              </div>
            )}
          />
        </article>

        <article className="fi-section fi-secondary-card">
          <SectionHeader
            title="Goldens needing review"
            description="Empty, flaky, or non-blocking Golden sets."
            action={
              caps.canGoldens ? (
                <Link href="/goldens" className="btn btn-soft btn-sm fi-btn-secondary">
                  Goldens
                </Link>
              ) : (
                <LockedUpgradeLink label="Upgrade to unlock Goldens" />
              )
            }
          />
          <QueueList
            items={goldensNeedingReview}
            empty="No goldens needing review."
            renderItem={(set) => (
              <Link key={set.id} href={`/goldens/${set.id}`} className="fi-queue-row">
                <div className="fi-queue-main">
                  <strong>{set.name}</strong>
                  <span>{goldenReviewReason(set)} - {formatCount(set.trace_count)} traces</span>
                </div>
                <StatusPill value={set.is_flaky ? "warning" : set.blocks_ci ? "stable" : "pending"} />
              </Link>
            )}
          />
        </article>

        <article className="fi-section fi-secondary-card">
          <SectionHeader
            title="Usage/plan status"
            description="Plan and usage indicators for action gates."
            action={
              <Link href="/cost" className="btn btn-soft btn-sm fi-btn-secondary">
                Cost
              </Link>
            }
          />
          <div className="fi-queue-list">
            <div className="fi-queue-row">
              <div className="fi-queue-main">
                <strong>Plan</strong>
                <span>{data.billing?.status ?? "Subscription status unavailable"}</span>
              </div>
              <span className="fi-mono">{planLabel}</span>
            </div>
            <div className="fi-queue-row">
              <div className="fi-queue-main">
                <strong>Replay quota</strong>
                <span>{planLimitText(data.quota)}</span>
              </div>
              <StatusPill value={data.quota?.enabled ? "stable" : "warning"} />
            </div>
            <div className="fi-queue-row">
              <div className="fi-queue-main">
                <strong>Calls in 24h</strong>
                <span>Latest analytics summary.</span>
              </div>
              <span className="fi-mono">{formatCount(data.summary?.calls_today)}</span>
            </div>
          </div>
        </article>
      </section>
        </>
      )}
    </div>
  );
}
