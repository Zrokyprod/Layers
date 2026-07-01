import { describe, expect, it } from "vitest";

import type { AgentProfileResponse } from "@/lib/api";
import { deriveSetupReadiness, setupReadinessFromProfile } from "./setup-readiness";

const base = {
  agentName: "Ops Agent",
  runtimePath: "sdk",
  selectedActionTypes: ["internal_api_mutation"],
  toolNames: ["internal.ops.execute"],
  approvalRequiredAboveUsd: "500",
  denyAboveUsd: "5000",
  credentialRef: "cred_prod_ops",
  verifierConnector: "generic_rest",
  sourceOfRecord: "Primary business system API",
  proofAssertion: "Source-of-record state matches the approved action.",
};

function profile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_1",
    project_id: "proj_1",
    display_name: "Ops Agent",
    slug: "ops-agent",
    description: null,
    runtime_path: "sdk",
    framework: "langgraph",
    environment: "production",
    model_provider: "openai",
    model_name: "gpt-4.1",
    tool_names: ["internal.ops.execute"],
    allowed_action_types: ["internal_api_mutation"],
    blocked_action_types: [],
    default_policy_id: null,
    risk_limits: {},
    verification_connectors: ["generic_rest"],
    metadata: {
      product_context: {
        product_name: "Ops Workflow",
        business_goal: "Control internal mutations.",
        critical_objects: ["customer"],
        source_systems: ["Generic REST"],
      },
      workflow_manifest: {
        workflow_id: "ops_workflow",
        owner_team: "AI Platform",
        goal: "Control one action.",
      },
      policy_preview: {
        approval_required_above_usd: 500,
        deny_above_usd: 5000,
        approval_surface: "dashboard_slack",
      },
      runner_verification: {
        credential_ref: "cred_prod_ops",
        verifier_connector: "generic_rest",
        source_of_record: "Primary business system API",
      },
      proof: {
        proof_assertion: "Source-of-record state matches the approved action.",
      },
      runtime_policy_mandate_enforced: false,
    },
    is_active: true,
    created_at: "2026-06-20T09:00:00.000Z",
    updated_at: "2026-06-20T09:00:00.000Z",
    ...overrides,
  };
}

describe("deriveSetupReadiness", () => {
  it("allows policy enable from essentials without optional enrichment", () => {
    const readiness = deriveSetupReadiness({
      ...base,
      productName: "",
      businessGoal: "",
      workflowId: "",
      workflowGoal: "",
      ownerTeam: "",
      criticalObjects: [],
      sourceSystems: [],
      approvalSurface: "",
    });

    expect(readiness.essentialComplete).toBe(true);
    expect(readiness.enrichmentComplete).toBe(false);
    expect(readiness.canEnablePolicy).toBe(true);
    expect(readiness.state).toBe("essentials_ready");
  });

  it("blocks policy enable when thresholds are invalid", () => {
    const readiness = deriveSetupReadiness({
      ...base,
      approvalRequiredAboveUsd: "5000",
      denyAboveUsd: "500",
    });

    expect(readiness.essentialComplete).toBe(false);
    expect(readiness.canEnablePolicy).toBe(false);
    expect(readiness.essentialChecks.find((check) => check.id === "policy_thresholds")?.done).toBe(false);
  });

  it("derives live state from real readiness signals instead of a stored latch", () => {
    const readiness = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: true, capabilityMatches: true },
      verifier: { selected: true, configured: true, tested: true, healthy: true, compatible: true },
      firstReceiptMatched: true,
    });

    expect(readiness.state).toBe("live");
    expect(readiness.canRunFirstAction).toBe(true);
    expect(readiness.runnerStatus).toBe("ready");
    expect(readiness.verifierStatus).toBe("ready");
  });

  it("regresses when runner or verifier signals degrade", () => {
    const readiness = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: false, capabilityMatches: true },
      verifier: { selected: true, configured: true, tested: true, healthy: false, compatible: true },
      firstReceiptMatched: true,
    });

    expect(readiness.state).toBe("runner_registered");
    expect(readiness.canRunFirstAction).toBe(false);
    expect(readiness.runnerStatus).toBe("registered_offline");
    expect(readiness.verifierStatus).toBe("failing");
  });

  it("does not mark an online runner ready when capability does not match", () => {
    const readiness = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: true, capabilityMatches: false },
      verifier: { selected: true, configured: true, tested: true, healthy: true, compatible: true },
    });

    expect(readiness.state).toBe("runner_registered");
    expect(readiness.canRunFirstAction).toBe(false);
    expect(readiness.runnerStatus).toBe("registered_offline");
  });

  it("derives verifier-ready only from healthy tested connector input", () => {
    const readiness = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: true, capabilityMatches: true },
      verifier: { selected: true, configured: true, tested: true, healthy: true, compatible: true },
    });

    expect(readiness.state).toBe("verifier_ready");
    expect(readiness.canRunFirstAction).toBe(true);
    expect(readiness.verifierStatus).toBe("ready");
  });

  it("keeps missing, untested, and incompatible verifier signals out of live readiness", () => {
    const missing = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: true, capabilityMatches: true },
      verifier: { selected: true, configured: false },
    });
    const untested = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: true, capabilityMatches: true },
      verifier: { selected: true, configured: true, tested: false },
    });
    const incompatible = deriveSetupReadiness({
      ...base,
      policyEnforced: true,
      runner: { exists: true, online: true, capabilityMatches: true },
      verifier: { selected: true, configured: true, tested: true, healthy: true, compatible: false },
    });

    expect(missing.verifierStatus).toBe("missing");
    expect(missing.canRunFirstAction).toBe(false);
    expect(untested.verifierStatus).toBe("not_tested");
    expect(untested.canRunFirstAction).toBe(false);
    expect(incompatible.verifierStatus).toBe("failing");
    expect(incompatible.canRunFirstAction).toBe(false);
  });
});

describe("setupReadinessFromProfile", () => {
  it("derives essentials and policy state from an AgentProfile", () => {
    const readiness = setupReadinessFromProfile(
      profile({
        metadata: {
          ...profile().metadata,
          runtime_policy_mandate_enforced: true,
        },
      }),
      {
        runner: { exists: false },
        verifier: { selected: true, configured: false },
      },
    );

    expect(readiness.essentialComplete).toBe(true);
    expect(readiness.enrichmentComplete).toBe(true);
    expect(readiness.state).toBe("policy_enforced");
    expect(readiness.runnerStatus).toBe("missing");
    expect(readiness.verifierStatus).toBe("missing");
  });
});
