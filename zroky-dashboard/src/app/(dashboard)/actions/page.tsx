"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ActionInspector } from "./ActionInspector";
import { ActionLifecycleQueue } from "./ActionLifecycleQueue";
import { ActionsMetricStrip } from "./ActionsMetricStrip";
import { ActionsVerdictHero } from "./ActionsVerdictHero";
import { DashboardWorkspace } from "@/components/dashboard-scaffold";
import {
  getActionIntentTimeline,
  listActionExecutionAttempts,
} from "@/lib/api";
import {
  filterActionLifecycle,
  type ActionLifecycleFilter,
  type ActionLifecycleRow,
} from "@/lib/action-lifecycle";
import type { StatusTone } from "@/lib/action-status";
import { loadActionsLifecycleFeed } from "@/lib/actions-lifecycle-feed";
import { formatCount, timeSince } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";

const DEFAULT_ACTION_WINDOW_DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;
const ACTION_FILTERS = new Set<ActionLifecycleFilter>([
  "all",
  "needs_action",
  "awaiting_runner",
  "in_progress",
  "completed",
  "stopped",
  "bypassed",
]);

function actionsWindowDays(dateRange: { from: Date | null; to: Date | null }): number {
  if (!dateRange.from || !dateRange.to) return DEFAULT_ACTION_WINDOW_DAYS;
  const fromMs = new Date(dateRange.from).getTime();
  const toMs = new Date(dateRange.to).getTime();
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) {
    return DEFAULT_ACTION_WINDOW_DAYS;
  }
  return Math.max(1, Math.min(90, Math.ceil((toMs - fromMs) / MS_PER_DAY)));
}

function initialFilter(search: URLSearchParams): ActionLifecycleFilter {
  const requested = search.get("filter") as ActionLifecycleFilter | null;
  return requested && ACTION_FILTERS.has(requested) ? requested : "all";
}

type HeroState = {
  title: string;
  copy: string;
  pill: string;
  tone: StatusTone;
  ctaHref: string;
  ctaLabel: string;
};

