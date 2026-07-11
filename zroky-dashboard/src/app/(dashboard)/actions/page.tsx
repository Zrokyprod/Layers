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
import type { BillingUsageMeter } from "@/lib/types";

function formatMeter(meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return "Loading";
  const used = formatCount(meter.used);
  if (meter.unlimited || meter.limit == null) return `${used} used`;
  return `${used} / ${formatCount(meter.limit)}`;
}

function meterHelper(label: string, meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return `${label} usage is loading.`;
  if (meter.state === "exceeded") return `${label} exceeded by ${formatCount(meter.overage ?? 0)}.`;
  if (meter.state === "near_limit") return `${label} is near the current plan limit.`;
  if (meter.state === "blocked") return `${label} is blocked on this plan.`;
  if (meter.unlimited) return `${label} is unlimited on this plan.`;
  return meter.resets_at ? `Resets ${meter.resets_at}.` : "Current billing period.";
}

function meterPercent(meter: BillingUsageMeter | null | undefined): number {
  if (!meter || meter.unlimited || meter.limit == null || meter.limit <= 0) return 0;
  return Math.min(100, Math.max(0, (meter.used / meter.limit) * 100));
}

function quotaState(meter: BillingUsageMeter | null | undefined): StatusTone {
  if (!meter || meter.unlimited || meter.limit == null) return "neutral";
  if (meter.state === "blocked" || meter.state === "exceeded") return "danger";
  if (meter.state === "near_limit" || meter.used / meter.limit >= 0.8) return "warning";
  return "success";
}

function ProtectedActionQuota({ meter }: { meter: BillingUsageMeter | null | undefined }) {
  const percent = meterPercent(meter);
  const tone = quotaState(meter);
  return (
    <section className={`al-quota-gauge al-tone-${tone}`} aria-label="Protected action quota">
      <div>
        <span className="al-eyebrow">Protected action quota</span>
        <strong>{formatMeter(meter)}</strong>
        <p>{meterHelper("Protected actions", meter)}</p>
      </div>
      {meter && !meter.unlimited && meter.limit != null ? (
        <div className="al-quota-meter" aria-label={`${Math.round(percent)}% of protected action quota used`}>
          <span style={{ width: `${percent}%` }} />
        </div>
      ) : null}
    </section>
  );
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
      ctaHref: "/actions?filter=executing",
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
  const [filter, setFilter] = useState<ActionLifecycleFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const search = useMemo(
    () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search),
    [],
  );

  const lifecycleQuery = useQuery({
    queryKey: ["actions", "lifecycle-summary", 30, 200],
    queryFn: ({ signal }) => loadActionsLifecycleFeed({ days: 30, limit: 200 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const lifecycleSummary = lifecycleQuery.data?.summary;
  const billing = lifecycleSummary?.data.billing_usage ?? null;
  const sourceSummary = lifecycleSummary?.data.source_summary ?? null;
  const outcomeSummary = lifecycleSummary?.data.outcome_summary ?? null;
  const rows = lifecycleQuery.data?.rows ?? [];
  const filteredRows = useMemo(() => filterActionLifecycle(rows, filter), [filter, rows]);
  const counts = lifecycleQuery.data?.counts ?? {
    total: 0,
    protectedActions: 0,
    guardOnly: 0,
    held: 0,
    awaitingRunner: 0,
    executing: 0,
    stalled: 0,
    mismatched: 0,
    notVerified: 0,
    bypassed: 0,
  };
  const selectedRow = rows.find((row) => row.id === selectedId)
    ?? filteredRows[0]
    ?? rows[0]
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
        lifecycleSources.stale_attempts ? null : "runner attempts",
      ].filter((feed): feed is string => Boolean(feed))
    : [];
  const hasError = lifecycleQuery.isError || degradedFeeds.length > 0;
  const billingUnavailable = Boolean(lifecycleQuery.data && lifecycleSources?.billing_usage === false);
  const bypassRisk = sourceSummary?.unreceipted ?? 0;
  const connectedBypassFeeds = sourceSummary?.connected_feeds ?? 0;
  const successfulBypassPollers = sourceSummary?.successful_pollers ?? 0;
  const bypassFeedLabel =
    connectedBypassFeeds > 0
      ? `${formatCount(connectedBypassFeeds)} connected feed${connectedBypassFeeds === 1 ? "" : "s"} / ${formatCount(successfulBypassPollers)} active poller${successfulBypassPollers === 1 ? "" : "s"}`
      : "Webhook/API feed ready; no poller connected.";
  const matched = outcomeSummary?.matched ?? 0;
  const mismatched = outcomeSummary?.mismatched ?? counts.mismatched;
  const notVerified = outcomeSummary?.not_verified ?? counts.notVerified;
  const hero = heroState({
    awaitingRunner: counts.awaitingRunner,
    bypassRisk,
    error: hasError,
    executing: counts.executing,
    guardOnly: counts.guardOnly,
    held: counts.held,
    loading,
    mismatched,
    notVerified,
    protectedActions: counts.protectedActions,
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
    const linked = initialDeepLink(rows, search);
    if (linked && selectedId == null) {
      setSelectedId(linked);
      return;
    }
    if (filteredRows.length > 0 && (!selectedId || !filteredRows.some((row) => row.id === selectedId))) {
      setSelectedId(filteredRows[0].id);
      return;
    }
    if (!selectedId || !rows.some((row) => row.id === selectedId)) {
      setSelectedId(rows[0].id);
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
        protectedActions={formatCount(counts.protectedActions)}
        policyChecks={formatMeter(billing?.policy_checks)}
        runnerExecutions={formatMeter(billing?.runner_executions)}
        receipts={formatMeter(billing?.action_receipts)}
        verifiedOutcomes={formatCount(matched)}
        bypassRisk={formatCount(bypassRisk)}
        policyHelper={`${formatCount(counts.held)} held action${counts.held === 1 ? "" : "s"}.`}
        runnerHelper={meterHelper("Runner executions", billing?.runner_executions)}
        receiptHelper={meterHelper("Action receipts", billing?.action_receipts)}
        outcomeHelper={`${formatCount(mismatched)} mismatched / ${formatCount(notVerified)} not verified.`}
        bypassHelper={`${formatCount(sourceSummary?.policy_bypass ?? 0)} policy bypass / ${formatCount(sourceSummary?.unmanaged_agent_action ?? 0)} unmanaged. ${bypassFeedLabel}`}
        tones={{
          protectedActions: counts.protectedActions > 0 ? "success" : "neutral",
          policyChecks: counts.held > 0 ? "warning" : "neutral",
          runnerExecutions: counts.stalled > 0 ? "danger" : (billing?.runner_executions.used ?? 0) > 0 ? "success" : "neutral",
          receipts: (billing?.action_receipts.used ?? 0) > 0 ? "success" : "warning",
          verifiedOutcomes: mismatched > 0 ? "danger" : notVerified > 0 ? "warning" : matched > 0 ? "success" : "neutral",
          bypassRisk: bypassRisk > 0 ? "danger" : "success",
        }}
      />

      <ProtectedActionQuota meter={billing?.protected_actions} />

      {billingUnavailable ? (
        <section className="al-alert al-tone-warning" role="status">
          <div>
            <span className="al-eyebrow">Billing meter</span>
            <strong>Quota usage unavailable</strong>
            <p>Action lifecycle data is still live. Refresh billing before making plan or quota decisions.</p>
          </div>
        </section>
      ) : null}

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
