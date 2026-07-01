import { describe, expect, it } from "vitest";

import type {
  AgentProfileResponse,
  PilotPolicyPayload,
  RuntimePolicyResolvePreviewResponse,
  RuntimePolicyRuleResponse,
} from "@/lib/api";
import { buildPolicyRulesView, describePolicyPatch } from "@/lib/policy-rules-view";

const now = "2026-06-20T09:00:00.000Z";

function agent(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_refund",
    project_id: "proj_1",
    display_name: "Refund Agent",
    slug: "refund-agent",
    description: null,
    runtime_path: "sdk",
    framework: null,
    environment: "production",
    model_provider: null,
    model_name: null,
    tool_names: [],
    allowed_action_types: ["refund"],
    blocked_action_types: [],
    default_policy_id: null,
    risk_limits: {},
    verification_connectors: [],
    metadata: {},
    is_active: true,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function rule(overrides: Partial<RuntimePolicyRuleResponse> = {}): RuntimePolicyRuleResponse {
  return {
    id: "rule_action",
    project_id: "proj_1",
    name: "Refund threshold",
    description: null,
    agent_id: null,
    action_type: "refund",
    environment: null,
    policy_patch: {
      runtime_amount_approval_threshold_usd: 300,
    },
    priority: 0,
    version: 1,
    is_enabled: true,
    created_by_subject: "ops@example.com",
    updated_by_subject: "ops@example.com",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function preview(overrides: Partial<RuntimePolicyResolvePreviewResponse> = {}): RuntimePolicyResolvePreviewResponse {
  return {
    project_id: "proj_1",
    policy: {
      runtime_enabled: true,
      runtime_amount_approval_threshold_usd: 50,
      runtime_amount_deny_threshold_usd: 1000,
    } as PilotPolicyPayload,
    matched_rules: [
      {
        id: "rule_action",
        name: "Refund threshold",
        agent_id: null,
        action_type: "refund",
        environment: null,
        priority: 0,
        version: 1,
        specificity: 10,
      },
      {
        id: "rule_agent",
        name: "Refund Agent strict",
        agent_id: "agent_refund",
        action_type: "refund",
        environment: null,
        priority: 0,
        version: 1,
        specificity: 50,
      },
    ],
    ...overrides,
  };
}

describe("policy-rules-view", () => {
  it("labels scoped rules and highlights matched order", () => {
    const view = buildPolicyRulesView({
      agents: [agent()],
      preview: preview(),
      rules: [
        rule(),
        rule({
          id: "rule_agent",
          name: "Refund Agent strict",
          agent_id: "agent_refund",
          policy_patch: { runtime_amount_approval_threshold_usd: 50 },
          priority: 10,
        }),
      ],
    });

    expect(view.cards).toHaveLength(2);
    expect(view.cards[0].id).toBe("rule_agent");
    expect(view.cards[0].scopeLabel).toBe("Refund Agent / Refund");
    expect(view.cards[0].matchIndex).toBe(2);
    expect(view.cards[0].conditionSummary).toContain("Approval above $50.00");
    expect(view.cards[1].matchIndex).toBe(1);
    expect(view.effective?.summary).toBe("2 scoped rules matched.");
  });

  it("keeps disabled rules visible but neutral", () => {
    const view = buildPolicyRulesView({
      agents: [],
      preview: null,
      rules: [
        rule({
          id: "disabled_rule",
          is_enabled: false,
          action_type: null,
          policy_patch: { runtime_enabled: false },
        }),
      ],
    });

    expect(view.cards[0].scopeLabel).toBe("Project default");
    expect(view.cards[0].tone).toBe("neutral");
    expect(view.cards[0].conditionSummary).toBe("Runtime gate disabled");
  });

  it("describes partial patches without implying a full policy", () => {
    expect(describePolicyPatch({ runtime_amount_deny_threshold_usd: 5000 })).toEqual([
      "Deny above $5,000.00",
    ]);
  });
});
