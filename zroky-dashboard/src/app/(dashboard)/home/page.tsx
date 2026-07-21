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
import { buildDecisionQueue, homeVerdictForQueue } from "@/lib/home-queue";
import { useDashboardStore } from "@/lib/store";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

import { AgentHealthTimeline } from "./AgentHealthTimeline";
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
  const hasVerificationConnected = data.outcomes.length > 0 || (data.outcomeSummary?.total ?? 0) > 0 || (data.sourceSummary?.matched_receipt ?? 0) > 0;
  const hasActionIntent = data.intents.length > 0;
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

function proofMetrics(data: MissionData, availability: MissionAvailability, protectedAgentCount: number): ProofMetric[] {
  const summary = data.homeSummary;
  if (!availability.homeSummary || !summary) {
    return [
      availability.agentProfiles
        ? {
            id: "agents-protected",
            label: "Agents protected",
            value: formatCount(protectedAgentCount),
            detail: protectedAgentCount > 0 ? "Active managed agents" : "No agents protected yet",
            href: "/operations",
            tone: protectedAgentCount > 0 ? "success" : "warning",
          }
        : unavailableProofMetric("agents-protected", "Agents protected", "Agent data unavailable", "/operations"),
      unavailableProofMetric("controlled-actions", "Actions controlled", "Home summary unavailable", "/operations"),
      unavailableProofMetric("pending-approvals", "Pending approvals", "Home summary unavailable", "/approvals"),
      unavailableProofMetric("proof-generated", "Proof generated", "Home summary unavailable", "/evidence"),
    ];
  }
  const receiptsGenerated = summary?.metrics.receipts_generated ?? 0;
  const windowLabel = summary ? `Last ${summary.window_days} days` : "Summary unavailable";

  return [
    {
      id: "agents-protected",
      label: "Agents protected",
      value: formatCount(protectedAgentCount),
      detail: protectedAgentCount > 0 ? "Active managed agents" : "No agents protected yet",
      href: "/operations",
      tone: protectedAgentCount > 0 ? "success" : "warning",
    },
    {
      id: "controlled-actions",
      label: "Actions controlled",
      value: formatCount(summary.metrics.controlled_actions),
      detail: windowLabel,
      href: "/operations",
      tone: summary.metrics.controlled_actions > 0 ? "success" : "neutral",
    },
    {
      id: "pending-approvals",
      label: "Pending approvals",
      value: formatCount(summary.metrics.pending_approvals),
      detail: "Open approval queue",
      href: "/approvals",
      tone: summary.metrics.pending_approvals > 0 ? "warning" : "success",
    },
    {
      id: "proof-generated",
      label: "Proof generated",
      value: formatCount(receiptsGenerated),
      detail: `Receipts generated, ${windowLabel.toLowerCase()}`,
      href: "/evidence",
      tone: receiptsGenerated > 0 ? "success" : "neutral",
    },
  ];
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
  const verdict = homeVerdictForQueue(rows, homeUnlocked);
  const protectedAgentCount = data.agentProfileMeta?.active_count ?? data.agentProfiles.filter((profile) => profile.is_active).length;
  const metrics = proofMetrics(data, availability, protectedAgentCount);
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
  const showFirstRun = !initialLoading && (
    !signals.hasRunnerConnected ||
    !signals.hasVerificationConnected ||
    !signals.hasActionIntent ||
    !signals.hasReceiptGenerated
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

        <ProofStrip metrics={metrics} loading={initialLoading} />
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
        {showFirstRun ? <FirstRunPanel signals={signals} /> : null}
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
