import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "./page";

const api = vi.hoisted(() => ({
  createBillingCheckout: vi.fn(),
  createBillingPortal: vi.fn(),
  getBillingMe: vi.fn(),
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
  });

  it("renders targeted upgrade_hint banners from module links", async () => {
    render(<BillingPage />);

    expect(
      screen.getByText("Replay runs are gated by your current plan. Upgrade to unlock more protected replay capacity."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Plan & Pricing")).toBeInTheDocument();
  });
});
