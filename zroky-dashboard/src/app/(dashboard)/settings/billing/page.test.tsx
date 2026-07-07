import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

function usageMeter(used: number, limit: number | null, state = "ok") {
  return {
    used,
    limit,
    unlimited: limit == null,
    overage: null,
    state,
    resets_at: "2026-07-01",
  };
}

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
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {
        "events.monthly_quota": 5000,
        "replay.monthly_runs": 0,
        "agents.max": 1,
        "connectors.system_of_record.max": 1,
        "actions.protected.monthly_quota": 500,
        "actions.receipts.monthly_quota": 500,
        "actions.verifications.monthly_quota": 1000,
        "retention.days": 7,
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
      calls: usageMeter(42, 5000),
      replay: usageMeter(0, 0, "blocked"),
      goldens: { ...usageMeter(0, 0, "blocked"), resets_at: null },
      golden_sets: { ...usageMeter(0, 0, "blocked"), resets_at: null },
      protected_actions: usageMeter(7, 500),
      policy_checks: usageMeter(18, 1000),
      runner_executions: usageMeter(4, 500),
      action_receipts: usageMeter(4, 500),
      verification_checks: usageMeter(9, 1000),
      source_mutations: usageMeter(11, 1000),
      active_connectors: usageMeter(1, 1, "near_limit"),
      metering_health: { state: "ok", failure_count: 0, last_failure_at: null, last_failure_type: null, failure_policy: "strict", detail: "Event metering is healthy." },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders targeted upgrade_hint banners from module links", async () => {
    render(<BillingPage />);

    expect(
      screen.getByText("That legacy quota is gated by your current plan. Billing now centers on protected actions, receipts, verification, and connectors."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Upgrade path")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Subscription status" })).toBeInTheDocument();
    expect(screen.getByText("Run protected agents on the FREE plan.")).toBeInTheDocument();
    expect(screen.queryByText("Capture events")).not.toBeInTheDocument();
    expect(screen.queryByText("Replay runs")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Protected action usage" })).toBeInTheDocument();
    expect(screen.getAllByText("7 / 500").length).toBeGreaterThan(0);
    expect(screen.getByText("Policy checks")).toBeInTheDocument();
    expect(screen.getByText("Runner executions")).toBeInTheDocument();
    expect(screen.getAllByText("Source mutations").length).toBeGreaterThan(0);
    expect(screen.getByText("Managed AgentProfile capacity")).toBeInTheDocument();
    expect(screen.getByText("Evidence retention days")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Actions" }).getAttribute("href")).toBe("/actions");
    expect(screen.getByRole("link", { name: "Open bypass risk" }).getAttribute("href")).toBe("/outcomes");
  });

  it("renders the launch self-serve plan catalog", async () => {
    render(<BillingPage />);

    expect(await screen.findByText("Starter")).toBeInTheDocument();
    expect(screen.getByText("Team")).toBeInTheDocument();
    expect(screen.getByText("Scale")).toBeInTheDocument();
    expect(screen.getByText("$199.00")).toBeInTheDocument();
    const teamCard = screen.getByRole("article", { name: "Team plan" });
    expect(within(teamCard).getByText(/10K protected actions\/mo/)).toBeInTheDocument();
    expect(within(teamCard).getByText(/6 connectors/)).toBeInTheDocument();
    expect(within(teamCard).getByText(/Bypass detection/)).toBeInTheDocument();
    expect(within(teamCard).getByText(/\$0.025\/action overage/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay with Razorpay for Team" })).toBeInTheDocument();
    expect(screen.queryByText("Plus")).not.toBeInTheDocument();
  });

  it("maps legacy Plus subscriptions to the Scale catalog card", async () => {
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "plus",
      status: "active",
      seats: 3,
      payment_provider: "razorpay",
      payment_customer_ref: "billing@example.com",
      payment_subscription_ref: "rzp_pay_123",
      payment_request_ref: "rzp_order_123",
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {
        "events.monthly_quota": 250000,
        "replay.monthly_runs": 500,
        "seats.included": -1,
      },
    });
    api.getBillingUsage.mockResolvedValue({
      tenant_id: "org_1",
      org_id: "org_1",
      period_month: "2026-06",
      period_start: "2026-06-01T00:00:00Z",
      period_end: "2026-07-01T00:00:00Z",
      plan_code: "scale",
      plan_name: "Scale",
      subscription_status: "active",
      calls: usageMeter(1000, 250000),
      replay: usageMeter(10, 500),
      goldens: { ...usageMeter(20, 2500), resets_at: null },
      golden_sets: { ...usageMeter(2, 25), resets_at: null },
      protected_actions: usageMeter(250, 50000),
      policy_checks: usageMeter(1800, 250000),
      runner_executions: usageMeter(220, 50000),
      action_receipts: usageMeter(200, 50000),
      verification_checks: usageMeter(700, 125000),
      source_mutations: usageMeter(900, 250000),
      active_connectors: usageMeter(4, null),
      metering_health: { state: "ok", failure_count: 0, last_failure_at: null, last_failure_type: null, failure_policy: "strict", detail: "Event metering is healthy." },
    });

    render(<BillingPage />);

    expect(await screen.findByText("PLUS")).toBeInTheDocument();
    expect(screen.getByText("Legacy Plus maps to Scale entitlements.")).toBeInTheDocument();

    const scaleCard = screen.getByRole("article", { name: "Scale plan" });
    expect(scaleCard?.className).toContain("billing-plan-current");
    expect(within(scaleCard as HTMLElement).getByText("Current")).toBeInTheDocument();
  });

  it("keeps legacy Pilot subscriptions mapped to Starter", async () => {
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "pilot",
      status: "active",
      seats: 3,
      payment_provider: "razorpay",
      payment_customer_ref: "billing@example.com",
      payment_subscription_ref: "rzp_pay_123",
      payment_request_ref: "rzp_order_123",
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {
        "events.monthly_quota": 50000,
        "replay.monthly_runs": 50,
        "seats.included": -1,
      },
    });

    render(<BillingPage />);

    expect(await screen.findByText("PILOT")).toBeInTheDocument();
    expect(screen.getByText("Legacy Pilot maps to grandfathered Starter entitlements. Team is the featured self-serve upgrade.")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Starter plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay with Razorpay for Team" })).toBeInTheDocument();
  });

  it("polls billing while a Razorpay payment request is pending", async () => {
    vi.useFakeTimers();
    api.getBillingMe.mockResolvedValue({
      org_id: "org_1",
      plan_code: "free",
      status: "active",
      seats: 1,
      payment_provider: "razorpay",
      payment_customer_ref: null,
      payment_subscription_ref: null,
      payment_request_ref: "order_pending:pro",
      current_period_end: null,
      trial_end: null,
      sla_tier: "standard",
      plan_template: {
        "events.monthly_quota": 5000,
        "replay.monthly_runs": 0,
        "seats.included": 2,
      },
    });

    render(<BillingPage />);

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(api.getBillingMe).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(5_000);
      await Promise.resolve();
    });

    expect(api.getBillingMe).toHaveBeenCalledTimes(2);
  });
});
