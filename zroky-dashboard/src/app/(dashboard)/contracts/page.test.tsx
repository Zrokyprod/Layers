import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GoldenSetView, RegressionContractView } from "@/lib/api";

import ContractsPage from "./page";

const api = vi.hoisted(() => ({
  importGoldenContracts: vi.fn(),
  listGoldenSets: vi.fn(),
  listRegressionContracts: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  contracts: [] as RegressionContractView[],
  fixtures: [] as GoldenSetView[],
  contractsError: null as Error | null,
  fixturesError: null as Error | null,
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

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: unknown[] }) => {
    const key = queryKey[0];
    if (key === "regression-contracts") {
      return {
        data: queryState.contracts,
        error: queryState.contractsError,
        isLoading: false,
      };
    }
    if (key === "golden-sets") {
      return {
        data: { items: queryState.fixtures, next_cursor: null, total_in_page: queryState.fixtures.length },
        error: queryState.fixturesError,
        isLoading: false,
      };
    }
    return { data: undefined, error: null, isLoading: false };
  }),
  useMutation: vi.fn((options: {
    mutationFn: () => unknown;
    onSuccess?: (data: unknown) => void;
  }) => ({
    mutate: () => {
      Promise.resolve()
        .then(() => options.mutationFn())
        .then((data) => options.onSuccess?.(data));
    },
    data: null,
    error: null,
    isPending: false,
  })),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

const now = "2026-06-19T08:00:00.000Z";

function contract(overrides: Partial<RegressionContractView> = {}): RegressionContractView {
  return {
    id: "contract_1",
    project_id: "proj_1",
    source_issue_id: "issue_47",
    name: "Refund policy Contract",
    description: "Refund status must be read before customer response.",
    severity: "critical",
    status: "active",
    active_version_id: "version_1",
    owner_id: "owner_1",
    created_at: now,
    updated_at: now,
    versions: [
      {
        id: "version_1",
        contract_id: "contract_1",
        version_number: 1,
        spec_version: "regression_contract_v1",
        spec_json: { proof: { candidate_sha: "fix-sha-123" } },
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

function fixture(overrides: Partial<GoldenSetView> = {}): GoldenSetView {
  return {
    id: "fixture_1",
    project_id: "proj_1",
    name: "Refund fixture set",
    description: "Verified refund flow evidence",
    judge_config_json: JSON.stringify({ source_issue_id: "issue_47" }),
    is_flaky: false,
    blocks_ci: true,
    trace_count: 12,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function mockContracts({
  contracts = [
    contract(),
    contract({
      id: "contract_2",
      active_version_id: null,
      name: "Address update Contract",
      severity: "medium",
      status: "draft",
      versions: [
        {
          ...contract().versions[0],
          id: "version_2",
          contract_id: "contract_2",
          fixture_set_id: null,
          baseline_release_id: null,
          approved_at: null,
          approved_by: null,
        },
      ],
    }),
  ],
  fixtures = [fixture(), fixture({ id: "fixture_2", name: "Address fixture set", description: "Address update evidence", trace_count: 0, blocks_ci: false })],
}: {
  contracts?: RegressionContractView[];
  fixtures?: GoldenSetView[];
} = {}) {
  queryState.contracts = contracts;
  queryState.fixtures = fixtures;
  queryState.contractsError = null;
  queryState.fixturesError = null;
  api.importGoldenContracts.mockResolvedValue({ imported_count: 1, versions: [] });
}

describe("Contracts page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockContracts();
  });

  it("renders contract readiness summary, proof flow, and contract columns", () => {
    render(<ContractsPage />);

    expect(screen.getByRole("heading", { name: "Contracts" })).toBeInTheDocument();
    expect(screen.getByText("Activated incident contracts and the fixture evidence used by repository replay and CI gates.")).toBeInTheDocument();
    const summary = screen.getByLabelText("Contract summary");
    for (const label of ["Active", "Needs approval", "Fixtures", "Gate coverage"]) {
      expect(within(summary).getByText(label)).toBeInTheDocument();
    }
    expect(within(summary).getByText("1/2")).toBeInTheDocument();

    const proofFlow = screen.getByLabelText("Contract activation proof flow");
    for (const label of ["Source incident", "Fixture evidence", "Approved version", "CI gate"]) {
      expect(within(proofFlow).getByText(label)).toBeInTheDocument();
    }
    expect(within(proofFlow).getByText("1/2 versions pinned; 1/2 fixture sets contain traces")).toBeInTheDocument();
    expect(within(proofFlow).getByText("1/2 contracts actively blocking regressions")).toBeInTheDocument();

    const table = screen.getByRole("table");
    for (const heading of ["Contract", "Severity", "Status", "Version", "Proof", "Fixture", "Updated"]) {
      expect(within(table).getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText("Refund policy Contract")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Address update Contract")).toBeInTheDocument();
    expect(screen.getByText("Missing pins")).toBeInTheDocument();
  });

  it("switches to fixture evidence without losing workspace controls", () => {
    render(<ContractsPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Fixtures" }));

    const table = screen.getByRole("table");
    for (const heading of ["Fixture set", "Traces", "CI", "Updated", "Open"]) {
      expect(within(table).getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText("Refund fixture set")).toBeInTheDocument();
    expect(screen.getByText("Verified refund flow evidence")).toBeInTheDocument();
    expect(screen.getByText("Blocks CI")).toBeInTheDocument();
    expect(screen.getByText("Address fixture set")).toBeInTheDocument();
    expect(screen.getByText("Address update evidence")).toBeInTheDocument();
    expect(screen.getByText("Evidence only")).toBeInTheDocument();
    expect(screen.getByLabelText("Search contracts or fixtures")).toBeInTheDocument();
  });

  it("shows a composed empty state when no contracts are imported", () => {
    mockContracts({ contracts: [], fixtures: [] });

    render(<ContractsPage />);

    expect(screen.getByText("No contracts yet")).toBeInTheDocument();
    expect(screen.getByText("0/0")).toBeInTheDocument();
    expect(screen.getByText("0/0 contracts actively blocking regressions")).toBeInTheDocument();
  });
});
