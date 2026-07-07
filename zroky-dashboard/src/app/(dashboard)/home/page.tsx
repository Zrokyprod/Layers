"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getBillingUsage,
  getHomeSummary,
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

const PREVIEW_TIME = "2026-07-02T16:30:00.000Z";

const FIRST_RUN_PREVIEW_DATA: MissionData = {
  intents: [
    {
      action_id: "act_preview_refund",
      project_id: "proj_preview",
      agent_id: "agent_preview_refunds",
      agent_profile: {
        id: "agent_preview_refunds",
        display_name: "Refund Agent",
        slug: "refund-agent",
        runtime_path: "sdk",
        environment: "production",
      },
      contract_version: "refund.issue.v1",
      action_type: "ledger.refund.issue",
      operation_kind: "TRANSFER",
      environment: "production",
      status: "approval_pending",
      proof_status: "pending",
      receipt_status: "pending",
      idempotency_key: "preview_refund_1",
      intent_digest: "sha256:preview-refund-digest",
      canonical_intent: {
        purpose: { summary: "Refund high-value invoice after policy check" },
        principal: { id: "refund-agent" },
        resource: { id: "refund_9182", type: "ledger_refund" },
        trace_context: { agent_name: "refund-agent", trace_id: "trace_preview_refund" },
      },
      created_at: PREVIEW_TIME,
      decided_at: PREVIEW_TIME,
      authorized_at: null,
      runtime_policy_decision_id: "decision_preview_refund",
      deadline: null,
      status_url: "/v1/action-intents/act_preview_refund",
    },
    {
      action_id: "act_preview_customer",
      project_id: "proj_preview",
      agent_id: "agent_preview_success",
      contract_version: "customer.update.v1",
      action_type: "crm.customer.update",
      operation_kind: "UPDATE",
      environment: "production",
      status: "authorized",
      proof_status: "matched",
      receipt_status: "generated",
      idempotency_key: "preview_customer_1",
      intent_digest: "sha256:preview-customer-digest",
      canonical_intent: {
        purpose: { summary: "Update verified customer status" },
        principal: { id: "crm-agent" },
        resource: { id: "customer_42", type: "crm_customer" },
        trace_context: { agent_name: "crm-agent", trace_id: "trace_preview_customer" },
      },
      created_at: "2026-07-02T16:12:00.000Z",
      decided_at: "2026-07-02T16:12:03.000Z",
      authorized_at: "2026-07-02T16:12:03.000Z",
      runtime_policy_decision_id: "decision_preview_customer",
      deadline: null,
      status_url: "/v1/action-intents/act_preview_customer",
    },
  ],
  approvals: [
    {
      id: "decision_preview_refund",
      project_id: "proj_preview",
      trace_id: "trace_preview_refund",
      call_id: null,
      agent_name: "refund-agent",
      role: "agent",
      action_type: "ledger.refund.issue",
      tool_name: "ledger.refunds.create",
      decision: "requires_approval",
      status: "pending_approval",
      allowed: false,
      requires_approval: true,
      reasons: ["sequence risk: repeated money movement in one run"],
      request: { amount_usd: 1280 },
      policy_snapshot: {},
      intended_action: { summary: "Issue refund for invoice INV-9182", amount_usd: 1280 },
      trace_context: { trace_id: "trace_preview_refund" },
      policy_hit: { sequence_risk: { pattern: "fund_drain" } },
      business_impact: { amount_usd: 1280, risk: "high" },
      audit_log: [],
      created_at: PREVIEW_TIME,
      expires_at: "2026-07-02T17:30:00.000Z",
      resolved_at: null,
      resolved_by: null,
      resolution_reason: null,
      consumed_at: null,
      consumed_by_decision_id: null,
      required_approval_count: 1,
      approval_count: 0,
      approver_subjects: [],
    },
  ],
  outcomes: [
    {
      id: "outcome_preview_customer",
      project_id: "proj_preview",
      call_id: null,
      trace_id: "trace_preview_customer",
      runtime_policy_decision_id: "decision_preview_customer",
      action_type: "crm.customer.update",
      connector_type: "generic_rest",
      system_ref: "customer_42",
      verdict: "matched",
      verification_status: "matched",
      reason: "source record matched signed receipt",
      amount_usd: null,
      currency: null,
      claimed: { status: "verified" },
      actual: { status: "verified" },
      comparison: {},
      idempotency_key: "preview_customer_1",
      metadata: {},
      checked_at: "2026-07-02T16:12:12.000Z",
      created_at: "2026-07-02T16:12:12.000Z",
    },
  ],
  outcomeSummary: {
    window_days: 30,
    total: 12,
    matched: 11,
    mismatched: 1,
    not_verified: 0,
  },
  sourceSummary: {
    total: 18,
    matched_receipt: 17,
    authorized_external: 1,
    legacy_path: 0,
    unmanaged_agent_action: 0,
    policy_bypass: 1,
    unknown_actor: 0,
    unreceipted: 1,
  },
  mutations: [
    {
      id: "mutation_preview_bypass",
      project_id: "proj_preview",
      source_system: "crm",
      mutation_id: "crm_mutation_77",
      action_type: "customer.export",
      resource_type: "customer_segment",
      resource_id: "segment_enterprise",
      system_ref: "segment_enterprise",
      actor_type: "agent",
      actor_id: "legacy-export-agent",
      zroky_action_id: null,
      action_receipt_id: null,
      idempotency_key: null,
      classification: "policy_bypass",
      metadata: {},
      occurred_at: "2026-07-02T16:03:00.000Z",
      created_at: "2026-07-02T16:03:00.000Z",
    },
  ],
  staleAttempts: [],
  agentProfiles: [
    {
      schema_version: "zroky.agent_tool_control.v1",
      id: "agent_preview_refunds",
      project_id: "proj_preview",
      display_name: "Refund Agent",
      slug: "refund-agent",
      description: "Handles high-risk refund actions with approval gates.",
      runtime_path: "sdk",
      framework: "langgraph",
      environment: "production",
      model_provider: "openai",
      model_name: "gpt-4.1",
      tool_names: ["ledger.refunds.create", "crm.customer.update"],
      allowed_action_types: ["refund", "customer_record_update"],
      blocked_action_types: [],
      default_policy_id: null,
      risk_limits: {},
      verification_connectors: ["ledger_refund", "generic_rest"],
      metadata: { agent_name: "refund-agent" },
      is_active: true,
      created_at: "2026-07-02T15:40:00.000Z",
      updated_at: PREVIEW_TIME,
    },
  ],
  agentProfileMeta: {
    active_count: 1,
    max_active_agents: 3,
    limit_reached: false,
  },
  actionRunners: [
    {
      runner_id: "runner_preview_primary",
      project_id: "proj_preview",
      name: "Production runner",
      runner_type: "customer_hosted",
      environment: "production",
      status: "online",
      supported_operation_kinds: ["UPDATE", "TRANSFER"],
      credential_scope: {},
      heartbeat_payload: {},
      capability_version: "2026-07-02",
      last_heartbeat_at: PREVIEW_TIME,
      created_at: "2026-07-02T15:40:00.000Z",
      updated_at: PREVIEW_TIME,
    },
  ],
  apiKeys: [
    {
      key_id: "key_preview",
      project_id: "proj_preview",
      name: "Production verified-action key",
      key_prefix: "zk_live_preview",
      scopes: ["project:member"],
      revoked: false,
      expired: false,
      expires_at: null,
      rotated_from_key_id: null,
      last_used_at: PREVIEW_TIME,
      created_at: "2026-07-02T15:30:00.000Z",
    },
  ],
  billingUsage: null,
  homeSummary: {
    project_id: "proj_preview",
    window_days: 30,
    window_start: "2026-06-02T16:30:00.000Z",
    generated_at: PREVIEW_TIME,
    metrics: {
      controlled_actions: 2,
      pending_approvals: 1,
      verified_outcomes: 1,
      outcome_checks: 2,
      receipts_generated: 1,
      bypass_mutations: 1,
      unreceipted_mutations: 1,
      sequence_risks: 1,
    },
  },
};

