import { describe, expect, it } from "vitest";

import type {
  ActionIntentResponse,
  ActionRunnerResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";

import { calculateAgentHealth, calculateOverallHealthScore, type AgentHealthInput } from "./agent-health";

const generatedAt = "2026-07-15T09:00:00.000Z";

function baseInput(overrides: Partial<AgentHealthInput> = {}): AgentHealthInput {
  return {
    windowDays: 7,
    windowStart: "2026-07-08T09:00:00.000Z",
    generatedAt,
    intents: [],
    approvals: [],
    outcomes: [],
    mutations: [],
    staleAttempts: [],
    actionRunners: [],
    availability: { runners: true, actions: true, policies: true, proof: true, mutations: true, attempts: true },
    ...overrides,
  };
}

function intent(createdAt: string, completed: boolean): ActionIntentResponse {
  return {
    created_at: createdAt,
    status: completed ? "completed" : "authorized",
    receipt_status: completed ? "generated" : "missing",
    proof_status: completed ? "matched" : "pending",
  } as ActionIntentResponse;
}

function decision(createdAt: string, passing: boolean): RuntimePolicyDecisionResponse {
  return {
    created_at: createdAt,
    status: passing ? "allowed" : "blocked",
    decision: passing ? "allow" : "block",
    allowed: passing,
    requires_approval: false,
  } as RuntimePolicyDecisionResponse;
}

function outcome(createdAt: string, matched: boolean): OutcomeReconciliationView {
  return {
    created_at: createdAt,
    checked_at: createdAt,
    verdict: matched ? "matched" : "mismatched",
    verification_status: matched ? "verified" : "mismatched",
  } as OutcomeReconciliationView;
}

describe("calculateOverallHealthScore", () => {
  it("uses the documented 30/30/20/20 weighting", () => {
    expect(calculateOverallHealthScore({
      runnerAvailability: 100,
      actionSuccessRate: 80,
      policyPassRate: 90,
      proofIntegrity: 70,
    })).toBe(86);
  });

  it("does not invent a score when one dimension is unavailable", () => {
    expect(calculateOverallHealthScore({
      runnerAvailability: 100,
      actionSuccessRate: 80,
      policyPassRate: null,
      proofIntegrity: 70,
    })).toBeNull();
  });
});

describe("calculateAgentHealth", () => {
  it("derives health only from real runner, action, policy and proof records", () => {
    const snapshot = calculateAgentHealth(baseInput({
      actionRunners: [{ status: "online" } as ActionRunnerResponse],
      intents: [intent("2026-07-11T02:00:00.000Z", true), intent("2026-07-12T02:00:00.000Z", false)],
      approvals: [decision("2026-07-11T02:00:00.000Z", true), decision("2026-07-12T02:00:00.000Z", false)],
      outcomes: [outcome("2026-07-11T03:00:00.000Z", true), outcome("2026-07-12T03:00:00.000Z", false)],
    }));

    expect(snapshot.signals.map((signal) => signal.displayValue)).toEqual(["100%", "50%", "50%", "50%"]);
    expect(snapshot.overallScore).toBe(65);
    expect(snapshot.overallStatus).toBe("critical");
    expect(snapshot.timeline).toHaveLength(7);
    expect(snapshot.timeline.some((segment) => segment.status === "critical")).toBe(true);
  });

  it("returns a truthful no-data score and empty timeline", () => {
    const snapshot = calculateAgentHealth(baseInput({
      availability: { runners: false, actions: false, policies: false, proof: false, mutations: false, attempts: false },
    }));

    expect(snapshot.overallScore).toBeNull();
    expect(snapshot.overallStatus).toBe("no-data");
    expect(snapshot.timeline.every((segment) => segment.status === "no-data")).toBe(true);
  });
});
