import type { AgentProfileResponse, AgentRiskActionType, AgentRuntimePath, AgentVerificationConnectorType } from "@/lib/api";

export type SetupCheck = {
  id: string;
  label: string;
  done: boolean;
  detail: string;
};

export type SetupState =
  | "draft"
  | "essentials_ready"
  | "policy_enforced"
  | "runner_registered"
  | "runner_ready"
  | "verifier_ready"
  | "live";

export type RunnerReadinessStatus = "missing" | "registered_offline" | "ready";
export type VerifierReadinessStatus = "missing" | "not_tested" | "failing" | "ready";

export type RunnerReadinessInput = {
  exists?: boolean;
  online?: boolean;
  capabilityMatches?: boolean;
};

export type VerifierReadinessInput = {
  selected?: boolean;
  configured?: boolean;
  tested?: boolean;
  healthy?: boolean;
  compatible?: boolean;
};

export type SetupReadinessInput = {
  agentName: string;
  runtimePath: AgentRuntimePath | string | null | undefined;
  selectedActionTypes: AgentRiskActionType[] | string[];
  toolNames: string[];
  approvalRequiredAboveUsd: string | number | null | undefined;
  denyAboveUsd: string | number | null | undefined;
  credentialRef: string;
  verifierConnector: AgentVerificationConnectorType | string | null | undefined;
  sourceOfRecord: string;
  proofAssertion: string;
  productName?: string | null;
  businessGoal?: string | null;
  workflowId?: string | null;
  workflowGoal?: string | null;
  ownerTeam?: string | null;
  criticalObjects?: string[];
  sourceSystems?: string[];
  approvalSurface?: string | null;
  policyEnforced?: boolean;
  runner?: RunnerReadinessInput | null;
  verifier?: VerifierReadinessInput | null;
  firstReceiptMatched?: boolean;
};

export type SetupReadiness = {
  state: SetupState;
  essentialComplete: boolean;
  enrichmentComplete: boolean;
  canEnablePolicy: boolean;
  canRunFirstAction: boolean;
  essentialChecks: SetupCheck[];
  enrichmentChecks: SetupCheck[];
  runnerStatus: RunnerReadinessStatus;
  verifierStatus: VerifierReadinessStatus;
};

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function hasText(value: unknown): boolean {
  return text(value).length > 0;
}

function hasItems(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.some((item) => hasText(item));
}

function numeric(value: string | number | null | undefined): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "boolean") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function thresholdCheck(input: SetupReadinessInput): SetupCheck {
  const approval = numeric(input.approvalRequiredAboveUsd);
  const deny = numeric(input.denyAboveUsd);
  const done = approval != null && deny != null && approval >= 0 && deny > approval;
  return {
    id: "policy_thresholds",
    label: "Policy thresholds valid",
    done,
    detail: done
      ? `Approval above ${approval}; deny above ${deny}.`
      : "Set a non-negative approval threshold and a higher deny threshold.",
  };
}

export function runnerReadinessStatus(input: RunnerReadinessInput | null | undefined): RunnerReadinessStatus {
  if (!input?.exists) return "missing";
  if (input.online && input.capabilityMatches !== false) return "ready";
  return "registered_offline";
}

export function verifierReadinessStatus(input: VerifierReadinessInput | null | undefined): VerifierReadinessStatus {
  if (!input?.selected || !input.configured) return "missing";
  if (!input.tested) return "not_tested";
  if (input.healthy && input.compatible !== false) return "ready";
  return "failing";
}