function heroState({
  bypassRisk,
  error,
  awaitingRunner,
  executing,
  guardOnly,
  held,
  loading,
  mismatched,
  notVerified,
  protectedActions,
  stalled,
}: {
  bypassRisk: number;
  error: boolean;
  awaitingRunner: number;
  executing: number;
  guardOnly: number;
  held: number;
  loading: boolean;
  mismatched: number;
  notVerified: number;
  protectedActions: number;
  stalled: number;
}): HeroState {
  if (error) {
    return {
      title: "Action visibility unavailable",
      copy: "One or more lifecycle feeds did not refresh cleanly.",
      pill: "refresh failed",
      tone: "danger",
      ctaHref: "/actions",
      ctaLabel: "Retry",
    };
  }
  if (loading) {
    return {
      title: "Loading protected actions",
      copy: "Refreshing action intents, policy decisions, runner attempts, outcomes, receipts, and connected bypass feeds.",
      pill: "loading",
      tone: "neutral",
      ctaHref: "/actions",
      ctaLabel: "Open actions",
    };
  }
  if (bypassRisk > 0) {
    return {
      title: "Bypass risk",
      copy: `${formatCount(bypassRisk)} webhook/poller-fed source mutation${bypassRisk === 1 ? "" : "s"} need receipt matching or exception review in Outcomes.`,
      pill: `${formatCount(bypassRisk)} unreceipted`,
      tone: "danger",
      ctaHref: "/outcomes",
      ctaLabel: "Review bypass",
    };
  }
  if (mismatched > 0) {
    return {
      title: "Action mismatch",
      copy: `${formatCount(mismatched)} protected action${mismatched === 1 ? "" : "s"} do not match the source of record.`,
      pill: `${formatCount(mismatched)} mismatch`,
      tone: "danger",
      ctaHref: "/evidence",
      ctaLabel: "Review mismatch",
    };
  }
  if (held > 0) {
    return {
      title: "Actions held",
      copy: `${formatCount(held)} action${held === 1 ? "" : "s"} are waiting at the policy approval gate.`,
      pill: `${formatCount(held)} held`,
      tone: "warning",
      ctaHref: "/approvals",
      ctaLabel: "Review held actions",
    };
  }
  if (awaitingRunner > 0 || stalled > 0) {
    const runnerGap = awaitingRunner + stalled;
    return {
      title: "Actions awaiting runner",
      copy: `${formatCount(runnerGap)} authorized action${runnerGap === 1 ? " has" : "s have"} no healthy protected runner attempt yet.`,
      pill: `${formatCount(runnerGap)} awaiting runner`,
      tone: "warning",
      ctaHref: "/agents",
      ctaLabel: "Restore runner",
    };
  }
  if (executing > 0) {
    return {
      title: "Actions executing",
      copy: `${formatCount(executing)} protected action${executing === 1 ? " is" : "s are"} still inside the runner lifecycle.`,
      pill: `${formatCount(executing)} executing`,
      tone: "neutral",
      ctaHref: "/actions?filter=in_progress",
      ctaLabel: "Review execution",
    };
  }
  if (notVerified > 0) {
    return {
      title: "Actions need proof",
      copy: `${formatCount(notVerified)} action path${notVerified === 1 ? " is" : "s are"} controlled but not verified against a source of record.`,
      pill: `${formatCount(notVerified)} need proof`,
      tone: "warning",
      ctaHref: "/outcomes",
      ctaLabel: "Connect proof",
    };
  }
  if (guardOnly > 0) {
    return {
      title: "Unlinked policy decisions",
      copy: `${formatCount(guardOnly)} policy decision${guardOnly === 1 ? " was" : "s were"} observed outside the Action Intent lifecycle.`,
      pill: `${formatCount(guardOnly)} unlinked`,
      tone: "warning",
      ctaHref: "/agents",
      ctaLabel: "Review routing",
    };
  }
  if (protectedActions > 0) {
    return {
      title: "Actions controlled",
      copy: "Protected action lifecycle, runner execution, proof, and receipts are visible.",
      pill: `${formatCount(protectedActions)} controlled`,
      tone: "success",
      ctaHref: "/evidence",
      ctaLabel: "Open receipts",
    };
  }
  return {
    title: "Setup required",
    copy: "Protect your first agent action to populate the lifecycle cockpit.",
    pill: "no actions yet",
    tone: "neutral",
    ctaHref: "/agents/setup",
    ctaLabel: "Protect first action",
  };
}

function initialDeepLink(rows: ActionLifecycleRow[], search: URLSearchParams): string | null {
  const actionId = search.get("action_id");
  const decisionId = search.get("decision_id");
  if (actionId) {
    return rows.find((row) => row.actionId === actionId)?.id ?? null;
  }
  if (decisionId) {
    return rows.find((row) => row.decisionId === decisionId)?.id ?? null;
  }
  return null;
}

