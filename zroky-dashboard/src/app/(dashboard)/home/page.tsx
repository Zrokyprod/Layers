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
import { formatCount, timeSince } from "@/lib/format";
import { buildDecisionQueue, homeVerdictForQueue } from "@/lib/home-queue";
import { useDashboardStore } from "@/lib/store";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

import { AgentRuntimeOverview } from "./AgentRuntimeOverview";
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

function homeWindowLabel(windowDays: number): string {
  return windowDays <= 1 ? "Last 24 hours" : `Last ${windowDays} days`;
}

function normalized(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function protectedAgentCount(data: MissionData): number {
  const activeProfileIds = new Set(
    data.agentProfiles.filter((profile) => profile.is_active).map((profile) => profile.id),
  );
  const onlineRunners = data.actionRunners.filter((runner) => normalized(runner.status) === "online");
  if (activeProfileIds.size === 0 || onlineRunners.length === 0) return 0;

  const protectedProfileIds = new Set<string>();
  for (const intent of data.intents) {
    const profileId = intent.agent_profile?.id ?? intent.agent_id;
    if (!profileId || !activeProfileIds.has(profileId)) continue;

    const intentEnvironment = normalized(intent.agent_profile?.environment ?? intent.environment);
    const operationKind = normalized(intent.operation_kind);
    const hasCompatibleRunner = onlineRunners.some((runner) => {
      const runnerEnvironment = normalized(runner.environment);
      if (
        intentEnvironment &&
        runnerEnvironment &&
        runnerEnvironment !== "all" &&
        runnerEnvironment !== intentEnvironment
      ) {
        return false;
      }
      const supportedKinds = runner.supported_operation_kinds.map(normalized).filter(Boolean);
      return supportedKinds.length === 0 || supportedKinds.includes(operationKind);
    });
    if (hasCompatibleRunner) protectedProfileIds.add(profileId);
  }
  return protectedProfileIds.size;
}

function protectedAgentDetail(protectedCount: number, activeCount: number): string {
  if (protectedCount > 0) return "Recent agents with an online runner";
  if (activeCount > 0) return "Managed agents need an online runner";
  return "No active agents yet";
}

function isCompletedIntent(intent: ActionIntentResponse): boolean {
  const status = normalized(intent.status);
  return (
    intent.receipt_status === "generated" ||
    intent.proof_status === "matched" ||
    ["completed", "executed", "succeeded", "verified"].includes(status)
  );
}

function latestRuntimeActivity(data: MissionData): string | null {
  const timestamps = [
    ...data.actionRunners.flatMap((runner) => [runner.last_heartbeat_at, runner.updated_at]),
    ...data.intents.map((intent) => intent.created_at),
    ...data.approvals.map((decision) => decision.created_at),
    ...data.outcomes.flatMap((outcome) => [outcome.checked_at, outcome.created_at]),
  ].filter((value): value is string => Boolean(value));
  if (timestamps.length === 0) return null;
  return timestamps.reduce((latest, value) => (
    new Date(value).getTime() > new Date(latest).getTime() ? value : latest
  ));
}

function runtimeEnvironment(data: MissionData): string | null {
  return (
    data.actionRunners.find((runner) => normalized(runner.status) === "online")?.environment ??
    data.actionRunners[0]?.environment ??
    data.agentProfiles.find((profile) => profile.is_active)?.environment ??
    data.intents[0]?.environment ??
    process.env.NEXT_PUBLIC_DASHBOARD_ENV ??
    null
  );
}

function proofMetrics(
  data: MissionData,
  availability: MissionAvailability,
  protectedCount: number,
  activeCount: number,
): ProofMetric[] {
  const summary = data.homeSummary;
  if (!availability.homeSummary || !summary) {
    return [
      availability.agentProfiles && availability.actionRunners
        ? {
            id: "agents-protected",
            label: "Agents protected",
            value: formatCount(protectedCount),
            detail: protectedAgentDetail(protectedCount, activeCount),
            href: "/agents",
            tone: protectedCount > 0 ? "success" : "warning",
          }
        : unavailableProofMetric("agents-protected", "Agents protected", "Agent data unavailable", "/agents"),
      unavailableProofMetric("controlled-actions", "Actions controlled", "Home summary unavailable", "/actions"),
      unavailableProofMetric("pending-approvals", "Pending approvals", "Home summary unavailable", "/approvals"),
      unavailableProofMetric("proof-generated", "Proof generated", "Home summary unavailable", "/evidence"),
    ];
  }
  const receiptsGenerated = summary?.metrics.receipts_generated ?? 0;
  const windowLabel = summary ? homeWindowLabel(summary.window_days) : "Summary unavailable";

  return [
    {
      id: "agents-protected",
      label: "Agents protected",
      value: formatCount(protectedCount),
      detail: protectedAgentDetail(protectedCount, activeCount),
      href: "/agents",
      tone: protectedCount > 0 ? "success" : "warning",
    },
    {
      id: "controlled-actions",
      label: "Actions controlled",
      value: formatCount(summary.metrics.controlled_actions),
      detail: windowLabel,
      href: "/actions",
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
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const dateRange = useDashboardStore((state) => state.dateRange);
  const summaryDays = useMemo(() => homeWindowDays(dateRange), [dateRange]);
  const [data, setData] = useState<MissionData>(EMPTY_DATA);
  const [availability, setAvailability] = useState<MissionAvailability>(NO_SOURCES_AVAILABLE);
  const [isLoading, setIsLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const [setupDialogOpen, setSetupDialogOpen] = useState(false);

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

  const signals = firstRunSignals(data);
  const homeUnlocked = hasProtectedActionSignal(signals);
  const verdict = homeVerdictForQueue(rows, homeUnlocked);
  const activeAgentCount = data.agentProfileMeta?.active_count ?? data.agentProfiles.filter((profile) => profile.is_active).length;
  const protectedCount = protectedAgentCount(data);
  const metrics = proofMetrics(data, availability, protectedCount, activeAgentCount);
  const activityWindow = useMemo(() => {
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
  const setupDismissalKey = `zroky.home.setup-dismissed.${selectedProject ?? "default"}`;

  useEffect(() => {
    if (!showFirstRun) {
      setSetupDialogOpen(false);
      return;
    }
    setSetupDialogOpen(window.localStorage.getItem(setupDismissalKey) !== "1");
  }, [setupDismissalKey, showFirstRun]);

  const handleSetupDialogOpenChange = useCallback((open: boolean) => {
    setSetupDialogOpen(open);
    if (!open) {
      window.localStorage.setItem(setupDismissalKey, "1");
    }
  }, [setupDismissalKey]);

  const updatedLabel = lastLoadedAt ? `Updated ${timeSince(lastLoadedAt)}` : "Loading";

  return (
    <main className="mission-control-page fi-home-option-a">
      <div className="mc-shell">
        <VerdictHero
          verdict={verdict}
          updatedLabel={updatedLabel}
          loading={isLoading}
          errorCount={loadErrors}
          hideCta={setupDialogOpen}
          quotaWarning={quotaWarning(data.billingUsage)}
          onRefresh={() => void load()}
        />

        <ProofStrip metrics={metrics} loading={initialLoading} />
        <AgentRuntimeOverview
          loading={initialLoading}
          runnerSourceAvailable={availability.actionRunners}
          hasManagedAgent={activeAgentCount > 0}
          hasOnlineRunner={data.actionRunners.some((runner) => normalized(runner.status) === "online")}
          lastActiveAt={latestRuntimeActivity(data)}
          generatedAt={activityWindow.generatedAt}
          environment={runtimeEnvironment(data)}
          openAttention={
            availability.intents &&
            availability.approvals &&
            availability.outcomes &&
            availability.mutations &&
            availability.staleAttempts
              ? rows.length
              : null
          }
          actionsControlled={availability.homeSummary && data.homeSummary ? data.homeSummary.metrics.controlled_actions : null}
          completedActions={availability.intents ? data.intents.filter(isCompletedIntent).length : null}
          pendingApprovals={availability.homeSummary && data.homeSummary ? data.homeSummary.metrics.pending_approvals : null}
          proofGenerated={availability.homeSummary && data.homeSummary ? data.homeSummary.metrics.receipts_generated : null}
        />
        {showFirstRun ? (
          <FirstRunPanel signals={signals} open={setupDialogOpen} onOpenChange={handleSetupDialogOpenChange} />
        ) : null}
        <HomeActivitySections
          windowStart={activityWindow.windowStart}
          generatedAt={activityWindow.generatedAt}
          intents={data.intents}
          approvals={data.approvals}
          outcomes={data.outcomes}
          staleAttempts={data.staleAttempts}
          loading={initialLoading}
        />

      </div>
    </main>
  );
}