export function deriveSetupReadiness(input: SetupReadinessInput): SetupReadiness {
  const essentialChecks: SetupCheck[] = [
    {
      id: "agent_identity",
      label: "Agent identity",
      done: hasText(input.agentName) && hasText(input.runtimePath),
      detail: "Agent name and runtime path are required.",
    },
    {
      id: "first_action",
      label: "First protected action",
      done: hasItems(input.selectedActionTypes) && hasItems(input.toolNames),
      detail: "Choose at least one risky action type and one tool/action key.",
    },
    thresholdCheck(input),
    {
      id: "credential_alias",
      label: "Credential alias",
      done: hasText(input.credentialRef),
      detail: "Use a non-secret credential pointer, not a raw secret.",
    },
    {
      id: "verifier_intent",
      label: "Verifier selected",
      done: hasText(input.verifierConnector) && hasText(input.sourceOfRecord) && hasText(input.proofAssertion),
      detail: "Select a verifier and define what the source of record must prove.",
    },
  ];

  const enrichmentChecks: SetupCheck[] = [
    {
      id: "product_context",
      label: "Product context",
      done: hasText(input.productName) && hasText(input.businessGoal),
      detail: "Optional context improves evidence narrative.",
    },
    {
      id: "workflow_manifest",
      label: "Workflow manifest",
      done: hasText(input.workflowId) && hasText(input.workflowGoal) && hasText(input.ownerTeam),
      detail: "Optional workflow ownership helps audit readers.",
    },
    {
      id: "business_scope",
      label: "Business scope",
      done: hasItems(input.criticalObjects) && hasItems(input.sourceSystems),
      detail: "Optional objects and source systems enrich receipts.",
    },
    {
      id: "approval_surface",
      label: "Approval surface",
      done: hasText(input.approvalSurface),
      detail: "Optional routing detail for human approvals.",
    },
  ];

  const essentialComplete = essentialChecks.every((check) => check.done);
  const enrichmentComplete = enrichmentChecks.every((check) => check.done);
  const runnerStatus = runnerReadinessStatus(input.runner);
  const verifierStatus = verifierReadinessStatus(input.verifier);
  const policyEnforced = input.policyEnforced === true;
  const runnerReady = runnerStatus === "ready";
  const verifierReady = verifierStatus === "ready";
  const canRunFirstAction = policyEnforced && runnerReady && verifierReady;
  const live = canRunFirstAction && input.firstReceiptMatched === true;
  let state: SetupState = "draft";

  if (live) {
    state = "live";
  } else if (canRunFirstAction) {
    state = "verifier_ready";
  } else if (policyEnforced && runnerReady) {
    state = "runner_ready";
  } else if (policyEnforced && input.runner?.exists) {
    state = "runner_registered";
  } else if (policyEnforced) {
    state = "policy_enforced";
  } else if (essentialComplete) {
    state = "essentials_ready";
  }

  return {
    state,
    essentialComplete,
    enrichmentComplete,
    canEnablePolicy: essentialComplete,
    canRunFirstAction,
    essentialChecks,
    enrichmentChecks,
    runnerStatus,
    verifierStatus,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function setupReadinessFromProfile(
  profile: AgentProfileResponse | null,
  options: {
    runner?: RunnerReadinessInput | null;
    verifier?: VerifierReadinessInput | null;
    firstReceiptMatched?: boolean;
  } = {},
): SetupReadiness {
  const metadata = asRecord(profile?.metadata);
  const product = asRecord(metadata.product_context);
  const workflow = asRecord(metadata.workflow_manifest);
  const policy = asRecord(metadata.policy_preview);
  const runner = asRecord(metadata.runner_verification);
  const proof = asRecord(metadata.proof);

  return deriveSetupReadiness({
    agentName: profile?.display_name ?? "",
    runtimePath: profile?.runtime_path ?? "",
    selectedActionTypes: profile?.allowed_action_types ?? [],
    toolNames: profile?.tool_names ?? [],
    approvalRequiredAboveUsd: policy.approval_required_above_usd as string | number | null | undefined,
    denyAboveUsd: policy.deny_above_usd as string | number | null | undefined,
    credentialRef: text(runner.credential_ref),
    verifierConnector: profile?.verification_connectors?.[0] ?? text(runner.verifier_connector),
    sourceOfRecord: text(runner.source_of_record),
    proofAssertion: text(proof.proof_assertion),
    productName: text(product.product_name),
    businessGoal: text(product.business_goal),
    workflowId: text(workflow.workflow_id),
    workflowGoal: text(workflow.goal),
    ownerTeam: text(workflow.owner_team),
    criticalObjects: Array.isArray(product.critical_objects) ? product.critical_objects.map(String) : [],
    sourceSystems: Array.isArray(product.source_systems) ? product.source_systems.map(String) : [],
    approvalSurface: text(policy.approval_surface),
    policyEnforced: metadata.runtime_policy_mandate_enforced === true,
    runner: options.runner,
    verifier: options.verifier,
    firstReceiptMatched: options.firstReceiptMatched,
  });
}
