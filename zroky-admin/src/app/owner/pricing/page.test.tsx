import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PricingPage from "./page";
import * as hooks from "@/lib/hooks";
import type {
  OwnerBillingAccountsResponse,
  OwnerBillingSummary,
  OwnerMoneyPathHealth,
  OwnerPricingPlansResponse,
  PricingConfigResponse,
} from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerPricing: vi.fn(),
  useOwnerPricingPlans: vi.fn(),
  useOwnerBillingSummary: vi.fn(),
  useOwnerBillingAccounts: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
  useUpdateOwnerPricing: vi.fn(),
  useConfirmOwnerRazorpayPayment: vi.fn(),
}));

const pricingConfig: PricingConfigResponse = {
  config: {},
  path: "redis",
  exists: true,
};

const pricingPlans: OwnerPricingPlansResponse = {
  schema_version: "1.0",
  source_of_truth: "api-contracts/pricing-plans.json",
  currency: "USD",
  unlimited: -1,
  canonical_plan_order: ["free", "pilot", "pro", "enterprise"],
  aliases: { plus: "pro" },
  drift: [],
  plans: [
    {
      code: "free",
      name: "Free",
      price: { label: "$0", monthly_usd: 0, period: "/mo" },
      description: "Free validation.",
      note: "No replay.",
      featured: false,
      pricing: {
        calls_per_month: 50000,
        retention_days: 7,
        replay_credits: 0,
        golden_traces: 0,
        golden_sets: 0,
        non_blocking_ci: false,
        blocking_ci: false,
        provider_key_vault: false,
      },
      enforcement: { limits: {}, entitlements: {}, compatibility: {} },
    },
    {
      code: "pro",
      name: "Pro",
      price: { label: "$149", monthly_usd: 149, period: "/mo" },
      description: "Release protection.",
      note: "Main release plan.",
      featured: true,
      pricing: {
        calls_per_month: 3000000,
        retention_days: 90,
        replay_credits: 1000,
        golden_traces: 1000,
        golden_sets: 50,
        non_blocking_ci: true,
        blocking_ci: true,
        provider_key_vault: false,
      },
      enforcement: { limits: {}, entitlements: {}, compatibility: {} },
    },
  ],
};

const billingSummary: OwnerBillingSummary = {
  total_subscriptions: 2,
  overdue: 0,
  canceled: 0,
  by_plan: [{ plan: "Pro", slug: "pro", tenant_count: 1 }],
  by_status: [
    { status: "active", count: 2 },
    { status: "past_due", count: 0 },
  ],
};

const billingAccounts: OwnerBillingAccountsResponse = {
  total: 2,
  items: [
    {
      org_id: "proj_pro",
      project_name: "Pro Tenant",
      plan_code: "pro",
      status: "active",
      sla_tier: "team",
      seats: 5,
      current_period_end: "2026-07-01T00:00:00Z",
      trial_end: null,
      payment_provider: "razorpay",
      payment_customer_ref: "billing@example.com",
      payment_subscription_ref: "rzp_pay_123",
      payment_request_ref: "rzp_order_123",
      payment_dashboard_url: "https://dashboard.razorpay.com/",
      updated_at: "2026-06-05T00:00:00Z",
    },
    {
      org_id: "proj_unknown",
      project_name: "Unknown Plan Tenant",
      plan_code: "ultra",
      status: "active",
      sla_tier: "team",
      seats: 5,
      current_period_end: null,
      trial_end: null,
      payment_provider: "razorpay",
      payment_customer_ref: null,
      payment_subscription_ref: null,
      payment_request_ref: null,
      payment_dashboard_url: "https://dashboard.razorpay.com/",
      updated_at: "2026-06-05T00:00:00Z",
    },
  ],
};

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 100,
    issues_open: 1,
    replay_runs_7d: 4,
    verified_replay_runs_7d: 1,
    golden_traces_active: 2,
    ci_runs_7d: 3,
    ci_blocks_7d: 0,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 0,
    last_deployed_smoke: {
      status: "passed",
      checked_at: "2026-06-05T11:00:00Z",
      project_id: "proj_pro",
      call_id: "call_1",
      golden_trace_id: "gt_1",
      ci_run_id: "ci_1",
      detail: "passed",
    },
  },
  tenants: [
    {
      project_id: "proj_pro",
      project_name: "Pro Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:30:00Z",
      captures_24h: 100,
      open_issue_count: 1,
      replay_run_count_7d: 4,
      verified_replay_count_7d: 1,
      golden_trace_count: 2,
      ci_run_count_7d: 3,
      blocking_ci_failures_7d: 0,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "near_limit", enabled: true, used: 950, limit: 1000, resets_at: "2026-07-01" },
      next_owner_action: "review_replay_quota",
    },
  ],
};

function mockHooks(moneyPathError: Error | null = null) {
  vi.mocked(hooks.useOwnerPricing).mockReturnValue({
    data: pricingConfig,
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useOwnerPricing>);
  vi.mocked(hooks.useOwnerPricingPlans).mockReturnValue({
    data: pricingPlans,
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useOwnerPricingPlans>);
  vi.mocked(hooks.useOwnerBillingSummary).mockReturnValue({
    data: billingSummary,
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useOwnerBillingSummary>);
  vi.mocked(hooks.useOwnerBillingAccounts).mockReturnValue({
    data: billingAccounts,
    error: null,
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerBillingAccounts>);
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data: moneyPathError ? null : moneyPath,
    error: moneyPathError,
    isLoading: false,
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  vi.mocked(hooks.useUpdateOwnerPricing).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useUpdateOwnerPricing>);
  vi.mocked(hooks.useConfirmOwnerRazorpayPayment).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useConfirmOwnerRazorpayPayment>);
}

describe("PricingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders backend entitlement contract and account risk evidence", () => {
    mockHooks();

    render(<PricingPage />);

    expect(screen.getByText("Revenue & Entitlements")).toBeInTheDocument();
    expect(screen.getByText("Plan Entitlement Matrix")).toBeInTheDocument();
    expect(screen.getByText("Confirm Razorpay Payment")).toBeInTheDocument();
    expect(screen.getByText("Razorpay Billing Accounts")).toBeInTheDocument();
    expect(screen.getByText("In sync")).toBeInTheDocument();
    expect(screen.getByText("api-contracts/pricing-plans.json")).toBeInTheDocument();
    expect(screen.getByText("Replay quota")).toBeInTheDocument();
    expect(screen.getByText("Tenant is near replay entitlement.")).toBeInTheDocument();
    expect(screen.getByText("Unknown plan")).toBeInTheDocument();
    expect(screen.getByText("No catalog entry matches this billing row.")).toBeInTheDocument();
    expect(screen.getAllByText("Included").length).toBeGreaterThan(0);
  });

  it("does not show account risk as healthy when money-path health fails", () => {
    mockHooks(new Error("HTTP 500"));

    render(<PricingPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.getByText("Money-path unavailable")).toBeInTheDocument();
    expect(screen.getByText("Product entitlement risk cannot be evaluated.")).toBeInTheDocument();
    expect(screen.queryByText("Billing and product evidence are aligned.")).toBe(null);
  });
});
