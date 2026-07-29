import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentProfileResponse, RuntimePolicyRuleResponse } from "@/lib/api";
import {
  PolicyRuleBuilder,
  buildPolicyRulePayload,
  type PolicyRuleDraft,
} from "./policy-rule-builder";

const agents = [
  {
    id: "agent_release",
    display_name: "Release Agent",
    slug: "release-agent",
  } as AgentProfileResponse,
];

function draft(overrides: Partial<PolicyRuleDraft> = {}): PolicyRuleDraft {
  return {
    agentId: "agent_release",
    actionChoice: "__custom__",
    customAction: "Publish Campaign",
    environmentChoice: "production",
    customEnvironment: "",
    outcome: "require_two_approvals",
    description: "Protect campaign launches.",
    maxToolCalls: "8",
    maxRetries: "1",
    maxCost: "0.5",
    approvalTtl: "20",
    approvalThreshold: "",
    dualApprovalThreshold: "",
    ...overrides,
  };
}

describe("policy rule builder", () => {
  it("builds an enforceable custom-action rule", () => {
    expect(buildPolicyRulePayload(draft(), agents)).toEqual({
      name: "Release Agent: Publish campaign - Two approvals",
      description: "Protect campaign launches.",
      agent_id: "agent_release",
      action_type: "publish_campaign",
      environment: "production",
      priority: 0,
      is_enabled: true,
      policy_patch: {
        runtime_enabled: true,
        runtime_action_decision: "require_two_approvals",
        runtime_max_tool_calls: 8,
        runtime_max_retries: 1,
        runtime_max_cost_usd: 0.5,
        runtime_approval_ttl_minutes: 20,
      },
    });
  });

  it("preserves advanced fields when editing through the simple builder", () => {
    const payload = buildPolicyRulePayload(
      draft({ outcome: "deny", maxToolCalls: "" }),
      agents,
      { runtime_block_pii_leak: true, runtime_max_tool_calls: 50 },
    );

    expect(payload.policy_patch).toEqual({
      runtime_block_pii_leak: true,
      runtime_enabled: true,
      runtime_action_decision: "deny",
      runtime_max_retries: 1,
      runtime_max_cost_usd: 0.5,
      runtime_approval_ttl_minutes: 20,
    });
  });

  it("supports a policy that covers every action for one agent", () => {
    const payload = buildPolicyRulePayload(
      draft({ actionChoice: "", customAction: "", outcome: "deny" }),
      agents,
    );

    expect(payload.action_type).toBeNull();
    expect(payload.name).toBe("Release Agent: Any action - Deny");
    expect(payload.policy_patch.runtime_action_decision).toBe("deny");
  });

  it("creates a template-backed rule without technical fields", () => {
    const onSave = vi.fn();
    render(
      <PolicyRuleBuilder
        agents={agents}
        disabled={false}
        disabling={false}
        onDisable={vi.fn()}
        onSave={onSave}
        rules={[]}
        saving={false}
      />,
    );

    fireEvent.change(screen.getByLabelText("Start from template"), { target: { value: "release" } });
    expect((screen.getByLabelText("Agent") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("Action") as HTMLSelectElement).value).toBe("deploy_change");
    expect((screen.getByLabelText("Environment") as HTMLSelectElement).value).toBe("production");
    fireEvent.click(screen.getByRole("button", { name: "Create policy rule" }));

    expect(onSave).toHaveBeenCalledWith(
      null,
      expect.objectContaining({
        action_type: "deploy_change",
        environment: "production",
        policy_patch: expect.objectContaining({ runtime_action_decision: "require_approval" }),
      }),
    );
  });

  it("shows saved policies and exposes edit and disable commands", () => {
    const onDisable = vi.fn();
    const rule = {
      id: "rule_1",
      name: "Release Agent: Deploy change - Review",
      agent_id: "agent_release",
      action_type: "deploy_change",
      environment: "production",
      policy_patch: { runtime_action_decision: "require_approval" },
      is_enabled: true,
      description: null,
    } as RuntimePolicyRuleResponse;

    render(
      <PolicyRuleBuilder
        agents={agents}
        disabled={false}
        disabling={false}
        onDisable={onDisable}
        onSave={vi.fn()}
        rules={[rule]}
        saving={false}
      />,
    );

    expect(screen.getByText("1 active")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `Disable ${rule.name}` }));
    expect(onDisable).toHaveBeenCalledWith("rule_1");
  });

  it("replaces an existing active rule instead of creating a conflicting scope", () => {
    const onSave = vi.fn();
    const existing = {
      id: "rule_email_all",
      name: "All agents: Email send - Review",
      agent_id: null,
      action_type: "email_send",
      environment: null,
      policy_patch: { runtime_action_decision: "require_approval" },
      is_enabled: true,
      description: null,
    } as RuntimePolicyRuleResponse;
    render(
      <PolicyRuleBuilder
        agents={agents}
        disabled={false}
        disabling={false}
        onDisable={vi.fn()}
        onSave={onSave}
        rules={[existing]}
        saving={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Replace existing policy" }));
    expect(onSave).toHaveBeenCalledWith("rule_email_all", expect.objectContaining({ action_type: "email_send" }));
  });
});
