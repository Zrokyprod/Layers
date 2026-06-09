import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerOverviewPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerHealth, OwnerMoneyPathHealth } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerHealth: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
  useToggleMaintenance: vi.fn(),
}));

const health: OwnerHealth = {
  overall: "ok",
  services: [
    { name: "db", status: "ok", detail: null, latency_ms: 5 },
    { name: "redis", status: "degraded", detail: "optional", latency_ms: null },
  ],
  exchange_rate: {},
  maintenance_mode: false,
  checked_at: "2026-06-04T12:00:00Z",
};

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-04T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 42,
    issues_open: 2,
    replay_runs_7d: 5,
    verified_replay_runs_7d: 1,
    golden_traces_active: 3,
    ci_runs_7d: 2,
    ci_blocks_7d: 1,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 1,
    last_deployed_smoke: {
      status: "failed",
      checked_at: "2026-06-04T11:55:00Z",
      project_id: "proj_smoke",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "rr_smoke",
      detail: "Latest deployed smoke CI gate run ended with status=fail.",
    },
  },
  tenants: [
    {
      project_id: "proj_good",
      project_name: "Good Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-04T11:00:00Z",
      captures_24h: 40,
      open_issue_count: 1,
      replay_run_count_7d: 5,
      verified_replay_count_7d: 1,
      golden_trace_count: 3,
      ci_run_count_7d: 2,
      blocking_ci_failures_7d: 1,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "ok", enabled: true, used: 10, limit: 1000, resets_at: "2026-07-01" },
      next_owner_action: "review_blocked_ci",
    },
    {
      project_id: "proj_gap",
      project_name: "Gap Tenant",
      plan_code: "pilot",
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
      next_owner_action: "restore_capture",
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
  vi.mocked(hooks.useOwnerHealth).mockReturnValue({
    data: health,
    error: null,
    dataUpdatedAt: Date.parse(health.checked_at),
    refetch: vi.fn(),
  } as ReturnType<typeof hooks.useOwnerHealth>);
  vi.mocked(hooks.useToggleMaintenance).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useToggleMaintenance>);
}

describe("OwnerOverviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders money-path product health from the owner endpoint", () => {
    setHookData(moneyPath);

    render(<OwnerOverviewPage />);

    expect(screen.getByText("Regression Firewall Health")).toBeInTheDocument();
    expect(screen.getByText("Primary Loop")).toBeInTheDocument();
    expect(screen.getByText("Deployment Smoke")).toBeInTheDocument();
    expect(screen.getByText("Latest deployed smoke CI gate run ended with status=fail.")).toBeInTheDocument();
    expect(screen.getByText("Good Tenant")).toBeInTheDocument();
    expect(screen.getByText("Gap Tenant")).toBeInTheDocument();
    expect(screen.getByText("Review blocked CI")).toBeInTheDocument();
    expect(screen.getByText("Restore capture")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
  });

  it("does not render fake success when money-path health fails", () => {
    setHookData(null, new Error("HTTP 500"));

    render(<OwnerOverviewPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("Primary Loop")).toBe(null);
    expect(screen.queryByText("Tenant Action Queue")).toBe(null);
  });
});