const STALE_ATTEMPT_SECONDS = 600;

function valueOr<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function available(result: PromiseSettledResult<unknown>): boolean {
  return result.status === "fulfilled";
}

function errorCount(results: PromiseSettledResult<unknown>[]): number {
  return results.filter((result) => result.status === "rejected").length;
}

function firstRunSignals(data: MissionData): FirstRunSignals {
  const hasProjectKey = data.apiKeys.some((key) => !key.revoked && !key.expired);
  const hasActiveAgent = data.agentProfiles.some((profile) => profile.is_active) || (data.agentProfileMeta?.active_count ?? 0) > 0;
  const hasActionIntent = data.intents.length > 0;
  const hasProofSignal =
    data.approvals.length > 0 ||
    data.outcomes.length > 0 ||
    (data.sourceSummary?.matched_receipt ?? 0) > 0 ||
    data.intents.some((intent) => intent.receipt_status === "generated" || ["matched", "mismatched"].includes(intent.proof_status));

  return {
    hasProjectKey,
    hasActiveAgent,
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
  const summaryAvailable = Boolean(availability.homeSummary && summary);
  const totalChecks = summary?.metrics.outcome_checks ?? 0;
  const matchedChecks = summary?.metrics.verified_outcomes ?? 0;
  const matchedRate = totalChecks > 0 ? (matchedChecks / totalChecks) * 100 : null;
  const bypassRisk = summary?.metrics.unreceipted_mutations ?? 0;
  const windowLabel = summary ? `Last ${summary.window_days} days` : "Summary unavailable";

  return [
    summaryAvailable
      ? {
          id: "controlled-actions",
          label: "Controlled actions",
          value: formatCount(summary.metrics.controlled_actions),
          detail: windowLabel,
          href: "/actions",
          tone: "neutral",
        }
      : unavailableProofMetric("controlled-actions", "Controlled actions", "Home summary unavailable", "/actions"),
    summaryAvailable
      ? {
          id: "pending-approvals",
          label: "Pending approvals",
          value: formatCount(summary.metrics.pending_approvals),
          detail: "Open approval queue",
          href: "/approvals",
          tone: summary.metrics.pending_approvals > 0 ? "warning" : "success",
        }
      : unavailableProofMetric("pending-approvals", "Pending approvals", "Home summary unavailable", "/approvals"),
    summaryAvailable
      ? {
          id: "verified-outcomes",
          label: "Verified outcomes",
          value: totalChecks > 0 ? `${formatPercent(matchedRate)} matched` : "No checks",
          detail: `${formatCount(matchedChecks)} matched / ${formatCount(totalChecks)} checks, ${windowLabel.toLowerCase()}`,
          href: "/outcomes",
          tone: totalChecks > 0 && matchedChecks === totalChecks ? "success" : totalChecks > 0 ? "warning" : "neutral",
        }
      : unavailableProofMetric("verified-outcomes", "Verified outcomes", "Home summary unavailable", "/outcomes"),
    summaryAvailable
      ? {
          id: "bypass-risk",
          label: "Bypass risk",
          value: formatCount(bypassRisk),
          detail: `Unreceipted mutations, ${windowLabel.toLowerCase()}`,
          href: "/outcomes",
          tone: bypassRisk > 0 ? "danger" : "success",
        }
      : unavailableProofMetric("bypass-risk", "Bypass risk", "Home summary unavailable", "/outcomes"),
  ];
}

function controlLoopStats(data: MissionData, availability: MissionAvailability): ControlLoopStats {
  const summary = data.homeSummary;
  const summaryAvailable = Boolean(availability.homeSummary && summary);

  return {
    actionCount: summaryAvailable ? summary.metrics.controlled_actions : null,
    approvalCount: summaryAvailable ? summary.metrics.pending_approvals : null,
    verifiedCount: summaryAvailable ? summary.metrics.verified_outcomes : null,
    receiptCount: summaryAvailable ? summary.metrics.receipts_generated : null,
    bypassCount: summaryAvailable ? summary.metrics.bypass_mutations : null,
    sequenceRiskCount: summaryAvailable ? summary.metrics.sequence_risks : null,
  };
}

export default function HomePage() {
  const selectedProject = useDashboardStore((state) => state.selectedProject);
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
    const results = await Promise.allSettled([
      getHomeSummary(30, signal),
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
      homeSummary,
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
      homeSummary: valueOr(homeSummary, null),
    });
    setAvailability({
      homeSummary: available(homeSummary),
      intents: available(intents),
      approvals: available(approvals),
      outcomes: available(outcomes),
      outcomeSummary: available(outcomeSummary),
      sourceSummary: available(sourceSummary),
      mutations: available(mutations),
      staleAttempts: available(staleAttempts),
      agentProfiles: available(agentProfiles),
      actionRunners: available(actionRunners),
      apiKeys: available(apiKeys),
      billingUsage: available(billingUsage),
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
  const previewRows = useMemo(
    () =>
      buildDecisionQueue({
        intents: FIRST_RUN_PREVIEW_DATA.intents,
        approvals: FIRST_RUN_PREVIEW_DATA.approvals,
        outcomes: FIRST_RUN_PREVIEW_DATA.outcomes,
        mutations: FIRST_RUN_PREVIEW_DATA.mutations,
        staleAttempts: FIRST_RUN_PREVIEW_DATA.staleAttempts,
        nowMs: new Date(PREVIEW_TIME).getTime(),
      }),
    [],
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
  const previewFleet = useMemo(() => buildFleetView({
    profiles: FIRST_RUN_PREVIEW_DATA.agentProfiles,
    profileMeta: FIRST_RUN_PREVIEW_DATA.agentProfileMeta,
    intents: FIRST_RUN_PREVIEW_DATA.intents,
    decisions: FIRST_RUN_PREVIEW_DATA.approvals,
    outcomes: FIRST_RUN_PREVIEW_DATA.outcomes,
    runners: FIRST_RUN_PREVIEW_DATA.actionRunners,
    attempts: FIRST_RUN_PREVIEW_DATA.staleAttempts,
    staleAttemptIds: [],
  }), []);

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
  const verdict = homeVerdictForQueue(rows, homeUnlocked);
  const metrics = proofMetrics(data, availability);
  const previewMetrics = proofMetrics(FIRST_RUN_PREVIEW_DATA, ALL_SOURCES_AVAILABLE);
  const loopStats = controlLoopStats(data, availability);
  const previewLoopStats = controlLoopStats(FIRST_RUN_PREVIEW_DATA, ALL_SOURCES_AVAILABLE);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0] ?? null;
  const selectedIntent = selectedRow?.actionId
    ? data.intents.find((intent) => intent.action_id === selectedRow.actionId) ?? null
    : null;
  const selectedPreviewRow = previewRows[0] ?? null;
  const selectedPreviewIntent = selectedPreviewRow?.actionId
    ? FIRST_RUN_PREVIEW_DATA.intents.find((intent) => intent.action_id === selectedPreviewRow.actionId) ?? null
    : null;
  const initialLoading = isLoading && lastLoadedAt == null;
  const showFirstRun = !homeUnlocked && !initialLoading;
  const updatedLabel = lastLoadedAt ? `Updated ${timeSince(lastLoadedAt)}` : "Loading";

  const liveDashboardBody = (
    <>
      <ProofStrip metrics={metrics} loading={initialLoading} />
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
  const previewDashboardBody = (
    <>
      <ProofStrip metrics={previewMetrics} loading={false} />
      <FleetContextLine fleet={previewFleet} loading={false} />
      <ControlLoopStrip {...previewLoopStats} />
      <div className="mc-main-grid">
        <DecisionQueue
          rows={previewRows}
          selectedId={selectedPreviewRow?.id ?? null}
          filter="all"
          onFilterChange={() => undefined}
          onSelect={() => undefined}
          loading={false}
        />
        <SelectedProofRail row={selectedPreviewRow} intent={selectedPreviewIntent} />
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
              {previewDashboardBody}
            </div>
            <FirstRunPanel signals={signals} />
          </section>
        ) : (
          liveDashboardBody
        )}

      </div>
    </main>
  );
}
