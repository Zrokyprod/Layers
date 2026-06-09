import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InfrastructurePage from "./page";
import * as hooks from "@/lib/hooks";
import type { InfraStats, OwnerHealth, OwnerMoneyPathHealth } from "@/lib/owner-api";

vi.mock("@/lib/hooks", () => ({
  useOwnerHealth: vi.fn(),
  useOwnerInfra: vi.fn(),
  useOwnerMoneyPathHealth: vi.fn(),
  useToggleMaintenance: vi.fn(),
}));

const health: OwnerHealth = {
  overall: "degraded",
  services: [
    { name: "PostgreSQL", status: "ok", detail: null, latency_ms: 4 },
    { name: "Redis", status: "degraded", detail: "slow ping", latency_ms: 80 },
    { name: "Celery", status: "down", detail: "No workers responding", latency_ms: null },
  ],
  exchange_rate: {
    cache_status: "ok",
    cache_rate: 83.2,
    cache_age_seconds: 12,
    cache_is_stale: false,
    cache_is_usable: true,
  },
  maintenance_mode: false,
  checked_at: "2026-06-05T12:00:00Z",
};

const infra: InfraStats = {
  worker_count: 0,
  worker_names: [],
  queues: [
    { queue_name: "diagnosis_fast", pending: 12, failed: 0 },
    { queue_name: "celery", pending: 3, failed: 1 },
  ],
  db_table_sizes: {
    calls: 1200,
    projects: 12,
    audit_logs: -1,
  },
};

const moneyPath: OwnerMoneyPathHealth = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 20,
    issues_open: 1,
    replay_runs_7d: 2,
    verified_replay_runs_7d: 1,
    golden_traces_active: 1,
    ci_runs_7d: 1,
    ci_blocks_7d: 1,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 0,
    tenants_without_recent_capture: 0,
    last_deployed_smoke: {
      status: "failed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_demo",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "ci_smoke",
      detail: "Latest deployed smoke CI gate failed.",
    },
  },
  tenants: [],
};

function setHooks(moneyPathError: Error | null = null) {
  vi.mocked(hooks.useOwnerHealth).mockReturnValue({
    data: health,
    error: null,
    dataUpdatedAt: 1,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerHealth>);
  vi.mocked(hooks.useOwnerInfra).mockReturnValue({
    data: infra,
    error: null,
    dataUpdatedAt: 2,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerInfra>);
  vi.mocked(hooks.useOwnerMoneyPathHealth).mockReturnValue({
    data: moneyPathError ? null : moneyPath,
    error: moneyPathError,
    dataUpdatedAt: 3,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useOwnerMoneyPathHealth>);
  vi.mocked(hooks.useToggleMaintenance).mockReturnValue({
    isPending: false,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useToggleMaintenance>);
}

describe("InfrastructurePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders ops health and deployed smoke proof from backend state", () => {
    setHooks();

    render(<InfrastructurePage />);

    expect(screen.getByText("Ops Health Proof")).toBeInTheDocument();
    expect(screen.getByText("Deployed Smoke Proof")).toBeInTheDocument();
    expect(screen.getByText("Latest deployed smoke CI gate failed.")).toBeInTheDocument();
    expect(screen.getByText("ci_smoke")).toBeInTheDocument();
    expect(screen.getByText("Service failures")).toBeInTheDocument();
    expect(screen.getByText("Queue pending")).toBeInTheDocument();
    expect(screen.getByText("table count probes failed")).toBeInTheDocument();
  });

  it("keeps deployed smoke unavailable when money-path health fails", () => {
    setHooks(new Error("HTTP 500"));

    render(<InfrastructurePage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("Latest deployed smoke CI gate failed.")).toBe(null);
    expect(screen.queryByText("ci_smoke")).toBe(null);
  });
});
