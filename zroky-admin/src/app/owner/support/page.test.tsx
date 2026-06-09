import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerSupportPage from "./page";
import * as hooks from "@/lib/hooks";
import type {
  OwnerMoneyPathHealth,
  OwnerSupportTicketDetailResponse,
  OwnerSupportTicketsResponse,
} from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerMoneyPathHealth: vi.fn(),
  useOwnerSupportTickets: vi.fn(),
  useOwnerSupportTicket: vi.fn(),
  useReplyOwnerSupportTicket: vi.fn(),
  useUpdateOwnerSupportTicket: vi.fn(),
}));

const tickets: OwnerSupportTicketsResponse = {
  total: 1,
  items: [
    {
      ticket_id: "ticket_1",
      tenant_id: "proj_ticket",
      user_id: "user_1",
      subject: "email:user@example.com",
      email: "user@example.com",
      title: "Replay gate failed",
      description: "CI gate failed after the prompt change.",
      category: "ci",
      priority: "high",
      status: "open",
      assigned_to: null,
      resolved_at: null,
      created_at: "2026-06-05T10:00:00Z",
      updated_at: "2026-06-05T11:00:00Z",
      message_count: 2,
    },
  ],
};

const detail: OwnerSupportTicketDetailResponse = {
  ticket: tickets.items[0],
  messages: [
    {
      message_id: "msg_1",
      sender_type: "user",
      sender_subject: "email:user@example.com",
      body: "The CI gate is blocking my PR.",
      is_internal: false,
      created_at: "2026-06-05T10:00:00Z",
    },
  ],
};

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 50,
    issues_open: 2,
    replay_runs_7d: 4,
    verified_replay_runs_7d: 1,
    golden_traces_active: 2,
    ci_runs_7d: 3,
    ci_blocks_7d: 1,
    tenants_missing_provider_key: 0,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 0,
    last_deployed_smoke: {
      status: "passed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_ticket",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "ci_smoke",
      detail: "passed",
    },
  },
  tenants: [
    {
      project_id: "proj_ticket",
      project_name: "Ticket Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:30:00Z",
      captures_24h: 50,
      open_issue_count: 2,
      replay_run_count_7d: 4,
      verified_replay_count_7d: 1,
      golden_trace_count: 2,
      ci_run_count_7d: 3,
      blocking_ci_failures_7d: 1,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "near_limit", enabled: true, used: 90, limit: 100, resets_at: "2026-07-01" },
      next_owner_action: "review_blocked_ci",
    },
  ],
};

function mockHooks(moneyPathError: Error | null = null) {
  vi.mocked(hooks.useOwnerSupportTickets).mockReturnValue({
    data: tickets,
    error: null,
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerSupportTickets>);
  vi.mocked(hooks.useOwnerSupportTicket).mockReturnValue({
    data: detail,
    error: null,
    isLoading: false,
    isFetching: false,
  } as unknown as ReturnType<typeof hooks.useOwnerSupportTicket>);
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data: moneyPathError ? null : moneyPath,
    error: moneyPathError,
    isFetching: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  vi.mocked(hooks.useUpdateOwnerSupportTicket).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useUpdateOwnerSupportTicket>);
  vi.mocked(hooks.useReplyOwnerSupportTicket).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useReplyOwnerSupportTicket>);
}

describe("OwnerSupportPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders ticket money-path evidence in list and detail", () => {
    mockHooks();

    render(<OwnerSupportPage />);

    expect(screen.getByText("Product Evidence")).toBeInTheDocument();
    expect(screen.getAllByText("Review blocked CI").length).toBeGreaterThan(0);
    expect(screen.getByText("Ticket Tenant")).toBeInTheDocument();
    expect(screen.getByText("Provider: configured (1)")).toBeInTheDocument();
    expect(screen.getByText("Replay quota: 90 / 100")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Project detail" }).getAttribute("href")).toBe("/owner/projects/proj_ticket");
  });

  it("does not synthesize product evidence when money-path health fails", () => {
    mockHooks(new Error("HTTP 500"));

    render(<OwnerSupportPage />);

    expect(screen.getAllByText("HTTP 500").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("Ticket Tenant")).toBe(null);
    expect(screen.queryByText("Provider: configured (1)")).toBe(null);
  });
});
