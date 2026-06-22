import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PilotPolicyPayload, PilotPolicyResponse, RuntimePolicyDecisionResponse } from "@/lib/api";
import PoliciesPage from "./page";

const api = vi.hoisted(() => ({
  getPilotPolicy: vi.fn(),
  listRuntimePolicyApprovals: vi.fn(),
  setRuntimePolicyKillSwitch: vi.fn(),
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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

const now = "2026-06-20T09:00:00.000Z";

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
}: {
  payload?: PilotPolicyPayload;
  decisions?: RuntimePolicyDecisionResponse[];
} = {}) {
  const response = policyResponse(payload);
  api.getPilotPolicy.mockResolvedValue(response);
  api.updatePilotPolicy.mockResolvedValue(response);
  api.setRuntimePolicyKillSwitch.mockResolvedValue({ project_id: "proj_1", enabled: true, policy: { kill_switch: true } });
  api.listRuntimePolicyApprovals.mockResolvedValue({ items: decisions, total_in_page: decisions.length });
}

function renderPoliciesPage() {
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

  it("surfaces mandate proof flow and latest runtime decisions", async () => {
    renderPoliciesPage();

    expect(await screen.findByRole("heading", { name: "Policies" })).toBeInTheDocument();
    expect(await screen.findByText("Controlled")).toBeInTheDocument();
    expect(screen.getByText("Mandate Control defines what autonomous agents may do, what must pause, what gets blocked, and where proof is recorded.")).toBeInTheDocument();

    const flow = screen.getByLabelText("Runtime mandate flow");
    for (const label of ["Mandate", "Runtime gate", "Human hold", "Evidence"]) {
      expect(within(flow).getByText(label)).toBeInTheDocument();
    }

    const proof = screen.getByLabelText("Mandate proof flow");
    for (const label of ["Mandate boundary", "Pre-action gate", "Human hold", "Evidence trail"]) {
      expect(within(proof).getByText(label)).toBeInTheDocument();
    }
    expect(within(proof).getByText("2 allowed tools, 2 sensitive tools.")).toBeInTheDocument();
    expect(within(proof).getByText("3/3 high-stakes guardrails enabled.")).toBeInTheDocument();
    expect(within(proof).getByText("1 pending approval before execution.")).toBeInTheDocument();
    expect(within(proof).getByText("2 recent decisions loaded.")).toBeInTheDocument();

    const boundary = screen.getByLabelText("Current mandate boundary");
    expect(within(boundary).getByText("Allowed surface")).toBeInTheDocument();
    expect(within(boundary).getAllByText("2 tools").length).toBeGreaterThan(0);
    expect(within(boundary).getByText("Sensitive actions hold for 15 minutes.")).toBeInTheDocument();
    expect(within(boundary).getByText("$50.00 per action")).toBeInTheDocument();

    const feed = screen.getByLabelText("Latest runtime decisions");
    expect(within(feed).getByText("refund")).toBeInTheDocument();
    expect(within(feed).getByText("Refund Agent - ledger.refund - call_1")).toBeInTheDocument();
    expect(within(feed).getByText("amount_requires_approval")).toBeInTheDocument();
    expect(within(feed).getByText("pending approval")).toBeInTheDocument();
    expect(within(feed).getByText("delete")).toBeInTheDocument();
    expect(within(feed).getByText("tool_not_allowed")).toBeInTheDocument();
  });

  it("saves comma-separated tool policy as structured arrays", async () => {
    renderPoliciesPage();

    await screen.findByText("Controlled");
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
      }),
    );
  });

  it("shows kill switch as a frozen mandate boundary", async () => {
    mockPolicies({
      payload: policy({ kill_switch: true }),
      decisions: [],
    });

    renderPoliciesPage();

    expect(await screen.findByText("Stopped")).toBeInTheDocument();
    const proof = screen.getByLabelText("Mandate proof flow");
    expect(within(proof).getByText("Frozen by kill switch.")).toBeInTheDocument();
    expect(screen.getByText("Kill switch on")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Kill switch" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
