import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerOverviewPage from "./page";
import * as hooks from "@/lib/hooks";
import type {
  OwnerBillingSummary,
  OwnerHealth,
  OwnerLaunchReadiness,
  OwnerMoneyPathHealth,
} from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerBillingSummary: vi.fn(),
  useOwnerHealth: vi.fn(),
  useOwnerLaunchReadiness: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
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
      next_owner_action: "restore_capture",
    },
  ],
};

const readiness: OwnerLaunchReadiness = {
  generated_at: "2026-06-04T12:00:00Z",
  product_standard: "Paid launch requires runtime stops, outcome proof, tenant isolation, billing readiness, and no fake verified state.",
  overall_status: "blocked",
  paid_launch_allowed: false,
  hard_blockers: ["runtime_risk_stop:runtime_risk_stop_evidence_missing"],
  verification_commands: ["powershell -ExecutionPolicy Bypass -File scripts/verify_paid_launch_readiness.ps1"],
  gates: [
    {
      code: "runtime_risk_stop",
      title: "Runtime Risk Stop",
      status: "not_verified",
      summary: "Risky actions must pause before damage.",
      blockers: ["runtime_risk_stop_evidence_missing"],
      evidence: [{ label: "risk_stopped_7d", value: 0, status: null, detail: null }],
      verification_commands: ["python -m pytest tests/test_runtime_policy_gate.py"],
    },
  ],
};

const billing: OwnerBillingSummary = {
  total_subscriptions: 3,
  overdue: 1,
  canceled: 0,
  by_plan: [{ plan: "pro", slug: "pro", tenant_count: 2 }],
  by_status: [{ status: "active", count: 2 }],
};

function setHookData(
  data: OwnerMoneyPathHealth | null,
  error: Error | null = null,
  launchData: OwnerLaunchReadiness | null = readiness,
  launchError: Error | null = null,
) {
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data,
    error,
    dataUpdatedAt: data ? Date.parse(data.generated_at) : 0,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  vi.mocked(hooks.useOwnerHealth).mockReturnValue({
    data: health,
    error: null,
    dataUpdatedAt: Date.parse(health.checked_at),
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerHealth>);
  vi.mocked(hooks.useOwnerLaunchReadiness).mockReturnValue({
    data: launchData,
    error: launchError,
    dataUpdatedAt: launchData ? Date.parse(launchData.generated_at) : 0,
    isLoading: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerLaunchReadiness>);
  vi.mocked(hooks.useOwnerBillingSummary).mockReturnValue({
    data: billing,
    error: null,
    dataUpdatedAt: Date.parse("2026-06-04T12:00:00Z"),
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerBillingSummary>);
}

describe("OwnerOverviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders money-path product health from the owner endpoint", () => {
    setHookData(moneyPath);

    render(<OwnerOverviewPage />);

    expect(screen.getByText("Owner 360 Home")).toBeInTheDocument();
    expect(screen.getByText("Paid Traffic")).toBeInTheDocument();
    expect(screen.getByText("Customers Needing Action")).toBeInTheDocument();
    expect(screen.getByText("Money")).toBeInTheDocument();
    expect(screen.getByText("Infrastructure")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Control Plane Health chart" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Customer Risk chart" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Money & Infra chart" })).toBeInTheDocument();
    expect(screen.getByText("Customer Action Queue")).toBeInTheDocument();
    expect(screen.getAllByText("No recent protected actions").length).toBeGreaterThan(0);
    expect(screen.getByText("Release check blocked")).toBeInTheDocument();
    expect(screen.getByText("Protected actions")).toBeInTheDocument();
    expect(screen.getByText("Proof checks")).toBeInTheDocument();
    expect(screen.getByText("Verified outcomes")).toBeInTheDocument();
    expect(screen.getByText("Receipt baselines")).toBeInTheDocument();
    expect(screen.queryByText("Replays")).toBe(null);
    expect(screen.queryByText("Goldens")).toBe(null);
    expect(screen.queryByText("Review blocked CI")).toBe(null);
    expect(screen.queryByText("Revenue")).toBe(null);
    expect(screen.getByRole("link", { name: /Customers Needing Action/i }).getAttribute("href")).toBe("/owner/projects");
    expect(screen.getByText("Good Tenant: Review release block")).toBeInTheDocument();
  }, 10_000);

  it("does not render fake success when money-path health fails", () => {
    setHookData(null, new Error("HTTP 500"));

    render(<OwnerOverviewPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.getByText("Owner 360 Home")).toBeInTheDocument();
    expect(screen.queryByText("Loading owner command center...")).toBe(null);
  });

  it("keeps owner launch approval blocked when launch readiness is unavailable", () => {
    setHookData(moneyPath, null, null, new Error("HTTP 503"));

    render(<OwnerOverviewPage />);

    expect(screen.getByText("HTTP 503")).toBeInTheDocument();
    expect(screen.getByText("Paid Traffic")).toBeInTheDocument();
    expect(screen.getByText("Checking")).toBeInTheDocument();
    expect(screen.queryByText("Allowed")).toBe(null);
    expect(screen.getByText("Money")).toBeInTheDocument();
  });
});
