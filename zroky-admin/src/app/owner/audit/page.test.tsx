import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuditLogPage from "./page";
import * as hooks from "@/lib/hooks";
import type { AuditLogResponse, OwnerMoneyPathHealth } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useAuditLog: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
}));

const audit: AuditLogResponse = {
  total: 2,
  entries: [
    {
      id: "audit_1",
      tenant_id: "proj_audit",
      diagnosis_id: "diag_1",
      action: "owner.tenant.rate_limit.set",
      actor_subject: "owner@example.com",
      metadata_json: "{\"target_id\":\"proj_audit\"}",
      created_at: "2026-06-05T10:00:00Z",
    },
    {
      id: "audit_2",
      tenant_id: "PLATFORM",
      diagnosis_id: "owner_action",
      action: "owner.broadcast",
      actor_subject: "owner@example.com",
      metadata_json: "{}",
      created_at: "2026-06-05T11:00:00Z",
    },
  ],
};

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 40,
    issues_open: 2,
    replay_runs_7d: 4,
    verified_replay_runs_7d: 1,
    golden_traces_active: 1,
    ci_runs_7d: 2,
    ci_blocks_7d: 1,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 0,
    tenants_without_recent_capture: 0,
    last_deployed_smoke: {
      status: "passed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_audit",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "ci_smoke",
      detail: "passed",
    },
  },
  tenants: [
    {
      project_id: "proj_audit",
      project_name: "Audit Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:30:00Z",
      captures_24h: 40,
      open_issue_count: 2,
      replay_run_count_7d: 4,
      verified_replay_count_7d: 1,
      golden_trace_count: 1,
      ci_run_count_7d: 2,
      blocking_ci_failures_7d: 1,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "ok", enabled: true, used: 20, limit: 1000, resets_at: "2026-07-01" },
      next_owner_action: "review_blocked_ci",
    },
  ],
};

function mockHooks(moneyPathError: Error | null = null) {
  vi.mocked(hooks.useAuditLog).mockReturnValue({
    data: audit,
    error: null,
    isLoading: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useAuditLog>);
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data: moneyPathError ? null : moneyPath,
    error: moneyPathError,
    isFetching: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
}

describe("AuditLogPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders audit rows with tenant control evidence", () => {
    mockHooks();

    render(<AuditLogPage />);

    expect(screen.getByText("Control Evidence")).toBeInTheDocument();
    expect(screen.getByText("Review release block")).toBeInTheDocument();
    expect(screen.getByText("2 issue(s), 1 release block(s)")).toBeInTheDocument();
    expect(screen.getByText("Platform event")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Project" }).getAttribute("href")).toBe("/owner/projects/proj_audit");
  });

  it("shows evidence unavailable when money-path health fails", () => {
    mockHooks(new Error("HTTP 500"));

    render(<AuditLogPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.getAllByText("Evidence unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("Review release block")).toBe(null);
    expect(screen.queryByText("2 issue(s), 1 release block(s)")).toBe(null);
  });
});
