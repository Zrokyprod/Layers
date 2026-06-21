import { describe, expect, it } from "vitest";

import {
  buildLiveSmokeCommand,
  pilotHandoffCriteria,
  pilotHandoffSteps,
  proofReadinessLabel,
  protectedAgentTemplates,
} from "./protected-agent-setup";

describe("protected-agent-setup", () => {
  it("keeps five protected-agent templates with honest proof readiness", () => {
    expect(protectedAgentTemplates.map((template) => template.id)).toEqual([
      "refund",
      "devops",
      "crm",
      "outreach",
      "procurement",
    ]);

    const packaged = protectedAgentTemplates.filter((template) => template.proofStatus === "packaged_full_proof");
    expect(packaged.map((template) => template.id)).toEqual(["refund", "crm"]);
    expect(packaged.every((template) => buildLiveSmokeCommand(template)?.includes("--write-evidence"))).toBe(true);
    expect(packaged.every((template) => !buildLiveSmokeCommand(template)?.includes("--preflight-only"))).toBe(true);

    const custom = protectedAgentTemplates.filter((template) => template.proofStatus === "custom_connector_required");
    expect(custom.map((template) => template.id)).toEqual(["devops", "outreach", "procurement"]);
    expect(custom.every((template) => buildLiveSmokeCommand(template) === null)).toBe(true);
    expect(custom.every((template) => proofReadinessLabel(template) === "Custom connector required")).toBe(true);
  });

  it("aligns pilot handoff steps and criteria with full outcome proof", () => {
    expect(pilotHandoffSteps).toContain("Run connector preflight");
    expect(pilotHandoffSteps).toContain("Run full proof command");
    expect(pilotHandoffCriteria).toEqual([
      "captured_call_linked",
      "unsafe_action_stopped",
      "connector_configured",
      "connector_health_verified",
      "real_connector_ready",
      "saved_test_endpoint_used",
      "matched_outcome_shown",
      "evidence_hash_visible",
      "evidence_json_exported",
      "not_verified_when_missing",
      "evidence_pack_passed",
      "secrets_redacted",
    ]);
  });
});
