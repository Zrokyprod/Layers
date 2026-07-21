"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getHomeSummary,
  type ActionExecutionAttemptResponse,
  type ActionIntentResponse,
  type ActionRunnerResponse,
  type AgentProfileListResponse,
  type AgentProfileResponse,
  type HomeSummaryResponse,
  type OutcomeReconciliationSummaryResponse,
  type OutcomeReconciliationView,
  type RuntimePolicyDecisionResponse,
  type SourceMutationSummaryResponse,
  type SourceMutationView,
} from "@/lib/api";
import { buildFleetView } from "@/lib/agent-fleet";
import { formatCount, timeSince } from "@/lib/format";
import { buildDecisionQueue } from "@/lib/home-queue";
import { useDashboardStore } from "@/lib/store";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";
import type { StatusTone } from "@/lib/action-status";

import { AgentHealthTimeline } from "./AgentHealthTimeline";
import { DecisionQueue } from "./DecisionQueue";
import { FirstRunPanel, type FirstRunSignals } from "./FirstRunPanel";
import { HomeActivitySections } from "./HomeActivitySections";
import { ProofStrip, type ProofMetric } from "./ProofStrip";
import { VerdictHero } from "./VerdictHero";

type MissionData = {
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
};

type MissionSource =
  | "homeSummary"
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

type MissionAvailability = Record<MissionSource, boolean>;

const DEFAULT_HOME_WINDOW_DAYS = 7;
const MS_PER_DAY = 86_400_000;

const EMPTY_DATA: MissionData = {
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
};

