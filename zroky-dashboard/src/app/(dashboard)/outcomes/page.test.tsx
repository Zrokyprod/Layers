import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OutcomesPage from "./page";

const apiState = vi.hoisted(() => ({
  reconcileSavedConnector: vi.fn(),
}));

const hookState = vi.hoisted(() => ({
  summaryRefetch: vi.fn(),
  checksRefetch: vi.fn(),
  sourceMutationSummaryRefetch: vi.fn(),
  unreceiptedMutationsRefetch: vi.fn(),
  summary: {
    window_days: 30,
    total: 3,
    matched: 1,
    mismatched: 1,
    not_verified: 1,
    verified: 1,
    pending: 0,
    unverifiable: 1,
    cancelled: 0,
  },
  sourceMutationSummary: {
    total: 4,
    matched_receipt: 1,
    authorized_external: 1,
    legacy_path: 0,
    unmanaged_agent_action: 1,
    policy_bypass: 1,
    unknown_actor: 1,
    unreceipted: 3,
  },
  unreceiptedMutations: [
    {
      id: "mutation_bypass_1",
      project_id: "proj_1",
      source_system: "stripe",
      mutation_id: "evt_refund_outside_zroky",
      action_type: "refund",
      resource_type: "refund",
      resource_id: "rf_bypass",
      system_ref: "stripe:rf_bypass",
      actor_type: "ai_agent",
      actor_id: "refund-agent",
      zroky_action_id: null,
      action_receipt_id: null,
      idempotency_key: null,
      classification: "policy_bypass",
      metadata: { protected_action: true },
      occurred_at: "2026-06-20T09:03:00Z",
      created_at: "2026-06-20T09:03:00Z",
    },
  ],
  checks: [
    {
      id: "check_mismatch",
      project_id: "proj_1",
      call_id: "call_refund_api",
      trace_id: "trace_refund_api",
      runtime_policy_decision_id: "decision_1",
      action_type: "refund",
      connector_type: "ledger_refund_api",
      reverify_connector: "ledger_refund_api",
      system_ref: "ledger:rf_999",
      verdict: "mismatched",
      verification_status: "mismatched",
      reason: "field_mismatch",
      amount_usd: 42.5,
      currency: "USD",
      claimed: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD", agent_name: "refund-agent" },
      actual: { refund_id: "rf_999", amount_usd: 41.5, currency: "USD" },
      comparison: {
        compared_fields: [
          { field: "amount_usd", claimed: 42.5, actual: 41.5, matched: false },
          { field: "currency", claimed: "USD", actual: "USD", matched: true },
        ],
        mismatches: [{ field: "amount_usd" }],
      },
      idempotency_key: "call_refund_api:rf_999",
      metadata: { source: "test", agent_name: "refund-agent", action_id: "action_1" },
      checked_at: "2026-06-20T09:00:00Z",
      created_at: "2026-06-20T09:00:00Z",
    },
    {
      id: "check_matched",
      project_id: "proj_1",
      call_id: "call_email_api",
      trace_id: null,
      runtime_policy_decision_id: null,
      action_type: "email",
      connector_type: "email_provider",
      reverify_connector: null,
      system_ref: "email:msg_1",
      verdict: "matched",
      verification_status: "verified",
      reason: "all_compared_fields_matched",
      amount_usd: null,
      currency: null,
      claimed: { email: "customer@example.com", email_status: "delivered" },
      actual: { email: "customer@example.com", email_status: "delivered" },
      comparison: { compared_fields: [], mismatches: [] },
      idempotency_key: null,
      metadata: null,
      checked_at: "2026-06-20T09:01:00Z",
      created_at: "2026-06-20T09:01:00Z",
    },
    {
      id: "check_not_verified",
      project_id: "proj_1",
      call_id: null,
      trace_id: "trace_payment_api",
      runtime_policy_decision_id: null,
      action_type: "payment",
      connector_type: "ledger_refund_api",
      reverify_connector: "ledger_refund_api",
      system_ref: "ledger:pay_1",
      verdict: "not_verified",
      verification_status: "unverifiable",
      reason: "system_of_record_missing",
      amount_usd: 120,
      currency: "USD",
      claimed: { payment_id: "pay_1", amount_usd: 120 },
      actual: null,
      comparison: { compared_fields: [], mismatches: [] },
      idempotency_key: null,
      metadata: null,
      checked_at: "2026-06-20T09:02:00Z",
      created_at: "2026-06-20T09:02:00Z",
    },
  ],
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
    reconcileSavedConnector: apiState.reconcileSavedConnector,
  };
});

vi.mock("@/lib/hooks", () => ({
  useOutcomeReconciliationSummary: () => ({
    data: hookState.summary,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: hookState.summaryRefetch,
  }),
  useOutcomeReconciliations: () => ({
    data: { items: hookState.checks, total_in_page: hookState.checks.length },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: hookState.checksRefetch,
  }),
  useSourceMutationSummary: () => ({
    data: hookState.sourceMutationSummary,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: hookState.sourceMutationSummaryRefetch,
  }),
  useUnreceiptedSourceMutations: () => ({
    data: { items: hookState.unreceiptedMutations, total_in_page: hookState.unreceiptedMutations.length },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: hookState.unreceiptedMutationsRefetch,
  }),
}));

