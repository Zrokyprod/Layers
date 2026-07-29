import { describe, expect, it } from "vitest";

import type { PilotPolicyPayload } from "@/lib/api";
import { generatePolicyFromAnswers } from "./policy-generator";

function basePolicy(overrides: Partial<PilotPolicyPayload> = {}): PilotPolicyPayload {
  return {
    tier1_enabled: true,
    tier1_actions: [],
    tier1_min_confidence: 0.95,
    tier1_max_blast_radius: "low",
    tier1_daily_cap: 10,
    tier2_enabled: true,
    tier2_actions: [],
    tier2_require_replay_pass: true,
    tier2_daily_cap: 5,
    tier3_alert_channels: ["email"],
    kill_switch: false,
    runtime_enabled: true,
    runtime_max_tool_calls: 20,
    runtime_max_retries: 3,
    runtime_max_cost_usd: 2,
    runtime_allowed_tools: ["crm.read"],
    runtime_sensitive_tools: ["custom.publish"],
    runtime_sensitive_actions_require_approval: true,
    runtime_block_pii_leak: false,
    runtime_block_prompt_injected_external_action: false,
    runtime_approval_ttl_minutes: 60,
    runtime_amount_approval_threshold_usd: null,
    runtime_amount_deny_threshold_usd: null,
    runtime_production_deploys_require_approval: false,
    runtime_changed_recipient_deny: false,
    runtime_sequence_risk_enabled: false,
    ...overrides,
  };
}

describe("guided policy generator", () => {
  it("generates the balanced runtime controls and preserves unrelated settings", () => {
    const generated = generatePolicyFromAnswers(
      basePolicy(),
      "balanced",
      ["money", "records", "messages", "production"],
    );

    expect(generated).toEqual(expect.objectContaining({
      runtime_enabled: true,
      runtime_max_tool_calls: 12,
      runtime_max_retries: 2,
      runtime_approval_ttl_minutes: 30,
      runtime_amount_approval_threshold_usd: 500,
      runtime_amount_deny_threshold_usd: 5000,
      runtime_block_pii_leak: true,
      runtime_block_prompt_injected_external_action: true,
      runtime_production_deploys_require_approval: true,
      runtime_changed_recipient_deny: true,
      runtime_sequence_risk_enabled: true,
      runtime_allowed_tools: ["crm.read"],
      runtime_max_cost_usd: 2,
    }));
    expect(generated.runtime_sensitive_tools).toEqual(expect.arrayContaining([
      "custom.publish",
      "delete",
      "email",
      "deploy_change",
    ]));
    expect(generated.runtime_sensitive_tools).not.toContain("refund");
  });

  it("makes every money action sensitive in review-first mode", () => {
    const generated = generatePolicyFromAnswers(basePolicy(), "review_first", ["money"]);

    expect(generated.runtime_amount_approval_threshold_usd).toBe(0);
    expect(generated.runtime_amount_deny_threshold_usd).toBe(500);
    expect(generated.runtime_sensitive_tools).toEqual(expect.arrayContaining([
      "payment",
      "refund",
      "transfer",
      "payout",
    ]));
  });

  it("clears money thresholds when money movement is not selected", () => {
    const generated = generatePolicyFromAnswers(
      basePolicy({ runtime_amount_approval_threshold_usd: 100 }),
      "higher_autonomy",
      ["production"],
    );

    expect(generated.runtime_amount_approval_threshold_usd).toBeNull();
    expect(generated.runtime_amount_deny_threshold_usd).toBeNull();
    expect(generated.runtime_sensitive_tools).toEqual(["custom.publish", "deploy_change"]);
  });
});
