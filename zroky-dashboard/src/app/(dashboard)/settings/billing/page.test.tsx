import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "./page";

const api = vi.hoisted(() => ({
  createBillingPortal: vi.fn(),
  createRazorpayOrder: vi.fn(),
  getBillingMe: vi.fn(),
  getBillingUsage: vi.fn(),
  verifyRazorpayPayment: vi.fn(),
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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

describe("BillingPage", () => {
  const originalRazorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID;

  beforeEach(() => {
    vi.clearAllMocks();
    navigation.query = "upgrade_hint=replay.monthly_runs";
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
      protected_actions: usageMeter(2, 500),
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
    process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID = originalRazorpayKey;
    delete window.Razorpay;
  });

  it("does not assume the Free plan when the billing record cannot be loaded", async () => {
    api.getBillingMe.mockRejectedValue(new Error("Billing service unavailable."));
    api.getBillingUsage.mockRejectedValue(new Error("Billing service unavailable."));

    render(<BillingPage />);

    expect(await screen.findByRole("region", { name: "Billing unavailable" })).toBeInTheDocument();
    expect(screen.getByText("No fallback plan has been assumed.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Billing overview" })).not.toBeInTheDocument();
    expect(screen.queryByText("FREE")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.getBillingMe).toHaveBeenCalledTimes(2));
  });

  it("renders targeted upgrade_hint banners from module links", async () => {
    render(<BillingPage />);

    expect(
      screen.getByText("That legacy quota is gated by your current plan. Billing now centers on protected actions, receipts, verification, and connectors."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Available plans")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Billing overview" })).toBeInTheDocument();
    expect(screen.getByText("Usage this month")).toBeInTheDocument();
    expect(screen.queryByText("Capture events")).not.toBeInTheDocument();
    expect(screen.queryByText("Replay runs")).not.toBeInTheDocument();
    expect(screen.queryByText("Spend limits")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Protected action usage" })).toBeInTheDocument();
    expect(screen.getAllByText("2 / 500").length).toBeGreaterThan(0);
    const protectedActionRow = screen.getByText("Protected actions").closest(".billing-usage-row") as HTMLElement;
    expect(within(protectedActionRow).getByText(/<1% used/)).toBeInTheDocument();
    expect(screen.queryByText("Policy checks")).not.toBeInTheDocument();
    expect(screen.queryByText("Runner executions")).not.toBeInTheDocument();
    expect(screen.queryByText("Managed AgentProfile capacity")).not.toBeInTheDocument();
  });

  it("renders the launch self-serve plan catalog", async () => {
    render(<BillingPage />);

    expect(await screen.findByText("Starter")).toBeInTheDocument();
    expect(screen.getByText("Team")).toBeInTheDocument();
    expect(screen.getByText("Scale")).toBeInTheDocument();
    expect(screen.getByText("$199")).toBeInTheDocument();
    const teamCard = screen.getByRole("article", { name: "Team plan" });
    expect(within(teamCard).getByText(/10K protected actions\/mo/)).toBeInTheDocument();
    expect(within(teamCard).getByText(/10 managed agents/)).toBeInTheDocument();
    expect(within(teamCard).getByText(/6 connectors/)).toBeInTheDocument();
    expect(within(teamCard).getByText(/For teams running multiple agents/)).toBeInTheDocument();
    expect(within(teamCard).queryByText(/Unlimited approver seats/)).not.toBeInTheDocument();
    expect(within(teamCard).queryByText(/Bypass detection/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upgrade to Team" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contact sales" }).getAttribute("href")).toBe(
      "/contact?subject=enterprise-plan",
    );
    expect(screen.queryByText("Plus")).not.toBeInTheDocument();
  });

  it("opens and verifies Razorpay checkout for only the selected plan", async () => {
    process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID = "rzp_test_key";
    const checkoutOpen = vi.fn();
    const checkoutOn = vi.fn();
    let paymentHandler: ((response: {
      razorpay_payment_id: string;
      razorpay_order_id: string;
      razorpay_signature: string;
    }) => void) | null = null;
    window.Razorpay = function Razorpay(options) {
      paymentHandler = options.handler;
      return { open: checkoutOpen, on: checkoutOn };
    } as typeof window.Razorpay;
    api.createRazorpayOrder.mockResolvedValue({
      order_id: "order_team_1",
      amount: 19_900,
      currency: "INR",
      receipt: "receipt_team_1",
      plan_code: "team",
      org_id: "org_1",
      payment_provider: "razorpay",
      amount_usd: 199,
    });
    api.verifyRazorpayPayment.mockResolvedValue({
      success: true,
      order_id: "order_team_1",
      payment_id: "payment_team_1",
      org_id: "org_1",
      plan_code: "team",
    });

    render(<BillingPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Upgrade to Team" }));

    await waitFor(() => expect(api.createRazorpayOrder).toHaveBeenCalledWith({ plan_code: "team" }));
    expect(checkoutOpen).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Opening checkout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upgrade to Starter" })).toBeInTheDocument();

    await act(async () => {
      paymentHandler?.({
        razorpay_payment_id: "payment_team_1",
        razorpay_order_id: "order_team_1",
        razorpay_signature: "signature_team_1",
      });
      await Promise.resolve();
    });

    await waitFor(() => expect(api.verifyRazorpayPayment).toHaveBeenCalledWith({
      razorpay_payment_id: "payment_team_1",
      razorpay_order_id: "order_team_1",
      razorpay_signature: "signature_team_1",
    }));
    expect(await screen.findByText("Payment verified for Team. Your plan is active.")).toBeInTheDocument();
  });

  it("describes an exact connector cap as reached instead of exceeded by zero", async () => {
    api.getBillingUsage.mockResolvedValue({
      ...(await api.getBillingUsage()),
      active_connectors: usageMeter(1, 1, "exceeded"),
    });

    render(<BillingPage />);

    expect(await screen.findByText("System-of-record connectors limit reached.")).toBeInTheDocument();
    expect(screen.queryByText("System-of-record connectors limit exceeded by 0.")).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Upgrade to Team" })).toBeInTheDocument();
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
