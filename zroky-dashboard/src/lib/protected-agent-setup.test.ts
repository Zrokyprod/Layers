import { describe, expect, it } from "vitest";

import {
  buildLiveSmokeCommand,
  buildWebhookBridgeCurl,
  buildWebhookBridgePayload,
  pilotHandoffCriteria,
  pilotHandoffSteps,
  proofReadinessLabel,
  protectedAgentTemplates,
  webhookBridgeDetail,
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
    expect(pilotHandoffSteps).toContain("Copy mandate and SDK or webhook bridge");
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

  it("builds saved connector bridge snippets for non-SDK agents", () => {
    const refund = protectedAgentTemplates.find((template) => template.id === "refund");
    const devops = protectedAgentTemplates.find((template) => template.id === "devops");

    expect(refund).toBeDefined();
    expect(devops).toBeDefined();

    const refundPayload = JSON.parse(buildWebhookBridgePayload(refund!));
    expect(refundPayload.connector).toBe("ledger_refund");
    expect(refundPayload.refund_id).toBe("rf_123");
    expect(refundPayload.action_type).toBe("refund");
    expect(refundPayload.metadata.agent_name).toBe("refund-ops-agent");

    const devopsPayload = JSON.parse(buildWebhookBridgePayload(devops!));
    expect(devopsPayload.connector).toBe("generic_rest");
    expect(devopsPayload.record_ref).toBe("release_guardrail_record_001");
    expect(devopsPayload.action_type).toBe("deploy_change");
    expect(webhookBridgeDetail(devops!)).toContain("Generic REST");

    const curl = buildWebhookBridgeCurl(refund!);
    expect(curl).toContain("/v1/outcomes/reconciliation/saved");
    expect(curl).toContain("x-api-key: $ZROKY_API_KEY");
    expect(curl).not.toContain("bearer_token");
  });
});
