import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FounderOpsPage from "./page";
import * as hooks from "@/lib/hooks";
import type {
  AuditLogResponse,
  OwnerBillingSummary,
  OwnerHealth,
  OwnerMoneyPathHealth,
  OwnerProjectsResponse,
  OwnerStats,
  OwnerSupportTicketsResponse,
} from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useAuditLog: vi.fn(),
  useOwnerBillingSummary: vi.fn(),
  useOwnerHealth: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
  useOwnerProjects: vi.fn(),
  useOwnerStats: vi.fn(),
  useOwnerSupportTickets: vi.fn(),
  useUpdateOwnerSupportTicket: vi.fn(),
}));

const stats: OwnerStats = {
  total_users: 12,
  total_projects: 4,
  total_calls: 1000,
  calls_last_7d: 200,
  total_cost_usd: 100,
  cost_last_7d_usd: 10,
  new_users_last_7d: 2,
  active_users_last_7d: 6,
};

const health: OwnerHealth = {
  overall: "ok",
  services: [
    { name: "PostgreSQL", status: "ok", detail: null, latency_ms: 4 },
    { name: "Redis", status: "ok", detail: null, latency_ms: 2 },
  ],
  exchange_rate: {},
  maintenance_mode: false,
  checked_at: "2026-06-05T12:00:00Z",
};

const billing: OwnerBillingSummary = {
  total_subscriptions: 2,
  overdue: 0,
  canceled: 0,
  by_plan: [{ plan: "Pro", slug: "pro", tenant_count: 2 }],
  by_status: [{ status: "active", count: 2 }],
};

const support: OwnerSupportTicketsResponse = {
  total: 1,
  items: [
    {
      ticket_id: "ticket_1",
      tenant_id: "proj_demo",
      user_id: "user_1",
      subject: null,
      email: "owner@example.com",
      title: "Replay failed",
      description: null,
      category: "replay",
      priority: "high",
      status: "open",
      assigned_to: null,
      resolved_at: null,
      created_at: "2026-06-05T11:00:00Z",
      updated_at: "2026-06-05T11:00:00Z",
      message_count: 2,
    },
  ],
};

const projects: OwnerProjectsResponse = {
  total: 1,
  projects: [
    {
      id: "proj_demo",
      name: "Demo Tenant",
      owner_ref: "owner_demo",
      is_active: true,
      created_at: "2026-06-05T10:00:00Z",
      call_count: 200,
      total_cost_usd: 42,
      member_count: 3,
    },
  ],
};

const audit: AuditLogResponse = {
  total: 1,
  entries: [
    {
      id: "audit_1",
      tenant_id: "proj_demo",
      diagnosis_id: "owner_action",
      action: "owner.test",
      actor_subject: "owner",
      metadata_json: "{}",
      created_at: "2026-06-05T10:30:00Z",
    },
  ],
};

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 80,
    issues_open: 2,
    replay_runs_7d: 5,
    verified_replay_runs_7d: 1,
    golden_traces_active: 3,
    ci_runs_7d: 4,
    ci_blocks_7d: 0,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 0,
    last_deployed_smoke: {
      status: "passed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_demo",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "ci_smoke",
      detail: "Latest deployed smoke CI gate passed.",
    },
  },
  tenants: [],
};

function setHooks(moneyPathError: Error | null = null) {
  vi.mocked(hooks.useOwnerStats).mockReturnValue({ data: stats, error: null, isLoading: false, dataUpdatedAt: 1, refetch: vi.fn() } as unknown as ReturnType<typeof hooks.useOwnerStats>);
  vi.mocked(hooks.useOwnerHealth).mockReturnValue({ data: health, error: null, dataUpdatedAt: 2, refetch: vi.fn() } as unknown as ReturnType<typeof hooks.useOwnerHealth>);
  vi.mocked(hooks.useOwnerBillingSummary).mockReturnValue({ data: billing, error: null, isLoading: false, dataUpdatedAt: 3, refetch: vi.fn() } as unknown as ReturnType<typeof hooks.useOwnerBillingSummary>);
  vi.mocked(hooks.useOwnerSupportTickets).mockReturnValue({ data: support, error: null, isLoading: false, dataUpdatedAt: 4, refetch: vi.fn() } as unknown as ReturnType<typeof hooks.useOwnerSupportTickets>);
  vi.mocked(hooks.useOwnerProjects).mockReturnValue({ data: projects, error: null, dataUpdatedAt: 5, refetch: vi.fn() } as unknown as ReturnType<typeof hooks.useOwnerProjects>);
  vi.mocked(hooks.useAuditLog).mockReturnValue({ data: audit, error: null, dataUpdatedAt: 6, refetch: vi.fn() } as unknown as ReturnType<typeof hooks.useAuditLog>);
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data: moneyPathError ? null : moneyPath,
    error: moneyPathError,
    dataUpdatedAt: 7,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  vi.mocked(hooks.useUpdateOwnerSupportTicket).mockReturnValue({ isPending: false, mutateAsync: vi.fn() } as unknown as ReturnType<typeof hooks.useUpdateOwnerSupportTicket>);
}

describe("FounderOpsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders deployed smoke proof and product loop metrics", () => {
    setHooks();

    render(<FounderOpsPage />);

    expect(screen.getByText("Deployed Smoke Proof")).toBeInTheDocument();
    expect(screen.getByText("Latest deployed smoke CI gate passed.")).toBeInTheDocument();
    expect(screen.getByText("ci_smoke")).toBeInTheDocument();
    expect(screen.getByText("Capture 24h")).toBeInTheDocument();
    expect(screen.getByText("CI blocks 7d")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Money path" }).getAttribute("href")).toBe("/owner/money-path");
  });

  it("shows money-path backend errors without synthetic smoke success", () => {
    setHooks(new Error("HTTP 500"));

    render(<FounderOpsPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("Latest deployed smoke CI gate passed.")).toBe(null);
    expect(screen.queryByText("ci_smoke")).toBe(null);
  });
});