function metric(label: string): HTMLElement {
  const metrics = screen.getByLabelText("Outcome verification metrics");
  const node = within(metrics).getByText(label);
  const card = node.closest(".dashboard-metric-card");
  if (!card) throw new Error(`Missing metric ${label}`);
  return card as HTMLElement;
}

function renderOutcomesPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <OutcomesPage />
    </QueryClientProvider>,
  );
}

describe("OutcomesPage", () => {
  beforeEach(() => {
    apiState.reconcileSavedConnector.mockReset();
    apiState.reconcileSavedConnector.mockResolvedValue(hookState.checks[0]);
    hookState.summaryRefetch.mockClear();
    hookState.checksRefetch.mockClear();
    hookState.sourceMutationSummaryRefetch.mockClear();
    hookState.unreceiptedMutationsRefetch.mockClear();
  });

  it("renders the verification cockpit with honest metrics and bypass signal", () => {
    renderOutcomesPage();

    expect(screen.getByRole("heading", { name: "Verified action mismatch" })).toBeInTheDocument();
    expect(within(metric("Verified")).getByText("1")).toBeInTheDocument();
    expect(within(metric("Mismatched")).getByText("1")).toBeInTheDocument();
    expect(within(metric("Not verified")).getByText("1")).toBeInTheDocument();
    expect(within(metric("Bypass risk")).getByText("3")).toBeInTheDocument();
    expect(within(metric("Verified rate")).getByText("33%")).toBeInTheDocument();

    const bypass = screen.getByRole("region", { name: "Bypass risk" });
    expect(within(bypass).getByRole("heading", { name: "3 system changes with no receipt" })).toBeInTheDocument();
    expect(within(bypass).getAllByText("stripe:rf_bypass").length).toBeGreaterThan(0);
    expect(within(bypass).getByRole("button", { name: /stripe:rf_bypass/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected bypass mutation" })).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Verified rate trend" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Connector health" })).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Reconciliation feed" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected outcome check" })).toBeInTheDocument();
    expect(screen.getAllByText("Refund id rf_999").length).toBeGreaterThan(0);
    expect(screen.getByText("refund-agent / Refund")).toBeInTheDocument();
  });

  it("shows a field-level claimed-vs-actual diff instead of raw JSON first", () => {
    renderOutcomesPage();

    const diff = screen.getByRole("table", { name: "Claimed versus actual field comparison" });
    expect(within(diff).getByText("amount_usd")).toBeInTheDocument();
    expect(within(diff).getByText("42.5")).toBeInTheDocument();
    expect(within(diff).getByText("41.5")).toBeInTheDocument();
    expect(within(diff).getByText("currency")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open signed evidence/ }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
    expect(screen.getByRole("link", { name: /Open action/ }).getAttribute("href")).toBe(
      "/actions?action_id=action_1",
    );
  });

  it("filters locally by verdict and search", () => {
    renderOutcomesPage();

    fireEvent.click(screen.getByRole("button", { name: "Not verified" }));

    expect(screen.getAllByText("Payment id pay_1").length).toBeGreaterThan(0);
    expect(screen.queryByText("Refund id rf_999")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByPlaceholderText("Search system ref, connector, claim..."), {
      target: { value: "customer@example.com" },
    });

    expect(screen.getAllByText("Email customer@example.com").length).toBeGreaterThan(0);
    expect(screen.queryByText("Refund id rf_999")).not.toBeInTheDocument();
  });

  it("refreshes reconciliation and source mutation feeds", () => {
    renderOutcomesPage();

    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

    expect(hookState.summaryRefetch).toHaveBeenCalledTimes(1);
    expect(hookState.checksRefetch).toHaveBeenCalledTimes(1);
    expect(hookState.sourceMutationSummaryRefetch).toHaveBeenCalledTimes(1);
    expect(hookState.unreceiptedMutationsRefetch).toHaveBeenCalledTimes(1);
  });

  it("runs a real saved-connector re-verification for unresolved checks", async () => {
    renderOutcomesPage();

    fireEvent.click(screen.getByRole("button", { name: "Re-verify saved connector" }));

    await waitFor(() => {
      expect(apiState.reconcileSavedConnector).toHaveBeenCalledWith(expect.objectContaining({
        action_type: "refund",
        connector: "ledger_refund_api",
        claimed: expect.objectContaining({ refund_id: "rf_999" }),
        match_fields: ["amount_usd", "currency"],
        runtime_policy_decision_id: "decision_1",
        system_ref: "ledger:rf_999",
        trace_id: "trace_refund_api",
      }));
    });
    await waitFor(() => {
      expect(hookState.checksRefetch).toHaveBeenCalled();
    });
    expect(screen.getByText("Re-check created: Mismatched.")).toBeInTheDocument();
  });
});
