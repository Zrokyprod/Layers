import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerLaunchReadinessPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerLaunchReadiness } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerLaunchReadiness: vi.fn(),
}));

const passGate = (code: string, title: string) => ({
  code,
  title,
  status: "pass",
  summary: `${title} has proof.`,
  blockers: [],
  evidence: [{ label: "proof", value: 1, status: "pass", detail: null }],
  verification_commands: [`verify ${code}`],
});

const readiness: OwnerLaunchReadiness = {
  generated_at: "2026-06-12T10:00:00Z",
  product_standard: "Did Zroky prevent an important AI agent failure from silently repeating?",
  overall_status: "blocked",
  paid_launch_allowed: false,
  hard_blockers: ["honest_replay_proof:stub_replay_marked_verified"],
  verification_commands: [
    "powershell -ExecutionPolicy Bypass -File scripts/verify_paid_launch_readiness.ps1",
    "python -m pytest tests/test_tenant_project_route_scoping.py",
  ],
  gates: [
    passGate("durable_capture", "Durable Capture"),
    passGate("tenant_isolation", "Tenant Isolation"),
    {
      code: "honest_replay_proof",
      title: "Honest Replay Proof",
      status: "fail",
      summary: "Replay must not fake proof.",
      blockers: ["stub_replay_marked_verified"],
      evidence: [
        { label: "trusted_verified_replays_7d", value: 0, status: null, detail: null },
        { label: "stub_marked_verified", value: 1, status: null, detail: null },
      ],
      verification_commands: ["python -m pytest tests/test_replay_runs.py"],
    },
    {
      code: "runtime_risk_stop",
      title: "Runtime Risk Stop",
      status: "not_verified",
      summary: "Risky actions must pause before damage.",
      blockers: ["runtime_risk_stop_evidence_missing"],
      evidence: [{ label: "risk_stopped_7d", value: 0, status: null, detail: null }],
      verification_commands: ["python -m pytest tests/test_runtime_policy_gate.py"],
    },
    {
      code: "outcome_verification",
      title: "Outcome Verification",
      status: "fail",
      summary: "Money-touching actions must reconcile against the system of record.",
      blockers: ["outcome_mismatch_detected", "outcome_not_verified"],
      evidence: [
        { label: "reconciliation_checks_7d", value: 2, status: null, detail: null },
        { label: "matched_7d", value: 0, status: null, detail: null },
        { label: "mismatched_7d", value: 1, status: null, detail: null },
        { label: "not_verified_7d", value: 1, status: null, detail: null },
      ],
      verification_commands: ["python -m pytest tests/test_outcome_reconciliation.py"],
    },
  ],
};

function setHookData(data: OwnerLaunchReadiness | null, error: Error | null = null) {
  vi.mocked(hooks.useOwnerLaunchReadiness).mockReturnValue({
    data,
    error,
    dataUpdatedAt: data ? Date.parse(data.generated_at) : 0,
    refetch: vi.fn(),
  } as ReturnType<typeof hooks.useOwnerLaunchReadiness>);
}

describe("OwnerLaunchReadinessPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders blocked launch readiness with exact gate evidence", () => {
    setHookData(readiness);

    render(<OwnerLaunchReadinessPage />);

    expect(screen.getByRole("heading", { name: "Launch Readiness" })).toBeInTheDocument();
    expect(screen.getByText("Paid launch blocked")).toBeInTheDocument();
    expect(screen.getByText(readiness.product_standard)).toBeInTheDocument();
    expect(screen.getByText("honest_replay_proof:stub_replay_marked_verified")).toBeInTheDocument();

    const gateRegion = screen.getByLabelText("Required launch gates");
    expect(within(gateRegion).getByText("Honest Replay Proof")).toBeInTheDocument();
    expect(within(gateRegion).getByText("stub_replay_marked_verified")).toBeInTheDocument();
    expect(within(gateRegion).getByText("Runtime Risk Stop")).toBeInTheDocument();
    expect(within(gateRegion).getByText("runtime_risk_stop_evidence_missing")).toBeInTheDocument();
    expect(within(gateRegion).getByText("Outcome Verification")).toBeInTheDocument();
    expect(within(gateRegion).getByText("outcome_mismatch_detected")).toBeInTheDocument();
    expect(within(gateRegion).getByText("outcome_not_verified")).toBeInTheDocument();
    expect(screen.getByText("powershell -ExecutionPolicy Bypass -File scripts/verify_paid_launch_readiness.ps1")).toBeInTheDocument();
  });

  it("does not render a fake healthy state when launch readiness fails to load", () => {
    setHookData(null, new Error("HTTP 500"));

    render(<OwnerLaunchReadinessPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("Paid launch allowed")).toBe(null);
  });
});