export default function ActionsPage() {
  const search = useMemo(
    () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search),
    [],
  );
  const [filter, setFilter] = useState<ActionLifecycleFilter>(() => initialFilter(search));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const dateRange = useDashboardStore((state) => state.dateRange);
  const windowDays = useMemo(() => actionsWindowDays(dateRange), [dateRange]);

  const lifecycleQuery = useQuery({
    queryKey: ["actions", "lifecycle-summary", windowDays, 200],
    queryFn: ({ signal }) => loadActionsLifecycleFeed({ days: windowDays, limit: 200 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const lifecycleSummary = lifecycleQuery.data?.summary;
  const sourceSummary = lifecycleSummary?.data.source_summary ?? null;
  const outcomeSummary = lifecycleSummary?.data.outcome_summary ?? null;
  const rows = useMemo(() => lifecycleQuery.data?.rows ?? [], [lifecycleQuery.data?.rows]);
  const filteredRows = useMemo(() => filterActionLifecycle(rows, filter), [filter, rows]);
  const counts = lifecycleQuery.data?.counts ?? {
    total: 0,
    protectedActions: 0,
    guardOnly: 0,
    needsAction: 0,
    held: 0,
    awaitingRunner: 0,
    inProgress: 0,
    executing: 0,
    completed: 0,
    stopped: 0,
    stalled: 0,
    mismatched: 0,
    notVerified: 0,
    bypassed: 0,
  };
  const selectedRow = filteredRows.find((row) => row.id === selectedId)
    ?? filteredRows[0]
    ?? null;
  const selectedActionId = selectedRow?.actionId ?? null;

  const actionTimelineQuery = useQuery({
    queryKey: ["action-intent", selectedActionId, "timeline", "actions-page"],
    enabled: Boolean(selectedActionId),
    queryFn: ({ signal }) => getActionIntentTimeline(selectedActionId ?? "", signal),
    staleTime: 10_000,
    retry: false,
  });
  const actionAttemptsQuery = useQuery({
    queryKey: ["action-intent", selectedActionId, "execution-attempts", "actions-page"],
    enabled: Boolean(selectedActionId),
    queryFn: ({ signal }) => listActionExecutionAttempts(selectedActionId ?? "", signal),
    staleTime: 10_000,
    retry: false,
  });

  const loading = lifecycleQuery.isLoading;
  const lifecycleSources = lifecycleSummary?.sources;
  const degradedFeeds = lifecycleSources
    ? [
        lifecycleSources.intents ? null : "action intents",
        lifecycleSources.approvals ? null : "policy decisions",
        lifecycleSources.outcomes ? null : "outcome checks",
        lifecycleSources.outcome_summary ? null : "outcome summary",
        lifecycleSources.source_summary ? null : "bypass summary",
        lifecycleSources.mutations ? null : "bypass mutations",
        lifecycleSources.attempts === false ? "runner attempts" : null,
        lifecycleSources.stale_attempts ? null : "runner attempts",
      ].filter((feed): feed is string => Boolean(feed))
    : [];
  const hasError = lifecycleQuery.isError || degradedFeeds.length > 0;
  const bypassRisk = sourceSummary?.unreceipted ?? 0;
  const connectedBypassFeeds = sourceSummary?.connected_feeds ?? 0;
  const successfulBypassPollers = sourceSummary?.successful_pollers ?? 0;
  const bypassCoverageLabel = connectedBypassFeeds === 0
    ? "No source mutation feed is connected; zero observed bypasses is not coverage."
    : successfulBypassPollers === 0
      ? `${formatCount(connectedBypassFeeds)} source feed${connectedBypassFeeds === 1 ? " is" : "s are"} configured, but no poller has synced successfully yet.`
      : `${formatCount(connectedBypassFeeds)} source feed${connectedBypassFeeds === 1 ? "" : "s"} configured / ${formatCount(successfulBypassPollers)} poller${successfulBypassPollers === 1 ? "" : "s"} synced.`;
  const bypassFeedLabel = bypassRisk > 0
    ? `${formatCount(bypassRisk)} unreceipted source mutation${bypassRisk === 1 ? "" : "s"} detected. ${
        connectedBypassFeeds === 0 ? "Continuous source coverage is not connected." : bypassCoverageLabel
      }`
    : bypassCoverageLabel;
  const matched = outcomeSummary?.matched ?? 0;
  const mismatched = outcomeSummary?.mismatched ?? counts.mismatched;
  const notVerified = outcomeSummary?.not_verified ?? counts.notVerified;
  const protectedActions = lifecycleSummary?.metrics.controlled_actions ?? counts.protectedActions;
  const heldActions = lifecycleSummary?.metrics.held_actions ?? counts.held;
  const hero = heroState({
    awaitingRunner: counts.awaitingRunner,
    bypassRisk,
    error: hasError,
    executing: counts.executing,
    guardOnly: counts.guardOnly,
    held: heldActions,
    loading,
    mismatched,
    notVerified,
    protectedActions,
    stalled: counts.stalled,
  });
  const lastUpdatedMs = Math.max(
    lifecycleQuery.dataUpdatedAt ?? 0,
  );
  const updatedLabel = lastUpdatedMs > 0
    ? `Updated ${timeSince(new Date(lastUpdatedMs).toISOString(), nowMs)}`
    : "Updated just now";

  useEffect(() => {
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 30_000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (rows.length === 0) {
      setSelectedId(null);
      return;
    }
    if (filteredRows.length === 0) {
      setSelectedId(null);
      return;
    }
    const linked = initialDeepLink(rows, search);
    if (linked && selectedId == null) {
      setSelectedId(linked);
      return;
    }
    if (filteredRows.length > 0 && (!selectedId || !filteredRows.some((row) => row.id === selectedId))) {
      setSelectedId(filteredRows[0].id);
    }
  }, [filteredRows, rows, search, selectedId]);

  function refreshAll() {
    void Promise.all([
      lifecycleQuery.refetch(),
      actionTimelineQuery.refetch(),
      actionAttemptsQuery.refetch(),
    ]);
  }

  return (
    <main className="actions-lifecycle-page">
      <ActionsVerdictHero
        title={hero.title}
        copy={hero.copy}
        pill={hero.pill}
        tone={hero.tone}
        ctaHref={hero.ctaHref}
        ctaLabel={hero.ctaLabel}
        updatedLabel={updatedLabel}
        onRefresh={refreshAll}
      />

      <ActionsMetricStrip
        protectedActions={formatCount(protectedActions)}
        waitingApproval={formatCount(heldActions)}
        awaitingRunner={formatCount(counts.awaitingRunner)}
        verifiedOutcomes={formatCount(matched)}
        bypassRisk={connectedBypassFeeds === 0 && bypassRisk === 0 ? "Not covered" : formatCount(bypassRisk)}
        protectedHelper={`Action intents in the selected ${windowDays}-day window.`}
        approvalHelper={`${formatCount(heldActions)} action${heldActions === 1 ? "" : "s"} waiting for a human decision.`}
        awaitingRunnerHelper={`${formatCount(counts.awaitingRunner)} authorized action${counts.awaitingRunner === 1 ? "" : "s"} without a healthy completion path.`}
        outcomeHelper={`${formatCount(mismatched)} mismatched / ${formatCount(notVerified)} need verification.`}
        bypassHelper={bypassFeedLabel}
        tones={{
          protectedActions: protectedActions > 0 ? "success" : "neutral",
          waitingApproval: heldActions > 0 ? "warning" : "neutral",
          awaitingRunner: counts.stalled > 0 ? "danger" : counts.awaitingRunner > 0 ? "warning" : "success",
          verifiedOutcomes: mismatched > 0 ? "danger" : notVerified > 0 ? "warning" : matched > 0 ? "success" : "neutral",
          bypassRisk: bypassRisk > 0 ? "danger" : connectedBypassFeeds > 0 && successfulBypassPollers > 0 ? "success" : "warning",
        }}
      />

      {lifecycleSummary?.truncated ? (
        <section className="al-alert al-tone-warning" role="status">
          <div>
            <span className="al-eyebrow">Row preview</span>
            <strong>Showing the newest {formatCount(lifecycleSummary.row_limit)} lifecycle rows</strong>
            <p>
              Metrics use exact backend totals. Detail rows are capped for{" "}
              {lifecycleSummary.truncated_sources.join(", ")}.
            </p>
          </div>
        </section>
      ) : null}

      <DashboardWorkspace
        left={(
          <ActionLifecycleQueue
            rows={filteredRows}
            selectedId={selectedRow?.id ?? null}
            filter={filter}
            onFilterChange={setFilter}
            onSelect={setSelectedId}
          />
        )}
        right={(
          <ActionInspector
            row={selectedRow}
            timeline={actionTimelineQuery.data?.items ?? []}
            attempts={actionAttemptsQuery.data?.items ?? []}
          />
        )}
      />

      {hasError ? (
        <section className="al-alert al-tone-danger" role="status">
          <div>
            <span className="al-eyebrow">Refresh status</span>
            <strong>One or more lifecycle feeds failed</strong>
            <p>Keep protected action review conservative until every feed refreshes cleanly.</p>
          </div>
        </section>
      ) : null}
    </main>
  );
}
