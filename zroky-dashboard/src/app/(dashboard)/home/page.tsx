"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getBillingUsage,
  getOutcomeReconciliationSummary,
  getSourceMutationSummary,
  listActionRunners,
  listActionIntents,
  listAgentProfiles,
  listOutcomeReconciliations,
  listProjectActionExecutionAttempts,
  listProjectApiKeys,
  listRuntimePolicyApprovals,
  listUnreceiptedSourceMutations,
  type ActionExecutionAttemptResponse,
  type ActionIntentResponse,
  type ActionRunnerResponse,
  type AgentProfileListResponse,
  type AgentProfileResponse,
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

import { ControlLoopStrip } from "./ControlLoopStrip";
import { DecisionQueue, type HomeQueueFilter } from "./DecisionQueue";
import { FleetContextLine } from "./FleetContextLine";
import { FirstRunPanel } from "./FirstRunPanel";
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
};

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
};

const STALE_ATTEMPT_SECONDS = 600;

function valueOr<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function errorCount(results: PromiseSettledResult<unknown>[]): number {
  return results.filter((result) => result.status === "rejected").length;
}

function hasProjectSetup(data: MissionData): boolean {
  return (
    data.apiKeys.some((key) => !key.revoked && !key.expired) ||
    data.agentProfiles.some((profile) => profile.is_active) ||
    (data.agentProfileMeta?.active_count ?? 0) > 0 ||
    data.intents.length > 0 ||
    data.approvals.length > 0 ||
    data.outcomes.length > 0
  );
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

function proofMetrics(data: MissionData): ProofMetric[] {
  const totalChecks = data.outcomeSummary?.total ?? 0;
  const matchedChecks = data.outcomeSummary?.matched ?? 0;
  const matchedRate = totalChecks > 0 ? (matchedChecks / totalChecks) * 100 : null;
  const bypassRisk = data.sourceSummary?.unreceipted ?? data.mutations.length;

  return [
    {
      id: "controlled-actions",
      label: "Controlled actions",
      value: formatCount(data.intents.length),
      detail: "Action intents in the current window",
      href: "/actions",
      tone: "neutral",
    },
    {
      id: "pending-approvals",
      label: "Pending approvals",
      value: formatCount(data.approvals.length),
      detail: "Human decisions waiting",
      href: "/approvals",
      tone: data.approvals.length > 0 ? "warning" : "success",
    },
    {
      id: "verified-outcomes",
      label: "Verified outcomes",
      value: totalChecks > 0 ? `${formatPercent(matchedRate)} matched` : "No checks",
      detail: `${formatCount(matchedChecks)} matched / ${formatCount(totalChecks)} checks`,
      href: "/outcomes",
      tone: totalChecks > 0 && matchedChecks === totalChecks ? "success" : totalChecks > 0 ? "warning" : "neutral",
    },
    {
      id: "bypass-risk",
      label: "Bypass risk",
      value: formatCount(bypassRisk),
      detail: "Unreceipted source mutations",
      href: "/outcomes",
      tone: bypassRisk > 0 ? "danger" : "success",
    },
  ];
}

export default function HomePage() {
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const [data, setData] = useState<MissionData>(EMPTY_DATA);
  const [isLoading, setIsLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [filter, setFilter] = useState<HomeQueueFilter>("all");

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    const results = await Promise.allSettled([
      listActionIntents({ limit: 75 }, signal),
      listRuntimePolicyApprovals("pending_approval", signal),
      listOutcomeReconciliations({ verdict: "all", limit: 75 }, signal),
      getOutcomeReconciliationSummary(30, signal),
      getSourceMutationSummary(signal),
      listUnreceiptedSourceMutations(75, signal),
      listProjectActionExecutionAttempts(
        { status: ["planned", "running"], stale: true, stale_after_seconds: STALE_ATTEMPT_SECONDS, limit: 75 },
        signal,
      ),
      listAgentProfiles({ limit: 200 }, signal),
      listActionRunners(signal),
      selectedProject ? listProjectApiKeys(selectedProject, signal) : Promise.resolve([]),
      getBillingUsage(signal),
    ]);

    if (signal?.aborted) {
      return;
    }

    const [
      intents,
      approvals,
      outcomes,
      outcomeSummary,
      sourceSummary,
      mutations,
      staleAttempts,
      agentProfiles,
      actionRunners,
      apiKeys,
      billingUsage,
    ] = results;

    const agentProfileResult = valueOr(agentProfiles, {
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
      active_count: 0,
      max_active_agents: -1,
      limit_reached: false,
    });

    setData({
      intents: valueOr(intents, { items: [], total_in_page: 0, limit: 75, offset: 0 }).items,
      approvals: valueOr(approvals, { items: [], total_in_page: 0 }).items,
      outcomes: valueOr(outcomes, { items: [], total_in_page: 0 }).items,
      outcomeSummary: valueOr(outcomeSummary, null),
      sourceSummary: valueOr(sourceSummary, null),
      mutations: valueOr(mutations, { items: [], total_in_page: 0 }).items,
      staleAttempts: valueOr(staleAttempts, { items: [] }).items,
      agentProfiles: agentProfileResult.items,
      agentProfileMeta: agentProfileResult,
      actionRunners: valueOr(actionRunners, { items: [] }).items,
      apiKeys: valueOr(apiKeys, []),
      billingUsage: valueOr(billingUsage, null),
    });
    setLoadErrors(errorCount(results));
    setLastLoadedAt(new Date().toISOString());
    setIsLoading(false);
  }, [selectedProject]);

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

  const setupComplete = hasProjectSetup(data);
  const verdict = homeVerdictForQueue(rows, setupComplete);
  const metrics = proofMetrics(data);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0] ?? null;
  const selectedIntent = selectedRow?.actionId
    ? data.intents.find((intent) => intent.action_id === selectedRow.actionId) ?? null
    : null;
  const initialLoading = isLoading && lastLoadedAt == null;
  const showFirstRun = !setupComplete && !initialLoading;
  const updatedLabel = lastLoadedAt ? `Updated ${timeSince(lastLoadedAt)}` : "Loading";

  const dashboardBody = (
    <>
      <ProofStrip metrics={metrics} loading={initialLoading} />
      <FleetContextLine fleet={fleet} loading={initialLoading} />
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
          <section className="mc-locked-home" aria-label="Locked Home dashboard preview">
            <div className="mc-locked-preview" aria-hidden="true" inert>
              {dashboardBody}
            </div>
            <FirstRunPanel />
          </section>
        ) : (
          dashboardBody
        )}

        <ControlLoopStrip />
      </div>
    </main>
  );
}
