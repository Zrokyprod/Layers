import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OutcomesPage from "./page";

const hookState = vi.hoisted(() => ({
  filter: "all",
  summaryRefetch: vi.fn(),
  checksRefetch: vi.fn(),
  summary: {
    window_days: 30,
    total: 3,
    matched: 1,
    mismatched: 1,
    not_verified: 1,
  },
  checks: [
    {
      id: "check_mismatch",
      project_id: "proj_1",
      call_id: "call_refund_api",
      trace_id: "trace_refund_api",
      runtime_policy_decision_id: "decision_1",
      action_type: "refund",
      connector_type: "ledger_api",
      system_ref: "ledger:rf_999",
      verdict: "mismatched",
      reason: "field_mismatch",
      amount_usd: 42.5,
      currency: "USD",
      claimed: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
      actual: { refund_id: "rf_999", amount_usd: 41.5, currency: "USD" },
      comparison: {
        compared_fields: [
          { field: "amount_usd", claimed: 42.5, actual: 41.5, matched: false },
        ],
        mismatches: [{ field: "amount_usd" }],
      },
      idempotency_key: "call_refund_api:rf_999",
      metadata: { source: "test" },
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
      system_ref: "email:msg_1",
      verdict: "matched",
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
      connector_type: "ledger_api",
      system_ref: "ledger:pay_1",
      verdict: "not_verified",
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

vi.mock("@/lib/hooks", () => ({
  useOutcomeReconciliationSummary: () => ({
    data: hookState.summary,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: hookState.summaryRefetch,
  }),
  useOutcomeReconciliations: (filter: string) => {
    hookState.filter = filter;
    const items =
      filter === "all"
        ? hookState.checks
        : hookState.checks.filter((item) => item.verdict === filter);
    return {
      data: { items, total_in_page: items.length },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: hookState.checksRefetch,
    };
  },
}));

function metricCard(label: string): HTMLElement {
  const labelNode = screen.getAllByText(label)[0];
  const card = labelNode.closest("article");
  if (!card) throw new Error(`Missing metric card ${label}`);
  return card;
}

describe("OutcomesPage", () => {
  beforeEach(() => {
    hookState.filter = "all";
    hookState.summaryRefetch.mockClear();
    hookState.checksRefetch.mockClear();
  });

  it("renders reconciliation KPIs and check evidence", () => {
    render(<OutcomesPage />);

    expect(screen.getByRole("heading", { name: "Outcomes" })).toBeInTheDocument();
    expect(within(metricCard("Mismatched")).getByText("1")).toBeInTheDocument();
    expect(within(metricCard("Not verified")).getByText("1")).toBeInTheDocument();
    expect(within(metricCard("Matched")).getByText("1")).toBeInTheDocument();
    expect(within(metricCard("Verified rate")).getByText("33%")).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Outcome check queue" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected outcome inspector" })).toBeInTheDocument();
    expect(screen.getAllByText("Refund rf_999").length).toBeGreaterThan(0);
    expect(screen.getByText("Outcome mismatch")).toBeInTheDocument();
    expect(screen.getByText("1 field mismatch")).toBeInTheDocument();
    expect(screen.getByText(/ledger:rf_999 \/ Field mismatch/)).toBeInTheDocument();
    expect(screen.getByText("call_refund_api").getAttribute("href")).toBe("/calls/call_refund_api");
    expect(screen.getByText("trace_refund_api").getAttribute("href")).toBe("/trace/trace_refund_api");
  });

  it("filters by verdict and refreshes both queries", () => {
    render(<OutcomesPage />);

    fireEvent.click(screen.getByRole("button", { name: "Mismatched" }));

    expect(hookState.filter).toBe("mismatched");
    expect(screen.getAllByText("Refund rf_999").length).toBeGreaterThan(0);
    expect(screen.queryByText("Email customer@example.com")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(hookState.summaryRefetch).toHaveBeenCalledTimes(1);
    expect(hookState.checksRefetch).toHaveBeenCalledTimes(1);
  });

  it("searches loaded checks without changing the server verdict filter", () => {
    render(<OutcomesPage />);

    fireEvent.change(screen.getByPlaceholderText("System ref, call, trace, action..."), {
      target: { value: "customer@example.com" },
    });

    expect(hookState.filter).toBe("all");
    expect(screen.getAllByText("Email customer@example.com").length).toBeGreaterThan(0);
    expect(screen.queryByText("Refund rf_999")).not.toBeInTheDocument();
  });
});
