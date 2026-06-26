import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OutcomesPage from "./page";

const hookState = vi.hoisted(() => ({
  filter: "all",
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
      connector_type: "ledger_api",
      system_ref: "ledger:rf_999",
      verdict: "mismatched",
      verification_status: "mismatched",
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
      connector_type: "ledger_api",
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
    hookState.sourceMutationSummaryRefetch.mockClear();
    hookState.unreceiptedMutationsRefetch.mockClear();
  });

  it("renders reconciliation KPIs and check evidence", () => {
    render(<OutcomesPage />);

    expect(screen.getByRole("heading", { name: "Agent outcome mismatch" })).toBeInTheDocument();
    expect(within(metricCard("Mismatched")).getByText("1")).toBeInTheDocument();
    expect(within(metricCard("Not verified")).getByText("1")).toBeInTheDocument();
    expect(within(metricCard("Matched")).getByText("1")).toBeInTheDocument();
    expect(within(metricCard("Matched rate")).getByText("33%")).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Outcome verification setup paths" })).toBeInTheDocument();
    expect(screen.getByText("SDK helper and webhook bridge land in the same verification queue.")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("verifyOutcome()"))).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("/v1/outcomes/reconciliation/saved"))).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("x-api-key"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open SDK setup/i }).getAttribute("href")).toBe(
      "/settings/keys?intent=protect-agent",
    );
    expect(screen.getByRole("link", { name: /Open bridge setup/i }).getAttribute("href")).toBe(
      "/integrations#generic-rest-connector",
    );

    const proofContract = screen.getByRole("region", { name: "Outcome proof state contract" });
    expect(
      within(proofContract).getByText("Every risky action must end as matched, mismatched, or not_verified."),
    ).toBeInTheDocument();
    expect(
      within(proofContract).getByText(
        "Green agent output is not proof. Zroky only trusts a real connector read or a signed outcome callback.",
      ),
    ).toBeInTheDocument();
    expect(within(proofContract).getByText("Safe to export")).toBeInTheDocument();
    expect(within(proofContract).getByText("Block the path")).toBeInTheDocument();
    expect(within(proofContract).getByText("Do not trust yet")).toBeInTheDocument();

    const bypassWatch = screen.getByRole("region", { name: "Reconciliation bypass watch" });
    expect(within(bypassWatch).getByText("Source mutations must map back to a signed Zroky receipt.")).toBeInTheDocument();
    expect(within(bypassWatch).getAllByText("1").length).toBeGreaterThan(0);
    expect(within(bypassWatch).getByText("stripe:rf_bypass")).toBeInTheDocument();
    expect(within(bypassWatch).getAllByText("Policy bypass").length).toBeGreaterThan(0);

    expect(screen.getByRole("region", { name: "Real outcome verification queue" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected outcome verification" })).toBeInTheDocument();
    expect(screen.getAllByText("Refund rf_999").length).toBeGreaterThan(0);
    expect(screen.getByText("Outcome mismatch")).toBeInTheDocument();
    expect(screen.getByText("1 field mismatch")).toBeInTheDocument();
    expect(screen.getByText(/ledger:rf_999 \/ Field mismatch/)).toBeInTheDocument();
    expect(screen.getByText("call_refund_api").getAttribute("href")).toBe("/evidence");
    expect(screen.getByText("trace_refund_api").getAttribute("href")).toBe("/evidence");
    expect(screen.getByRole("link", { name: "Open Evidence Pack" }).getAttribute("href")).toBe(
      "/evidence?decision_id=decision_1",
    );
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
    expect(hookState.sourceMutationSummaryRefetch).toHaveBeenCalledTimes(1);
    expect(hookState.unreceiptedMutationsRefetch).toHaveBeenCalledTimes(1);
  });

  it("searches loaded checks without changing the server verdict filter", () => {
    render(<OutcomesPage />);

    fireEvent.change(screen.getByPlaceholderText("System ref, call, trace, action, claim..."), {
      target: { value: "customer@example.com" },
    });

    expect(hookState.filter).toBe("all");
    expect(screen.getAllByText("Email customer@example.com").length).toBeGreaterThan(0);
    expect(screen.queryByText("Refund rf_999")).not.toBeInTheDocument();
  });
});
