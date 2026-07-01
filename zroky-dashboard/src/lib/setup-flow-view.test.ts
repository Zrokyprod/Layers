import { describe, expect, it } from "vitest";

import { buildSetupFlowView } from "@/lib/setup-flow-view";
import type { SetupReadiness } from "@/lib/setup-readiness";

function readiness(overrides: Partial<SetupReadiness> = {}): SetupReadiness {
  return {
    canEnablePolicy: false,
    canRunFirstAction: false,
    enrichmentChecks: [],
    enrichmentComplete: false,
    essentialChecks: [],
    essentialComplete: false,
    runnerStatus: "missing",
    state: "draft",
    verifierStatus: "missing",
    ...overrides,
  };
}

describe("setup-flow-view", () => {
  it("keeps live reserved for a real first matched receipt", () => {
    const view = buildSetupFlowView(readiness({
      canEnablePolicy: true,
      canRunFirstAction: true,
      essentialComplete: true,
      runnerStatus: "ready",
      state: "verifier_ready",
      verifierStatus: "ready",
    }), "Ops Agent");

    expect(view.title).toBe("Run the first protected action");
    expect(view.metrics.find((metric) => metric.id === "receipt")).toMatchObject({
      tone: "warning",
      value: "Waiting",
    });
  });

  it("marks the flow live when readiness is live", () => {
    const view = buildSetupFlowView(readiness({
      canEnablePolicy: true,
      canRunFirstAction: true,
      essentialComplete: true,
      runnerStatus: "ready",
      state: "live",
      verifierStatus: "ready",
    }), "Ops Agent");

    expect(view.title).toBe("Ops Agent is live and verified");
    expect(view.tone).toBe("success");
    expect(view.metrics.find((metric) => metric.id === "receipt")).toMatchObject({
      tone: "success",
      value: "Matched",
    });
  });
});
