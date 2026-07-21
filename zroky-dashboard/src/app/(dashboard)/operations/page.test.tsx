import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OperationsPage from "./page";

const api = vi.hoisted(() => ({
  listFinalApprovalRequirements: vi.fn(),
  listFinalIncidents: vi.fn(),
  listFinalRuns: vi.fn(),
}));

const queryState = vi.hoisted(() => ({
  overrides: {} as Record<string, { data?: unknown; error?: unknown; isError?: boolean; isLoading?: boolean }>,
}));

vi.mock("@/lib/api", () => api);

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey, queryFn }: { queryKey: unknown[]; queryFn: (input: { signal?: AbortSignal }) => unknown }) => {
    const key = queryKey.join(":");
    const override = queryState.overrides[key];
    if (override) {
      return {
        data: override.data,
        error: override.error,
        isError: Boolean(override.isError),
        isLoading: Boolean(override.isLoading),
      };
    }
    return {
      data: queryFn({}),
      error: null,
      isError: false,
      isLoading: false,
    };
  }),
}));

describe("OperationsPage", () => {
  beforeEach(() => {
    api.listFinalRuns.mockReset();
    api.listFinalIncidents.mockReset();
    api.listFinalApprovalRequirements.mockReset();
    queryState.overrides = {};
    api.listFinalRuns.mockReturnValue({
      items: [
        {
          id: "run_1",
          workflow_key: "refund-workflow",
          status: "running",
          created_at: "2026-07-21T10:00:00Z",
        },
      ],
    });
    api.listFinalIncidents.mockReturnValue([
      {
        id: "incident_1",
        status: "open",
        severity: "high",
        created_at: "2026-07-21T10:01:00Z",
        incident: { deviation_type: "wrong", reason: "Outcome graph classified as wrong." },
      },
    ]);
    api.listFinalApprovalRequirements.mockReturnValue({
      items: [
        {
          id: "approval_1",
          required_role: "admin",
          status: "pending",
          created_at: "2026-07-21T10:02:00Z",
        },
      ],
    });
  });

  it("renders live operations queues from final APIs", () => {
    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Outcome incidents need review" })).toBeInTheDocument();
    expect(screen.getByText("Open incidents")).toBeInTheDocument();
    expect(screen.getByText("Pending approvals")).toBeInTheDocument();
    expect(screen.getByText("wrong")).toBeInTheDocument();
    expect(screen.getByText("refund-workflow: running")).toBeInTheDocument();
    expect(screen.getByText("admin: pending")).toBeInTheDocument();
  });

  it("renders empty states without demo data", () => {
    api.listFinalRuns.mockReturnValue({ items: [] });
    api.listFinalIncidents.mockReturnValue([]);
    api.listFinalApprovalRequirements.mockReturnValue({ items: [] });

    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Operations are clear" })).toBeInTheDocument();
    expect(screen.getByText("No incidents found.")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Runs queue")).getByText("No runs found.")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Approvals queue")).getByText("No approval requirements found.")).toBeInTheDocument();
  });

  it("renders loading states without pretending queues are empty", () => {
    queryState.overrides = {
      "final-runs": { isLoading: true },
      "final-incidents": { isLoading: true },
      "final-approval-requirements": { isLoading: true },
    };

    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Loading operations" })).toBeInTheDocument();
    expect(screen.getByText("Loading incidents...")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Runs queue")).getByText("Loading runs...")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Approvals queue")).getByText("Loading approval requirements...")).toBeInTheDocument();
    expect(screen.queryByText("No incidents found.")).not.toBeInTheDocument();
  });

  it("renders API error and permission states without demo fallback", () => {
    queryState.overrides = {
      "final-runs": { isError: true, error: new Error("403 forbidden") },
      "final-incidents": { isError: true, error: new Error("403 forbidden") },
      "final-approval-requirements": { isError: true, error: new Error("403 forbidden") },
    };

    render(<OperationsPage />);

    expect(screen.getByRole("heading", { name: "Operations access unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Unable to load incidents from the live API.")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Runs queue")).getByText("Unable to load runs from the live API.")).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Approvals queue")).getByText("Unable to load approval requirements from the live API."),
    ).toBeInTheDocument();
    expect(screen.queryByText("No incidents found.")).not.toBeInTheDocument();
  });
});