const NO_SOURCES_AVAILABLE: MissionAvailability = {
  homeSummary: false,
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

const ALL_SOURCES_AVAILABLE: MissionAvailability = {
  homeSummary: true,
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

function firstRunSignals(data: MissionData): FirstRunSignals {
  const hasProjectKey = data.apiKeys.some((key) => !key.revoked && !key.expired);
  const hasActiveAgent = data.agentProfiles.some((profile) => profile.is_active) || (data.agentProfileMeta?.active_count ?? 0) > 0;
  const hasRunnerConnected = data.actionRunners.length > 0;
  const hasVerificationConnected =
    data.outcomes.length > 0 ||
    (data.outcomeSummary?.total ?? 0) > 0 ||
    (data.sourceSummary?.matched_receipt ?? 0) > 0 ||
    (data.sourceSummary?.connected_feeds ?? 0) > 0;
  const hasActionIntent = data.intents.length > 0;
  const hasAssurancePack = hasActionIntent || hasVerificationConnected && data.agentProfiles.length > 0;
  const hasReceiptGenerated =
    data.intents.some((intent) => intent.receipt_status === "generated") ||
    (data.homeSummary?.metrics.receipts_generated ?? 0) > 0 ||
    (data.sourceSummary?.matched_receipt ?? 0) > 0;
  const hasProofSignal =
    data.approvals.length > 0 ||
    data.outcomes.length > 0 ||
    (data.sourceSummary?.matched_receipt ?? 0) > 0 ||
    data.intents.some((intent) => intent.receipt_status === "generated" || ["matched", "mismatched"].includes(intent.proof_status));

  return {
    hasProjectKey,
    hasActiveAgent,
    hasRunnerConnected,
    hasVerificationConnected,
    hasAssurancePack,
    hasActionIntent,
    hasProofSignal,
    hasReceiptGenerated,
  };
}

function hasProtectedActionSignal(signals: FirstRunSignals): boolean {
  return signals.hasActionIntent || signals.hasProofSignal;
}

function quotaWarning(usage: BillingUsageResponse | null): string | null {
  if (!usage) {
    return null;
  }
  const meters: Array<[string, BillingUsageMeter]> = [
    ["Protected actions", usage.protected_actions],
    ["Runner executions", usage.runner_executions],
    ["Action receipts", usage.action_receipts],
    ["Verification checks", usage.verification_checks],
  ];
  for (const [label, meter] of meters) {
    if (!meter || meter.unlimited || meter.limit == null || meter.limit <= 0) {
      continue;
    }
    const ratio = meter.used / meter.limit;
    const state = (meter.state ?? "").toLowerCase();
    if (meter.overage != null && meter.overage > 0) {
      return `${label} quota exceeded`;
    }
    if (state.includes("exceeded") || state.includes("over")) {
      return `${label} quota exceeded`;
    }
    if (ratio >= 0.9) {
      return `${label} quota ${Math.round(ratio * 100)}% used`;
    }
  }
  return null;
}

function unavailableProofMetric(id: string, label: string, detail: string, href: string): ProofMetric {
  return {
    id,
    label,
    value: "— unavailable",
    detail,
    href,
    tone: "warning",
  };
}

function homeWindowDays(dateRange: { from: Date | null; to: Date | null }): number {
  if (!dateRange.from || !dateRange.to) {
    return DEFAULT_HOME_WINDOW_DAYS;
  }
  const fromMs = new Date(dateRange.from).getTime();
  const toMs = new Date(dateRange.to).getTime();
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) {
    return DEFAULT_HOME_WINDOW_DAYS;
  }
  return Math.max(1, Math.min(90, Math.ceil((toMs - fromMs) / MS_PER_DAY)));
}

type ProofStats = {
  totalActions: number;
  proven: number;
  mismatches: number;
  unverifiable: number;
  pendingApprovals: number;
  openIncidents: number;
  blockedAttempts: number;
  coveragePercent: number | null;
};

function proofStats(data: MissionData): ProofStats {
  const summary = data.homeSummary;
  const totalActions = Math.max(summary?.metrics.controlled_actions ?? 0, data.intents.length, data.outcomeSummary?.total ?? 0, data.outcomes.length);
  const proven = Math.max(summary?.metrics.verified_outcomes ?? 0, data.outcomeSummary?.matched ?? 0, data.outcomes.filter((item) => item.verdict === "matched" || item.verification_status === "matched").length);
  const mismatches = Math.max(data.outcomeSummary?.mismatched ?? 0, data.outcomes.filter((item) => item.verdict === "mismatched" || item.verification_status === "mismatched").length);
  const explicitUnknown = Math.max(
    data.outcomeSummary?.not_verified ?? 0,
    data.outcomes.filter((item) => ["not_verified", "unknown", "pending"].includes(String(item.verdict ?? item.verification_status ?? ""))).length,
  );
  const unchecked = Math.max(0, totalActions - Math.max(summary?.metrics.outcome_checks ?? 0, data.outcomeSummary?.total ?? 0, data.outcomes.length));
  const unverifiable = Math.max(explicitUnknown + data.staleAttempts.length, unchecked);
  const pendingApprovals = Math.max(summary?.metrics.pending_approvals ?? 0, data.approvals.filter((item) => item.status === "pending_approval").length);
  const blockedAttempts = data.approvals.filter((item) => ["blocked", "rejected", "expired"].includes(item.status)).length + (summary?.metrics.bypass_mutations ?? 0);
  const openIncidents = mismatches + data.mutations.filter((item) => ["policy_bypass", "unmanaged_agent_action", "unknown_actor"].includes(item.classification)).length;
  const coveragePercent = totalActions > 0 ? Math.round((proven / totalActions) * 100) : null;
  return { totalActions, proven, mismatches, unverifiable, pendingApprovals, openIncidents, blockedAttempts, coveragePercent };
}

function proofMetrics(data: MissionData, availability: MissionAvailability): ProofMetric[] {
  const summary = data.homeSummary;
  const stats = proofStats(data);
  if (!availability.homeSummary || !summary) {
    return [
      unavailableProofMetric("mismatches-caught", "Mismatches caught", "Home summary unavailable", "/operations"),
      unavailableProofMetric("proven-outcomes", "Proven outcomes", "Home summary unavailable", "/evidence"),
      unavailableProofMetric("unverifiable", "Unverifiable", "Home summary unavailable", "/operations"),
      unavailableProofMetric("open-incidents", "Open incidents", "Home summary unavailable", "/operations"),
      unavailableProofMetric("pending-approvals", "Pending approvals", "Home summary unavailable", "/approvals"),
      unavailableProofMetric("coverage", "Coverage", "Home summary unavailable", "/evidence"),
    ];
  }
  const windowLabel = `Last ${summary.window_days} days`;

  return [
    {
      id: "mismatches-caught",
      label: "Mismatches caught",
      value: formatCount(stats.mismatches),
      detail: stats.mismatches > 0 ? "Claims contradicted by source-of-truth" : `No mismatches, ${windowLabel.toLowerCase()}`,
      href: "/operations",
      tone: stats.mismatches > 0 ? "danger" : "success",
    },
    {
      id: "proven-outcomes",
      label: "Proven outcomes",
      value: formatCount(stats.proven),
      detail: `${formatCount(stats.totalActions)} total actions`,
      href: "/evidence",
      tone: stats.proven > 0 ? "success" : "neutral",
    },
    {
      id: "unverifiable",
      label: "Unverifiable",
      value: formatCount(stats.unverifiable),
      detail: stats.unverifiable > 0 ? "Blind spots, not safe by default" : "No unknown outcomes",
      href: "/operations",
      tone: stats.unverifiable > 0 ? "warning" : "success",
    },
    {
      id: "open-incidents",
      label: "Open incidents",
      value: formatCount(stats.openIncidents),
      detail: stats.openIncidents > 0 ? "Needs investigation" : "No open proof incidents",
      href: "/operations",
      tone: stats.openIncidents > 0 ? "danger" : "success",
    },
    {
      id: "pending-approvals",
      label: "Pending approvals",
      value: formatCount(stats.pendingApprovals),
      detail: "Open approval queue",
      href: "/approvals",
      tone: stats.pendingApprovals > 0 ? "warning" : "success",
    },
    {
      id: "coverage",
      label: "Coverage",
      value: stats.coveragePercent == null ? "No signal" : `${stats.coveragePercent}%`,
      detail: `${formatCount(stats.blockedAttempts)} blocked/bypass signals`,
      href: "/evidence",
      tone: stats.coveragePercent == null ? "neutral" : stats.coveragePercent >= 95 ? "success" : "warning",
    },
  ];
}

type TrustHealthItem = {
  id: string;
  label: string;
  value: string;
  detail: string;
  tone: StatusTone;
};

function trustHealth(data: MissionData, availability: MissionAvailability): TrustHealthItem[] {
  const connectedFeeds = data.sourceSummary?.connected_feeds ?? 0;
  const successfulPollers = data.sourceSummary?.successful_pollers ?? 0;
  const runnerTotal = data.actionRunners.length;
  const runnerOnline = data.actionRunners.filter((runner) => runner.status === "online").length;
  const receipts = data.homeSummary?.metrics.receipts_generated ?? data.intents.filter((intent) => intent.receipt_status === "generated").length;
  const outcomeChecks = data.homeSummary?.metrics.outcome_checks ?? data.outcomeSummary?.total ?? data.outcomes.length;
  return [
    {
      id: "source-freshness",
      label: "Source freshness",
      value: !availability.sourceSummary ? "Unavailable" : connectedFeeds === 0 ? "No source" : `${successfulPollers}/${connectedFeeds} fresh`,
      detail: connectedFeeds === 0 ? "Connect proof source" : "Fresh source reads",
      tone: !availability.sourceSummary || connectedFeeds === 0 || successfulPollers < connectedFeeds ? "warning" : "success",
    },
    {
      id: "executor-health",
      label: "Executor health",
      value: runnerTotal === 0 ? "No runner" : `${runnerOnline}/${runnerTotal} online`,
      detail: data.staleAttempts.length > 0 ? `${data.staleAttempts.length} stale attempts` : "Recovery/execution rail",
      tone: runnerTotal === 0 || runnerOnline < runnerTotal || data.staleAttempts.length > 0 ? "warning" : "success",
    },
    {
      id: "evidence-signer",
      label: "Evidence signer",
      value: receipts > 0 ? "Signing" : "No signal",
      detail: `${formatCount(receipts)} signed receipts`,
      tone: receipts > 0 ? "success" : "neutral",
    },
    {
      id: "connector-test-read",
      label: "Connector test-read",
      value: outcomeChecks > 0 ? "Active" : "No proof read",
      detail: `${formatCount(outcomeChecks)} checks`,
      tone: outcomeChecks > 0 ? "success" : "warning",
    },
  ];
}

function worstTone(items: TrustHealthItem[], stats: ProofStats, unavailableCount: number): StatusTone {
  if (stats.mismatches > 0 || stats.openIncidents > 0) return "danger";
  if (stats.unverifiable > 0 || stats.pendingApprovals > 0 || unavailableCount > 0) return "warning";
  if (items.some((item) => item.tone === "danger")) return "danger";
  if (items.some((item) => item.tone === "warning")) return "warning";
  return stats.totalActions > 0 ? "success" : "neutral";
}

function homeVerdict(data: MissionData, items: TrustHealthItem[], unavailableCount: number, hasSetup: boolean) {
  const stats = proofStats(data);
  const tone = hasSetup ? worstTone(items, stats, unavailableCount) : "neutral";
  const denominator = `${formatCount(stats.totalActions)} actions · ${formatCount(stats.proven)} proven · ${formatCount(stats.mismatches)} mismatches caught · ${formatCount(stats.unverifiable)} unverifiable · ${formatCount(stats.pendingApprovals)} need approval`;
  if (!hasSetup) {
    return {
      title: "Set up proof before trusting Home",
      detail: "Connect a source, define an Assurance Pack, connect an agent, then verify the first run.",
      tone,
      ctaLabel: "Start setup",
      ctaHref: "/integrations",
    };
  }
  if (stats.mismatches > 0) {
    return { title: `${formatCount(stats.mismatches)} mismatches caught`, detail: denominator, tone, ctaLabel: "Investigate", ctaHref: "/operations" };
  }
  if (stats.unverifiable > 0) {
    return { title: `${formatCount(stats.unverifiable)} unverifiable actions`, detail: denominator, tone, ctaLabel: "Review blind spots", ctaHref: "/operations" };
  }
  if (stats.pendingApprovals > 0) {
    return { title: `${formatCount(stats.pendingApprovals)} actions need approval`, detail: denominator, tone, ctaLabel: "Review approvals", ctaHref: "/operations" };
  }
  if (stats.proven > 0) {
    return { title: `${formatCount(stats.proven)} actions proven`, detail: denominator, tone, ctaLabel: "View evidence", ctaHref: "/evidence" };
  }
  return { title: "No proven actions yet", detail: denominator, tone, ctaLabel: "Connect source", ctaHref: "/integrations" };
}

function TrustMachineHealth({ items, loading }: { items: TrustHealthItem[]; loading: boolean }) {
  return (
    <section className="mc-agent-health-panel mc-trust-health" aria-label="Trust-machine health">
      <div className="mc-agent-health-copy">
        <div>
          <p className="mc-eyebrow">Trust-machine health</p>
          <h2>Can Zroky prove the numbers above?</h2>
        </div>
        <p>Green metrics are only trustworthy when source reads, executors, and evidence signing are healthy.</p>
      </div>
      <div className="mc-agent-health-breakdown">
        {loading
          ? Array.from({ length: 4 }).map((_, index) => (
              <div key={index}>
                <span className="mc-skeleton mc-skeleton-label" />
                <strong className="mc-skeleton mc-skeleton-line" />
              </div>
            ))
          : items.map((item) => (
              <div data-tone={item.tone} key={item.id}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.detail}</small>
              </div>
            ))}
      </div>
    </section>
  );
}

