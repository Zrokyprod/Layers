import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectDetailPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerMoneyPathHealth, OwnerProjectItem, ProjectMemberItem } from "@/lib/owner-api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "proj_demo" }),
}));

vi.mock("@/lib/hooks", () => ({
  useOwnerProject: vi.fn(),
  useProjectMembers: vi.fn(),
  useProjectRateLimit: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
  useSetProjectStatus: vi.fn(),
  useSetProjectRateLimit: vi.fn(),
  useClearProjectRateLimit: vi.fn(),
}));

const project: OwnerProjectItem = {
  id: "proj_demo",
  name: "Demo Tenant",
  owner_ref: "owner_demo",
  is_active: true,
  created_at: "2026-06-05T10:00:00Z",
  call_count: 2480,
  total_cost_usd: 32.4,
  member_count: 1,
};

const member: ProjectMemberItem = {
  membership_id: "mem_1",
  user_id: "user_1",
  email: "owner@example.com",
  github_login: null,
  display_name: null,
  role: "owner",
  is_active: true,
  joined_at: "2026-06-05T10:00:00Z",
};

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
    tenants_without_recent_capture: 0,
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
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:30:00Z",
      captures_24h: 42,
      open_issue_count: 1,
      replay_run_count_7d: 3,
      verified_replay_count_7d: 2,
      golden_trace_count: 1,
      ci_run_count_7d: 0,
      blocking_ci_failures_7d: 0,
      provider_key_status: { state: "missing", active_provider_count: 0 },
      replay_quota_status: { state: "near_limit", enabled: true, used: 18, limit: 100, resets_at: "2026-07-01" },
      event_metering_status: { state: "ok", used: 2400, limit: 5000, failure_count: 0, last_failure_at: null },
      pricing_cost_status: {
        state: "stale",
        pricing_version: "2026-05",
        pricing_source: "fallback",
        pricing_age_days: 18,
        cost_confidence: "estimated",
        detail: "Pricing metadata is older than allowed.",
      },
      billing_status: {
        state: "missing_paid",
        plan_code: "pro",
        subscription_status: "past_due",
        current_period_end: "2026-07-01T00:00:00Z",
      },
      support_status: { state: "urgent", open_count: 2, urgent_count: 1 },
      money_path_breaks: ["provider_key_missing", "billing_past_due"],
      value_status: "risk",
      tenant_priority_score: 87,
      next_owner_action: "connect_provider_key",
    },
  ],
};

function mockBaseQueries(data: OwnerMoneyPathHealth | null, moneyPathError: Error | null = null) {
  vi.mocked(hooks.useOwnerProject).mockReturnValue({
    data: project,
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useOwnerProject>);
  vi.mocked(hooks.useProjectMembers).mockReturnValue({
    data: { members: [member] },
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useProjectMembers>);
  vi.mocked(hooks.useProjectRateLimit).mockReturnValue({
    data: {
      project_id: "proj_demo",
      has_override: true,
      overrides: {
        ingest_soft_limit_rpm: 300,
        ingest_burst_limit_rpm: 600,
        ingest_enforce_rate_limit: true,
      },
    },
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useProjectRateLimit>);
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data,
    error: moneyPathError,
    isLoading: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  vi.mocked(hooks.useSetProjectStatus).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useSetProjectStatus>);
  vi.mocked(hooks.useSetProjectRateLimit).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useSetProjectRateLimit>);
  vi.mocked(hooks.useClearProjectRateLimit).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useClearProjectRateLimit>);
}

describe("ProjectDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders tenant-specific proof ledger evidence from money-path health", () => {
    mockBaseQueries(moneyPath);

    render(<ProjectDetailPage />);

    expect(screen.getAllByText("Demo Tenant").length).toBeGreaterThan(0);
    expect(screen.getByText("Tenant proof ledger")).toBeInTheDocument();
    expect(screen.getByText("Next owner action")).toBeInTheDocument();
    expect(screen.getAllByText("Connect provider key").length).toBeGreaterThan(0);
    expect(screen.getByText("provider key missing")).toBeInTheDocument();
    expect(screen.getByText("billing past due")).toBeInTheDocument();
    expect(screen.getByText("Commercial readiness")).toBeInTheDocument();
    expect(screen.getByText("Paid-path signals")).toBeInTheDocument();
    expect(screen.getAllByText("2,400 / 5,000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("missing paid").length).toBeGreaterThan(0);
    expect(screen.getAllByText("18d age - estimated").length).toBeGreaterThan(0);
    expect(screen.getByText("missing (0)")).toBeInTheDocument();
    expect(screen.getByText("18 / 100")).toBeInTheDocument();
    expect(screen.getByText("2 verified")).toBeInTheDocument();
    expect(screen.getAllByText("near limit").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("300")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Money path/i }).getAttribute("href")).toBe("/owner/money-path");
  }, 10_000);

  it("is honest when the money-path endpoint has no row for this tenant", () => {
    mockBaseQueries({ ...moneyPath, tenants: [] });

    render(<ProjectDetailPage />);

    expect(screen.getByText("No regression-firewall health row exists for this tenant.")).toBeInTheDocument();
    expect(screen.queryByText("Connect provider key")).toBe(null);
    expect(screen.queryByText("No open issue reported by backend.")).toBe(null);
    expect(screen.queryByText("Commercial readiness")).toBe(null);
  });

  it("shows money-path backend errors without rendering synthetic product health", () => {
    mockBaseQueries(null, new Error("HTTP 500"));

    render(<ProjectDetailPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("No regression-firewall health row exists for this tenant.")).toBe(null);
    expect(screen.queryByText("Connect provider key")).toBe(null);
  });
});
