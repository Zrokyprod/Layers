import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerMoneyPathPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerMoneyPathHealth } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerMoneyPathHealth: vi.fn(),
}));

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 120,
    issues_open: 3,
    replay_runs_7d: 8,
    verified_replay_runs_7d: 2,
    golden_traces_active: 5,
    ci_runs_7d: 4,
    ci_blocks_7d: 1,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 1,
    tenants_without_goldens: 1,
    tenants_with_failed_ci: 1,
    tenants_with_stale_replay_workers: 1,
    tenants_with_stale_pricing: 1,
    tenants_with_quota_risk: 1,
    tenants_with_billing_risk: 1,
    support_tickets_open: 1,
    support_tickets_urgent: 1,
    blocked_regressions_7d: 1,
    verified_fixes_7d: 2,
    last_deployed_smoke: {
      status: "passed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_smoke",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "ci_smoke",
      detail: "Latest deployed smoke has a passing CI gate run.",
    },
  },
  tenants: [
    {
      project_id: "proj_blocked",
      project_name: "Blocked Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:00:00Z",
      captures_24h: 80,
      open_issue_count: 2,
      replay_run_count_7d: 7,
      verified_replay_count_7d: 2,
      golden_trace_count: 5,
      ci_run_count_7d: 4,
      blocking_ci_failures_7d: 1,
      replay_jobs_pending: 0,
      replay_jobs_stale: 0,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "ok", enabled: true, used: 12, limit: 1000, resets_at: "2026-07-01" },
      pricing_cost_status: { state: "ok", pricing_version: "v1", pricing_source: "test", pricing_age_days: 1, cost_confidence: "high", detail: "fresh" },
      billing_status: { state: "ok", plan_code: "pro", subscription_status: "active", current_period_end: "2026-07-01T00:00:00Z" },
      support_status: { state: "none", open_count: 0, urgent_count: 0 },
      blocked_regressions_7d: 1,
      verified_fixes_7d: 2,
      value_status: "blocked",
      money_path_breaks: ["failed_ci"],
      tenant_priority_score: 100,
      next_owner_action: "review_blocked_ci",
    },
    {
      project_id: "proj_gap",
      project_name: "Provider Gap Tenant",
      plan_code: "starter",
      last_capture_at: null,
      captures_24h: 0,
      open_issue_count: 1,
      replay_run_count_7d: 0,
      verified_replay_count_7d: 0,
      golden_trace_count: 0,
      ci_run_count_7d: 0,
      blocking_ci_failures_7d: 0,
      replay_jobs_pending: 2,
      replay_jobs_stale: 1,
      provider_key_status: { state: "missing", active_provider_count: 0 },
      replay_quota_status: { state: "near_limit", enabled: true, used: 95, limit: 100, resets_at: "2026-07-01" },
      pricing_cost_status: { state: "stale", pricing_version: "old", pricing_source: "fallback_default", pricing_age_days: 45, cost_confidence: "stale", detail: "old pricing" },
      billing_status: { state: "risk", plan_code: "starter", subscription_status: "past_due", current_period_end: "2026-07-01T00:00:00Z" },
      support_status: { state: "urgent", open_count: 1, urgent_count: 1 },
      blocked_regressions_7d: 0,
      verified_fixes_7d: 0,
      value_status: "blocked",
      money_path_breaks: ["capture_unhealthy", "provider_key_missing", "replay_worker_stale", "billing_risk"],
      tenant_priority_score: 90,
      next_owner_action: "restore_capture",
    },
    {
      project_id: "proj_monitor",
      project_name: "Healthy Tenant",
      plan_code: "enterprise",
      last_capture_at: "2026-06-05T10:00:00Z",
      captures_24h: 40,
      open_issue_count: 0,
      replay_run_count_7d: 1,
      verified_replay_count_7d: 0,
      golden_trace_count: 1,
      ci_run_count_7d: 1,
      blocking_ci_failures_7d: 0,
      replay_jobs_pending: 0,
      replay_jobs_stale: 0,
      provider_key_status: { state: "configured", active_provider_count: 2 },
      replay_quota_status: { state: "unlimited", enabled: true, used: 20, limit: -1, resets_at: "2026-07-01" },
      pricing_cost_status: { state: "ok", pricing_version: "v1", pricing_source: "test", pricing_age_days: 1, cost_confidence: "high", detail: "fresh" },
      billing_status: { state: "ok", plan_code: "enterprise", subscription_status: "active", current_period_end: "2026-07-01T00:00:00Z" },
      support_status: { state: "none", open_count: 0, urgent_count: 0 },
      blocked_regressions_7d: 0,
      verified_fixes_7d: 1,
      value_status: "getting_value",
      money_path_breaks: [],
      tenant_priority_score: 0,
      next_owner_action: "monitor",
    },
  ],
};

function setHookData(data: OwnerMoneyPathHealth | null, error: Error | null = null) {
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data,
    error,
    dataUpdatedAt: data ? Date.parse(data.generated_at) : 0,
    refetch: vi.fn(),
  } as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
}

describe("OwnerMoneyPathPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders tenant money-path evidence and selects a tenant", () => {
    setHookData(moneyPath);

    render(<OwnerMoneyPathPage />);

    expect(screen.getByRole("heading", { name: "Money Path" })).toBeInTheDocument();
    expect(screen.getByText("Platform Money Path")).toBeInTheDocument();
    expect(screen.getAllByText("Blocked Tenant").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Provider Gap Tenant").length).toBeGreaterThan(0);
    expect(screen.getByText("Blocked CI Evidence")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[1]);
    const panel = screen.getByRole("complementary", { name: "Selected tenant money-path evidence" });
    expect(within(panel).getByText("Provider Gap Tenant")).toBeInTheDocument();
    expect(within(panel).getByText("missing (0)")).toBeInTheDocument();
    expect(within(panel).getByText("95 / 100")).toBeInTheDocument();
  });

  it("filters tenants by risk and search text", () => {
    setHookData(moneyPath);

    render(<OwnerMoneyPathPage />);

    fireEvent.click(screen.getByRole("button", { name: "Provider missing" }));
    let table = screen.getByRole("table");
    expect(within(table).getByText("Provider Gap Tenant")).toBeInTheDocument();
    expect(within(table).queryByText("Blocked Tenant")).toBe(null);

    fireEvent.change(screen.getByLabelText("Search tenants"), { target: { value: "enterprise" } });
    table = screen.getByRole("table");
    expect(within(table).queryByText("Provider Gap Tenant")).toBe(null);
    expect(within(table).getByText("No tenants match the current money-path filter.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Getting value" }));
    table = screen.getByRole("table");
    expect(within(table).getByText("Healthy Tenant")).toBeInTheDocument();
  });

  it("shows backend error without rendering fake healthy state", () => {
    setHookData(null, new Error("HTTP 500"));

    render(<OwnerMoneyPathPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("Platform Money Path")).toBe(null);
    expect(screen.queryByText("Every active tenant has capture in the 24-hour window.")).toBe(null);
  });
});
