import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RegressionContractView } from "@/lib/api";

import ContractProofPage from "./page";

const nav = vi.hoisted(() => ({
  params: { id: "contract_1" },
}));

const queryState = vi.hoisted(() => ({
  contract: null as RegressionContractView | null,
  error: null as Error | null,
  loading: false,
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

vi.mock("next/navigation", () => ({
  useParams: () => nav.params,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(() => ({
    data: queryState.contract,
    error: queryState.error,
    isLoading: queryState.loading,
  })),
}));

const now = "2026-06-19T08:00:00.000Z";

function contract(overrides: Partial<RegressionContractView> = {}): RegressionContractView {
  return {
    id: "contract_1",
    project_id: "proj_1",
    source_issue_id: "issue_47",
    name: "refund-status-required",
    description: "Refund status must be read before customer response.",
    severity: "critical",
    status: "active",
    active_version_id: "version_3",
    owner_id: "admin_1",
    created_at: now,
    updated_at: now,
    versions: [
      {
        id: "version_3",
        contract_id: "contract_1",
        version_number: 3,
        spec_version: "regression_contract_v1",
        spec_json: {
          schema: "regression_contract_v1",
          proof: {
            incident_confirmed: true,
            baseline_reproduced: true,
            candidate_verified: true,
            required_trials: 10,
            critical_violations: 0,
            fixture_pinned: true,
            evaluator_bundle_pinned: true,
            candidate_sha: "fix-sha-123",
            ci_gate_verdict: "pass",
          },
        },
        fixture_set_id: "fixture_1",
        baseline_release_id: "release_broken",
        trial_policy: { required_trials: 10, critical_violation_tolerance: 0 },
        evaluator_bundle_version: "default-v1",
        approved_by: "admin@zroky.test",
        approved_at: now,
        created_at: now,
      },
    ],
    ...overrides,
  };
}

describe("Contract proof page", () => {
  beforeEach(() => {
    queryState.contract = contract();
    queryState.error = null;
    queryState.loading = false;
  });

  it("renders the paid-launch proof artifact for an active contract", () => {
    render(<ContractProofPage />);

    expect(screen.getByRole("heading", { name: "refund-status-required" })).toBeInTheDocument();
    expect(screen.getByText("Launch ready")).toBeInTheDocument();
    expect(screen.getByText("9/9 proof checks satisfied")).toBeInTheDocument();

    const proofChecks = screen.getByLabelText("Proof checks");
    for (const label of [
      "Original incident",
      "Baseline reproduction",
      "Candidate SHA",
      "Candidate trials",
      "Critical violations",
      "Fixture",
      "Evaluator bundle",
      "Admin approval",
      "CI gate verdict",
    ]) {
      expect(within(proofChecks).getByText(label)).toBeInTheDocument();
    }

    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.getByText("Failed as expected")).toBeInTheDocument();
    expect(screen.getAllByText("fix-sha-123").length).toBeGreaterThan(0);
    expect(screen.getByText("10/10 passed")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("Pinned")).toBeInTheDocument();
    expect(screen.getAllByText("default-v1").length).toBeGreaterThan(0);
    expect(screen.getByText("pass")).toBeInTheDocument();
    expect(screen.getByText("issue_47")).toBeInTheDocument();
    expect(screen.getByText("release_broken")).toBeInTheDocument();
    expect(screen.getByText("fixture_1")).toBeInTheDocument();
  });

  it("blocks launch readiness when proof is incomplete", () => {
    queryState.contract = contract({
      status: "draft",
      active_version_id: null,
      versions: [
        {
          ...contract().versions[0],
          approved_at: null,
          approved_by: null,
          spec_json: {
            schema: "regression_contract_v1",
            proof: {
              baseline_reproduced: true,
              candidate_verified: true,
              required_trials: 8,
              critical_violations: 1,
              fixture_pinned: false,
              evaluator_bundle_pinned: false,
              candidate_sha: "",
            },
          },
        },
      ],
    });

    render(<ContractProofPage />);

    expect(screen.getByText("Incomplete")).toBeInTheDocument();
    expect(screen.getByText("Activation proof is incomplete.")).toBeInTheDocument();
    expect(screen.getByText("8/10 passed")).toBeInTheDocument();
    expect(screen.getByText("Missing confirmation")).toBeInTheDocument();
  });
});
