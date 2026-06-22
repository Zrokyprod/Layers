import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OwnerSettingsPage from "./page";
import * as hooks from "@/lib/hooks";
import type { OwnerProductionReadiness } from "@/lib/owner-api";

vi.mock("@/lib/owner-api", () => ({
  clearOwnerToken: vi.fn(),
  getOwnerToken: vi.fn(() => "active"),
}));

vi.mock("@/lib/hooks", () => ({
  useOwnerProductionReadiness: vi.fn(),
  useOwnerRetention: vi.fn(),
}));

const readiness: OwnerProductionReadiness = {
  overall_status: "blocked",
  app_env: "production",
  production_profile: true,
  checked_at: "2026-06-23T10:00:00Z",
  hard_blockers: [
    "provider_key_vault_kek:PROVIDER_KEY_VAULT_KEK is missing, placeholder, or too short.",
    "replay_real_llm:REPLAY_REAL_LLM_ENABLED or REPLAY_WORKER_TOKEN is not production-ready.",
  ],
  checks: [
    {
      code: "owner_routes",
      label: "Owner routes enabled",
      status: "pass",
      required_for_launch: true,
      detail: "FEATURE_LEGACY_OWNER is enabled for zroky-admin.",
    },
    {
      code: "provider_key_vault_kek",
      label: "Provider key vault KEK",
      status: "fail",
      required_for_launch: true,
      detail: "PROVIDER_KEY_VAULT_KEK is missing, placeholder, or too short.",
    },
    {
      code: "replay_real_llm",
      label: "Real replay enabled",
      status: "fail",
      required_for_launch: true,
      detail: "REPLAY_REAL_LLM_ENABLED or REPLAY_WORKER_TOKEN is not production-ready.",
    },
  ],
};

function setHooks(data: OwnerProductionReadiness | null, error: Error | null = null) {
  vi.mocked(hooks.useOwnerProductionReadiness).mockReturnValue({
    data,
    error,
    isLoading: false,
  } as ReturnType<typeof hooks.useOwnerProductionReadiness>);
  vi.mocked(hooks.useOwnerRetention).mockReturnValue({
    data: {
      call_retention_days: 30,
      diagnosis_retention_days: 30,
      audit_log_retention_days: 365,
      notification_retention_days: 90,
      note: "Retention is enforced by scheduled purge tasks.",
    },
    error: null,
    isLoading: false,
  } as ReturnType<typeof hooks.useOwnerRetention>);
}

describe("OwnerSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders backend production readiness blockers without exposing secrets", () => {
    setHooks(readiness);

    render(<OwnerSettingsPage />);

    const section = screen.getByLabelText("Production readiness");
    expect(within(section).getByText("blocked")).toBeInTheDocument();
    expect(within(section).getByText("production")).toBeInTheDocument();
    expect(within(section).getByText("2")).toBeInTheDocument();
    expect(within(section).getByText("Provider key vault KEK")).toBeInTheDocument();
    expect(within(section).getByText("Real replay enabled")).toBeInTheDocument();
    expect(within(section).getByText("Owner routes enabled")).toBeInTheDocument();
    expect(section.textContent).not.toContain("owner-secret-production");
  });

  it("does not render a fake pass state when readiness fails to load", () => {
    setHooks(null, new Error("HTTP 500"));

    render(<OwnerSettingsPage />);

    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
    expect(screen.queryByText("pass")).toBe(null);
  });
});
