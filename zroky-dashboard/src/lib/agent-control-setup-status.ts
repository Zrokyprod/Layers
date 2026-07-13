import type { AgentProfileResponse } from "@/lib/api";
import type { CaptureHealthResponse } from "@/lib/types";

export type AgentControlSetupState =
  | "not_started"
  | "incomplete"
  | "plan_saved"
  | "policy_enforced"
  | "live";

export type AgentControlSetupStatus = {
  state: AgentControlSetupState;
  complete: boolean;
  profileCount: number;
  setupProfileCount: number;
  setupAgentId: string | null;
  completedCount: number;
  totalCount: number;
  progressPct: number;
  title: string;
  body: string;
  ctaLabel: string;
  ctaHref: string;
  checks: {
    id: string;
    label: string;
    done: boolean;
    detail: string;
  }[];
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function hasNonEmptyString(source: Record<string, unknown> | null, key: string): boolean {
  const value = source?.[key];
  return typeof value === "string" && value.trim().length > 0;
}

function hasNonEmptyArray(source: Record<string, unknown> | null, key: string): boolean {
  const value = source?.[key];
  return Array.isArray(value) && value.length > 0;
}

function hasWizardMetadata(profile: AgentProfileResponse): boolean {
  return profile.metadata?.setup_source === "agent_control_setup_wizard";
}

function runtimePolicyMandateEnforced(profile: AgentProfileResponse | null): boolean {
  return profile?.metadata?.runtime_policy_mandate_enforced === true;
}

function productContextComplete(profile: AgentProfileResponse | null): boolean {
  const context = asRecord(profile?.metadata?.product_context);
  const richContextComplete = hasNonEmptyString(context, "product_name") &&
    hasNonEmptyString(context, "business_goal") &&
    hasNonEmptyArray(context, "critical_objects") &&
    hasNonEmptyArray(context, "source_systems");
  return richContextComplete || (
    Boolean(profile && hasWizardMetadata(profile)) &&
    typeof profile?.metadata?.setup_action_pack_id === "string" &&
    profile.metadata.setup_action_pack_id.trim().length > 0
  );
}

function workflowComplete(profile: AgentProfileResponse | null): boolean {
  const workflow = asRecord(profile?.metadata?.workflow_manifest);
  const richWorkflowComplete = hasNonEmptyString(workflow, "workflow_id") &&
    hasNonEmptyString(workflow, "owner_team") &&
    hasNonEmptyArray(workflow, "protected_actions");
  return richWorkflowComplete || Boolean(
    profile &&
    hasWizardMetadata(profile) &&
    (profile.tool_names ?? []).length > 0,
  );
}

function actionContractsComplete(profile: AgentProfileResponse | null): boolean {
  const contracts = profile?.metadata?.action_contracts;
  const richContractsComplete = Array.isArray(contracts) && contracts.some((contract) => {
    const value = asRecord(contract);
    return hasNonEmptyString(value, "id") &&
      hasNonEmptyString(value, "verb") &&
      hasNonEmptyString(value, "risk_class");
  });
  const installedContracts = profile?.metadata?.setup_action_contract_versions;
  return richContractsComplete || (
    Array.isArray(installedContracts) &&
    installedContracts.some((value) => typeof value === "string" && value.trim().length > 0)
  );
}

function policyComplete(profile: AgentProfileResponse | null): boolean {
  const policy = asRecord(profile?.metadata?.policy_preview);
  return runtimePolicyMandateEnforced(profile) || (policy != null &&
    typeof policy.approval_required_above_usd === "number" &&
    typeof policy.deny_above_usd === "number" &&
    policy.unknown_contract_decision === "deny");
}

function runnerComplete(profile: AgentProfileResponse | null): boolean {
  const runner = asRecord(profile?.metadata?.runner_verification);
  return hasNonEmptyString(runner, "credential_ref");
}

function verifierComplete(profile: AgentProfileResponse | null): boolean {
  const runner = asRecord(profile?.metadata?.runner_verification);
  return hasNonEmptyString(runner, "verifier_connector") &&
    hasNonEmptyString(runner, "source_of_record");
}

function captureLive(captureHealth: CaptureHealthResponse | null | undefined): boolean {
  return Boolean(
    captureHealth &&
    captureHealth.status === "connected" &&
    ((captureHealth.calls_24h ?? 0) > 0 || (captureHealth.outcome_events_24h ?? 0) > 0),
  );
}

function statusCopy(state: AgentControlSetupState): Pick<AgentControlSetupStatus, "body" | "ctaHref" | "ctaLabel" | "title"> {
  if (state === "not_started") {
    return {
      title: "Agent control setup required",
      body: "Zroky does not yet know your product context, agent workflow, risky tool calls, runner, or verifier.",
      ctaLabel: "Start setup",
      ctaHref: "/agents/setup",
    };
  }
  if (state === "incomplete") {
    return {
      title: "Agent control setup incomplete",
      body: "Finish the product map, action contracts, policy, runner, and verifier before trusting protected actions.",
      ctaLabel: "Continue setup",
      ctaHref: "/agents/setup",
    };
  }
  if (state === "plan_saved") {
    return {
      title: "Control plan saved",
      body: "The setup plan is saved, but enforcement is not active until a runtime-policy mandate and real action proof are wired.",
      ctaLabel: "Open setup",
      ctaHref: "/agents/setup",
    };
  }
  if (state === "policy_enforced") {
    return {
      title: "Project policy enabled",
      body: "The project runtime policy is enforced. Route one real protected action to generate the first verified receipt.",
      ctaLabel: "Run first protected action",
      ctaHref: "/agents/setup",
    };
  }
  return {
    title: "Agent control setup live",
    body: "Zroky has saved setup metadata, protected actions, runner, verifier, and real action signals for this project.",
    ctaLabel: "Review setup",
    ctaHref: "/agents/setup",
  };
}

export function getAgentControlSetupStatus(
  profiles: AgentProfileResponse[],
  captureHealth?: CaptureHealthResponse | null,
): AgentControlSetupStatus {
  const setupProfiles = profiles.filter(hasWizardMetadata);
  const primary = setupProfiles[0] ?? null;
  const checks = [
    {
      id: "agent_profile",
      label: "Save agent profile",
      done: profiles.length > 0,
      detail: profiles.length > 0 ? `${profiles.length} agent profile${profiles.length === 1 ? "" : "s"} found.` : "Create one protected agent profile.",
    },
    {
      id: "product_context",
      label: "Map product context",
      done: productContextComplete(primary),
      detail: "Business goal, critical objects, and source systems must be explicit.",
    },
    {
      id: "workflow_manifest",
      label: "Save workflow manifest",
      done: workflowComplete(primary),
      detail: "Agent owner, workflow ID, and protected actions must be linked.",
    },
    {
      id: "action_contracts",
      label: "Create action contracts",
      done: actionContractsComplete(primary),
      detail: "Risky tool calls need deterministic contracts before policy.",
    },
    {
      id: "policy",
      label: "Define policy and approval",
      done: policyComplete(primary),
      detail: "Unknown contracts must deny and risky actions must hold or deny.",
    },
    {
      id: "runner",
      label: "Connect protected runner",
      done: runnerComplete(primary),
      detail: "Select a protected credential reference for customer-hosted execution.",
    },
    {
      id: "verifier",
      label: "Connect source verification",
      done: verifierComplete(primary),
      detail: "Select the source of record and verifier connector for independent proof.",
    },
  ];
  const completedCount = checks.filter((check) => check.done).length;
  const totalCount = checks.length;
  const savedSetupComplete = completedCount === totalCount;
  const mandateEnforced = runtimePolicyMandateEnforced(primary);
  const live = savedSetupComplete && mandateEnforced && captureLive(captureHealth);
  const state: AgentControlSetupState = profiles.length === 0
    ? "not_started"
    : savedSetupComplete
      ? live
        ? "live"
        : mandateEnforced
          ? "policy_enforced"
          : "plan_saved"
      : "incomplete";
  return {
    state,
    complete: state === "live",
    profileCount: profiles.length,
    setupProfileCount: setupProfiles.length,
    setupAgentId: primary?.id ?? null,
    completedCount,
    totalCount,
    progressPct: Math.round((completedCount / totalCount) * 100),
    checks,
    ...statusCopy(state),
  };
}
