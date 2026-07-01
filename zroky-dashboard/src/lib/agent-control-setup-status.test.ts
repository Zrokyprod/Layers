import { describe, expect, it } from "vitest";

import type { AgentProfileResponse } from "@/lib/api";
import type { CaptureHealthResponse } from "@/lib/types";
import { getAgentControlSetupStatus } from "./agent-control-setup-status";

const now = "2026-06-27T10:00:00.000Z";

function agentProfile(overrides: Partial<AgentProfileResponse> = {}): AgentProfileResponse {
  return {
    schema_version: "zroky.agent_tool_control.v1",
    id: "agent_profile_1",
    project_id: "proj_1",
    display_name: "Refund Agent",
    slug: "refund-agent",
    description: "Issues refunds through Zroky.",
    runtime_path: "sdk",
    framework: "langgraph",
    environment: "production",
    model_provider: "openai",
    model_name: "gpt-4.1",
    tool_names: ["stripe.refunds.create"],
    allowed_action_types: ["refund"],
    blocked_action_types: [],
    default_policy_id: null,
    risk_limits: {},
    verification_connectors: ["ledger_refund"],
    metadata: {},
    is_active: true,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function setupMetadata(): Record<string, unknown> {
  return {
    setup_source: "agent_control_setup_wizard",
    product_context: {
      product_name: "Customer Operations AI",
      business_goal: "Control refunds before money moves.",
      critical_objects: ["customer", "refund"],
      source_systems: ["Stripe"],
    },
    workflow_manifest: {
      workflow_id: "refund_customer",
      owner_team: "Support Platform",
      protected_actions: ["refund"],
    },
    action_contracts: [
      {
        id: "refund_customer.refund",
        verb: "TRANSFER",
        risk_class: "R4",
      },
    ],
    policy_preview: {
      approval_required_above_usd: 500,
      deny_above_usd: 5000,
      unknown_contract_decision: "deny",
    },
    runner_verification: {
      credential_ref: "cred_prod_stripe_refunds_scoped",
      verifier_connector: "ledger_refund",
      source_of_record: "Stripe refund ledger",
    },
    runtime_policy_mandate_enforced: false,
  };
}

function captureHealth(overrides: Partial<CaptureHealthResponse> = {}): CaptureHealthResponse {
  return {
    project_id: "proj_1",
    status: "connected",
    stale_after_minutes: 10,
    last_call_id: "call_1",
    last_seen_at: now,
    seconds_since_last_call: 8,
    last_provider: "openai",
    last_model: "gpt-4.1",
    last_call_type: "agent",
    last_source: "sdk_ingest",
    calls_24h: 1,
    sdk_events_24h: 1,
    gateway_events_24h: 0,
    retrieval_spans_24h: 0,
    memory_spans_24h: 0,
    trace_runs_24h: 1,
    trace_spans_24h: 1,
    policy_spans_24h: 1,
    handoff_spans_24h: 0,
    incomplete_trace_runs_24h: 0,
    projection_failures_24h: 0,
    gateway_count: 0,
    gateway_unhealthy_count: 0,
    gateway_worst_status: "unknown",
    gateway_spool_backlog: 0,
    gateway_spool_bytes: 0,
    gateway_spool_oldest_age_seconds: 0,
    gateway_loss_count: 0,
    gateway_backpressure_rejections: 0,
    gateway_last_heartbeat_at: null,
    error_events_24h: 0,
    outcome_events_24h: 1,
    sampled_recent_calls: 1,
    validation_warnings: [],
    ...overrides,
  };
}

describe("getAgentControlSetupStatus", () => {
  it("requires setup metadata before treating an agent profile as setup-ready", () => {
    const status = getAgentControlSetupStatus([agentProfile()], captureHealth());

    expect(status.state).toBe("incomplete");
    expect(status.completedCount).toBe(1);
    expect(status.checks.find((check) => check.id === "product_context")?.done).toBe(false);
  });

  it("keeps setup visible as a saved plan until enforcement is wired", () => {
    const status = getAgentControlSetupStatus(
      [agentProfile({ metadata: setupMetadata() })],
      captureHealth({ calls_24h: 0, outcome_events_24h: 0 }),
    );

    expect(status.state).toBe("plan_saved");
    expect(status.complete).toBe(false);
    expect(status.completedCount).toBe(status.totalCount);
  });

  it("does not mark setup live from capture alone without an enforced mandate", () => {
    const status = getAgentControlSetupStatus(
      [agentProfile({ metadata: setupMetadata() })],
      captureHealth({ calls_24h: 2, outcome_events_24h: 1 }),
    );

    expect(status.state).toBe("plan_saved");
    expect(status.complete).toBe(false);
  });

  it("shows policy enforced until a real protected action is captured", () => {
    const status = getAgentControlSetupStatus(
      [agentProfile({
        metadata: {
          ...setupMetadata(),
          runtime_policy_mandate_enforced: true,
        },
      })],
      captureHealth({ calls_24h: 0, outcome_events_24h: 0 }),
    );

    expect(status.state).toBe("policy_enforced");
    expect(status.complete).toBe(false);
    expect(status.title).toBe("Project policy enabled");
  });

  it("marks setup live when saved setup, enforced mandate, and live capture are present", () => {
    const status = getAgentControlSetupStatus(
      [agentProfile({
        metadata: {
          ...setupMetadata(),
          runtime_policy_mandate_enforced: true,
        },
      })],
      captureHealth({ calls_24h: 2, outcome_events_24h: 1 }),
    );

    expect(status.state).toBe("live");
    expect(status.complete).toBe(true);
    expect(status.progressPct).toBe(100);
  });
});
