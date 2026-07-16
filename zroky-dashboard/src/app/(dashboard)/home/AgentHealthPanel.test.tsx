import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ActionIntentResponse, ActionRunnerResponse, OutcomeReconciliationView, RuntimePolicyDecisionResponse } from "@/lib/api";

import { AgentHealthPanel } from "./AgentHealthPanel";

const commonProps = {
  windowDays: 7,
  windowStart: "2026-07-08T09:00:00.000Z",
  generatedAt: "2026-07-15T09:00:00.000Z",
  mutations: [],
  staleAttempts: [],
  updatedLabel: "Updated just now",
  onRefresh: vi.fn(),
};

describe("AgentHealthPanel", () => {
  it("renders a premium empty state without fake metrics", () => {
    render(
      <AgentHealthPanel
        {...commonProps}
        loading={false}
        intents={[]}
        approvals={[]}
        outcomes={[]}
        actionRunners={[]}
        availability={{ runners: false, actions: false, policies: false, proof: false, mutations: false, attempts: false }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Agent health" })).toBeInTheDocument();
    expect(screen.getByText("No health history available yet.")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(7);
    expect(screen.getByRole("button", { name: "Refresh agent health" })).toBeInTheDocument();
  });

  it("renders real health signals and accessible timeline details", () => {
    render(
      <AgentHealthPanel
        {...commonProps}
        loading={false}
        actionRunners={[{ status: "online" } as ActionRunnerResponse]}
        intents={[{
          created_at: "2026-07-11T02:00:00.000Z",
          status: "completed",
          receipt_status: "generated",
          proof_status: "matched",
        } as ActionIntentResponse]}
        approvals={[{
          created_at: "2026-07-11T02:00:00.000Z",
          status: "allowed",
          decision: "allow",
          allowed: true,
          requires_approval: false,
        } as RuntimePolicyDecisionResponse]}
        outcomes={[{
          created_at: "2026-07-11T03:00:00.000Z",
          checked_at: "2026-07-11T03:00:00.000Z",
          verdict: "matched",
          verification_status: "verified",
        } as OutcomeReconciliationView]}
        availability={{ runners: true, actions: true, policies: true, proof: true, mutations: true, attempts: true }}
      />,
    );

    expect(screen.getByText("100", { selector: ".mc-health-score-ring strong" })).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Agent health history" }).children).toHaveLength(7);
    expect(screen.getByRole("button", { name: /Healthy.*1 actions, 0 attention items/i })).toBeInTheDocument();
  });
});
