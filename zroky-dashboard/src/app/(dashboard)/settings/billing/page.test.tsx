import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "./page";

const api = vi.hoisted(() => ({
  createBillingPortal: vi.fn(),
  createRazorpayOrder: vi.fn(),
  getBillingMe: vi.fn(),
  getBillingUsage: vi.fn(),
  verifyRazorpayPayment: vi.fn(),
}));

const hooks = vi.hoisted(() => ({
  useBudget: vi.fn(),
  useBudgetStatus: vi.fn(),
  useUpdateBudget: vi.fn(),
}));

const navigation = vi.hoisted(() => ({
  query: "upgrade_hint=replay.monthly_runs",
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

vi.mock("@/lib/hooks", () => hooks);

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

describe("BillingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.query = "upgrade_hint=replay.monthly_runs";
    hooks.useBudget.mockReturnValue({
      data: { monthly_limit_usd: 100, threshold_percentage: 80 },
      isLoading: false,
      error: null,
    });
    hooks.useBudgetStatus.mockReturnValue({
      data: { spent_usd: 12.5, limit_usd: 100, percent_used: 12.5, days_remaining_in_period: 20, forecast_exhaust_in_days: null, status: "ok", forecast_risk_level: "low", forecast_recommendation: "Within budget." },
      isLoading: false,
      error: null,
    });
    hooks.useUpdateBudget.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "free",
      status: "active",
      seats: 1,
      payment_provider: "razorpay",
      payment_customer_ref: null,
      payment_subscription_ref: null,
      payment_request_ref: null,
      stripe_customer_id: null,
      stripe_sub_id: null,
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {
        "events.monthly_quota": 50000,
        "replay.monthly_runs": 0,
        "seats.included": 2,
      },
    });
    api.getBillingUsage.mockResolvedValue({
      tenant_id: "org_1",
      org_id: "org_1",
      period_month: "2026-06",
      period_start: "2026-06-01T00:00:00Z",
      period_end: "2026-07-01T00:00:00Z",
      plan_code: "free",
      plan_name: "Free",
      subscription_status: "active",
      calls: { used: 42, limit: 50000, unlimited: false, overage: null, state: "ok", resets_at: "2026-07-01" },
      replay: { used: 0, limit: 0, unlimited: false, overage: null, state: "blocked", resets_at: "2026-07-01" },
      goldens: { used: 0, limit: 0, unlimited: false, overage: null, state: "blocked", resets_at: null },
      golden_sets: { used: 0, limit: 0, unlimited: false, overage: null, state: "blocked", resets_at: null },
      metering_health: { state: "ok", failure_count: 0, last_failure_at: null, last_failure_type: null, failure_policy: "strict", detail: "Event metering is healthy." },
    });
  });

  it("renders targeted upgrade_hint banners from module links", async () => {
    render(<BillingPage />);

    expect(
      screen.getByText("Replay runs are gated by your current plan. Upgrade to unlock more protected replay capacity."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Plan & Pricing")).toBeInTheDocument();
    expect(screen.getAllByText("42 / 50,000").length).toBeGreaterThan(0);
  });

  it("renders the backend-aligned self-serve plan catalog", async () => {
    render(<BillingPage />);

    expect(await screen.findByText("Pilot")).toBeInTheDocument();
    expect(screen.getByText(/500K events\/mo/)).toBeInTheDocument();
    expect(screen.getByText(/100 mocked-tool replay runs\/mo/)).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("$149.00")).toBeInTheDocument();
    expect(screen.getByText(/3M events\/mo/)).toBeInTheDocument();
    expect(screen.getByText(/100 real LLM replay runs\/mo/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay with Razorpay for Pilot" })).toBeInTheDocument();
    expect(screen.queryByText("Plus")).not.toBeInTheDocument();
  });

  it("maps legacy Plus subscriptions to the Pro catalog card", async () => {
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "plus",
      status: "active",
      seats: 3,
      payment_provider: "razorpay",
      payment_customer_ref: "billing@example.com",
      payment_subscription_ref: "rzp_pay_123",
      payment_request_ref: "rzp_order_123",
      stripe_customer_id: "cus_123",
      stripe_sub_id: "sub_123",
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {
        "events.monthly_quota": 3000000,
        "replay.monthly_runs": 1000,
        "seats.included": 10,
      },
    });
    api.getBillingUsage.mockResolvedValue({
      tenant_id: "org_1",
      org_id: "org_1",
      period_month: "2026-06",
      period_start: "2026-06-01T00:00:00Z",
      period_end: "2026-07-01T00:00:00Z",
      plan_code: "pro",
      plan_name: "Pro",
      subscription_status: "active",
      calls: { used: 1000, limit: 3000000, unlimited: false, overage: null, state: "ok", resets_at: "2026-07-01" },
      replay: { used: 10, limit: 1000, unlimited: false, overage: null, state: "ok", resets_at: "2026-07-01" },
      goldens: { used: 20, limit: 1000, unlimited: false, overage: null, state: "ok", resets_at: null },
      golden_sets: { used: 2, limit: 50, unlimited: false, overage: null, state: "ok", resets_at: null },
      metering_health: { state: "ok", failure_count: 0, last_failure_at: null, last_failure_type: null, failure_policy: "strict", detail: "Event metering is healthy." },
    });

    render(<BillingPage />);

    expect(await screen.findByText("PLUS")).toBeInTheDocument();
    expect(screen.getByText("Legacy Plus maps to Pro entitlements.")).toBeInTheDocument();

    const proCard = screen.getByText("Pro").closest(".billing-plan-card");
    expect(proCard?.className).toContain("billing-plan-current");
    expect(within(proCard as HTMLElement).getByText("Current")).toBeInTheDocument();
  });
});
