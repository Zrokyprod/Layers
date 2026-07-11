import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AgentProfileResponse,
  PilotPolicyPayload,
  PilotPolicyResponse,
  RuntimePolicyDecisionResponse,
  RuntimePolicyDryRunResponse,
  RuntimePolicyResolvePreviewResponse,
  RuntimePolicyRuleResponse,
} from "@/lib/api";
import PoliciesPage from "./page";

const api = vi.hoisted(() => ({
  getBillingMe: vi.fn(),
  getPilotPolicy: vi.fn(),
  createRuntimePolicyRule: vi.fn(),
  disableRuntimePolicyRule: vi.fn(),
  dryRunRuntimePolicy: vi.fn(),
  listAgentProfiles: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
  listRuntimePolicyRules: vi.fn(),
  resolveRuntimePolicyPreview: vi.fn(),
  setRuntimePolicyKillSwitch: vi.fn(),
  updateRuntimePolicyRule: vi.fn(),
  updatePilotPolicy: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", () => api);

const now = "2026-06-20T09:00:00.000Z";
let seededPolicyResponse: PilotPolicyResponse;
let seededApprovalsResponse: { items: RuntimePolicyDecisionResponse[]; total_in_page: number };
let seededAgentsResponse: { items: AgentProfileResponse[]; total: number; limit: number; offset: number; active_count: number; max_active_agents: number; limit_reached: boolean };
let seededRulesResponse: { items: RuntimePolicyRuleResponse[]; total_in_page: number };
let seededPreviewResponse: RuntimePolicyResolvePreviewResponse;
let seededBillingResponse: {
  plan_code: string;
  plan_template: Record<string, unknown>;
};

function policy(overrides: Partial<PilotPolicyPayload> = {}): PilotPolicyPayload {
  return {
    tier1_enabled: true,
    tier1_actions: ["schema_fix"],
    tier1_min_confidence: 0.95,
    tier1_max_blast_radius: "low",
    tier1_daily_cap: 10,
    tier2_enabled: true,
    tier2_actions: ["prompt_revert"],
    tier2_require_replay_pass: true,
    tier2_daily_cap: 5,
    tier3_alert_channels: ["slack"],
    kill_switch: false,
    runtime_enabled: true,
    runtime_max_tool_calls: 8,
    runtime_max_retries: 2,
    runtime_max_cost_usd: 50,
    runtime_allowed_tools: ["ledger.lookup", "crm.read"],
    runtime_sensitive_tools: ["ledger.refund", "email.send"],
    runtime_sensitive_actions_require_approval: true,
    runtime_block_pii_leak: true,
    runtime_block_prompt_injected_external_action: true,
    runtime_approval_ttl_minutes: 15,
    runtime_amount_approval_threshold_usd: 500,
    runtime_amount_deny_threshold_usd: 5000,
    runtime_production_deploys_require_approval: true,
    runtime_changed_recipient_deny: true,
    runtime_sequence_risk_enabled: true,
    ...overrides,
  };
}

function policyResponse(payload: PilotPolicyPayload = policy()): PilotPolicyResponse {
  return {
    id: "policy_1",
    project_id: "proj_1",
    policy: payload,
    updated_by: "ops@example.com",
    created_at: now,
    updated_at: now,
  };
}

function decision(overrides: Partial<RuntimePolicyDecisionResponse> = {}): RuntimePolicyDecisionResponse {
  return {
    id: "decision_1",
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "Refund Agent",
    role: "refund_ops",
    action_type: "refund",
    tool_name: "ledger.refund",
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["amount_requires_approval"],
    request: {},
    policy_snapshot: {},
    intended_action: {},
    trace_context: {},
    policy_hit: {},
    business_impact: {},
    audit_log: [],
    created_at: now,
    expires_at: null,
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    consumed_at: null,
    consumed_by_decision_id: null,
    ...overrides,
  };
}

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

function scopedRule(overrides: Partial<RuntimePolicyRuleResponse> = {}): RuntimePolicyRuleResponse {
  return {
    id: "rule_refund_agent",
    project_id: "proj_1",
    name: "Refund Agent strict threshold",
    description: "Hold larger refunds for this agent.",
    agent_id: "agent_refund",
    action_type: "refund",
    environment: "production",
    policy_patch: {
      runtime_amount_approval_threshold_usd: 100,
      runtime_amount_deny_threshold_usd: 1000,
    },
    priority: 10,
    version: 1,
    is_enabled: true,
    created_by_subject: "ops@example.com",
    updated_by_subject: "ops@example.com",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function dryRun(overrides: Partial<RuntimePolicyDryRunResponse> = {}): RuntimePolicyDryRunResponse {
  return {
    recorded: false,
    decision: "requires_approval",
    status: "pending_approval",
    allowed: false,
    requires_approval: true,
    reasons: ["amount exceeds approval threshold $100.00"],
    request: {},
    policy_hit: {},
    business_impact: {},
    intended_action: {},
    required_approval_count: 1,
    ...overrides,
  };
}

function mockPolicies({
  payload = policy(),
  decisions = [
    decision(),
    decision({
      id: "decision_blocked",
      action_type: "delete",
      tool_name: "crm.delete",
      status: "blocked",
      decision: "block",
      reasons: ["tool_not_allowed"],
      requires_approval: false,
    }),
  ],
  rules = [scopedRule()],
}: {
  payload?: PilotPolicyPayload;
  decisions?: RuntimePolicyDecisionResponse[];
  rules?: RuntimePolicyRuleResponse[];
} = {}) {
  const response = policyResponse(payload);
  seededPolicyResponse = response;
  seededApprovalsResponse = { items: decisions, total_in_page: decisions.length };
  seededAgentsResponse = {
    items: [agent()],
    total: 1,
    limit: 200,
    offset: 0,
    active_count: 1,
    max_active_agents: 3,
    limit_reached: false,
  };
  seededRulesResponse = { items: rules, total_in_page: rules.length };
  seededPreviewResponse = {
    project_id: "proj_1",
    policy: {
      ...payload,
      runtime_amount_approval_threshold_usd: 100,
      runtime_amount_deny_threshold_usd: 1000,
      _runtime_policy_resolution: {
        source: "project_policy+scoped_rules",
        matched_rules: [
          {
            id: "rule_refund_agent",
            name: "Refund Agent strict threshold",
            agent_id: "agent_refund",
            action_type: "refund",
            environment: "production",
            priority: 10,
            version: 1,
            specificity: 70,
          },
        ],
      },
    },
    matched_rules: [
      {
        id: "rule_refund_agent",
        name: "Refund Agent strict threshold",
        agent_id: "agent_refund",
        action_type: "refund",
        environment: "production",
        priority: 10,
        version: 1,
        specificity: 70,
      },
    ],
  };
  seededBillingResponse = {
    plan_code: "team",
    plan_template: { "pilot.autopilot_enabled": true },
  };
  api.getBillingMe.mockResolvedValue(seededBillingResponse);
  api.getPilotPolicy.mockResolvedValue(response);
  api.updatePilotPolicy.mockResolvedValue(response);
  api.setRuntimePolicyKillSwitch.mockResolvedValue({ project_id: "proj_1", enabled: true, policy: { kill_switch: true } });
  api.listRuntimePolicyApprovals.mockResolvedValue(seededApprovalsResponse);
  api.listAgentProfiles.mockResolvedValue(seededAgentsResponse);
  api.listRuntimePolicyRules.mockResolvedValue(seededRulesResponse);
  api.resolveRuntimePolicyPreview.mockResolvedValue(seededPreviewResponse);
  api.createRuntimePolicyRule.mockResolvedValue(scopedRule({ id: "rule_new", name: "New scoped rule" }));
  api.updateRuntimePolicyRule.mockResolvedValue(scopedRule());
  api.disableRuntimePolicyRule.mockResolvedValue(scopedRule({ is_enabled: false }));
  api.dryRunRuntimePolicy.mockResolvedValue(dryRun());
}

function renderPoliciesPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  client.setQueryData(["pilot-policy"], seededPolicyResponse);
  client.setQueryData(["runtime-policy", "approvals", "all"], seededApprovalsResponse);
  client.setQueryData(["agents", "profiles", "policy-rules"], seededAgentsResponse);
  client.setQueryData(["runtime-policy", "rules"], seededRulesResponse);
  client.setQueryData(["runtime-policy", "resolve-preview", "", "refund", "production"], seededPreviewResponse);
  client.setQueryData(["billing", "me"], seededBillingResponse);

  return render(
    <QueryClientProvider client={client}>
      <PoliciesPage />
    </QueryClientProvider>,
  );
}

function renderUnseededPoliciesPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <PoliciesPage />
    </QueryClientProvider>,
  );
}

describe("PoliciesPage mandate control", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    mockPolicies();
  });

  it("surfaces runtime action control and latest runtime decisions", async () => {
    renderPoliciesPage();

    expect(await screen.findByRole("heading", { name: "Human review waiting" })).toBeInTheDocument();
    expect(screen.getAllByText("Runtime Action Control").length).toBeGreaterThan(0);
    expect(screen.getByText("The policy gate is working and has paused sensitive actions for human approval before execution.")).toBeInTheDocument();

    const summary = screen.getByLabelText("Policy safety summary");
    expect(within(summary).getByText("Runtime action control")).toBeInTheDocument();
    expect(within(summary).getByText("Policy gate")).toBeInTheDocument();
    expect(within(summary).getByText("Pending approvals")).toBeInTheDocument();
    expect(within(summary).getByText("Blocked actions")).toBeInTheDocument();

    const boundary = screen.getByLabelText("Current mandate boundary");
    expect(within(boundary).getByText("Allowed surface")).toBeInTheDocument();
    expect(within(boundary).getAllByText("2 tools").length).toBeGreaterThan(0);
    expect(within(boundary).getByText("Sensitive actions hold for 15 minutes.")).toBeInTheDocument();
    expect(within(boundary).getByText("$500 approval")).toBeInTheDocument();
    expect(within(boundary).getByText("$5,000 requires dual approval.")).toBeInTheDocument();
    expect(within(boundary).getByText("$50.00 per action")).toBeInTheDocument();

    const feed = screen.getByLabelText("Latest runtime decisions");
    expect(within(feed).getByText("refund")).toBeInTheDocument();
    expect(within(feed).getByText("Refund Agent / ledger.refund / call_1")).toBeInTheDocument();
    expect(within(feed).getByText("amount_requires_approval")).toBeInTheDocument();
    expect(within(feed).getByText("pending approval")).toBeInTheDocument();
    expect(within(feed).getByText("delete")).toBeInTheDocument();
    expect(within(feed).getByText("tool_not_allowed")).toBeInTheDocument();
  });

  it("terminates loading with an honest plan-limited policy state", async () => {
    api.getPilotPolicy.mockRejectedValue(new Error("Your plan does not include 'pilot.autopilot_enabled'. Upgrade to use this feature."));

    renderUnseededPoliciesPage();

    expect(await screen.findByRole("heading", { name: "Policy upgrade required" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Policy status loading" })).not.toBeInTheDocument();
    expect(screen.getByText("This plan cannot configure Runtime Action Control. Existing policy decisions remain visible in the audit trail.")).toBeInTheDocument();
    const summary = screen.getByLabelText("Policy safety summary");
    expect(within(summary).getByText("Unavailable")).toBeInTheDocument();
    expect(within(summary).getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save policy" }).hasAttribute("disabled")).toBe(true);
  });

  it("keeps free-plan policy visible but disables paid configuration", async () => {
    seededBillingResponse = { plan_code: "free", plan_template: {} };

    const { container } = renderPoliciesPage();

    expect(await screen.findByRole("heading", { name: "Human review waiting" })).toBeInTheDocument();
    expect(screen.getByText(/Read-only policy view/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upgrade plan" }).getAttribute("href")).toBe("/settings/billing");
    expect(screen.getByRole("button", { name: "Save policy" }).hasAttribute("disabled")).toBe(true);
    expect(container.querySelector(".policies-configuration-scope")?.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Allowed surface")).toBeInTheDocument();
  });

  it("saves comma-separated tool policy as structured arrays", async () => {
    renderPoliciesPage();

    await screen.findByRole("heading", { name: "Human review waiting" });
    fireEvent.change(screen.getByLabelText("Allowed tools"), {
      target: { value: "ledger.lookup, crm.update" },
    });
    fireEvent.change(screen.getByLabelText("Sensitive tools"), {
      target: { value: "ledger.refund, email.send, crm.delete" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save policy" }));

    await waitFor(() => expect(api.updatePilotPolicy).toHaveBeenCalled());
    expect(api.updatePilotPolicy.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        runtime_allowed_tools: ["ledger.lookup", "crm.update"],
        runtime_sensitive_tools: ["ledger.refund", "email.send", "crm.delete"],
        expected_updated_at: now,
      }),
    );
  });

  it("enables sequence-risk holds through the mandate toggle", async () => {
    mockPolicies({ payload: policy({ runtime_sequence_risk_enabled: false }) });
    renderPoliciesPage();

    await screen.findByRole("heading", { name: "Guardrails incomplete" });
    fireEvent.click(screen.getByLabelText(/Sequence risk holds/i));
    fireEvent.click(screen.getByRole("button", { name: "Save policy" }));

    await waitFor(() => expect(api.updatePilotPolicy).toHaveBeenCalled());
    expect(api.updatePilotPolicy.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ runtime_sequence_risk_enabled: true }),
    );
  });

  it("surfaces scoped rules, effective policy, and per-agent dry-run", async () => {
    renderPoliciesPage();

    expect(await screen.findByRole("heading", { name: "Scoped policy rules" })).toBeInTheDocument();
    const rules = screen.getByLabelText("Scoped policy rules");
    expect(within(rules).getByText("Refund Agent strict threshold")).toBeInTheDocument();
    expect(within(rules).getByText("Refund Agent / Refund / env:production")).toBeInTheDocument();
    expect(within(rules).getByText(/match #1/)).toBeInTheDocument();

    const effective = screen.getByLabelText("Effective policy preview");
    expect(within(effective).getByText("1 scoped rule matched.")).toBeInTheDocument();
    expect(within(effective).getByText("Approval above $100.00")).toBeInTheDocument();

    fireEvent.click(within(effective).getByRole("button", { name: "Run dry-run" }));

    await waitFor(() => expect(api.dryRunRuntimePolicy).toHaveBeenCalledTimes(1));
    expect(api.dryRunRuntimePolicy.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        agent_id: null,
        action_type: "refund",
        environment: "production",
        tool_args: { amount: 600, currency: "USD" },
      }),
    );
    expect(await within(effective).findByText("amount exceeds approval threshold $100.00")).toBeInTheDocument();
  });

  it("creates scoped rules from the editor as partial patches", async () => {
    renderPoliciesPage();

    await screen.findByRole("heading", { name: "Scoped policy rules" });
    fireEvent.click(screen.getByRole("button", { name: "New rule" }));
    const editor = screen.getByLabelText("Scoped rule editor");
    fireEvent.change(within(editor).getByLabelText("Rule name"), {
      target: { value: "Deploy approval rule" },
    });
    fireEvent.change(within(editor).getByLabelText("Action type"), {
      target: { value: "deploy_change" },
    });
    fireEvent.change(within(editor).getByLabelText("Approval threshold (USD)"), {
      target: { value: "10" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Create rule" }));

    await waitFor(() => expect(api.createRuntimePolicyRule).toHaveBeenCalledTimes(1));
    expect(api.createRuntimePolicyRule.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        name: "Deploy approval rule",
        action_type: "deploy_change",
        policy_patch: {
          runtime_amount_approval_threshold_usd: 10,
        },
      }),
    );
  });

  it("keeps explicit empty list overrides when editing a scoped rule", async () => {
    mockPolicies({
      rules: [
        scopedRule({
          policy_patch: {
            runtime_allowed_tools: ["ledger.lookup"],
          },
        }),
      ],
    });
    renderPoliciesPage();

    await screen.findByRole("heading", { name: "Scoped policy rules" });
    fireEvent.click(screen.getByRole("button", { name: /Refund Agent strict threshold/ }));
    const editor = screen.getByLabelText("Scoped rule editor");
    fireEvent.change(within(editor).getByLabelText("Allowed tools override"), {
      target: { value: "" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Save rule" }));

    await waitFor(() => expect(api.updateRuntimePolicyRule).toHaveBeenCalledTimes(1));
    expect(api.updateRuntimePolicyRule.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        policy_patch: {
          runtime_allowed_tools: [],
        },
      }),
    );
  });

  it("requires confirmation before enabling the runtime kill switch", async () => {
    renderPoliciesPage();

    await screen.findByRole("heading", { name: "Human review waiting" });
    fireEvent.click(screen.getByRole("button", { name: "Arm kill switch" }));
    expect(api.setRuntimePolicyKillSwitch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm kill switch" }));

    await waitFor(() => expect(api.setRuntimePolicyKillSwitch.mock.calls[0]?.[0]).toBe(true));
  });

  it("shows kill switch as a frozen mandate boundary with a resume action", async () => {
    mockPolicies({
      payload: policy({ kill_switch: true }),
      decisions: [],
    });
    api.setRuntimePolicyKillSwitch.mockResolvedValue({ project_id: "proj_1", enabled: false, policy: { kill_switch: false } });

    renderPoliciesPage();

    expect(await screen.findByRole("heading", { name: "Autonomy stopped" })).toBeInTheDocument();
    const mandate = screen.getByLabelText("Runtime action control mandate");
    expect(within(mandate).getByText("Kill switch on")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resume autonomy" }));
    expect(api.setRuntimePolicyKillSwitch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm resume" }));
    await waitFor(() => expect(api.setRuntimePolicyKillSwitch.mock.calls[0]?.[0]).toBe(false));
  });
});
