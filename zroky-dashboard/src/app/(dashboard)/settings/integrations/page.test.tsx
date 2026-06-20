import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IntegrationsSettingsPage from "./page";

const api = vi.hoisted(() => ({
  disconnectGithubRepoConnection: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getSlackInstallStatus: vi.fn(),
  listOutcomeReconciliations: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

describe("IntegrationsSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    api.getGithubConnectionStatus.mockResolvedValue({
      connected: true,
      github_id: "123",
      github_login: "zroky",
      scopes: ["repo"],
      connected_at: "2026-06-17T10:00:00.000Z",
      updated_at: "2026-06-17T10:30:00.000Z",
    });
    api.getSlackInstallStatus.mockResolvedValue({
      connected: false,
      team_id: null,
      team_name: null,
      channel_id: null,
      channel_name: null,
      bot_user_id: null,
      scopes: [],
      installed_by_user: null,
      installed_at: null,
      updated_at: null,
    });
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_ledger_refund",
          project_id: "proj_1",
          call_id: "call_refund_api",
          trace_id: "trace_refund_api",
          runtime_policy_decision_id: "decision_1",
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:rf_999",
          verdict: "matched",
          reason: "all_compared_fields_matched",
          amount_usd: 42.5,
          currency: "USD",
          claimed: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
          actual: { refund_id: "rf_999", amount_usd: 42.5, currency: "USD" },
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: "call_refund_api:rf_999",
          metadata: {
            connector_kind: "ledger_refund_api",
            connector: {
              request_url: "https://ledger.example.com/api/refunds/rf_999",
              http_status: 200,
              record_path: "data.0",
              bearer_token: "ledger-secret-token",
            },
          },
          checked_at: "2026-06-20T09:00:00Z",
          created_at: "2026-06-20T09:00:00Z",
        },
      ],
    });
  });

  it("shows GitHub beside alert delivery integrations", async () => {
    render(<IntegrationsSettingsPage />);

    expect(await screen.findByRole("heading", { name: "GitHub" })).toBeInTheDocument();
    expect(screen.getAllByText("@zroky").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Reconnect GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Slack" })).toBeInTheDocument();
    expect(screen.getByText((_content, element) => element?.textContent === "2/3")).toBeInTheDocument();
    expect(api.getSlackInstallStatus).toHaveBeenCalledTimes(1);
    expect(api.listOutcomeReconciliations).toHaveBeenCalledWith({ limit: 25 });
  });

  it("surfaces ledger refund connector proof without leaking secrets", async () => {
    render(<IntegrationsSettingsPage />);

    expect(await screen.findByRole("heading", { name: "Ledger refund connector" })).toBeInTheDocument();
    expect(screen.getAllByText("Verified").length).toBeGreaterThan(0);
    expect(screen.getByText("https://ledger.***/...")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("data.0")).toBeInTheDocument();
    expect(screen.getByText("ledger:rf_999")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("ledger-secret-token");
  });

  it("shows not_verified when no trusted connector proof is available", async () => {
    api.listOutcomeReconciliations.mockResolvedValue({
      total_in_page: 1,
      items: [
        {
          id: "check_ledger_unverified",
          project_id: "proj_1",
          call_id: "call_refund_api",
          trace_id: null,
          runtime_policy_decision_id: null,
          action_type: "refund",
          connector_type: "ledger_refund_api",
          system_ref: "ledger:rf_missing",
          verdict: "not_verified",
          reason: "system_of_record_missing",
          amount_usd: null,
          currency: null,
          claimed: { refund_id: "rf_missing" },
          actual: null,
          comparison: { compared_fields: [], mismatches: [] },
          idempotency_key: null,
          metadata: { connector: { request_url: "https://ledger.example.com/api/refunds/rf_missing" } },
          checked_at: "2026-06-20T09:00:00Z",
          created_at: "2026-06-20T09:00:00Z",
        },
      ],
    });

    render(<IntegrationsSettingsPage />);

    expect(await screen.findByRole("heading", { name: "Ledger refund connector" })).toBeInTheDocument();
    expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
    expect(screen.getByText("No response yet")).toBeInTheDocument();
    expect(screen.getByText("data or data.0")).toBeInTheDocument();
  });

  it("copies the ledger refund reconciliation payload", async () => {
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    render(<IntegrationsSettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Copy API payload" }));

    await waitFor(() =>
      expect(clipboardWrite).toHaveBeenCalledWith(
        expect.stringContaining("/v1/outcomes/reconciliation/ledger-refund"),
      ),
    );
    expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining("$LEDGER_TOKEN"));
    expect(await screen.findByText("Ledger refund reconciliation payload copied.")).toBeInTheDocument();
  });
});