function missionDataFromSummary(summary: HomeSummaryResponse): MissionData {
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
  };
}

function availabilityFromSummary(summary: HomeSummaryResponse): MissionAvailability {
  const sources = summary.sources;
  if (!sources) {
    return ALL_SOURCES_AVAILABLE;
  }
  return {
    homeSummary: sources.home_summary,
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

function unavailableSourceCount(availability: MissionAvailability): number {
  return Object.values(availability).filter((value) => !value).length;
}

export default function HomePage() {
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const dateRange = useDashboardStore((state) => state.dateRange);
  const summaryDays = useMemo(() => homeWindowDays(dateRange), [dateRange]);
  const [data, setData] = useState<MissionData>(EMPTY_DATA);
  const [availability, setAvailability] = useState<MissionAvailability>(NO_SOURCES_AVAILABLE);
  const [isLoading, setIsLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const summary = await getHomeSummary(summaryDays, signal);
      if (signal?.aborted) {
        return;
      }
      const nextAvailability = availabilityFromSummary(summary);
      setData(missionDataFromSummary(summary));
      setAvailability(nextAvailability);
      setLoadErrors(unavailableSourceCount(nextAvailability));
      setLastLoadedAt(new Date().toISOString());
    } catch {
      if (signal?.aborted) {
        return;
      }
      setData(EMPTY_DATA);
      setAvailability(NO_SOURCES_AVAILABLE);
      setLoadErrors(1);
      setLastLoadedAt(null);
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, [summaryDays]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (!realTimeEnabled) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      const controller = new AbortController();
      void load(controller.signal);
    }, 30_000);
    return () => window.clearInterval(interval);
  }, [load, realTimeEnabled]);

  const rows = useMemo(
    () =>
      buildDecisionQueue({
        intents: data.intents,
        approvals: data.approvals,
        outcomes: data.outcomes,
        mutations: data.mutations,
        staleAttempts: data.staleAttempts,
        nowMs: lastLoadedAt ? new Date(lastLoadedAt).getTime() : Date.now(),
      }),
    [data.approvals, data.intents, data.mutations, data.outcomes, data.staleAttempts, lastLoadedAt],
  );

  const fleet = useMemo(() => buildFleetView({
    profiles: data.agentProfiles,
    profileMeta: data.agentProfileMeta,
    intents: data.intents,
    decisions: data.approvals,
    outcomes: data.outcomes,
    runners: data.actionRunners,
    attempts: data.staleAttempts,
    staleAttemptIds: data.staleAttempts.map((attempt) => attempt.attempt_id),
  }), [
    data.actionRunners,
    data.agentProfileMeta,
    data.agentProfiles,
    data.approvals,
    data.intents,
    data.outcomes,
    data.staleAttempts,
  ]);

  const signals = firstRunSignals(data);
  const homeUnlocked = hasProtectedActionSignal(signals);
  const metrics = proofMetrics(data, availability);
  const trustItems = trustHealth(data, availability);
  const verdict = homeVerdict(data, trustItems, loadErrors, homeUnlocked);
  const healthWindow = useMemo(() => {
    const generatedAt = data.homeSummary?.generated_at ?? lastLoadedAt ?? new Date().toISOString();
    const generatedAtMs = new Date(generatedAt).getTime();
    const safeGeneratedAtMs = Number.isFinite(generatedAtMs) ? generatedAtMs : Date.now();
    return {
      windowDays: data.homeSummary?.window_days ?? summaryDays,
      windowStart: data.homeSummary?.window_start ?? new Date(safeGeneratedAtMs - summaryDays * MS_PER_DAY).toISOString(),
      generatedAt: new Date(safeGeneratedAtMs).toISOString(),
    };
  }, [data.homeSummary, lastLoadedAt, summaryDays]);
  const initialLoading = isLoading && lastLoadedAt == null;
  const showFirstRun = !initialLoading && !signals.hasProofSignal && (
    !signals.hasVerificationConnected ||
    !signals.hasAssurancePack ||
    !signals.hasActiveAgent ||
    !signals.hasProofSignal
  );
  const updatedLabel = lastLoadedAt ? `Updated ${timeSince(lastLoadedAt)}` : "Loading";

  return (
    <main className="mission-control-page">
      <div className="mc-shell">
        <VerdictHero
          verdict={verdict}
          updatedLabel={updatedLabel}
          loading={isLoading}
          errorCount={loadErrors}
          hideCta={showFirstRun}
          quotaWarning={quotaWarning(data.billingUsage)}
          onRefresh={() => void load()}
        />

        {showFirstRun ? <FirstRunPanel signals={signals} /> : null}
        <ProofStrip metrics={metrics} loading={initialLoading} />
        {!showFirstRun ? <DecisionQueue rows={rows} selectedId={null} loading={initialLoading} /> : null}
        <TrustMachineHealth items={trustItems} loading={initialLoading} />
        <AgentHealthTimeline
          loading={initialLoading}
          windowDays={healthWindow.windowDays}
          windowStart={healthWindow.windowStart}
          generatedAt={healthWindow.generatedAt}
          intents={data.intents}
          approvals={data.approvals}
          outcomes={data.outcomes}
          mutations={data.mutations}
          staleAttempts={data.staleAttempts}
          fleet={fleet}
        />
        <HomeActivitySections
          intents={data.intents}
          approvals={data.approvals}
          outcomes={data.outcomes}
          loading={initialLoading}
        />

      </div>
    </main>
  );
}
