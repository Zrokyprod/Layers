import type {
  ActionExecutionAttemptResponse,
  ActionIntentResponse,
  ActionRunnerResponse,
  AgentProfileResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
  ToolImplementationStatus,
  ToolRegistryItemResponse,
  ToolRegistryResponse,
} from "@/lib/api";
import {
  agentIdentityKnown,
  buildFleetView,
  type AgentFleetAttemptSummary,
  type AgentFleetRow,
  type AgentFleetRunnerSummary,
} from "@/lib/agent-fleet";
import type { ActionLifecycleRow } from "@/lib/action-lifecycle";
import type { ProofChainStep } from "@/lib/action-view";

export type AgentToolPlanItem = {
  id: string;
  label: string;
  description: string;
  status: ToolImplementationStatus | string;
  tier: string;
  recommended: boolean;
  requiresCredentials: boolean;
  href: string | null;
  capability: string | null;
};

export type AgentToolPlanGroup = {
  id: "runtime_paths" | "verification_connectors" | "native_tool_families";
  label: string;
  items: AgentToolPlanItem[];
};

export type AgentToolPlanSummary = {
  available: number;
  template: number;
  planned: number;
  recommended: number;
};

export type AgentProfileConfig = {
  displayName: string;
  description: string;
  runtimePath: string;
  framework: string;
  environment: string;
  modelProvider: string;
  modelName: string;
  toolNames: string[];
  allowedActionTypes: string[];
  blockedActionTypes: string[];
  defaultPolicyId: string;
  verificationConnectors: string[];
  riskLimits: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type AgentDetailView = {
  profile: AgentProfileResponse;
  row: AgentFleetRow;
  config: AgentProfileConfig;
  latestAction: ActionLifecycleRow | null;
  proofChain: ProofChainStep[];
  runners: ActionRunnerResponse[];
  runnerSummary: AgentFleetRunnerSummary;
  attempts: ActionExecutionAttemptResponse[];
  attemptSummary: AgentFleetAttemptSummary;
  stalledAttemptIds: string[];
  toolPlan: {
    summary: AgentToolPlanSummary;
    groups: AgentToolPlanGroup[];
    nextSteps: string[];
    actionTypes: string[];
  } | null;
};

export type BuildAgentDetailInput = {
  profile: AgentProfileResponse;
  intents?: ActionIntentResponse[];
  decisions?: RuntimePolicyDecisionResponse[];
  outcomes?: OutcomeReconciliationView[];
  runners?: ActionRunnerResponse[];
  attempts?: ActionExecutionAttemptResponse[];
  staleAttemptIds?: string[];
  bypassCoverageAvailable?: boolean;
  toolRegistry?: ToolRegistryResponse | null;
};

function emptyRunnerSummary(): AgentFleetRunnerSummary {
  return { total: 0, online: 0, degraded: 0, offline: 0, disabled: 0, other: 0 };
}

function emptyAttemptSummary(): AgentFleetAttemptSummary {
  return { total: 0, claimable: 0, running: 0, stalled: 0 };
}

function profileConfig(profile: AgentProfileResponse): AgentProfileConfig {
  return {
    displayName: profile.display_name,
    description: profile.description ?? "",
    runtimePath: profile.runtime_path,
    framework: profile.framework ?? "",
    environment: profile.environment ?? "",
    modelProvider: profile.model_provider ?? "",
    modelName: profile.model_name ?? "",
    toolNames: [...profile.tool_names],
    allowedActionTypes: [...profile.allowed_action_types],
    blockedActionTypes: [...profile.blocked_action_types],
    defaultPolicyId: profile.default_policy_id ?? "",
    verificationConnectors: [...profile.verification_connectors],
    riskLimits: { ...profile.risk_limits },
    metadata: { ...profile.metadata },
  };
}

function registryItem(
  item: ToolRegistryItemResponse,
  recommendedIds: Set<string>,
): AgentToolPlanItem {
  return {
    id: item.id,
    label: item.label,
    description: item.description,
    status: item.implementation_status,
    tier: item.launch_tier,
    recommended: recommendedIds.has(item.id),
    requiresCredentials: item.requires_customer_credentials,
    href: item.dashboard_href,
    capability: item.backend_capability,
  };
}

function countSummary(groups: AgentToolPlanGroup[]): AgentToolPlanSummary {
  const summary: AgentToolPlanSummary = {
    available: 0,
    template: 0,
    planned: 0,
    recommended: 0,
  };
  for (const group of groups) {
    for (const item of group.items) {
      if (item.status === "available") summary.available += 1;
      else if (item.status === "template") summary.template += 1;
      else if (item.status === "planned") summary.planned += 1;
      if (item.recommended) summary.recommended += 1;
    }
  }
  return summary;
}

function buildToolPlan(registry: ToolRegistryResponse | null | undefined): AgentDetailView["toolPlan"] {
  if (!registry) return null;

  const runtimeIds = new Set(registry.recommended.runtime_path_ids);
  const connectorIds = new Set(registry.recommended.verification_connector_ids);
  const nativeToolIds = new Set(registry.recommended.native_tool_family_ids);
  const groups: AgentToolPlanGroup[] = [
    {
      id: "runtime_paths",
      label: "Runtime paths",
      items: registry.runtime_paths.map((item) => registryItem(item, runtimeIds)),
    },
    {
      id: "verification_connectors",
      label: "Verification connectors",
      items: registry.verification_connectors.map((item) => registryItem(item, connectorIds)),
    },
    {
      id: "native_tool_families",
      label: "Native tool families",
      items: registry.native_tool_families.map((item) => registryItem(item, nativeToolIds)),
    },
  ];

  return {
    summary: countSummary(groups),
    groups,
    nextSteps: [...registry.recommended.next_steps],
    actionTypes: [...registry.recommended.action_types],
  };
}

function fallbackRow(profile: AgentProfileResponse, bypassCoverageAvailable: boolean): AgentFleetRow {
  return {
    id: `profile:${profile.id}`,
    kind: "profile",
    agentName: profile.display_name,
    identityKnown: agentIdentityKnown(profile.display_name),
    profile,
    telemetryNames: [],
    aliases: [profile.id, profile.slug, profile.display_name],
    status: "profile_ready",
    statusLabel: "Profile ready",
    tone: "neutral",
    actionRollup: {
      total: 0,
      protectedActions: 0,
      bypassed: 0,
      held: 0,
      awaitingRunner: 0,
      executing: 0,
      stalled: 0,
      matched: 0,
      mismatched: 0,
      notVerified: 0,
      receiptsGenerated: 0,
      receiptsMissing: 0,
    },
    coverage: {
      available: bypassCoverageAvailable,
      configured: profile.allowed_action_types.length,
      protectedObserved: 0,
      bypassedObserved: 0,
      observed: 0,
      percent: null,
      label: bypassCoverageAvailable
        ? profile.allowed_action_types.length > 0 ? `${profile.allowed_action_types.length} mandated` : "No coverage yet"
        : "Not covered",
      detail: !bypassCoverageAvailable
        ? "Connect a source mutation feed to measure actions that bypass Zroky."
        : profile.allowed_action_types.length > 0
        ? `${profile.allowed_action_types.length} protected action ${profile.allowed_action_types.length === 1 ? "type" : "types"} configured`
        : "No protected action mandate configured",
      tone: bypassCoverageAvailable && profile.allowed_action_types.length > 0 ? "neutral" : "warning",
    },
    riskSignals: {
      coverageAvailable: bypassCoverageAvailable,
      bypassed: 0,
      sequenceRisk: 0,
      mismatched: 0,
      label: bypassCoverageAvailable ? "No risky drift" : "Bypass feed not connected",
      tone: bypassCoverageAvailable ? "success" : "warning",
    },
    mandate: {
      label: profile.allowed_action_types.length > 0
        ? profile.allowed_action_types.slice(0, 2).join(" / ").replace(/_/g, " ")
        : "Mandate not scoped",
      detail: `${profile.verification_connectors.length} verifier${profile.verification_connectors.length === 1 ? "" : "s"} / ${profile.tool_names.length} tools`,
      actionTypes: profile.allowed_action_types.map((type) => type.replace(/_/g, " ")),
      toolCount: profile.tool_names.length,
      verifierCount: profile.verification_connectors.length,
      runnerMode: null,
    },
    runnerCount: 0,
    onlineRunnerCount: 0,
    runners: [],
    attemptSummary: emptyAttemptSummary(),
    latestActivityAt: profile.updated_at,
    actionRows: [],
    href: `/agents/${encodeURIComponent(profile.id)}`,
  };
}

export function buildAgentDetail({
  profile,
  intents = [],
  decisions = [],
  outcomes = [],
  runners = [],
  attempts = [],
  staleAttemptIds = [],
  bypassCoverageAvailable = false,
  toolRegistry = null,
}: BuildAgentDetailInput): AgentDetailView {
  const fleet = buildFleetView({
    profiles: [profile],
    intents,
    decisions,
    outcomes,
    runners,
    attempts,
    staleAttemptIds,
    bypassCoverageAvailable,
  });
  const row = fleet.rows.find((item) => item.profile?.id === profile.id)
    ?? fallbackRow(profile, bypassCoverageAvailable);
  const latestAction = row.actionRows[0] ?? null;
  const actionIds = new Set(row.actionRows.map((action) => action.actionId).filter(Boolean));
  const linkedAttempts = attempts.filter((attempt) => actionIds.has(attempt.action_id));
  const staleIds = new Set(staleAttemptIds);

  return {
    profile,
    row,
    config: profileConfig(profile),
    latestAction,
    proofChain: latestAction?.proofChain ?? [],
    runners: row.runners,
    runnerSummary: fleet.runners ?? emptyRunnerSummary(),
    attempts: linkedAttempts,
    attemptSummary: row.attemptSummary,
    stalledAttemptIds: linkedAttempts
      .filter((attempt) => staleIds.has(attempt.attempt_id))
      .map((attempt) => attempt.attempt_id),
    toolPlan: buildToolPlan(toolRegistry),
  };
}
