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
  getBillingUsage,
  getOutcomeReconciliationSummary,
  getSourceMutationSummary,
  listActionExecutionAttempts,
  listActionIntents,
  listOutcomeReconciliations,
  listProjectActionExecutionAttempts,
  listRuntimePolicyApprovals,
  listUnreceiptedSourceMutations,
} from "@/lib/api";
import {
  actionLifecycleCounts,
  buildActionLifecycle,
  filterActionLifecycle,
  type ActionLifecycleFilter,
  type ActionLifecycleRow,
} from "@/lib/action-lifecycle";
import type { StatusTone } from "@/lib/action-status";
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
  held,
  loading,
  mismatched,
  protectedActions,
}: {
  bypassRisk: number;
  error: boolean;
  held: number;
  loading: boolean;
  mismatched: number;
  protectedActions: number;
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

  const billingQuery = useQuery({
    queryKey: ["billing", "usage", "protected-action-dashboard"],
    queryFn: ({ signal }) => getBillingUsage(signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const actionIntentsQuery = useQuery({
    queryKey: ["action-intents", "actions", "all"],
    queryFn: ({ signal }) => listActionIntents({ status: "all", limit: 100 }, signal),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
  const decisionsQuery = useQuery({
    queryKey: ["runtime-policy", "actions", "all"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
  const outcomesQuery = useQuery({
    queryKey: ["outcomes", "actions", "reconciliation"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ verdict: "all", limit: 100 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const staleAttemptsQuery = useQuery({
    queryKey: ["action-execution-attempts", "actions", "stale"],
    queryFn: ({ signal }) => listProjectActionExecutionAttempts(
      { status: ["planned", "dispatched", "running"], stale: true, limit: 100 },
      signal,
    ),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const outcomeSummaryQuery = useQuery({
    queryKey: ["outcomes", "actions", "summary", 30],
    queryFn: ({ signal }) => getOutcomeReconciliationSummary(30, signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const sourceMutationSummaryQuery = useQuery({
    queryKey: ["outcomes", "actions", "source-mutations", "summary"],
    queryFn: ({ signal }) => getSourceMutationSummary(signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const sourceMutationsQuery = useQuery({
    queryKey: ["outcomes", "actions", "source-mutations", "unreceipted"],
    queryFn: ({ signal }) => listUnreceiptedSourceMutations(100, signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const billing = billingQuery.data;
  const sourceSummary = sourceMutationSummaryQuery.data;
  const outcomeSummary = outcomeSummaryQuery.data;
  const intents = useMemo(() => actionIntentsQuery.data?.items ?? [], [actionIntentsQuery.data?.items]);
  const decisions = useMemo(() => decisionsQuery.data?.items ?? [], [decisionsQuery.data?.items]);
  const outcomes = useMemo(() => outcomesQuery.data?.items ?? [], [outcomesQuery.data?.items]);
  const staleAttempts = useMemo(() => staleAttemptsQuery.data?.items ?? [], [staleAttemptsQuery.data?.items]);
  const sourceMutations = useMemo(() => sourceMutationsQuery.data?.items ?? [], [sourceMutationsQuery.data?.items]);
  const rows = useMemo(
    () => buildActionLifecycle({
      intents,
      decisions,
      outcomes,
      attempts: staleAttempts,
      staleAttemptIds: staleAttempts.map((attempt) => attempt.attempt_id),
      mutations: sourceMutations,
    }),
    [decisions, intents, outcomes, sourceMutations, staleAttempts],
  );
  const filteredRows = useMemo(() => filterActionLifecycle(rows, filter), [filter, rows]);
  const counts = useMemo(() => actionLifecycleCounts(rows), [rows]);
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

  const loading =
    actionIntentsQuery.isLoading ||
    decisionsQuery.isLoading ||
    outcomesQuery.isLoading ||
    staleAttemptsQuery.isLoading ||
    outcomeSummaryQuery.isLoading ||
    sourceMutationSummaryQuery.isLoading ||
    sourceMutationsQuery.isLoading;
  const hasError =
    actionIntentsQuery.isError ||
    decisionsQuery.isError ||
    outcomesQuery.isError ||
    staleAttemptsQuery.isError ||
    outcomeSummaryQuery.isError ||
    sourceMutationSummaryQuery.isError ||
    sourceMutationsQuery.isError;
  const billingUnavailable = billingQuery.isError;
  const bypassRisk = sourceSummary?.unreceipted ?? 0;
  const connectedBypassFeeds = sourceSummary?.connected_feeds ?? 0;
  const successfulBypassPollers = sourceSummary?.successful_pollers ?? 0;
  const bypassFeedLabel =
    connectedBypassFeeds > 0
      ? `${formatCount(connectedBypassFeeds)} connected feed${connectedBypassFeeds === 1 ? "" : "s"} / ${formatCount(successfulBypassPollers)} active poller${successfulBypassPollers === 1 ? "" : "s"}`
      : "Webhook/API feed ready; no poller connected.";
  const matched = outcomeSummary?.matched ?? outcomes.filter((item) => item.verdict === "matched").length;
  const mismatched = outcomeSummary?.mismatched ?? counts.mismatched;
  const notVerified = outcomeSummary?.not_verified ?? counts.notVerified;
  const hero = heroState({
    bypassRisk,
    error: hasError,
    held: counts.held,
    loading,
    mismatched,
    protectedActions: counts.protectedActions,
  });
  const lastUpdatedMs = Math.max(
    billingQuery.dataUpdatedAt ?? 0,
    actionIntentsQuery.dataUpdatedAt ?? 0,
    decisionsQuery.dataUpdatedAt ?? 0,
    outcomesQuery.dataUpdatedAt ?? 0,
    staleAttemptsQuery.dataUpdatedAt ?? 0,
    outcomeSummaryQuery.dataUpdatedAt ?? 0,
    sourceMutationSummaryQuery.dataUpdatedAt ?? 0,
    sourceMutationsQuery.dataUpdatedAt ?? 0,
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
      billingQuery.refetch(),
      actionIntentsQuery.refetch(),
      decisionsQuery.refetch(),
      outcomesQuery.refetch(),
      staleAttemptsQuery.refetch(),
      outcomeSummaryQuery.refetch(),
      sourceMutationSummaryQuery.refetch(),
      sourceMutationsQuery.refetch(),
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
