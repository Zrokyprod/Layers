import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerProjectsPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerMoneyPathHealth, OwnerProjectItem } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerMoneyPathHealth: vi.fn(),
  useOwnerProjects: vi.fn(),
}));

const projects: OwnerProjectItem[] = [
  {
    id: "proj_demo",
    name: "Demo Tenant",
    owner_ref: "owner_demo",
    is_active: true,
    created_at: "2026-06-05T10:00:00Z",
    call_count: 120,
    total_cost_usd: 4.2,
    member_count: 1,
  },
  {
    id: "proj_live",
    name: "Live Tenant",
    owner_ref: "owner_live",
    is_active: true,
    created_at: "2026-06-05T10:00:00Z",
    call_count: 420,
    total_cost_usd: 12.4,
    member_count: 2,
  },
];

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 42,
    issues_open: 1,
    replay_runs_7d: 3,
    verified_replay_runs_7d: 2,
    golden_traces_active: 1,
    ci_runs_7d: 0,
    ci_blocks_7d: 0,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 1,
    last_deployed_smoke: {
      status: "passed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_demo",
      call_id: "call_demo",
      golden_trace_id: "gt_demo",
      ci_run_id: "ci_demo",
      detail: "Smoke passed.",
    },
  },
  tenants: [
    {
      project_id: "proj_demo",
      project_name: "Demo Tenant",
      plan_code: "starter",
      last_capture_at: null,
      captures_24h: 0,
      open_issue_count: 1,
      replay_run_count_7d: 0,
      verified_replay_count_7d: 0,
      golden_trace_count: 0,
      ci_run_count_7d: 0,
      blocking_ci_failures_7d: 0,
      provider_key_status: { state: "missing", active_provider_count: 0 },
      replay_quota_status: { state: "near_limit", enabled: true, used: 90, limit: 100, resets_at: "2026-07-01" },
      billing_status: { state: "active", plan_code: "starter", subscription_status: "active", current_period_end: "2026-07-01T00:00:00Z" },
      next_owner_action: "restore_capture",
    },
    {
      project_id: "proj_live",
      project_name: "Live Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:30:00Z",
      captures_24h: 42,
      open_issue_count: 0,
      replay_run_count_7d: 3,
      verified_replay_count_7d: 2,
      golden_trace_count: 1,
      ci_run_count_7d: 1,
      blocking_ci_failures_7d: 0,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "ok", enabled: true, used: 18, limit: 1000, resets_at: "2026-07-01" },
      billing_status: { state: "active", plan_code: "pro", subscription_status: "active", current_period_end: "2026-07-01T00:00:00Z" },
      next_owner_action: "monitor",
    },
  ],
};

describe("OwnerProjectsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(hooks.useOwnerProjects).mockReturnValue({
      data: { projects, total: projects.length },
      error: null,
      isLoading: false,
    } as unknown as ReturnType<typeof hooks.useOwnerProjects>);
    vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
      data: moneyPath,
      error: null,
      isLoading: false,
    } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  });

  it("renders the tenant issue dashboard with plan, SDK, connector, quota, proof, and actions", () => {
    render(<OwnerProjectsPage />);

    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByText("Need action")).toBeInTheDocument();
    expect(screen.getAllByText("No actions").length).toBeGreaterThan(0);
    expect(screen.getByText("Connector gaps")).toBeInTheDocument();
    expect(screen.getAllByText("Proof quota").length).toBeGreaterThan(0);
    expect(screen.getByText("Actions")).toBeInTheDocument();
    expect(screen.getByText("Demo Tenant")).toBeInTheDocument();
    expect(screen.getByText("Live Tenant")).toBeInTheDocument();
    expect(screen.getAllByText("starter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("configured").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Verified").length).toBeGreaterThan(0);
    expect(screen.queryByText("SDK silent")).toBe(null);
    expect(screen.queryByText("Quota risk")).toBe(null);
    expect(screen.queryByText("No proof")).toBe(null);
    expect(screen.queryByText("CI risk")).toBe(null);
    expect(screen.getAllByText("Change plan").length).toBe(2);
    expect(screen.getAllByRole("link", { name: "Open" })[0].getAttribute("href")).toBe("/owner/projects/proj_demo");
  });
});
