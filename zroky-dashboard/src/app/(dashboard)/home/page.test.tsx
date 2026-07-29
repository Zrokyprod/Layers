import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { HomeSummaryResponse } from "@/lib/api";
import type { CurrentUserProjectResponse } from "@/lib/types";

import HomePage from "./page";

const api = vi.hoisted(() => ({
  getHomeSummary: vi.fn(),
  listMyProjects: vi.fn(),
}));

const storeState = vi.hoisted(() => ({
  selectedProject: "proj_1",
  realTimeEnabled: false,
  dateRange: { from: null, to: null },
  setDateRange: vi.fn(),
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

vi.mock("@/lib/store", () => ({
  useDashboardStore: <T,>(
    selector: (state: {
      selectedProject: string;
      realTimeEnabled: boolean;
      dateRange: { from: Date | null; to: Date | null };
      setDateRange: (range: { from: Date | null; to: Date | null }) => void;
    }) => T,
  ) => selector(storeState),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getHomeSummary: api.getHomeSummary,
    listMyProjects: api.listMyProjects,
  };
});

const now = "2026-05-29T10:00:00.000Z";

function project(role = "owner"): CurrentUserProjectResponse {
  return {
    membership_id: "mem_1",
    project_id: "proj_1",
    project_name: "Acme",
    role,
    is_active: true,
    created_at: now,
    updated_at: now,
  };
}

function summary(overrides: Partial<HomeSummaryResponse> = {}): HomeSummaryResponse {
  return {
    project_id: "proj_1",
    window_days: 7,
    window_start: "2026-05-22T10:00:00.000Z",
    generated_at: now,
    metrics: {
      controlled_actions: 300,
      pending_approvals: 6,
      verified_outcomes: 142,
      outcome_checks: 145,
      receipts_generated: 1248,
      bypass_mutations: 12,
      unreceipted_mutations: 0,
      sequence_risks: 0,
    },
    sources: {
      home_summary: true,
      intents: true,
      approvals: true,
      outcomes: true,
      outcome_summary: true,
      source_summary: true,
      mutations: true,
      stale_attempts: true,
      agent_profiles: true,
      action_runners: true,
      api_keys: true,
      billing_usage: true,
    },
    data: {
      intents: [],
      approvals: [
        approval("decision_1"),
        approval("decision_2"),
        approval("decision_3"),
        approval("decision_4"),
        approval("decision_5"),
        approval("decision_6"),
      ],
      outcomes: [
        outcome("outcome_1", "mismatched"),
        outcome("outcome_2", "matched"),
        outcome("outcome_3", "matched"),
      ],
      outcome_summary: {
        window_days: 7,
        total: 300,
        matched: 142,
        mismatched: 3,
        not_verified: 155,
      },
      source_summary: {
        total: 10,
        matched_receipt: 8,
        authorized_external: 0,
        legacy_path: 0,
        unmanaged_agent_action: 1,
        policy_bypass: 1,
        unknown_actor: 0,
        unreceipted: 2,
        connected_feeds: 8,
        successful_pollers: 7,
      },
      mutations: [
        mutation("mutation_1", "policy_bypass"),
        mutation("mutation_2", "unmanaged_agent_action"),
      ],
      stale_attempts: [attempt()],
      agent_profiles: [
        {
          schema_version: "zroky.agent_tool_control.v1",
          id: "agent_1",
          project_id: "proj_1",
          display_name: "Payroll Agent",
          slug: "payroll-agent",
          description: null,
          runtime_path: "sdk",
          framework: null,
          environment: "production",
          model_provider: null,
          model_name: null,
          tool_names: ["workday.export"],
          allowed_action_types: ["custom"],
          blocked_action_types: [],
          default_policy_id: "policy_1",
          risk_limits: {},
          verification_connectors: ["generic_rest"],
          metadata: {},
          is_active: true,
          created_at: now,
          updated_at: now,
        },
      ],
      agent_profile_meta: { active_count: 24, max_active_agents: 100, limit_reached: false },
      action_runners: [
        {
          runner_id: "runner_1",
          project_id: "proj_1",
          name: "Production runner",
          runner_type: "local",
          environment: "production",
          status: "online",
          supported_operation_kinds: ["read"],
          credential_scope: {},
          heartbeat_payload: {},
          capability_version: null,
          last_heartbeat_at: now,
          created_at: now,
          updated_at: now,
        },
      ],
      api_keys: [],
      billing_usage: null,
    },
    ...overrides,
  };
}

function approval(id: string) {
  return {
    id,
    project_id: "proj_1",
    trace_id: "trace_1",
    call_id: "call_1",
    agent_name: "Vendor Payments WF",
    role: "agent",
    action_type: "payment_adjustment",
    tool_name: "Vendor Payments",
    decision: "requires_approval" as const,
    status: "pending_approval" as const,
    allowed: false,
    requires_approval: true,
    reasons: ["Policy exception"],
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
  };
}

function outcome(id: string, verdict: "matched" | "mismatched") {
  return {
    id,
    project_id: "proj_1",
    call_id: null,
    trace_id: null,
    runtime_policy_decision_id: null,
    action_type: verdict === "mismatched" ? "payroll export" : "evidence bundle",
    connector_type: verdict === "mismatched" ? "Workday Payroll" : "generic_rest",
    system_ref: "Payroll Export WF",
    verdict,
    verification_status: verdict,
    reason: null,
    amount_usd: null,
    currency: null,
    claimed: {},
    actual: {},
    comparison: {},
    idempotency_key: null,
    metadata: {},
    checked_at: now,
    created_at: now,
  };
}

function mutation(id: string, classification: "policy_bypass" | "unmanaged_agent_action") {
  return {
    id,
    project_id: "proj_1",
    source_system: id === "mutation_1" ? "Workday Payroll" : "Salesforce",
    mutation_id: id,
    action_type: "payroll export",
    resource_type: "record",
    resource_id: "rec_1",
    system_ref: "rec_1",
    actor_type: "agent",
    actor_id: "agent_1",
    zroky_action_id: null,
    action_receipt_id: null,
    idempotency_key: null,
    classification,
    metadata: {},
    occurred_at: now,
    created_at: now,
  };
}

function attempt() {
  return {
    attempt_id: "attempt_1",
    project_id: "proj_1",
    action_id: "DB Recovery WF",
    runner_id: "PostgreSQL",
    attempt_number: 1,
    status: "failed",
    idempotency_key: "attempt_idem",
    credential_ref: "secret_ref",
    plan_digest: "plan_digest",
    execution_plan: {},
    result_summary: {},
    error_message: "timeout",
    protected_credential_returned: false,
    requested_by_subject: null,
    started_at: now,
    finished_at: null,
    created_at: now,
    updated_at: now,
  };
}

describe("Home dashboard", () => {
  beforeEach(() => {
    api.getHomeSummary.mockReset();
    api.listMyProjects.mockReset();
    api.getHomeSummary.mockResolvedValue(summary());
    api.listMyProjects.mockResolvedValue([project()]);
    storeState.selectedProject = "proj_1";
    storeState.realTimeEnabled = false;
    storeState.dateRange = { from: null, to: null };
    storeState.setDateRange.mockImplementation((range) => {
      storeState.dateRange = range;
    });
    window.history.pushState({}, "", "/home");
    window.localStorage.clear();
  });

  it("renders the proof-first degraded dashboard without old Home language", async () => {
    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "DEGRADED" })).toBeInTheDocument();
    expect(screen.getByLabelText("Proof posture")).toBeInTheDocument();
    expect(screen.getByLabelText("Proof metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Attention queue")).toBeInTheDocument();
    expect(screen.getByLabelText("Trust-machine health")).toBeInTheDocument();
    expect(screen.getByLabelText("Recent proof")).toBeInTheDocument();
    expect(screen.queryByLabelText("Quick actions")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Verification readiness")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Trust Advisor")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Control surface")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Coverage")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Agent/system scope")).not.toBeInTheDocument();

    const proofMetrics = screen.getByLabelText("Proof metrics");
    expect(within(proofMetrics).getByText("Mismatches caught")).toBeInTheDocument();
    expect(within(proofMetrics).getByText("3")).toBeInTheDocument();
    expect(within(proofMetrics).getByText("Coverage")).toBeInTheDocument();
    expect(within(proofMetrics).getByText("47%")).toBeInTheDocument();

    expect(screen.getByText("Connector test-read")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resolve blocker" }).getAttribute("href")).toBe("/integrations");
    expect(screen.queryByText("Good morning")).not.toBeInTheDocument();
    expect(screen.queryByText("Mission Control")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Agent health over time")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Recent protected actions")).not.toBeInTheDocument();
  });

  it("renders the attention queue as a compact ranked list", async () => {
    render(<HomePage />);

    const queue = await screen.findByLabelText("Attention queue");
    expect(within(queue).queryByRole("columnheader", { name: "Priority" })).not.toBeInTheDocument();
    expect(within(queue).queryByRole("columnheader", { name: "Source/system" })).not.toBeInTheDocument();
    expect(within(queue).getByText("Mismatch in payroll export")).toBeInTheDocument();
    expect(within(queue).getAllByText("Approval required: policy exception").length).toBeGreaterThan(0);
    expect(within(queue).getByText("Recovery job failed")).toBeInTheDocument();
  });

  it("refetches summary data when the Home window changes", async () => {
    const { rerender } = render(<HomePage />);

    await waitFor(() => expect(api.getHomeSummary).toHaveBeenCalledWith(7, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "24h" }));
    expect(storeState.setDateRange).toHaveBeenCalled();
    rerender(<HomePage />);

    await waitFor(() => expect(api.getHomeSummary).toHaveBeenCalledWith(1, expect.any(AbortSignal)));
  });

  it("keeps owner-only remediation disabled for viewer role", async () => {
    api.listMyProjects.mockResolvedValue([project("viewer")]);

    render(<HomePage />);

    await screen.findByText("Proof posture");
    expect(screen.queryByText("Read-only")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Resolve blocker" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Resolve blocker")[0].getAttribute("aria-disabled")).toBe("true");
  });

  it("uses a first-run layout without fake activity or fake chart", async () => {
    api.getHomeSummary.mockResolvedValue(
      summary({
        metrics: {
          controlled_actions: 0,
          pending_approvals: 0,
          verified_outcomes: 0,
          outcome_checks: 0,
          receipts_generated: 0,
          bypass_mutations: 0,
          unreceipted_mutations: 0,
          sequence_risks: 0,
        },
        data: {
          intents: [],
          approvals: [],
          outcomes: [],
          outcome_summary: { window_days: 7, total: 0, matched: 0, mismatched: 0, not_verified: 0 },
          source_summary: {
            total: 0,
            matched_receipt: 0,
            authorized_external: 0,
            legacy_path: 0,
            unmanaged_agent_action: 0,
            policy_bypass: 0,
            unknown_actor: 0,
            unreceipted: 0,
            connected_feeds: 0,
            successful_pollers: 0,
          },
          mutations: [],
          stale_attempts: [],
          agent_profiles: [],
          agent_profile_meta: { active_count: 0, max_active_agents: 100, limit_reached: false },
          action_runners: [],
          api_keys: [],
          billing_usage: null,
        },
      }),
    );

    render(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Build the proof rail before trusting automated work" })).toBeInTheDocument();
    expect(screen.getByLabelText("First-run setup")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect source" }).getAttribute("href")).toBe("/integrations");
    expect(screen.queryByLabelText("Proof posture")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Proof metrics")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Attention queue")).not.toBeInTheDocument();
    expect(screen.queryByText("No events yet")).not.toBeInTheDocument();
    expect(screen.queryByText("No coverage trend yet")).not.toBeInTheDocument();
  });

  it("does not turn a failed home summary into reassuring zero metrics", async () => {
    api.getHomeSummary.mockRejectedValue(new Error("backend unavailable"));

    render(<HomePage />);

    await waitFor(() => expect(api.getHomeSummary).toHaveBeenCalled());
    expect(await screen.findByText("12 source feed unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText("Home unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "INACTIVE" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Proof metrics")).not.toBeInTheDocument();
  });

  it("shows an auth state instead of source outage copy on 401", async () => {
    api.getHomeSummary.mockRejectedValue(Object.assign(new Error("Session expired"), { status: 401 }));

    render(<HomePage />);

    await waitFor(() => expect(api.getHomeSummary).toHaveBeenCalled());
    expect(await screen.findByText("Sign in to load proof posture")).toBeInTheDocument();
    expect(screen.getByLabelText("Home authentication required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/auth/login");
    expect(screen.queryByText("12 source feed unavailable")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Proof metrics")).not.toBeInTheDocument();
  });

  it("renders local demo Home without calling the backend", async () => {
    window.history.pushState({}, "", "/home?demoHome=1");

    render(<HomePage />);

    expect(await screen.findByText("3 mismatches caught")).toBeInTheDocument();
    expect(api.getHomeSummary).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Proof metrics")).toBeInTheDocument();
    expect(screen.queryByText("Sign in to load proof posture")).not.toBeInTheDocument();
    expect(screen.queryByText("12 source feed unavailable")).not.toBeInTheDocument();
  });
});
