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
import { formatCount, formatPercent, timeSince } from "@/lib/format";
import { buildDecisionQueue, homeVerdictForQueue, type HomeQueueRow } from "@/lib/home-queue";
import { useDashboardStore } from "@/lib/store";
import type { ApiKeyResponse, BillingUsageMeter, BillingUsageResponse } from "@/lib/types";

import { ControlLoopStrip, type ControlLoopStats } from "./ControlLoopStrip";
import { buildControlReadiness, ControlHealthPanel, firstMissingControl } from "./ControlHealthPanel";
import { DecisionQueue, type HomeQueueFilter } from "./DecisionQueue";
import { FleetContextLine } from "./FleetContextLine";
import { FirstRunPanel, type FirstRunSignals } from "./FirstRunPanel";
import { ProofStrip, type ProofMetric } from "./ProofStrip";
import { SelectedProofRail } from "./SelectedProofRail";
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
  controlHealth: NonNullable<NonNullable<HomeSummaryResponse["data"]>["control_health"]> | null;
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
  controlHealth: null,
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
  const setupAgent = data.agentProfiles.find((profile) => profile.metadata?.setup_source === "agent_control_setup_wizard")
    ?? data.agentProfiles.find((profile) => profile.is_active)
    ?? data.agentProfiles[0]
    ?? null;
  const hasProjectKey = data.apiKeys.some((key) => !key.revoked && !key.expired);
  const hasActiveAgent = data.agentProfiles.some((profile) => profile.is_active) || (data.agentProfileMeta?.active_count ?? 0) > 0;
  const hasInstalledActions = data.agentProfiles.some((profile) => (
    typeof profile.metadata?.setup_action_pack_id === "string" && profile.metadata.setup_action_pack_id.trim().length > 0
  ));
  const hasActionIntent = data.intents.length > 0;
  const hasProofSignal =
    data.approvals.length > 0 ||
    data.outcomes.length > 0 ||
    (data.sourceSummary?.matched_receipt ?? 0) > 0 ||
    data.intents.some((intent) => intent.receipt_status === "generated" || ["matched", "mismatched"].includes(intent.proof_status));

  return {
    agentId: setupAgent?.id ?? null,
    hasProjectKey,
    hasActiveAgent,
    hasInstalledActions,
    hasActionIntent,
    hasProofSignal,
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

function proofMetrics(data: MissionData, availability: MissionAvailability): ProofMetric[] {
  const summary = data.homeSummary;
  if (!availability.homeSummary || !summary) {
    return [
      unavailableProofMetric("controlled-actions", "Controlled actions", "Home summary unavailable", "/actions"),
      unavailableProofMetric("pending-approvals", "Pending approvals", "Home summary unavailable", "/approvals"),
      unavailableProofMetric("verified-outcomes", "Verified outcomes", "Home summary unavailable", "/outcomes"),
      unavailableProofMetric("bypass-risk", "Bypass risk", "Home summary unavailable", "/outcomes"),
    ];
  }
  const totalChecks = summary?.metrics.outcome_checks ?? 0;
  const matchedChecks = summary?.metrics.verified_outcomes ?? 0;
  const matchedRate = totalChecks > 0 ? (matchedChecks / totalChecks) * 100 : null;
  const bypassRisk = summary?.metrics.unreceipted_mutations ?? 0;
  const windowLabel = summary ? `Last ${summary.window_days} days` : "Summary unavailable";

  return [
    {
      id: "controlled-actions",
      label: "Controlled actions",
      value: formatCount(summary.metrics.controlled_actions),
      detail: windowLabel,
      href: "/actions",
      tone: "neutral",
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
      id: "verified-outcomes",
      label: "Verified outcomes",
      value: totalChecks > 0 ? `${formatPercent(matchedRate)} matched` : "No checks",
      detail: `${formatCount(matchedChecks)} matched / ${formatCount(totalChecks)} checks, ${windowLabel.toLowerCase()}`,
      href: "/outcomes",
      tone: totalChecks > 0 && matchedChecks === totalChecks ? "success" : totalChecks > 0 ? "warning" : "neutral",
    },
    {
      id: "bypass-risk",
      label: "Bypass risk",
      value: formatCount(bypassRisk),
      detail: `Unreceipted mutations, ${windowLabel.toLowerCase()}`,
      href: "/outcomes",
      tone: bypassRisk > 0 ? "danger" : "success",
    },
  ];
}

function controlLoopStats(data: MissionData, availability: MissionAvailability): ControlLoopStats {
  const summary = data.homeSummary;
  if (!availability.homeSummary || !summary) {
    return {
      actionCount: null,
      approvalCount: null,
      verifiedCount: null,
      receiptCount: null,
      bypassCount: null,
      sequenceRiskCount: null,
    };
  }

  return {
    actionCount: summary.metrics.controlled_actions,
    approvalCount: summary.metrics.pending_approvals,
    verifiedCount: summary.metrics.verified_outcomes,
    receiptCount: summary.metrics.receipts_generated,
    bypassCount: summary.metrics.bypass_mutations,
    sequenceRiskCount: summary.metrics.sequence_risks,
  };
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
    controlHealth: details?.control_health ?? null,
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
  const [data, setData] = useState<MissionData>(EMPTY_DATA);
  const [availability, setAvailability] = useState<MissionAvailability>(NO_SOURCES_AVAILABLE);
  const [isLoading, setIsLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [filter, setFilter] = useState<HomeQueueFilter>("all");

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const summary = await getHomeSummary(30, signal);
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
  }, []);

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
  useEffect(() => {
    if (rows.length === 0) {
      setSelectedRowId(null);
      return;
    }
    if (!selectedRowId || !rows.some((row) => row.id === selectedRowId)) {
      setSelectedRowId(rows[0].id);
    }
  }, [rows, selectedRowId]);

  const signals = firstRunSignals(data);
  const homeUnlocked = hasProtectedActionSignal(signals);
  const readiness = buildControlReadiness(data.controlHealth, data.homeSummary?.metrics.receipts_generated ?? 0);
  const missingControl = firstMissingControl(readiness);
  const verdict = homeVerdictForQueue(rows, homeUnlocked, missingControl ?? undefined);
  const metrics = proofMetrics(data, availability);
  const loopStats = controlLoopStats(data, availability);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0] ?? null;
  const selectedIntent = selectedRow?.actionId
    ? data.intents.find((intent) => intent.action_id === selectedRow.actionId) ?? null
    : null;
  const initialLoading = isLoading && lastLoadedAt == null;
  const showFirstRun = !homeUnlocked && !initialLoading;
  const updatedLabel = lastLoadedAt ? `Updated ${timeSince(lastLoadedAt)}` : "Loading";

  const liveDashboardBody = (
    <>
      <ProofStrip metrics={metrics} loading={initialLoading} />
      <ControlHealthPanel
        health={data.controlHealth}
        receipts={data.homeSummary?.metrics.receipts_generated ?? 0}
        proof={data.outcomeSummary}
      />
      <FleetContextLine fleet={fleet} loading={initialLoading} />
      <ControlLoopStrip {...loopStats} />
      <div className="mc-main-grid">
        <DecisionQueue
          rows={rows}
          selectedId={selectedRow?.id ?? null}
          filter={filter}
          onFilterChange={setFilter}
          onSelect={(row: HomeQueueRow) => setSelectedRowId(row.id)}
          loading={initialLoading}
        />
        <SelectedProofRail row={selectedRow} intent={selectedIntent} />
      </div>
    </>
  );
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

        {showFirstRun ? (
          <section className="mc-locked-home" aria-label="Home setup required">
            <FirstRunPanel signals={signals} />
          </section>
        ) : (
          liveDashboardBody
        )}

      </div>
    </main>
  );
}
